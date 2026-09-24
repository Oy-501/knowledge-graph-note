/* ============================================================
 * 知识图谱 · 两级边模型架构
 *
 * 三层实体模型:
 *   Document     (文档): 知识点来源归属，图谱主节点
 *     { docId, filename, title, summary, createdAt }
 *   KnowledgePoint(知识点): 最小单元，内部存储，不直接图谱展示
 *     { pointId, docId, description, keywords[], entities[], type, vector[], createdAt }
 *
 * 两级边模型:
 *   Kp_Edge  (知识点边，内部存储): 知识点之间的关联
 *     { edgeId(auto), from(pointId), to(pointId), strength(weight), isRender(is_valid),
 *       relationType, validationStatus, source, vectorScore, entityScore,
 *       keywordScore, llmScore, createdAt }
 *   Doc_Edge (文件-文件关联，图谱渲染使用):
 *     { id(auto), doc_a_id, doc_b_id, doc_relation_weight, valid_kp_pair_count }
 *
 * 双存储:
 *   普通DB (IndexedDB): 结构化业务数据 (docs, points, edges, doc_edges)
 *   向量索引 (内存): state.vectorIndex = [{pointId, vector, docId}]，启动时从 STORE_POINTS 加载
 *
 * 关联流程:
 *   分片抽取知识点 → 入库 + 写向量 → 多路召回(向量KNN + 实体共现 + 关键词重叠)
 *   → 过滤(同文件配对 + 去重 + 每知识点限流) → 校验(高分放行/低分拒绝/中段LLM)
 *   → 写 Kp_Edge → 异步聚合 recompute Doc_Edge
 *
 * 可视化: D3.js force simulation，文档为图谱主节点，Doc_Edge 为连线
 * ============================================================ */

// ============ 常量 ============
const DB_NAME = 'knowledge_map_db';
const DB_VERSION = 3;
const STORE_MAPS = 'maps';        // 旧 store，保留以兼容历史数据
const STORE_LINKS = 'links';      // 旧 store，保留以兼容历史数据
const STORE_DOCS = 'docs';        // 文档
const STORE_POINTS = 'points';    // 知识点
const STORE_EDGES = 'edges';      // Kp_Edge 知识点边（内部存储）
const STORE_DOC_EDGES = 'doc_edges'; // Doc_Edge 文件-文件关联边（图谱渲染使用）
const SETTINGS_KEY = 'knowledge_map_settings';

// 节点颜色（按来源文档着色）
const DOC_COLORS = [
  '#7aa2f7', '#bb9af7', '#9ece6a', '#e0af68',
  '#f7768e', '#73daca', '#ff9e64', '#c0caf5',
  '#94e2d5', '#cba6f7', '#fab387', '#a6e3a1',
];

const DEFAULT_SETTINGS = {
  llmApiUrl: 'https://api.openai.com/v1/chat/completions',
  llmApiKey: '',
  llmModel: 'gpt-4o-mini',
  embeddingApiUrl: 'https://api.openai.com/v1/embeddings',
  embeddingApiKey: '',
  embeddingModel: 'text-embedding-3-small',
  threshold: 0.65,
  ontologyWeight: 0.2,   // 领域本体推理权重，0=完全关闭知识库推理
};

// 关系类型
const RELATION_TYPES = ['related', 'similar', 'prerequisite', 'derivative'];
const RELATION_LABELS = {
  related: '相关',
  similar: '相似',
  prerequisite: '前置',
  derivative: '衍生',
};

// 召回 KNN Top N
const KNN_TOP_N = 15;
// 等价于 KNN_TOP_N，统一命名
const TOP_K = 15;
// 校验阈值：高分直接放行，低分直接拒绝，中段送 LLM
const HIGH_SCORE_THRESHOLD = 0.75;
const LOW_SCORE_THRESHOLD = 0.4;
// 每个知识点最大候选数（防爆炸）
const MAX_CANDIDATE_PER_KP = 20;
// 文件边最少有效知识点对数
const MIN_VALID_KP_PAIR = 2;
// 全局重建分片大小
const BATCH_SIZE = 50;
// 知识点去重相似度阈值
const DEDUP_SIMILARITY = 0.9;
// 分片目标长度
const CHUNK_TARGET_SIZE = 1000;

// ============ 状态 ============
const state = {
  settings: { ...DEFAULT_SETTINGS },
  docs: [],                 // 文档列表
  points: [],               // 知识点列表（含 vector）
  edges: [],                // Kp_Edge 知识点边列表（内部存储）
  docEdges: [],             // Doc_Edge 文件-文件关联边列表（图谱渲染使用）
  vectorIndex: [],          // 内存向量索引 [{pointId, vector, docId}]
  pointMap: new Map(),      // pointId -> point 快速查找
  docFilter: new Set(),     // 文档筛选：空集合=显示全部；非空=仅显示这些 docId
  selectedPointId: null,    // 选中的知识点（查看跨文件关联时）
  selectedDocId: null,      // 点击查看详情的文档
  contextMenuPointId: null,
  contextMenuDocId: null,   // 右键菜单所在文档 id
  watchDir: null,           // 监控的文件夹路径
  isWatching: false,        // 是否正在监控
  isRebuilding: false,      // 全局重建进行中
  ontology: { domains: {} },     // 领域本体（从 ontology.json + localStorage 加载）
  ontologyLoaded: false,         // 本体是否已加载
  hideOntologyEdges: false,       // 图谱中隐藏纯知识库推导的连线
  ontologyEditDomain: 'software', // 本体管理弹窗当前编辑的领域
};

let dbInstance = null;
let simulation = null;
let svgZoom = null;

// 检测是否运行在 Electron 环境
const isElectron = typeof window !== 'undefined' && window.electron && window.electron.isElectron === true;

// ============ 工具函数 ============
const $ = sel => document.querySelector(sel);
const $$ = sel => Array.from(document.querySelectorAll(sel));
// 知识点 id
const uid = () => 'p_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
// 文档 id
const docUid = () => 'd_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
const now = () => new Date().toISOString();

function toast(msg, type = 'info', duration = 2500) {
  const el = $('#toast');
  el.textContent = msg;
  el.className = 'toast ' + type;
  clearTimeout(toast._t);
  requestAnimationFrame(() => el.classList.remove('hidden'));
  toast._t = setTimeout(() => el.classList.add('hidden'), duration);
}

function showProgress(text, detail = '') {
  $('#processing-text').textContent = text;
  $('#processing-detail').textContent = detail;
  $('#processing-overlay').classList.remove('hidden');
}
function hideProgress() {
  $('#processing-overlay').classList.add('hidden');
}

// 按文档着色
function getDocColor(docId) {
  const idx = state.docs.findIndex(d => d.docId === docId);
  return DOC_COLORS[idx % DOC_COLORS.length] || '#7aa2f7';
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

function truncate(str, max = 30) {
  const s = str == null ? '' : String(str);
  return s.length > max ? s.slice(0, max) + '…' : s;
}

// 无序边对 key，用于去重
function edgePairKey(a, b) {
  return a < b ? a + '||' + b : b + '||' + a;
}

// 由 pointId 查所属 docId
function getPointDocId(pointId) {
  const p = state.pointMap.get(pointId);
  return p ? p.docId : null;
}

// 获取知识点完整元数据
function getPointMeta(pointId) {
  return state.pointMap.get(pointId);
}

// ============ IndexedDB 存储层 ============
function initDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onerror = () => reject(req.error);
    req.onsuccess = () => { dbInstance = req.result; resolve(dbInstance); };
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      // 旧 store 保留（不删除，兼容历史数据）
      if (!db.objectStoreNames.contains(STORE_MAPS)) {
        db.createObjectStore(STORE_MAPS, { keyPath: 'mapId' });
      }
      if (!db.objectStoreNames.contains(STORE_LINKS)) {
        const oldLinkStore = db.createObjectStore(STORE_LINKS, { keyPath: 'id', autoIncrement: true });
        oldLinkStore.createIndex('from', 'from', { unique: false });
        oldLinkStore.createIndex('to', 'to', { unique: false });
        oldLinkStore.createIndex('type', 'type', { unique: false });
      }
      // 新 store：文档
      if (!db.objectStoreNames.contains(STORE_DOCS)) {
        db.createObjectStore(STORE_DOCS, { keyPath: 'docId' });
      }
      // 新 store：知识点
      if (!db.objectStoreNames.contains(STORE_POINTS)) {
        const pointStore = db.createObjectStore(STORE_POINTS, { keyPath: 'pointId' });
        pointStore.createIndex('docId', 'docId', { unique: false });
      }
      // 新 store：关联边（Kp_Edge 知识点边）
      if (!db.objectStoreNames.contains(STORE_EDGES)) {
        const edgeStore = db.createObjectStore(STORE_EDGES, { keyPath: 'edgeId', autoIncrement: true });
        edgeStore.createIndex('from', 'from', { unique: false });
        edgeStore.createIndex('to', 'to', { unique: false });
      }
      // 新 store：Doc_Edge 文件-文件关联边（图谱渲染使用）
      if (!db.objectStoreNames.contains(STORE_DOC_EDGES)) {
        const docEdgeStore = db.createObjectStore(STORE_DOC_EDGES, { keyPath: 'id', autoIncrement: true });
        docEdgeStore.createIndex('doc_a', 'doc_a_id', { unique: false });
        docEdgeStore.createIndex('doc_b', 'doc_b_id', { unique: false });
      }
    };
  });
}

// 通用查询
function dbGetAll(storeName) {
  return new Promise((resolve, reject) => {
    const tx = dbInstance.transaction(storeName, 'readonly');
    const req = tx.objectStore(storeName).getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}

function dbGetAllDocs() { return dbGetAll(STORE_DOCS); }
function dbGetAllPoints() { return dbGetAll(STORE_POINTS); }
function dbGetAllEdges() { return dbGetAll(STORE_EDGES); }
function dbGetAllDocEdges() { return dbGetAll(STORE_DOC_EDGES); }

function dbPutDoc(doc) {
  return new Promise((resolve, reject) => {
    const tx = dbInstance.transaction(STORE_DOCS, 'readwrite');
    const req = tx.objectStore(STORE_DOCS).put(doc);
    req.onsuccess = () => resolve(doc);
    req.onerror = () => reject(req.error);
  });
}

function dbPutPoint(point) {
  return new Promise((resolve, reject) => {
    const tx = dbInstance.transaction(STORE_POINTS, 'readwrite');
    const req = tx.objectStore(STORE_POINTS).put(point);
    req.onsuccess = () => resolve(point);
    req.onerror = () => reject(req.error);
  });
}

// 写边（autoIncrement edgeId）
function dbPutEdge(edge) {
  return new Promise((resolve, reject) => {
    const tx = dbInstance.transaction(STORE_EDGES, 'readwrite');
    const store = tx.objectStore(STORE_EDGES);
    const req = store.add(edge);
    req.onsuccess = () => { edge.edgeId = req.result; resolve(edge); };
    req.onerror = () => reject(req.error);
  });
}

function dbDeleteDoc(docId) {
  return new Promise((resolve, reject) => {
    const tx = dbInstance.transaction(STORE_DOCS, 'readwrite');
    const req = tx.objectStore(STORE_DOCS).delete(docId);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

function dbDeletePoint(pointId) {
  return new Promise((resolve, reject) => {
    const tx = dbInstance.transaction(STORE_POINTS, 'readwrite');
    const req = tx.objectStore(STORE_POINTS).delete(pointId);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

function dbDeleteEdge(edgeId) {
  return new Promise((resolve, reject) => {
    const tx = dbInstance.transaction(STORE_EDGES, 'readwrite');
    const req = tx.objectStore(STORE_EDGES).delete(edgeId);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

// 删除某文档相关的全部边（from 或 to 任一端属于该文档）
function dbDeleteEdgesByDoc(docId) {
  return new Promise((resolve, reject) => {
    const tx = dbInstance.transaction(STORE_EDGES, 'readwrite');
    const store = tx.objectStore(STORE_EDGES);
    const cursorReq = store.openCursor();
    cursorReq.onsuccess = (e) => {
      const cursor = e.target.result;
      if (cursor) {
        const edge = cursor.value;
        const fromDoc = getPointDocId(edge.from);
        const toDoc = getPointDocId(edge.to);
        if (fromDoc === docId || toDoc === docId) {
          store.delete(cursor.key);
        }
        cursor.continue();
      }
    };
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

// 删除某知识点相关的全部边
function dbDeleteEdgesByPoint(pointId) {
  return new Promise((resolve, reject) => {
    const tx = dbInstance.transaction(STORE_EDGES, 'readwrite');
    const store = tx.objectStore(STORE_EDGES);
    const cursorReq = store.openCursor();
    cursorReq.onsuccess = (e) => {
      const cursor = e.target.result;
      if (cursor) {
        const edge = cursor.value;
        if (edge.from === pointId || edge.to === pointId) {
          store.delete(cursor.key);
        }
        cursor.continue();
      }
    };
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

function dbClearEdges() {
  return new Promise((resolve, reject) => {
    const tx = dbInstance.transaction(STORE_EDGES, 'readwrite');
    const req = tx.objectStore(STORE_EDGES).clear();
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

// ============ Doc_Edge CRUD ============

// 写入/更新一条 Doc_Edge（指定 id 时为更新）
function dbPutDocEdge(edge) {
  return new Promise((resolve, reject) => {
    const tx = dbInstance.transaction(STORE_DOC_EDGES, 'readwrite');
    const req = tx.objectStore(STORE_DOC_EDGES).put(edge);
    req.onsuccess = () => resolve(edge);
    req.onerror = () => reject(req.error);
  });
}

// 删除一条 Doc_Edge
function dbDeleteDocEdge(id) {
  return new Promise((resolve, reject) => {
    const tx = dbInstance.transaction(STORE_DOC_EDGES, 'readwrite');
    const req = tx.objectStore(STORE_DOC_EDGES).delete(id);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

// 删除某文档相关的全部 Doc_Edge（doc_a 或 doc_b 任一端属于该文档）
function dbDeleteDocEdgesByDoc(docId) {
  return new Promise((resolve, reject) => {
    const tx = dbInstance.transaction(STORE_DOC_EDGES, 'readwrite');
    const store = tx.objectStore(STORE_DOC_EDGES);
    const cursorReq = store.openCursor();
    cursorReq.onsuccess = (e) => {
      const cursor = e.target.result;
      if (cursor) {
        const de = cursor.value;
        if (de.doc_a_id === docId || de.doc_b_id === docId) {
          store.delete(cursor.key);
        }
        cursor.continue();
      }
    };
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

// 清空全部 Doc_Edge
function dbClearDocEdges() {
  return new Promise((resolve, reject) => {
    const tx = dbInstance.transaction(STORE_DOC_EDGES, 'readwrite');
    const req = tx.objectStore(STORE_DOC_EDGES).clear();
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

// 查找两端为 (docA, docB) 的现有 Doc_Edge（无序匹配）
function dbFindDocEdgeByPair(docA, docB) {
  return new Promise((resolve, reject) => {
    const tx = dbInstance.transaction(STORE_DOC_EDGES, 'readonly');
    const store = tx.objectStore(STORE_DOC_EDGES);
    const cursorReq = store.openCursor();
    let found = null;
    cursorReq.onsuccess = (e) => {
      const cursor = e.target.result;
      if (cursor) {
        const v = cursor.value;
        if ((v.doc_a_id === docA && v.doc_b_id === docB) ||
            (v.doc_a_id === docB && v.doc_b_id === docA)) {
          found = v;
          // 找到后停止遍历
        } else {
          cursor.continue();
          return;
        }
      }
    };
    tx.oncomplete = () => resolve(found);
    tx.onerror = () => reject(tx.error);
  });
}

// upsert Doc_Edge：查找现有边，有则更新无则插入
async function dbUpsertDocEdge(docA, docB, weight, pairCount, scoreBreakdown) {
  const existing = await dbFindDocEdgeByPair(docA, docB);
  const rec = {
    doc_a_id: docA,
    doc_b_id: docB,
    doc_relation_weight: Math.round(weight * 1000) / 1000,
    valid_kp_pair_count: pairCount,
    updatedAt: now(),
  };
  // 保存关联依据（用于 tooltip 展示）
  if (scoreBreakdown) {
    rec.avg_vector_score = scoreBreakdown.avgVectorScore || 0;
    rec.avg_keyword_score = scoreBreakdown.avgKeywordScore || 0;
    rec.avg_fused_score = scoreBreakdown.avgFusedScore || 0;
    rec.overlap_keywords = scoreBreakdown.overlapKeywords || [];
    rec.overlap_entities = scoreBreakdown.overlapEntities || [];
    rec.top_pairs = (scoreBreakdown.topPairs || []).slice(0, 5);
    // 关联来源标记 + 本体推理统计 + 原始依据证据链
    rec.source_type = scoreBreakdown.sourceType || 'private';
    rec.ontology_pair_count = scoreBreakdown.ontologyPairCount || 0;
    rec.private_pair_count = scoreBreakdown.privatePairCount || 0;
    rec.avg_ontology_score = scoreBreakdown.avgOntologyScore || 0;
    rec.ontology_evidence = (scoreBreakdown.ontologyEvidence || []).slice(0, 2);
  }
  if (existing && existing.id !== undefined) {
    rec.id = existing.id;
    if (existing.createdAt) rec.createdAt = existing.createdAt;
  } else {
    rec.createdAt = now();
  }
  return dbPutDocEdge(rec);
}

// 查询某文档（或文档集合）相关的全部 Doc_Edge
function dbGetDocEdgeByDocId(docIds) {
  const idSet = new Set(Array.isArray(docIds) ? docIds : [docIds]);
  return new Promise((resolve, reject) => {
    const tx = dbInstance.transaction(STORE_DOC_EDGES, 'readonly');
    const req = tx.objectStore(STORE_DOC_EDGES).getAll();
    req.onsuccess = () => {
      const all = req.result || [];
      resolve(all.filter(de => idSet.has(de.doc_a_id) || idSet.has(de.doc_b_id)));
    };
    req.onerror = () => reject(req.error);
  });
}

// 查询两组文档之间全部有效(is_valid=true)的跨文件 Kp_Edge
// docIds: 文档 id 集合，返回两端文档均在该集合内的有效跨文件知识点边
function dbGetValidKpEdgesBetweenDocs(docIds) {
  const idSet = new Set(Array.isArray(docIds) ? docIds : [docIds]);
  return new Promise((resolve, reject) => {
    const tx = dbInstance.transaction(STORE_EDGES, 'readonly');
    const req = tx.objectStore(STORE_EDGES).getAll();
    req.onsuccess = () => {
      const all = req.result || [];
      const result = all.filter(e => {
        if (!e.isRender) return false; // is_valid = isRender
        const fromDoc = getPointDocId(e.from);
        const toDoc = getPointDocId(e.to);
        if (!fromDoc || !toDoc || fromDoc === toDoc) return false; // 跨文件
        return idSet.has(fromDoc) && idSet.has(toDoc);
      });
      resolve(result);
    };
    req.onerror = () => reject(req.error);
  });
}

function dbClearAll() {
  return Promise.all([
    new Promise((resolve, reject) => {
      const tx = dbInstance.transaction(STORE_DOCS, 'readwrite');
      const req = tx.objectStore(STORE_DOCS).clear();
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    }),
    new Promise((resolve, reject) => {
      const tx = dbInstance.transaction(STORE_POINTS, 'readwrite');
      const req = tx.objectStore(STORE_POINTS).clear();
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    }),
    new Promise((resolve, reject) => {
      const tx = dbInstance.transaction(STORE_EDGES, 'readwrite');
      const req = tx.objectStore(STORE_EDGES).clear();
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    }),
    dbClearDocEdges(),
  ]);
}
