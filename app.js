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

// ============ 旧数据迁移（maps -> docs/points/edges） ============
async function migrateOldMaps() {
  const existingDocs = await dbGetAllDocs();
  if (existingDocs.length > 0) return; // 新库已有数据，无需迁移

  const oldMaps = await dbGetAll(STORE_MAPS);
  if (oldMaps.length === 0) return;

  toast('正在迁移历史数据到新架构...', 'info', 3000);

  for (const map of oldMaps) {
    const doc = {
      docId: map.mapId,
      filename: map.filename || '未知文档',
      title: map.mindMapTitle || map.filename || '未知文档',
      summary: map.summary || '',
      createdAt: map.createdAt || now(),
    };
    await dbPutDoc(doc);
    state.docs.push(doc);

    const points = Array.isArray(map.points) ? map.points : [];
    for (let i = 0; i < points.length; i++) {
      const p = points[i];
      const desc = typeof p === 'string' ? p : (p.description || String(p));
      const pointId = `${map.mapId}::${i}`;
      const vec = (map.pointVecs && map.pointVecs[i]) ? map.pointVecs[i] : simpleEmbedding(desc);
      const point = {
        pointId,
        docId: map.mapId,
        description: desc,
        keywords: typeof p === 'string' ? [] : (p.keywords || []),
        entities: typeof p === 'string' ? [] : (p.entities || []),
        type: typeof p === 'string' ? 'concept' : (p.type || 'concept'),
        vector: vec,
        createdAt: map.createdAt || now(),
      };
      await dbPutPoint(point);
      state.points.push(point);
    }
  }

  // 旧 link 仅迁移知识点-知识点边；旧 map-map 边在新架构不再使用
  const oldLinks = await dbGetAll(STORE_LINKS);
  for (const link of oldLinks) {
    if (link.type !== 'point') continue;
    const weight = link.final_weight !== undefined ? link.final_weight : (link.score || 0);
    const shouldRender = link.is_render !== undefined ? link.is_render : true;
    const edge = {
      from: link.from,
      to: link.to,
      strength: Math.round(weight * 1000) / 1000,
      relationType: 'related',
      validationStatus: shouldRender ? 'validated' : 'rejected',
      isRender: shouldRender,
      source: link.source || 'vector',
      vectorScore: weight,
      entityScore: 0,
      keywordScore: 0,
      createdAt: link.createdAt || now(),
    };
    await dbPutEdge(edge);
    state.edges.push(edge);
  }

  rebuildPointMap();
  loadVectorIndex();
}

// ============ 配置管理 ============
function loadSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) {
      state.settings = { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
    }
  } catch (e) {
    console.warn('加载设置失败', e);
  }
}

function saveSettings(settings) {
  state.settings = { ...state.settings, ...settings };
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(state.settings));
}

// ============ 领域公共本体知识库（语料驱动） ============
const CORPUS_MANIFEST = 'domain_corpus/manifest.json';
const ONTOLOGY_OVERRIDE_KEY = 'knowledge_map_ontology_overrides';

// 别名索引: alias/name(小写) -> 规范名
let ontologyAliasMap = new Map();
// 实体索引: 规范名 -> {name, alias, relations:[{target,source_text,source_file}], domain, source_file, description}
let ontologyEntityMap = new Map();
// 关系索引: "from\u0000to" -> {source_text, source_file}  （供 tooltip 直接查证）
let ontologyRelationMap = new Map();

// 页面初始化：从 domain_corpus 读取 md 语料，浏览器内抽取实体/别名/关系三元组
async function buildOntologyFromCorpus() {
  state.ontology = { domains: {}, builtAt: Date.now() };
  let manifest;
  try {
    const res = await fetch(CORPUS_MANIFEST);
    if (!res.ok) throw new Error('manifest 不可用');
    manifest = await res.json();
  } catch (e) {
    console.warn('读取语料 manifest 失败，本体为空:', e);
    buildOntologyIndex();
    state.ontologyLoaded = true;
    return;
  }

  // 逐文件解析
  const allEntities = new Map();  // name -> entity 对象
  const allParagraphs = [];        // {text, file, domain} 用于共现分析

  for (const fileInfo of (manifest.files || [])) {
    let text = '';
    try {
      const res = await fetch(fileInfo.path);
      if (!res.ok) continue;
      text = await res.text();
    } catch (e) {
      console.warn('读取语料失败:', fileInfo.path, e);
      continue;
    }
    parseCorpusText(text, fileInfo.path, fileInfo.domain, fileInfo.label, allEntities, allParagraphs);
  }

  // 共现分析：从句子中提取关系并附带 source_text 原文
  coOccurrenceAnalysis(allEntities, allParagraphs);

  // 合并用户 localStorage 覆盖（手动增删编辑）
  applyOntologyOverrides(allEntities);

  // 组装 ontology 对象（按 domain 分组）
  const domains = {};
  for (const ent of allEntities.values()) {
    const dk = ent.domain || 'misc';
    if (!domains[dk]) domains[dk] = { label: ent.domainLabel || dk, entities: [] };
    domains[dk].entities.push({
      name: ent.name,
      alias: ent.alias || [],
      relations: (ent.relations || []).map(r => ({
        target: r.target,
        source_text: r.source_text || '',
        source_file: r.source_file || '',
      })),
      source_file: ent.source_file || '',
      description: ent.description || '',
    });
  }
  state.ontology.domains = domains;
  buildOntologyIndex();
  state.ontologyLoaded = true;
  console.log('领域本体已从语料构建，实体数:', ontologyEntityMap.size, '关系数:', ontologyRelationMap.size);
}

// 解析单个 md 语料文件：结构化字段(别名/关系) + 段落收集
function parseCorpusText(text, filename, domain, domainLabel, entities, paragraphs) {
  const lines = text.split('\n');
  let currentEntity = null;
  let paraBuffer = [];

  const flushPara = () => {
    if (paraBuffer.length === 0) return;
    const paraText = paraBuffer.join(' ').trim();
    if (paraText) {
      paragraphs.push({ text: paraText, file: filename, domain });
      if (currentEntity && !currentEntity.description) {
        currentEntity.description = paraText;
      }
    }
    paraBuffer = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) continue;

    // domain 声明行: # domain: xxx
    const dm = line.match(/^#\s+domain:\s*(\S+)/i);
    if (dm) { domain = dm[1]; continue; }

    // 实体标题: ## Name
    const em = line.match(/^##\s+(.+)/);
    if (em) {
      flushPara();
      const name = em[1].trim();
      currentEntity = {
        name,
        alias: [],
        relations: [],
        domain,
        domainLabel: domainLabel || domain,
        source_file: filename,
        description: '',
      };
      entities.set(name, currentEntity);
      continue;
    }

    // 别名行: 别名: a, b, c
    const am = line.match(/^别名[:：]\s*(.+)/);
    if (am && currentEntity) {
      currentEntity.alias = am[1].split(/[,，]/).map(s => s.trim()).filter(Boolean);
      continue;
    }

    // 关系行: 关系: x, y, z
    const rm = line.match(/^(?:关系|关联)[:：]\s*(.+)/);
    if (rm && currentEntity) {
      const targets = rm[1].split(/[,，|]/).map(s => s.trim()).filter(Boolean);
      for (const t of targets) {
        currentEntity.relations.push({
          target: t,
          source_text: '',   // 待共现分析填充
          source_file: filename,
        });
      }
      continue;
    }

    // 普通文本行 → 段落缓冲
    if (currentEntity) {
      paraBuffer.push(line);
    } else {
      paragraphs.push({ text: line, file: filename, domain });
    }
  }
  flushPara();
}

// 共现分析：在句子中找两个实体同时出现 → 建立/增强关系并记录 source_text 原文
function coOccurrenceAnalysis(entities, paragraphs) {
  // 构建别名→规范名查找表
  const aliasToName = new Map();
  for (const [name, ent] of entities) {
    aliasToName.set(name.toLowerCase(), name);
    for (const a of (ent.alias || [])) {
      const k = String(a).toLowerCase().trim();
      if (k) aliasToName.set(k, name);
    }
  }

  // 按实体名长度降序排列，避免短名误匹配（如 "C" 匹配到 "C++"）
  const sortedAliases = Array.from(aliasToName.entries()).sort((a, b) => b[0].length - a[0].length);

  for (const para of paragraphs) {
    const sentences = splitSentences(para.text);
    for (const sentence of sentences) {
      const lower = sentence.toLowerCase();
      // 找出此句中出现的所有规范实体名
      const mentioned = new Set();
      for (const [alias, name] of sortedAliases) {
        if (lower.includes(alias)) {
          mentioned.add(name);
        }
      }
      if (mentioned.size < 2) continue;
      // 为每对实体建立/增强双向关系，附带 source_text
      const arr = Array.from(mentioned);
      for (let i = 0; i < arr.length; i++) {
        for (let j = 0; j < arr.length; j++) {
          if (i === j) continue;
          enrichRelationWithEvidence(entities, arr[i], arr[j], sentence, para.file);
        }
      }
    }
  }

  // 为结构化声明的关系补充 source_text（未命中共现时用实体描述）
  for (const ent of entities.values()) {
    for (const rel of (ent.relations || [])) {
      if (!rel.source_text && ent.description) {
        rel.source_text = ent.description;
      }
    }
  }
}

// 增强/新建关系并记录最佳 source_text（优先更长的句子 = 更充分的依据）
function enrichRelationWithEvidence(entities, fromName, toName, sentence, file) {
  const ent = entities.get(fromName);
  if (!ent) return;
  let rel = ent.relations.find(r => r.target === toName);
  if (!rel) {
    ent.relations.push({ target: toName, source_text: sentence, source_file: file });
  } else if (!rel.source_text || rel.source_text.length < sentence.length) {
    rel.source_text = sentence;
    rel.source_file = file;
  }
}

// 中文/英文分句
function splitSentences(text) {
  // 按 。！？；.!?; 以及换行分句
  return text.split(/[。！？；.!?;\n]+/).map(s => s.trim()).filter(s => s.length > 4);
}

// 合并 localStorage 用户覆盖（手动增删）
function applyOntologyOverrides(entities) {
  let overrides;
  try {
    overrides = JSON.parse(localStorage.getItem(ONTOLOGY_OVERRIDE_KEY) || '{}');
  } catch (e) { overrides = {}; }

  // 用户新增的实体
  for (const ent of (overrides.added || [])) {
    if (!entities.has(ent.name)) {
      entities.set(ent.name, { ...ent, relations: (ent.relations || []).map(r => typeof r === 'string' ? { target: r, source_text: '', source_file: 'manual' } : r) });
    }
  }
  // 用户删除的实体
  for (const name of (overrides.removed || [])) {
    entities.delete(name);
  }
}

// 构建别名/实体/关系索引（供关联分数计算 + tooltip 查证）
function buildOntologyIndex() {
  ontologyAliasMap = new Map();
  ontologyEntityMap = new Map();
  ontologyRelationMap = new Map();
  const domains = (state.ontology && state.ontology.domains) || {};
  for (const [domainKey, domain] of Object.entries(domains)) {
    for (const ent of (domain.entities || [])) {
      const canon = String(ent.name).trim();
      ontologyEntityMap.set(canon, { ...ent, domain: domainKey });
      ontologyAliasMap.set(canon.toLowerCase(), canon);
      for (const a of (ent.alias || [])) {
        const aliasKey = String(a).toLowerCase().trim();
        if (aliasKey) ontologyAliasMap.set(aliasKey, canon);
      }
      // 关系索引：from→to 的 source_text
      for (const rel of (ent.relations || [])) {
        const rKey = canon + '\u0000' + rel.target;
        if (!ontologyRelationMap.has(rKey) || (rel.source_text || '').length > (ontologyRelationMap.get(rKey)?.source_text || '').length) {
          ontologyRelationMap.set(rKey, { source_text: rel.source_text || '', source_file: rel.source_file || '' });
        }
      }
    }
  }
}

// 将知识点实体列表解析为本体规范名（命中别名的归一化）
function resolveOntologyEntities(entities) {
  if (!entities || !Array.isArray(entities) || !state.ontologyLoaded) return [];
  const result = [];
  const seen = new Set();
  for (const e of entities) {
    if (e == null) continue;
    const key = String(e).toLowerCase().trim();
    const canon = ontologyAliasMap.get(key);
    if (canon && !seen.has(canon)) {
      seen.add(canon);
      result.push(canon);
    }
  }
  return result;
}

// 本体推理匹配：返回分数 + 证据链（含 source_text 原文）
// 同实体(别名共现) -> 0.6；直接关系 -> 1.0；2跳传递关系 -> 0.4
function ontologyMatch(pointA, candidate) {
  if (!state.ontologyLoaded || state.settings.ontologyWeight <= 0) {
    return { score: 0, evidence: [] };
  }
  const ontoA = resolveOntologyEntities(pointA.entities || []);
  const ontoB = resolveOntologyEntities(candidate.entities || []);
  if (ontoA.length === 0 || ontoB.length === 0) return { score: 0, evidence: [] };

  const setB = new Set(ontoB);
  let best = 0;
  const evidence = [];

  for (const name of ontoA) {
    const ent = ontologyEntityMap.get(name);
    if (!ent) continue;
    // 别名共现
    if (setB.has(name)) {
      best = Math.max(best, 0.6);
      evidence.push({ type: 'alias', from: name, to: name, source_text: ent.description || '', source_file: ent.source_file || '', score: 0.6 });
    }
    // 直接关系
    for (const rel of (ent.relations || [])) {
      if (setB.has(rel.target)) {
        best = Math.max(best, 1.0);
        evidence.push({ type: 'relation', from: name, to: rel.target, source_text: rel.source_text || '', source_file: rel.source_file || '', score: 1.0 });
      }
    }
    // 2 跳传递推理
    for (const rel of (ent.relations || [])) {
      const relEnt = ontologyEntityMap.get(rel.target);
      if (relEnt) {
        for (const rel2 of (relEnt.relations || [])) {
          if (setB.has(rel2.target) && rel2.target !== name) {
            best = Math.max(best, 0.4);
            evidence.push({ type: 'transitive', from: name, via: rel.target, to: rel2.target, source_text: rel2.source_text || '', source_file: rel2.source_file || '', score: 0.4 });
          }
        }
      }
    }
  }

  return { score: best, evidence: evidence.slice(0, 5) };
}

// 持久化用户覆盖到 localStorage（语料本体每次重建，仅覆盖增量持久化）
function persistOntologyOverrides() {
  localStorage.setItem(ONTOLOGY_OVERRIDE_KEY, JSON.stringify(buildOntologyOverrideSnapshot()));
}

function buildOntologyOverrideSnapshot() {
  const added = [];
  const removed = [];
  let overrides;
  try { overrides = JSON.parse(localStorage.getItem(ONTOLOGY_OVERRIDE_KEY) || '{}'); } catch (e) { overrides = {}; }
  return overrides;
}

// ============ 本体实体管理（增删改查） ============

// 获取某领域实体列表
function getOntologyEntities(domainKey) {
  const domain = (state.ontology.domains || {})[domainKey];
  return domain ? (domain.entities || []) : [];
}

// 新增实体（内存 + localStorage 覆盖）
function addOntologyEntity(domainKey, name, aliasArr, relationArr) {
  if (!state.ontology.domains) state.ontology.domains = {};
  if (!state.ontology.domains[domainKey]) {
    state.ontology.domains[domainKey] = { label: domainKey, entities: [] };
  }
  const cleanName = String(name).trim();
  if (!cleanName) { toast('实体名称不能为空', 'warning'); return false; }
  const exists = getOntologyEntities(domainKey).some(e => String(e.name).toLowerCase() === cleanName.toLowerCase());
  if (exists) { toast('该实体已存在', 'warning'); return false; }
  const newEnt = {
    name: cleanName,
    alias: aliasArr.filter(a => a.trim()),
    relations: relationArr.filter(r => r.trim()).map(t => ({ target: t, source_text: '', source_file: 'manual' })),
    source_file: 'manual',
    description: '',
    domain: domainKey,
    domainLabel: ((state.ontology.domains[domainKey] || {}).label) || domainKey,
  };
  state.ontology.domains[domainKey].entities.push(newEnt);
  saveOntologyOverride('add', newEnt);
  buildOntologyIndex();
  return true;
}

// 更新实体（按索引）
function updateOntologyEntity(domainKey, index, name, aliasArr, relationArr) {
  const entities = getOntologyEntities(domainKey);
  if (index < 0 || index >= entities.length) return false;
  const cleanName = String(name).trim();
  if (!cleanName) { toast('实体名称不能为空', 'warning'); return false; }
  entities[index] = {
    ...entities[index],
    name: cleanName,
    alias: aliasArr.filter(a => a.trim()),
    relations: relationArr.filter(r => r.trim()).map(t => ({ target: t, source_text: entities[index].relations?.find(r2 => r2.target === t)?.source_text || '', source_file: entities[index].source_file || 'manual' })),
  };
  saveOntologyOverride('update', entities[index]);
  buildOntologyIndex();
  return true;
}

// 删除实体（按索引）
function deleteOntologyEntity(domainKey, index) {
  const entities = getOntologyEntities(domainKey);
  if (index < 0 || index >= entities.length) return false;
  const removed = entities.splice(index, 1)[0];
  saveOntologyOverride('remove', { name: removed.name, domain: domainKey });
  buildOntologyIndex();
  return true;
}

// 保存用户覆盖到 localStorage（added / removed 增量）
function saveOntologyOverride(action, entity) {
  let overrides;
  try { overrides = JSON.parse(localStorage.getItem(ONTOLOGY_OVERRIDE_KEY) || '{}'); } catch (e) { overrides = {}; }
  if (!overrides.added) overrides.added = [];
  if (!overrides.removed) overrides.removed = [];

  if (action === 'add' || action === 'update') {
    // 同名替换
    overrides.added = overrides.added.filter(e => e.name !== entity.name);
    overrides.added.push({
      name: entity.name, alias: entity.alias || [],
      relations: (entity.relations || []).map(r => typeof r === 'string' ? r : { target: r.target, source_text: r.source_text || '', source_file: r.source_file || '' }),
      source_file: entity.source_file || 'manual', description: entity.description || '',
      domain: entity.domain, domainLabel: entity.domainLabel,
    });
  } else if (action === 'remove') {
    overrides.added = overrides.added.filter(e => e.name !== entity.name);
    if (!overrides.removed.includes(entity.name)) overrides.removed.push(entity.name);
  }
  localStorage.setItem(ONTOLOGY_OVERRIDE_KEY, JSON.stringify(overrides));
}

// 重置本体：清除覆盖，重新从语料构建
async function resetOntology() {
  localStorage.removeItem(ONTOLOGY_OVERRIDE_KEY);
  await buildOntologyFromCorpus();
  return true;
}

// 打开本体管理弹窗
function openOntologyModal() {
  $('#ontology-modal').classList.remove('hidden');
  renderOntologyTabs();
  renderOntologyList();
}

function closeOntologyModal() {
  $('#ontology-modal').classList.add('hidden');
}

// 渲染领域 Tab
function renderOntologyTabs() {
  const tabContainer = $('#ontology-tabs');
  if (!tabContainer) return;
  const domains = state.ontology.domains || {};
  const tabs = Object.keys(domains);
  tabContainer.innerHTML = tabs.map(key => {
    const label = domains[key].label || key;
    const active = key === state.ontologyEditDomain ? 'tab-active' : '';
    return `<button class="ontology-tab ${active}" data-domain="${escapeHtml(key)}">${escapeHtml(label)}</button>`;
  }).join('');
  tabContainer.querySelectorAll('.ontology-tab').forEach(btn => {
    btn.onclick = () => {
      state.ontologyEditDomain = btn.dataset.domain;
      renderOntologyTabs();
      renderOntologyList();
    };
  });
}

// 渲染实体列表（当前领域）
function renderOntologyList() {
  const listEl = $('#ontology-entity-list');
  if (!listEl) return;
  const domainKey = state.ontologyEditDomain;
  const entities = getOntologyEntities(domainKey);
  const domainLabel = ((state.ontology.domains || {})[domainKey] || {}).label || domainKey;

  if (entities.length === 0) {
    listEl.innerHTML = `<p class="settings-hint">「${escapeHtml(domainLabel)}」领域暂无实体，点击下方"添加实体"创建。</p>`;
    return;
  }
  listEl.innerHTML = entities.map((ent, i) => {
    const aliases = (ent.alias || []).join(', ');
    const relations = (ent.relations || []).map(r => {
      const target = typeof r === 'string' ? r : r.target;
      const src = typeof r === 'string' ? '' : (r.source_file || '');
      const srcTag = src ? `<span class="entity-src" title="${escapeHtml(src)}">📄 ${escapeHtml(src.split('/').pop())}</span>` : '';
      return `<span class="tag">${escapeHtml(target)}</span>${srcTag}`;
    }).join(' ');
    const srcFile = ent.source_file ? `<div class="entity-src-line">📄 来源: ${escapeHtml(ent.source_file)}</div>` : '';
    return `<div class="ontology-entity-card" data-index="${i}">
      <div class="entity-header">
        <span class="entity-name">${escapeHtml(ent.name)}</span>
        <span class="entity-actions">
          <button class="btn btn-sm entity-edit" data-index="${i}" title="编辑">✏️</button>
          <button class="btn btn-sm btn-danger entity-delete" data-index="${i}" title="删除">🗑</button>
        </span>
      </div>
      ${aliases ? `<div class="entity-aliases">别名: ${escapeHtml(aliases)}</div>` : ''}
      ${relations ? `<div class="entity-relations">关系: ${relations}</div>` : '<div class="entity-relations entity-empty">无关系</div>'}
      ${srcFile}
    </div>`;
  }).join('');

  // 绑定编辑/删除事件
  listEl.querySelectorAll('.entity-edit').forEach(btn => {
    btn.onclick = () => openEntityEditor(Number(btn.dataset.index));
  });
  listEl.querySelectorAll('.entity-delete').forEach(btn => {
    btn.onclick = () => {
      const idx = Number(btn.dataset.index);
      const ent = getOntologyEntities(domainKey)[idx];
      if (confirm(`确定删除实体「${ent.name}」？`)) {
        deleteOntologyEntity(domainKey, idx);
        renderOntologyList();
        toast('实体已删除', 'success');
      }
    };
  });
}

// 实体编辑/新增表单
function openEntityEditor(index = -1) {
  const domainKey = state.ontologyEditDomain;
  const entities = getOntologyEntities(domainKey);
  const isEdit = index >= 0 && index < entities.length;
  const ent = isEdit ? entities[index] : { name: '', alias: [], relations: [] };

  const formEl = $('#ontology-entity-form');
  formEl.dataset.mode = isEdit ? 'edit' : 'add';
  formEl.dataset.index = String(index);

  $('#entity-name').value = ent.name || '';
  $('#entity-alias').value = (ent.alias || []).join(', ');
  // 关系候选：当前领域全部实体名
  const allNames = entities.map(e => e.name);
  // relations 是对象数组 {target, source_text, source_file}，提取 target
  $('#entity-relations').value = (ent.relations || []).map(r => typeof r === 'string' ? r : r.target).join(', ');
  $('#entity-relations').setAttribute('list', 'entity-name-list');
  // 更新 datalist
  let dl = $('#entity-name-list');
  if (!dl) {
    dl = document.createElement('datalist');
    dl.id = 'entity-name-list';
    document.body.appendChild(dl);
  }
  dl.innerHTML = allNames.map(n => `<option value="${escapeHtml(n)}">`).join('');

  $('#entity-editor-title').textContent = isEdit ? `编辑实体：${ent.name}` : '新增实体';
  formEl.classList.remove('hidden');
  $('#entity-name').focus();
}

function closeEntityEditor() {
  $('#ontology-entity-form').classList.add('hidden');
}

// 保存实体（新增/编辑统一入口）
function saveEntityFromForm() {
  const domainKey = state.ontologyEditDomain;
  const formEl = $('#ontology-entity-form');
  const isEdit = formEl.dataset.mode === 'edit';
  const index = Number(formEl.dataset.index);
  const name = $('#entity-name').value;
  const aliasArr = $('#entity-alias').value.split(',').map(s => s.trim()).filter(Boolean);
  const relationArr = $('#entity-relations').value.split(',').map(s => s.trim()).filter(Boolean);

  let ok;
  if (isEdit) {
    ok = updateOntologyEntity(domainKey, index, name, aliasArr, relationArr);
  } else {
    ok = addOntologyEntity(domainKey, name, aliasArr, relationArr);
  }
  if (ok) {
    closeEntityEditor();
    renderOntologyList();
    toast(isEdit ? '实体已更新' : '实体已添加', 'success');
  }
}

function openSettingsModal() {
  $('#setting-llm-url').value = state.settings.llmApiUrl;
  $('#setting-llm-key').value = state.settings.llmApiKey;
  $('#setting-llm-model').value = state.settings.llmModel;
  $('#setting-emb-url').value = state.settings.embeddingApiUrl;
  $('#setting-emb-key').value = state.settings.embeddingApiKey;
  $('#setting-emb-model').value = state.settings.embeddingModel;
  $('#setting-threshold').value = state.settings.threshold;
  $('#threshold-value').textContent = state.settings.threshold.toFixed(2);
  $('#setting-ontology-weight').value = state.settings.ontologyWeight;
  $('#ontology-weight-value').textContent = state.settings.ontologyWeight.toFixed(2);
  $('#settings-modal').classList.remove('hidden');
}

function closeSettingsModal() {
  $('#settings-modal').classList.add('hidden');
}

// ============ 文件读取层 ============
function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file, 'UTF-8');
  });
}

// ============ 文本预处理 ============
function cleanText(text) {
  if (!text) return '';
  // 去除 BOM
  text = text.replace(/^\uFEFF/, '');
  // 统一换行
  text = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  // 去除 markdown 图片/链接纯文本化（保留可读文本）
  text = text.replace(/!\[[^\]]*\]\([^)]*\)/g, '');
  text = text.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1');
  // 去除 html 标签
  text = text.replace(/<[^>]+>/g, '');
  // 去除代码块围栏
  text = text.replace(/```[\s\S]*?```/g, m => m.replace(/```[a-zA-Z]*\n?/g, '').replace(/```/g, ''));
  // 去除行内代码反引号
  text = text.replace(/`([^`]+)`/g, '$1');
  // 去除 markdown 标题标记符（保留文字）
  text = text.replace(/^(#{1,6})\s+/gm, '');
  // 去除引用标记
  text = text.replace(/^>\s?/gm, '');
  // 去除列表标记
  text = text.replace(/^[-*+]\s+/gm, '');
  // 去除水平分割线
  text = text.replace(/^---+$/gm, '');
  // 压缩页眉页脚式重复行（连续相同字符行只保留一行）
  text = text.replace(/^(.{1,40})\n\1$/gm, '$1');
  // 去除多余空行（连续3个以上换行压缩为2个）
  text = text.replace(/\n{3,}/g, '\n\n');
  // 去除行尾空格
  text = text.replace(/[ \t]+$/gm, '');
  // 去除首尾空白
  return text.trim();
}

// 按句子切分（中英文句末标点）
function splitSentences(text) {
  const parts = text.match(/[^。！？；\n.!?;]+[。！？；\n.!?;]?/g) || [text];
  return parts.map(s => s).filter(s => s.trim().length > 0);
}

// 文本分片：控制单段 ~targetSize 字符，按段落/句子边界切分
function chunkText(text, targetSize = CHUNK_TARGET_SIZE) {
  if (!text) return [];
  const chunks = [];
  const paragraphs = text.split(/\n{2,}/).map(p => p.trim()).filter(p => p.length > 0);

  let current = '';
  const flush = () => {
    const t = current.trim();
    if (t.length > 0) chunks.push(t);
    current = '';
  };

  const pushParagraph = (para) => {
    if (current.length === 0) {
      current = para;
    } else if ((current + '\n\n' + para).length <= targetSize) {
      current = current + '\n\n' + para;
    } else {
      flush();
      if (para.length <= targetSize) {
        current = para;
      } else {
        // 段落过长，按句子切分
        const sentences = splitSentences(para);
        let cur = '';
        for (const s of sentences) {
          if (cur.length === 0) {
            cur = s;
          } else if ((cur + s).length <= targetSize) {
            cur += s;
          } else {
            if (cur.trim().length > 0) chunks.push(cur.trim());
            if (s.length > targetSize) {
              // 句子过长，硬切
              for (let i = 0; i < s.length; i += targetSize) {
                chunks.push(s.slice(i, i + targetSize));
              }
              cur = '';
            } else {
              cur = s;
            }
          }
        }
        if (cur.trim().length > 0) chunks.push(cur.trim());
      }
    }
  };

  for (const para of paragraphs) pushParagraph(para);
  flush();

  return chunks.length > 0 ? chunks : [text.slice(0, targetSize)];
}

// ============ LLM 知识点抽取 ============

// 分片抽取知识点。withMeta=true 时（首片）一并输出文档标题与摘要
async function callLLMExtract(chunk, withMeta) {
  if (!state.settings.llmApiKey) {
    const points = fallbackExtractPoints(chunk);
    if (withMeta) {
      const meta = fallbackDocMeta(chunk, chunk);
      return { points, title: meta.title, summary: meta.summary };
    }
    return { points };
  }

  const metaRule = withMeta
    ? '- docTitle: 提炼文档主题标题（10-20字，概括核心主题，不要直接用文件名）\n- docSummary: 文档整体摘要（80-200字，概括核心主旨）\n'
    : '';
  const outputFormat = withMeta
    ? '{"docTitle":"标题","docSummary":"摘要","points":[{"description":"知识点描述","keywords":["关键词"],"entities":["实体"],"type":"concept"}]}'
    : '{"points":[{"description":"知识点描述","keywords":["关键词"],"entities":["实体"],"type":"concept"}]}';

  const prompt = `你是一个文档分析助手。请阅读以下文本片段，抽取其中的核心知识点。

要求：
${metaRule}- points: 该片段中的核心知识点列表（1-6个），每个知识点是一个对象：
  - description: 知识点描述（10-40字，概括该知识点核心内容）
  - keywords: 关键词列表（2-5个，每个2-6字，用于语义匹配）
  - entities: 涉及的命名实体（如技术名、产品名、人名、地名、标准名等，0-5个）
  - type: 知识点类型，取值之一：concept(概念)、principle(原理)、method(方法)、example(示例)、definition(定义)、fact(事实)

注意：只抽取知识点本身，不要计算知识点之间的关系。
只输出 JSON，不要任何其他内容。格式：
${outputFormat}

文本片段：
---
${chunk.slice(0, 6000)}
---`;

  try {
    const response = await fetch(state.settings.llmApiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${state.settings.llmApiKey}`,
      },
      body: JSON.stringify({
        model: state.settings.llmModel,
        messages: [{ role: 'user', content: prompt }],
        temperature: 0.3,
      }),
    });

    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`API ${response.status}: ${errText.slice(0, 200)}`);
    }

    const data = await response.json();
    const content = data.choices[0].message.content;
    const jsonMatch = content.match(/\{[\s\S]*\}/);
    if (!jsonMatch) throw new Error('LLM 输出中未找到 JSON');

    const parsed = JSON.parse(jsonMatch[0]);
    if (!Array.isArray(parsed.points)) throw new Error('LLM 输出 points 结构不完整');

    const points = parsed.points.map(normalizePoint);
    const result = { points };
    if (withMeta) {
      result.title = parsed.docTitle || '';
      result.summary = parsed.docSummary || '';
    }
    return result;
  } catch (e) {
    console.error('LLM 抽取失败，使用降级方案:', e);
    toast('AI 解析失败，使用降级方案: ' + e.message, 'warning', 4000);
    const points = fallbackExtractPoints(chunk);
    if (withMeta) {
      const meta = fallbackDocMeta(chunk, chunk);
      return { points, title: meta.title, summary: meta.summary };
    }
    return { points };
  }
}

// 规范化知识点结构
function normalizePoint(p) {
  if (p == null) return { description: '', keywords: [], entities: [], type: 'concept' };
  if (typeof p === 'string') {
    return { description: p, keywords: [], entities: [], type: 'concept' };
  }
  return {
    description: p.description || p.text || String(p),
    keywords: Array.isArray(p.keywords) ? p.keywords : [],
    entities: Array.isArray(p.entities) ? p.entities : [],
    type: p.type || 'concept',
  };
}

// 降级解析：从片段中提取知识点
function fallbackExtractPoints(chunk) {
  const lines = chunk.split('\n').filter(l => l.trim());
  const headings = lines
    .filter(l => /^#{1,4}\s+/.test(l))
    .map(l => l.replace(/^#{1,4}\s+/, '').trim())
    .filter(h => h.length > 0);

  let rawPoints;
  if (headings.length >= 2) {
    rawPoints = headings.slice(0, 6);
  } else {
    rawPoints = chunk.split(/\n+/)
      .filter(p => p.trim().length > 10)
      .slice(0, 5)
      .map(p => truncate(p.trim().replace(/\n/g, ' '), 40));
  }

  return rawPoints.map(p => ({
    description: p,
    keywords: extractKeywords(p, chunk),
    entities: extractEntities(p, chunk),
    type: classifyPointType(p),
  }));
}

// 降级生成文档标题与摘要
function fallbackDocMeta(text, filename) {
  const lines = text.split('\n').filter(l => l.trim());
  const firstHeading = lines.find(l => /^#{1,3}\s+/.test(l));
  const title = firstHeading
    ? firstHeading.replace(/^#{1,3}\s+/, '').trim()
    : filename.replace(/\.(md|txt|markdown)$/i, '');
  const summary = text.slice(0, 200).replace(/\n/g, ' ') + (text.length > 200 ? '...' : '');
  return { title, summary };
}

// 从知识点描述和上下文中提取关键词
function extractKeywords(pointText, fullText) {
  const stopwords = new Set(['的', '了', '是', '在', '和', '与', '或', '等', '为', '对', '中', '可', '以', '及', '但', '也', '都', '不', '有', '无', '一', '个', '这', '那', '到', '从', '被', '将', '让', '使', '给', 'the', 'a', 'an', 'is', 'are', 'was', 'were', 'to', 'of', 'in', 'on', 'for', 'and', 'or', 'but', 'with', 'from', 'by']);
  const tokens = pointText.match(/[\u4e00-\u9fa5]{2,4}|[a-zA-Z]{3,}/g) || [];
  const freq = {};
  for (const t of tokens) {
    if (stopwords.has(t.toLowerCase())) continue;
    freq[t] = (freq[t] || 0) + 1;
  }
  return Object.entries(freq)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(e => e[0]);
}

// 从文本中提取命名实体
function extractEntities(pointText, fullText) {
  const entities = new Set();
  const caps = pointText.match(/\b[A-Z][a-z]{2,}\b/g) || [];
  caps.forEach(c => entities.add(c));
  const acronyms = pointText.match(/\b[A-Z]{2,5}\b/g) || [];
  acronyms.forEach(a => entities.add(a));
  const tech = pointText.match(/[a-z]+-[a-z]+/g) || [];
  tech.forEach(t => entities.add(t));
  const techSuffixes = ['架构', '协议', '算法', '框架', '模型', '系统', '服务', '平台', '数据库', '缓存', '队列', '网关', '容器', '节点', '模块', '组件', '接口', '引擎', '代理', '副本'];
  for (const suffix of techSuffixes) {
    const idx = pointText.indexOf(suffix);
    if (idx >= 0) {
      const start = Math.max(0, idx - 4);
      const entity = pointText.slice(start, idx + suffix.length);
      if (entity.length >= 2) entities.add(entity);
    }
  }
  const quoted = fullText.match(/[\u300c\u201c\u201d"'](.{2,20})[\u300d\u201c\u201d"']/g) || [];
  quoted.forEach(q => {
    const inner = q.slice(1, -1);
    if (inner.length >= 2 && inner.length <= 20) entities.add(inner);
  });
  return Array.from(entities).slice(0, 5);
}

// 知识点类型分类
function classifyPointType(text) {
  const lower = text.toLowerCase();
  if (/定义|是指|什么是|concept|definition/.test(lower)) return 'definition';
  if (/原理|理论|机制|principle|theory/.test(lower)) return 'principle';
  if (/方法|步骤|流程|如何|实现|method|step|process|how/.test(lower)) return 'method';
  if (/示例|例子|举例|比如|例如|example|case/.test(lower)) return 'example';
  if (/事实|数据|统计|fact|stat/.test(lower)) return 'fact';
  return 'concept';
}

// ============ Embedding 语义向量 ============
// ============ 本地 Embedding（transformers.js） ============
// 使用 @xenova/transformers 在浏览器端本地生成语义向量
// 模型: Xenova/all-MiniLM-L6-v2（384 维，轻量快速）
let _embeddingPipeline = null;
let _embeddingLoading = false;

async function getLocalEmbedding(text) {
  // transformers.js 未加载
  if (typeof window.transformers === 'undefined' && typeof window.Transformers === 'undefined') {
    return null;
  }
  try {
    if (!_embeddingPipeline && !_embeddingLoading) {
      _embeddingLoading = true;
      const T = window.transformers || window.Transformers;
      _embeddingPipeline = await T.pipeline('feature-extraction', 'Xenova/all-MiniLM-L6-v2', {
        quantized: true,
      });
      _embeddingLoading = false;
    }
    // 等待加载完成
    if (_embeddingLoading) {
      while (_embeddingLoading) {
        await new Promise(r => setTimeout(r, 200));
      }
    }
    if (!_embeddingPipeline) return null;
    const output = await _embeddingEmbed(_embeddingPipeline, text);
    return output;
  } catch (e) {
    console.error('transformers.js embedding 失败:', e);
    _embeddingPipeline = null;
    _embeddingLoading = false;
    return null;
  }
}

// 调用 pipeline 并做 mean pooling → 归一化
async function _embeddingEmbed(pipeline, text) {
  const result = await pipeline(text, { pooling: 'mean', normalize: true });
  // transformers.js 返回 Tensor，取 toList() 转普通数组
  if (result && result.tolist) {
    return result.tolist()[0];
  }
  if (result && result.data) {
    return Array.from(result.data);
  }
  if (Array.isArray(result)) {
    return Array.isArray(result[0]) ? result[0] : result;
  }
  return null;
}

async function getEmbedding(text) {
  const inputText = (text || '').slice(0, 8000);
  // 优先：transformers.js 本地模型（无需 API Key）
  const localVec = await getLocalEmbedding(inputText);
  if (localVec && localVec.length > 0) {
    return localVec;
  }
  // 次选：配置了外部 Embedding API
  if (state.settings.embeddingApiKey) {
    try {
      const response = await fetch(state.settings.embeddingApiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${state.settings.embeddingApiKey}`,
        },
        body: JSON.stringify({
          model: state.settings.embeddingModel,
          input: inputText,
        }),
      });
      if (!response.ok) throw new Error(`Embedding API ${response.status}`);
      const data = await response.json();
      return data.data[0].embedding;
    } catch (e) {
      console.error('Embedding API 调用失败，使用本地降级方案:', e);
    }
  }
  // 最终降级：字符 n-gram 向量
  return simpleEmbedding(inputText);
}

// 本地降级方案：基于字符 n-gram 的向量
function simpleEmbedding(text) {
  const dim = 384;
  const vec = new Array(dim).fill(0);
  const chars = (text || '').toLowerCase().replace(/\s+/g, ' ').trim();
  for (let i = 0; i < chars.length - 1; i++) {
    const bigram = chars.charCodeAt(i) * 31 + chars.charCodeAt(i + 1);
    vec[Math.abs(bigram) % dim] += 1.0;
  }
  for (let i = 0; i < chars.length - 2; i++) {
    const trigram = (chars.charCodeAt(i) * 31 + chars.charCodeAt(i + 1)) * 31 + chars.charCodeAt(i + 2);
    vec[Math.abs(trigram) % dim] += 0.5;
  }
  const norm = Math.sqrt(vec.reduce((s, v) => s + v * v, 0));
  return norm > 0 ? vec.map(v => v / norm) : vec;
}

// 余弦相似度
function cosineSimilarity(a, b) {
  if (!a || !b || a.length !== b.length) return 0;
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  const denom = Math.sqrt(normA) * Math.sqrt(normB);
  return denom > 0 ? dot / denom : 0;
}

// ============ 实体别名映射 ============
// 同义实体归一化：如 "JS" → "JavaScript", "AI" → "人工智能"
const ENTITY_ALIASES = {
  'js': 'javascript', 'javascript': 'javascript',
  'ts': 'typescript', 'typescript': 'typescript',
  'ai': '人工智能', '人工智能': '人工智能',
  'ml': '机器学习', '机器学习': '机器学习',
  'dl': '深度学习', '深度学习': '深度学习',
  'nlp': '自然语言处理', '自然语言处理': '自然语言处理',
  'cv': '计算机视觉', '计算机视觉': '计算机视觉',
  'api': 'api', 'rest': 'restful api',
  'restful': 'restful api', 'restful api': 'restful api',
  'db': '数据库', 'database': '数据库', '数据库': '数据库',
  'sql': 'sql', 'nosql': 'nosql',
  'py': 'python', 'python': 'python',
  'go': 'golang', 'golang': 'golang',
  'docker': 'docker', 'k8s': 'kubernetes', 'kubernetes': 'kubernetes',
  '微服务': '微服务', 'microservice': '微服务', 'microservices': '微服务',
  '前端': '前端开发', 'frontend': '前端开发',
  '后端': '后端开发', 'backend': '后端开发',
  'css': 'css', 'html': 'html',
  'react': 'react', 'vue': 'vue', 'angular': 'angular',
  'node': 'node.js', 'nodejs': 'node.js', 'node.js': 'node.js',
  'redis': 'redis', 'mysql': 'mysql', 'postgres': 'postgresql', 'postgresql': 'postgresql',
  'linux': 'linux', 'shell': 'shell', 'bash': 'bash',
  'git': 'git', 'github': 'github', 'gitlab': 'gitlab',
};

// 实体归一化：小写 + 别名映射
function normalizeEntity(entity) {
  if (!entity) return '';
  const key = String(entity).toLowerCase().trim();
  return ENTITY_ALIASES[key] || key;
}

// 批量归一化实体列表
function normalizeEntities(entities) {
  if (!entities || !Array.isArray(entities)) return [];
  return entities.map(e => normalizeEntity(e));
}

// Jaccard 集合相似度
function jaccardSimilarity(setA, setB) {
  if (!setA || !setB || setA.size === 0 || setB.size === 0) return 0;
  let intersection = 0;
  for (const x of setA) {
    if (setB.has(x)) intersection++;
  }
  const union = setA.size + setB.size - intersection;
  return union > 0 ? intersection / union : 0;
}

// ============ 向量索引（内存） ============

// 从 state.points 构建向量索引（启动时调用）
function loadVectorIndex() {
  state.vectorIndex = state.points.map(p => ({
    pointId: p.pointId,
    vector: p.vector,
    docId: p.docId,
  }));
}

// 重建 pointMap
function rebuildPointMap() {
  state.pointMap = new Map(state.points.map(p => [p.pointId, p]));
}

// 新增知识点时同步写入向量索引与 pointMap
function addToVectorIndex(point) {
  state.vectorIndex.push({ pointId: point.pointId, vector: point.vector, docId: point.docId });
  state.pointMap.set(point.pointId, point);
}

// 知识点内部去重（向量相似度 > 阈值视为重复，保留靠前的）
function dedupePoints(points) {
  const result = [];
  for (const p of points) {
    if (!p.description || !p.description.trim()) continue;
    let isDup = false;
    for (const r of result) {
      if (cosineSimilarity(p.vector, r.vector) > DEDUP_SIMILARITY) {
        isDup = true;
        break;
      }
    }
    if (!isDup) result.push(p);
  }
  return result;
}

// ============ 多路召回 ============

// 路径1：向量 KNN Top N（在指定候选池内）
function vectorKNN(point, candidatePoints, k = KNN_TOP_N) {
  if (!point.vector) return [];
  return candidatePoints
    .filter(p => p.pointId !== point.pointId)
    .map(p => ({
      pointId: p.pointId,
      docId: p.docId,
      description: p.description,
      keywords: p.keywords || [],
      entities: p.entities || [],
      type: p.type || 'concept',
      vector: p.vector,
      vectorScore: cosineSimilarity(point.vector, p.vector),
      sources: ['vector'],
    }))
    .filter(p => p.vectorScore > 0.01)
    .sort((a, b) => b.vectorScore - a.vectorScore)
    .slice(0, k);
}

// 路径2：实体共现召回（使用归一化实体匹配）
function entityRecall(point, candidatePoints) {
  if (!point.entities || point.entities.length === 0) return [];
  const pointEntities = new Set(normalizeEntities(point.entities));
  return candidatePoints
    .filter(p => p.pointId !== point.pointId)
    .filter(p => p.entities && normalizeEntities(p.entities).some(e => pointEntities.has(e)))
    .map(p => ({
      pointId: p.pointId,
      docId: p.docId,
      description: p.description,
      keywords: p.keywords || [],
      entities: p.entities || [],
      type: p.type || 'concept',
      vector: p.vector,
      entityScore: jaccardSimilarity(pointEntities, new Set(normalizeEntities(p.entities))),
      sources: ['entity'],
    }));
}

// 路径3：关键词重叠召回
function keywordRecall(point, candidatePoints) {
  if (!point.keywords || point.keywords.length === 0) return [];
  const pointKeywords = new Set(point.keywords.map(k => String(k).toLowerCase()));
  return candidatePoints
    .filter(p => p.pointId !== point.pointId)
    .filter(p => p.keywords && p.keywords.some(k => pointKeywords.has(String(k).toLowerCase())))
    .map(p => ({
      pointId: p.pointId,
      docId: p.docId,
      description: p.description,
      keywords: p.keywords || [],
      entities: p.entities || [],
      type: p.type || 'concept',
      vector: p.vector,
      keywordScore: jaccardSimilarity(pointKeywords, new Set((p.keywords || []).map(k => String(k).toLowerCase()))),
      sources: ['keyword'],
    }));
}

// 多路召回：合并候选、去重、补全分数（仅扩大候选池，不做严格过滤）
function multiPathRecall(point, candidatePoints) {
  const vecC = vectorKNN(point, candidatePoints);
  const entC = entityRecall(point, candidatePoints);
  const kwC = keywordRecall(point, candidatePoints);

  const merged = new Map();
  for (const c of [...vecC, ...entC, ...kwC]) {
    if (merged.has(c.pointId)) {
      const ex = merged.get(c.pointId);
      if (c.vectorScore !== undefined) ex.vectorScore = c.vectorScore;
      if (c.entityScore !== undefined) ex.entityScore = c.entityScore;
      if (c.keywordScore !== undefined) ex.keywordScore = c.keywordScore;
      ex.sources = [...new Set([...ex.sources, ...c.sources])];
    } else {
      merged.set(c.pointId, { ...c });
    }
  }

  // 补全缺失分数为 0，向量缺失则即时计算
  for (const c of merged.values()) {
    if (c.vectorScore === undefined) {
      c.vectorScore = point.vector && c.vector ? cosineSimilarity(point.vector, c.vector) : 0;
    }
    if (c.entityScore === undefined) c.entityScore = 0;
    if (c.keywordScore === undefined) c.keywordScore = 0;
  }

  return Array.from(merged.values());
}

// ============ LLM 裁判 ============
// 返回 { score, relationType } 或 null
async function llmJudge(pointA, pointB) {
  if (!state.settings.llmApiKey) return null;

  const prompt = `判断以下两个知识点是否存在语义关联，并给出关系类型与置信度。

知识点A: ${pointA.description}
关键词: ${(pointA.keywords || []).join(', ')}
类型: ${pointA.type || 'concept'}

知识点B: ${pointB.description}
关键词: ${(pointB.keywords || []).join(', ')}
类型: ${pointB.type || 'concept'}

关系类型取值：related(相关)、similar(相似)、prerequisite(A是B的前置知识)、derivative(B是A的衍生)
只输出 JSON: {"related": true/false, "confidence": 0.0-1.0, "relationType": "related|similar|prerequisite|derivative"}`;

  try {
    const response = await fetch(state.settings.llmApiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${state.settings.llmApiKey}`,
      },
      body: JSON.stringify({
        model: state.settings.llmModel,
        messages: [{ role: 'user', content: prompt }],
        temperature: 0.2,
      }),
    });
    if (!response.ok) return null;
    const data = await response.json();
    const content = data.choices[0].message.content;
    const jsonMatch = content.match(/\{[\s\S]*\}/);
    if (!jsonMatch) return null;
    const result = JSON.parse(jsonMatch[0]);
    const relationType = RELATION_TYPES.includes(result.relationType) ? result.relationType : 'related';
    return {
      valid: result.related !== false,
      score: result.related ? (Number(result.confidence) || 0.5) : 0,
      relationType,
    };
  } catch (e) {
    return null;
  }
}

// 无 LLM 时根据分数猜测关系类型
function guessRelationType(c) {
  if (c.vectorScore >= 0.85) return 'similar';
  return 'related';
}

// ============ 校验流水线 ============
// 基础规则 → 向量复核 → 加权融合(向量相似度 + 关键词重合 + 实体共现) → 阈值过滤 → LLM校验(可选)
// 参考 Obsidian/Logseq：语义相近但文字不同的知识点也能建立连接
async function validateCandidates(candidates, pointA) {
  const threshold = state.settings.threshold;

  // 1. 基础规则：去自环、去重复候选
  const seen = new Set();
  const unique = [];
  for (const c of candidates) {
    if (!c.pointId || c.pointId === pointA.pointId) continue;
    const key = edgePairKey(pointA.pointId, c.pointId);
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(c);
  }

  // 2. 向量复核：确保 vectorScore 有值（transformers.js 语义向量）
  for (const c of unique) {
    if (c.vectorScore === undefined || c.vectorScore === 0) {
      c.vectorScore = pointA.vector && c.vector ? cosineSimilarity(pointA.vector, c.vector) : 0;
    }
    if (c.entityScore === undefined) c.entityScore = 0;
    if (c.keywordScore === undefined) c.keywordScore = 0;
  }

  // 3. 加权融合分数：向量语义相似度(主) + 关键词重合(辅) + 实体共现(辅) + 本体推理(可配置)
  // 参考 Obsidian: 语义相近 > 关键词精确匹配；领域本体提供常识级关联补充
  const W_VECTOR = 0.6;    // 向量余弦相似度（语义层）
  const W_KEYWORD = 0.25;   // 关键词 Jaccard 重合（精确匹配层）
  const W_ENTITY = 0.15;    // 实体共现（实体归一化后匹配）
  const W_ONTO = state.settings.ontologyWeight || 0; // 本体推理权重，0=关闭

  for (const c of unique) {
    const ontoResult = ontologyMatch(pointA, c);
    c.ontologyScore = ontoResult.score;
    c.ontologyEvidence = ontoResult.evidence;  // 证据链 [{type, from, to, source_text, source_file, score}]
    // 本体权重为 0 或无本体命中时，使用原始公式（向后兼容）
    const baseScore = W_VECTOR * c.vectorScore + W_KEYWORD * c.keywordScore + W_ENTITY * c.entityScore;
    if (W_ONTO > 0 && c.ontologyScore > 0) {
      const totalW = W_VECTOR + W_KEYWORD + W_ENTITY + W_ONTO;
      c.fusedScore = (baseScore + W_ONTO * c.ontologyScore) / totalW;
    } else {
      c.fusedScore = baseScore;
    }
    c.fusedScore = Math.round(c.fusedScore * 1000) / 1000;
    // 关联来源标记：private 私有文档推导 / ontology 知识库推导 / mixed 混合
    if (c.ontologyScore <= 0) {
      c.sourceType = 'private';
    } else if (baseScore < threshold && c.fusedScore >= threshold) {
      // 无本体则低于阈值、有本体则达标 → 知识库推理起决定作用
      c.sourceType = 'ontology';
    } else {
      c.sourceType = 'mixed';
    }
  }

  // 4. 阈值过滤：总分低于阈值不生成连线
  for (const c of unique) {
    if (c.fusedScore >= HIGH_SCORE_THRESHOLD) {
      // 高分直接放行
      c.needsLLM = false;
      c.isRender = true;
      c.relationType = 'similar';
      c.validationStatus = 'validated';
    } else if (c.fusedScore >= threshold) {
      // 中段：满足阈值，标记为可选 LLM 校验
      c.needsLLM = state.settings.llmApiKey ? true : false;
      c.isRender = true;
      c.relationType = 'related';
      c.validationStatus = 'validated';
    } else if (c.fusedScore >= LOW_SCORE_THRESHOLD) {
      // 低-中段：不满足阈值，但有 LLM 时可尝试校验
      c.needsLLM = state.settings.llmApiKey ? true : false;
      c.isRender = false;
      c.validationStatus = 'rejected';
    } else {
      // 极低分直接拒绝
      c.needsLLM = false;
      c.isRender = false;
      c.validationStatus = 'rejected';
    }
  }

  // 5. LLM 裁判：仅对模糊区间候选（可选，无 LLM 则跳过）
  const fuzzyCandidates = unique.filter(c => c.needsLLM);
  if (fuzzyCandidates.length > 0 && state.settings.llmApiKey) {
    showProgress('LLM 裁判校验中...', `校验 ${fuzzyCandidates.length} 个候选`);
    for (const c of fuzzyCandidates) {
      const result = await llmJudge(pointA, c);
      if (result) {
        c.llmScore = result.score;
        c.relationType = result.relationType;
        // LLM 判定有效 + 高置信度 → 放行
        c.isRender = result.valid !== false && result.score >= 0.5;
      }
      c.validationStatus = c.isRender ? 'validated' : 'rejected';
    }
  }

  // 6. 计算 final_weight = 融合分数（LLM 开启时加权）
  for (const c of unique) {
    let weight;
    if (c.llmScore !== undefined) {
      weight = 0.4 * c.fusedScore + 0.6 * c.llmScore;
    } else {
      weight = c.fusedScore;
    }
    c.final_weight = Math.round(weight * 1000) / 1000;
    if (!c.relationType) c.relationType = guessRelationType(c);
    if (!c.validationStatus) c.validationStatus = c.isRender ? 'validated' : 'rejected';
  }

  return unique;
}

// 构造边对象（保存关联得分 + 关联依据）
function buildEdgeObject(fromPointId, candidate) {
  // 计算重合关键词列表（用于 tooltip 展示关联依据）
  const fromPoint = getPointMeta(fromPointId);
  let overlapKeywords = [];
  if (fromPoint && candidate.keywords) {
    const fromKw = new Set((fromPoint.keywords || []).map(k => String(k).toLowerCase()));
    overlapKeywords = candidate.keywords.filter(k => fromKw.has(String(k).toLowerCase()));
  }
  // 计算重合实体列表（归一化后匹配）
  let overlapEntities = [];
  if (fromPoint && candidate.entities) {
    const fromEnt = new Set(normalizeEntities(fromPoint.entities || []));
    overlapEntities = normalizeEntities(candidate.entities).filter(e => fromEnt.has(e));
    overlapEntities = [...new Set(overlapEntities)]; // 去重
  }

  return {
    from: fromPointId,
    to: candidate.pointId,
    strength: candidate.final_weight,
    relationType: candidate.relationType || 'related',
    validationStatus: candidate.validationStatus || (candidate.isRender ? 'validated' : 'rejected'),
    isRender: candidate.isRender,
    source: (candidate.sources || []).join('+'),
    vectorScore: Math.round((candidate.vectorScore || 0) * 1000) / 1000,
    entityScore: Math.round((candidate.entityScore || 0) * 1000) / 1000,
    keywordScore: Math.round((candidate.keywordScore || 0) * 1000) / 1000,
    fusedScore: candidate.fusedScore || 0,
    ontologyScore: Math.round((candidate.ontologyScore || 0) * 1000) / 1000,
    sourceType: candidate.sourceType || 'private',
    ontologyEvidence: (candidate.ontologyEvidence || []).slice(0, 3),
    llmScore: candidate.llmScore !== undefined ? Math.round(candidate.llmScore * 1000) / 1000 : undefined,
    overlapKeywords: overlapKeywords,
    overlapEntities: overlapEntities,
    createdAt: now(),
  };
}

// ============ 候选过滤与限流 ============

// 丢弃同文件内部配对，只保留跨文件配对
// 候选需携带 sourceDocId 与目标 docId（targetDocId 或 docId）
function filterSameDocPair(candidatePairs) {
  return candidatePairs.filter(c => {
    const sourceDoc = c.sourceDocId;
    const targetDoc = c.targetDocId || c.docId;
    if (!sourceDoc || !targetDoc) return true; // 缺少文档信息时不丢弃，保守保留
    return sourceDoc !== targetDoc;
  });
}

// 去重与去自环：候选需携带 sourcePointId 与目标 pointId（targetPointId 或 pointId）
function dedupeAndRemoveSelfLoop(candidatePairs) {
  const seen = new Set();
  const result = [];
  for (const c of candidatePairs) {
    const src = c.sourcePointId;
    const tgt = c.targetPointId || c.pointId;
    if (!src || !tgt) continue;
    if (src === tgt) continue; // 自环
    const key = edgePairKey(src, tgt);
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(c);
  }
  return result;
}

// 每个知识点最多保留 maxNum 个候选对，按 vectorScore 降序取前 N
function limitMaxCandidatePerKp(candidatePairs, maxNum) {
  const bySource = new Map();
  for (const c of candidatePairs) {
    const src = c.sourcePointId || c.pointId;
    if (!src) continue;
    if (!bySource.has(src)) bySource.set(src, []);
    bySource.get(src).push(c);
  }
  const result = [];
  for (const list of bySource.values()) {
    list.sort((a, b) => (b.vectorScore || 0) - (a.vectorScore || 0));
    result.push(...list.slice(0, maxNum));
  }
  return result;
}

// 将数组按 batchSize 分片
function splitToBatches(arr, batchSize) {
  const batches = [];
  const size = Math.max(1, batchSize | 0);
  for (let i = 0; i < arr.length; i += size) {
    batches.push(arr.slice(i, i + size));
  }
  return batches;
}

// ============ 边构建（召回 + 校验 + 写入） ============

// 单文件：每条新知识点对全库做全局召回（覆盖所有已存在知识点）
// 写入 Kp_Edge 后异步聚合重算 Doc_Edge（不阻塞）
async function buildEdgesGlobal(newPointIds) {
  const seenPairs = new Set();
  // 候选池 = 全库知识点（state.points 已包含新增）
  const candidatePool = state.points;
  const affectedDocIds = new Set();

  for (const pointId of newPointIds) {
    const point = getPointMeta(pointId);
    if (!point) continue;
    affectedDocIds.add(point.docId);

    // 召回
    let candidates = multiPathRecall(point, candidatePool);
    // 标注 source 信息，供过滤函数使用
    candidates.forEach(c => { c.sourcePointId = point.pointId; c.sourceDocId = point.docId; });
    // 1. 丢弃同文件配对
    candidates = filterSameDocPair(candidates);
    // 2. 去重 + 去自环
    candidates = dedupeAndRemoveSelfLoop(candidates);
    // 3. 每知识点候选限流
    candidates = limitMaxCandidatePerKp(candidates, MAX_CANDIDATE_PER_KP);
    // 4. 校验流水线
    const validated = await validateCandidates(candidates, point);
    // 5. 写入 Kp_Edge
    for (const c of validated) {
      const key = edgePairKey(pointId, c.pointId);
      if (seenPairs.has(key)) continue;
      seenPairs.add(key);
      const edge = buildEdgeObject(pointId, c);
      await dbPutEdge(edge);
      state.edges.push(edge);
      // 收集受影响文档（目标端）
      const toDoc = getPointDocId(c.pointId);
      if (toDoc) affectedDocIds.add(toDoc);
    }
  }

  // 6. 异步重算 Doc_Edge（不阻塞前端），完成后刷新图谱
  const affected = Array.from(affectedDocIds);
  if (affected.length > 0) {
    setTimeout(() => {
      recomputeDocEdge(affected)
        .then(() => renderGraph())
        .catch(e => console.error('recomputeDocEdge 失败:', e));
    }, 0);
  }
}

// 批量上传：仅对本批新增知识点内部执行召回（不触发全库历史旧数据）
async function buildEdgesInternal(newPointIds) {
  const newSet = new Set(newPointIds);
  const candidatePool = state.points.filter(p => newSet.has(p.pointId));
  const seenPairs = new Set();
  const affectedDocIds = new Set();

  for (const pointId of newPointIds) {
    const point = getPointMeta(pointId);
    if (!point) continue;
    affectedDocIds.add(point.docId);

    let candidates = multiPathRecall(point, candidatePool);
    candidates.forEach(c => { c.sourcePointId = point.pointId; c.sourceDocId = point.docId; });
    candidates = filterSameDocPair(candidates);
    candidates = dedupeAndRemoveSelfLoop(candidates);
    candidates = limitMaxCandidatePerKp(candidates, MAX_CANDIDATE_PER_KP);
    const validated = await validateCandidates(candidates, point);
    for (const c of validated) {
      const key = edgePairKey(pointId, c.pointId);
      if (seenPairs.has(key)) continue;
      seenPairs.add(key);
      const edge = buildEdgeObject(pointId, c);
      await dbPutEdge(edge);
      state.edges.push(edge);
      const toDoc = getPointDocId(c.pointId);
      if (toDoc) affectedDocIds.add(toDoc);
    }
  }

  // 异步重算 Doc_Edge，完成后刷新图谱
  const affected = Array.from(affectedDocIds);
  if (affected.length > 0) {
    setTimeout(() => {
      recomputeDocEdge(affected)
        .then(() => renderGraph())
        .catch(e => console.error('recomputeDocEdge 失败:', e));
    }, 0);
  }
}

// 局部重建：仅重建选中文档所有知识点之间的关联
async function rebuildEdgesForDocs(docIds) {
  const docIdSet = new Set(docIds);
  const selectedPointIds = state.points
    .filter(p => docIdSet.has(p.docId))
    .map(p => p.pointId);

  if (selectedPointIds.length === 0) {
    toast('所选文档没有知识点', 'warning');
    return 0;
  }

  // 清除两端均属于所选文档的旧边
  const toRemove = [];
  for (const e of state.edges) {
    const fromDoc = getPointDocId(e.from);
    const toDoc = getPointDocId(e.to);
    if (docIdSet.has(fromDoc) && docIdSet.has(toDoc)) toRemove.push(e);
  }
  for (const e of toRemove) {
    if (e.edgeId !== undefined) await dbDeleteEdge(e.edgeId);
  }
  state.edges = state.edges.filter(e => !toRemove.includes(e));

  // 召回池仅限所选文档的知识点
  const candidatePool = state.points.filter(p => docIdSet.has(p.docId));
  const seenPairs = new Set();

  for (const pointId of selectedPointIds) {
    const point = getPointMeta(pointId);
    if (!point) continue;
    let candidates = multiPathRecall(point, candidatePool);
    candidates.forEach(c => { c.sourcePointId = point.pointId; c.sourceDocId = point.docId; });
    candidates = filterSameDocPair(candidates);
    candidates = dedupeAndRemoveSelfLoop(candidates);
    candidates = limitMaxCandidatePerKp(candidates, MAX_CANDIDATE_PER_KP);
    const validated = await validateCandidates(candidates, point);
    for (const c of validated) {
      const key = edgePairKey(pointId, c.pointId);
      if (seenPairs.has(key)) continue;
      seenPairs.add(key);
      const edge = buildEdgeObject(pointId, c);
      await dbPutEdge(edge);
      state.edges.push(edge);
    }
  }

  // 局部重建后重算受影响文档的 Doc_Edge
  await recomputeDocEdge(docIds);

  return selectedPointIds.length;
}

// 全局完整重建：手动触发，后台异步对全部知识点执行召回+校验（非阻塞前端）
async function rebuildAllEdges() {
  if (state.points.length === 0) {
    toast('没有知识点，无法重建', 'warning');
    return;
  }
  if (state.isRebuilding) {
    toast('全局重建正在进行中，请稍候', 'info');
    return;
  }
  if (!confirm(`确定全局完整重建关联？\n将清除 ${state.edges.length} 条现有知识点边，对全部 ${state.points.length} 个知识点分片执行召回+校验。\n后台异步执行，不阻塞前端。`)) {
    return;
  }

  state.isRebuilding = true;
  toast('开始后台全局重建...', 'info');

  try {
    // 1. 清除所有 Kp_Edge
    await dbClearEdges();
    state.edges = [];

    const candidatePool = state.points;
    const seenPairs = new Set();

    // 2. 分片处理
    const batches = splitToBatches(state.points, BATCH_SIZE);
    let processed = 0;
    for (let bi = 0; bi < batches.length; bi++) {
      const batch = batches[bi];
      for (const point of batch) {
        processed++;
        // 召回
        let candidates = multiPathRecall(point, candidatePool);
        candidates.forEach(c => { c.sourcePointId = point.pointId; c.sourceDocId = point.docId; });
        // 过滤
        candidates = filterSameDocPair(candidates);
        candidates = dedupeAndRemoveSelfLoop(candidates);
        candidates = limitMaxCandidatePerKp(candidates, MAX_CANDIDATE_PER_KP);
        // 校验
        const validated = await validateCandidates(candidates, point);
        // 写入 Kp_Edge
        for (const c of validated) {
          const key = edgePairKey(point.pointId, c.pointId);
          if (seenPairs.has(key)) continue;
          seenPairs.add(key);
          const edge = buildEdgeObject(point.pointId, c);
          await dbPutEdge(edge);
          state.edges.push(edge);
        }
      }
      // 每批结束后更新进度并让出 UI
      $('#rebuild-status').textContent = `重建中 批次 ${bi + 1}/${batches.length} (${processed}/${state.points.length})`;
      await new Promise(r => setTimeout(r, 0));
    }

    // 3. 重算全部 Doc_Edge
    $('#rebuild-status').textContent = '重算文档关联...';
    await recomputeAllDocEdge();

    toast(`全局重建完成，共 ${state.edges.length} 条知识点边，${state.docEdges.length} 条文档边`, 'success', 3000);
  } catch (e) {
    console.error('全局重建失败:', e);
    toast('全局重建出错: ' + e.message, 'error', 4000);
  } finally {
    state.isRebuilding = false;
    $('#rebuild-status').textContent = '';
    renderGraph();
  }
}

// 文件更新处理：清除该文档原有全部关联边与知识点，重新走完整召回校验（全局）
async function handleFileUpdate(docId, text, fileName) {
  // 清除该文档全部 Kp_Edge
  await dbDeleteEdgesByDoc(docId);
  state.edges = state.edges.filter(e => {
    const fromDoc = getPointDocId(e.from);
    const toDoc = getPointDocId(e.to);
    return fromDoc !== docId && toDoc !== docId;
  });

  // 清除该文档全部 Doc_Edge
  await dbDeleteDocEdgesByDoc(docId);
  state.docEdges = state.docEdges.filter(de => de.doc_a_id !== docId && de.doc_b_id !== docId);

  // 清除该文档全部旧知识点
  const oldPoints = state.points.filter(p => p.docId === docId);
  for (const p of oldPoints) {
    await dbDeletePoint(p.pointId);
  }
  state.points = state.points.filter(p => p.docId !== docId);
  state.vectorIndex = state.vectorIndex.filter(v => v.docId !== docId);
  rebuildPointMap();

  // 重新抽取 + 全局召回（buildEdgesGlobal 内部会异步重算 Doc_Edge）
  const result = await extractAndStorePoints(text, fileName, docId);
  if (!result) return false;
  await buildEdgesGlobal(result.newPointIds);
  return true;
}

// ============ Doc_Edge 聚合计算 ============

// 聚合计算受影响文档的 Doc_Edge
// 获取受影响文档之间全部有效(is_valid/isRender=true)跨文件 Kp_Edge
// 按 (doc_a, doc_b) 分组，pair_count=边数，sum_weight=权重之和
// norm_weight = sum_weight / sqrt(count_a * count_b)
// pair_count >= MIN_VALID_KP_PAIR: upsert；否则删除该 Doc_Edge
async function recomputeDocEdge(affectedDocIds) {
  const docIdSet = new Set(affectedDocIds);
  if (docIdSet.size === 0) return;

  // 各文档知识点数（缓存）
  const docKpCount = new Map();
  const countKp = (docId) => {
    if (!docKpCount.has(docId)) {
      docKpCount.set(docId, state.points.filter(p => p.docId === docId).length);
    }
    return docKpCount.get(docId);
  };

  // 受影响文档相关的现有 Doc_Edge（用于发现需删除的边）
  const existing = await dbGetDocEdgeByDocId(affectedDocIds);
  const existingByKey = new Map();
  for (const de of existing) {
    existingByKey.set(edgePairKey(de.doc_a_id, de.doc_b_id), de);
  }

  // 收集受影响的有效跨文件 Kp_Edge（至少一端受影响）
  const validEdges = state.edges.filter(e => {
    if (!e.isRender) return false; // is_valid
    const fromDoc = getPointDocId(e.from);
    const toDoc = getPointDocId(e.to);
    if (!fromDoc || !toDoc || fromDoc === toDoc) return false; // 跨文件
    return docIdSet.has(fromDoc) || docIdSet.has(toDoc);
  });

  // 按 (doc_a, doc_b) 分组
  const groups = new Map();
  for (const e of validEdges) {
    const fromDoc = getPointDocId(e.from);
    const toDoc = getPointDocId(e.to);
    const key = edgePairKey(fromDoc, toDoc);
    if (!groups.has(key)) groups.set(key, { doc_a: fromDoc, doc_b: toDoc, edges: [] });
    groups.get(key).edges.push(e);
  }

  const handledKeys = new Set();
  for (const g of groups.values()) {
    const count_a = countKp(g.doc_a);
    const count_b = countKp(g.doc_b);
    const pair_count = g.edges.length;
    const sum_weight = g.edges.reduce((s, e) => s + (e.strength || 0), 0);
    const norm_weight = count_a > 0 && count_b > 0
      ? sum_weight / Math.sqrt(count_a * count_b)
      : 0;
    const key = edgePairKey(g.doc_a, g.doc_b);
    handledKeys.add(key);

    if (pair_count >= MIN_VALID_KP_PAIR) {
      // 聚合关联依据 + 来源标记（共用函数）
      const breakdown = computeDocEdgeBreakdown(g.edges, pair_count);
      await dbUpsertDocEdge(g.doc_a, g.doc_b, norm_weight, pair_count, breakdown);
    } else {
      // pair_count 不足，删除现有边
      const ex = existingByKey.get(key);
      if (ex && ex.id !== undefined) await dbDeleteDocEdge(ex.id);
    }
  }

  // 受影响但现在不在 groups 中的现有 Doc_Edge → 删除（已无有效 Kp_Edge 支撑）
  for (const [key, de] of existingByKey) {
    if (!handledKeys.has(key) && de.id !== undefined) {
      await dbDeleteDocEdge(de.id);
    }
  }

  // 刷新内存中的 docEdges
  state.docEdges = await dbGetAllDocEdges();
}

// 对所有文档重新计算 Doc_Edge（先清空再聚合重建）
async function recomputeAllDocEdge() {
  await dbClearDocEdges();
  state.docEdges = [];

  const docKpCount = new Map();
  const countKp = (docId) => {
    if (!docKpCount.has(docId)) {
      docKpCount.set(docId, state.points.filter(p => p.docId === docId).length);
    }
    return docKpCount.get(docId);
  };

  // 全部有效跨文件 Kp_Edge
  const validEdges = state.edges.filter(e => {
    if (!e.isRender) return false;
    const fromDoc = getPointDocId(e.from);
    const toDoc = getPointDocId(e.to);
    return fromDoc && toDoc && fromDoc !== toDoc;
  });

  const groups = new Map();
  for (const e of validEdges) {
    const fromDoc = getPointDocId(e.from);
    const toDoc = getPointDocId(e.to);
    const key = edgePairKey(fromDoc, toDoc);
    if (!groups.has(key)) groups.set(key, { doc_a: fromDoc, doc_b: toDoc, edges: [] });
    groups.get(key).edges.push(e);
  }

  for (const g of groups.values()) {
    const count_a = countKp(g.doc_a);
    const count_b = countKp(g.doc_b);
    const pair_count = g.edges.length;
    const sum_weight = g.edges.reduce((s, e) => s + (e.strength || 0), 0);
    const norm_weight = count_a > 0 && count_b > 0
      ? sum_weight / Math.sqrt(count_a * count_b)
      : 0;
    if (pair_count >= MIN_VALID_KP_PAIR) {
      const breakdown = computeDocEdgeBreakdown(g.edges, pair_count);
      await dbUpsertDocEdge(g.doc_a, g.doc_b, norm_weight, pair_count, breakdown);
    }
  }

  state.docEdges = await dbGetAllDocEdges();
}

// 聚合一组 Kp_Edge 的关联依据 + 来源标记（recomputeDocEdge / recomputeAllDocEdge 共用）
function computeDocEdgeBreakdown(edges, pairCount) {
  const avgVec = edges.reduce((s, e) => s + (e.vectorScore || 0), 0) / pairCount;
  const avgKw = edges.reduce((s, e) => s + (e.keywordScore || 0), 0) / pairCount;
  const avgFused = edges.reduce((s, e) => s + (e.fusedScore || 0), 0) / pairCount;
  const avgOnto = edges.reduce((s, e) => s + (e.ontologyScore || 0), 0) / pairCount;
  const kwSet = new Set();
  const entSet = new Set();
  for (const e of edges) {
    (e.overlapKeywords || []).forEach(k => kwSet.add(k));
    (e.overlapEntities || []).forEach(en => entSet.add(en));
  }
  const privateCount = edges.filter(e => (e.ontologyScore || 0) === 0).length;
  const ontoCount = pairCount - privateCount;
  let sourceType;
  if (privateCount >= MIN_VALID_KP_PAIR) {
    sourceType = ontoCount > 0 ? 'mixed' : 'private';
  } else {
    sourceType = 'ontology';
  }
  // 汇总最佳本体证据（按分数排序取前 2 条，附带 source_text 原文）
  const allEvidence = [];
  for (const e of edges) {
    for (const ev of (e.ontologyEvidence || [])) {
      allEvidence.push(ev);
    }
  }
  const bestEvidence = allEvidence
    .sort((a, b) => (b.score || 0) - (a.score || 0))
    .slice(0, 2);
  const topPairs = edges
    .map(e => ({
      from: e.from, to: e.to,
      score: e.fusedScore || e.strength || 0,
      vectorScore: e.vectorScore || 0,
      keywordScore: e.keywordScore || 0,
      ontologyScore: e.ontologyScore || 0,
      sourceType: e.sourceType || 'private',
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);
  return {
    avgVectorScore: Math.round(avgVec * 1000) / 1000,
    avgKeywordScore: Math.round(avgKw * 1000) / 1000,
    avgFusedScore: Math.round(avgFused * 1000) / 1000,
    overlapKeywords: Array.from(kwSet),
    overlapEntities: Array.from(entSet),
    topPairs: topPairs,
    sourceType: sourceType,
    ontologyPairCount: ontoCount,
    privatePairCount: privateCount,
    avgOntologyScore: Math.round(avgOnto * 1000) / 1000,
    ontologyEvidence: bestEvidence,
  };
}

// 获取文档详情 DocDetailVO
// { doc_info, kp_list, related_doc_list, cross_kp_edges }
async function getDocumentDetail(docId) {
  const doc = state.docs.find(d => d.docId === docId) || null;
  const kp_list = state.points.filter(p => p.docId === docId);

  // 关联文档列表：该文档的 Doc_Edge
  const related_doc_list = state.docEdges
    .filter(de => de.doc_a_id === docId || de.doc_b_id === docId)
    .map(de => {
      const otherDocId = de.doc_a_id === docId ? de.doc_b_id : de.doc_a_id;
      const otherDoc = state.docs.find(d => d.docId === otherDocId);
      return {
        id: de.id,
        other_doc_id: otherDocId,
        other_doc_title: otherDoc ? otherDoc.title : '未知文档',
        other_doc_filename: otherDoc ? otherDoc.filename : '',
        doc_relation_weight: de.doc_relation_weight,
        valid_kp_pair_count: de.valid_kp_pair_count,
      };
    });

  // 跨文件 Kp_Edge：与该文档相关的全部跨文件知识点边（含有效/无效）
  const cross_kp_edges = state.edges
    .filter(e => {
      const fromDoc = getPointDocId(e.from);
      const toDoc = getPointDocId(e.to);
      if (fromDoc === toDoc) return false; // 跨文件
      return fromDoc === docId || toDoc === docId;
    })
    .map(e => {
      const fromP = getPointMeta(e.from);
      const toP = getPointMeta(e.to);
      return {
        edgeId: e.edgeId,
        from_point_id: e.from,
        to_point_id: e.to,
        from_desc: fromP ? fromP.description : '',
        to_desc: toP ? toP.description : '',
        weight: e.strength,
        relation_type: e.relationType || 'related',
        is_valid: !!e.isRender,
      };
    });

  return { doc_info: doc, kp_list, related_doc_list, cross_kp_edges };
}

// ============ 文件解析与抽取核心 ============

// 抽取知识点并入库（写入 docs/points + 内存向量索引）
// 复用 existingDocId 时为文件更新场景，沿用原 docId
async function extractAndStorePoints(text, fileName, existingDocId) {
  showProgress('正在清洗文本...', fileName);
  const cleaned = cleanText(text);
  if (cleaned.length < 10) {
    toast(`文件「${fileName}」内容过短，已跳过`, 'warning');
    return null;
  }

  // 分片
  const chunks = chunkText(cleaned);
  showProgress('AI 正在抽取知识点...', `${chunks.length} 个分片`);

  let allPoints = [];
  let docTitle = '';
  let docSummary = '';
  for (let i = 0; i < chunks.length; i++) {
    const result = await callLLMExtract(chunks[i], i === 0);
    if (i === 0) {
      const meta = fallbackDocMeta(cleaned, fileName);
      docTitle = result.title || meta.title;
      docSummary = result.summary || meta.summary;
    }
    if (Array.isArray(result.points)) allPoints.push(...result.points);
  }
  if (!docTitle) {
    const meta = fallbackDocMeta(cleaned, fileName);
    docTitle = meta.title;
    docSummary = meta.summary;
  }

  // 规范化 + 过滤空内容
  allPoints = allPoints.map(normalizePoint).filter(p => p.description && p.description.trim());
  if (allPoints.length === 0) {
    toast(`文件「${fileName}」未提取到知识点`, 'warning');
    return null;
  }

  // 生成向量
  showProgress('正在生成语义向量...', `${allPoints.length} 个知识点`);
  for (const p of allPoints) {
    p.vector = await getEmbedding(p.description + ' ' + (p.keywords || []).join(' '));
  }

  // 去重（description 相似度 > 0.9 视为重复）
  allPoints = dedupePoints(allPoints);
  if (allPoints.length === 0) {
    toast(`文件「${fileName}」去重后无有效知识点`, 'warning');
    return null;
  }

  // 创建/更新文档
  const docId = existingDocId || docUid();
  const existingDocIdx = state.docs.findIndex(d => d.docId === docId);
  const doc = {
    docId,
    filename: fileName,
    title: docTitle,
    summary: docSummary,
    createdAt: existingDocIdx >= 0 ? state.docs[existingDocIdx].createdAt : now(),
  };
  await dbPutDoc(doc);
  if (existingDocIdx >= 0) {
    state.docs[existingDocIdx] = doc;
  } else {
    state.docs.push(doc);
  }

  // 写入知识点
  const newPointIds = [];
  for (const p of allPoints) {
    const pointId = uid();
    const point = {
      pointId,
      docId,
      description: p.description,
      keywords: p.keywords || [],
      entities: p.entities || [],
      type: p.type || 'concept',
      vector: p.vector,
      createdAt: now(),
    };
    await dbPutPoint(point);
    state.points.push(point);
    addToVectorIndex(point);
    newPointIds.push(pointId);
  }

  return { doc, newPointIds };
}

// 单文件处理：抽取 + 全局召回
async function processText(text, fileName) {
  try {
    const result = await extractAndStorePoints(text, fileName);
    if (!result) {
      hideProgress();
      return false;
    }
    showProgress('正在计算关联关系...', '全局召回 + 校验');
    await buildEdgesGlobal(result.newPointIds);
    hideProgress();
    renderGraph();
    renderDocFilter();
    updateCount();
    toast(`「${result.doc.title}」解析完成，抽取 ${result.newPointIds.length} 个知识点`, 'success');
    return true;
  } catch (e) {
    console.error('处理文件失败:', fileName, e);
    hideProgress();
    toast(`文件「${fileName}」处理失败: ${e.message}`, 'error', 4000);
    return false;
  }
}

// 浏览器模式：从 File 对象处理（单文件）
async function processFile(file) {
  showProgress('正在读取文件...', file.name);
  const text = await readFileAsText(file);
  return processText(text, file.name);
}

// 批量导入文本（内部召回）：items = [{content, name}]
async function importTextsBatch(items) {
  const allNewPointIds = [];
  let successCount = 0;
  for (let i = 0; i < items.length; i++) {
    const { content, name } = items[i];
    showProgress('正在处理文件...', `(${i + 1}/${items.length}) ${name}`);
    try {
      const result = await extractAndStorePoints(content, name);
      if (result) {
        successCount++;
        allNewPointIds.push(...result.newPointIds);
      }
    } catch (e) {
      console.error('处理失败:', name, e);
    }
  }

  // 批量上传：仅对本批新增知识点内部执行召回
  if (allNewPointIds.length > 0) {
    showProgress('正在计算本批关联...', `${allNewPointIds.length} 个知识点内部召回`);
    await buildEdgesInternal(allNewPointIds);
  }

  hideProgress();
  renderGraph();
  renderDocFilter();
  updateCount();
  toast(`批量导入完成: ${successCount}/${items.length} 个文件`, 'success');
}

// 批量处理 File 对象（浏览器模式）
async function processFilesBatch(files) {
  const items = [];
  for (const f of files) {
    try {
      const content = await readFileAsText(f);
      items.push({ content, name: f.name });
    } catch (e) {
      console.error('读取失败:', f.name, e);
    }
  }
  await importTextsBatch(items);
}

// 统一入口：单文件→全局召回；多文件→内部召回
async function processFiles(files) {
  const fileArr = Array.from(files);
  if (fileArr.length === 0) return;
  const validFiles = fileArr.filter(isTextFile);
  const skipped = fileArr.length - validFiles.length;
  if (validFiles.length === 0) {
    toast('未找到可识别的文本文件', 'warning');
    return;
  }

  if (validFiles.length === 1) {
    // 单文件上传：全局召回
    await processFile(validFiles[0]);
  } else {
    // 批量上传：内部召回
    await processFilesBatch(validFiles);
  }

  renderGraph();
  if (skipped > 0) toast(`已跳过 ${skipped} 个非文本文件`, 'info');
}

// 判断文件是否为文本类型
function isTextFile(file) {
  const textExts = /\.(md|txt|markdown|text|json|yaml|yml|xml|csv|tsv|log|ini|conf|cfg|toml|env|sh|bash|zsh|fish|bat|ps1|py|js|ts|jsx|tsx|java|c|cpp|cc|h|hpp|cs|go|rs|rb|php|pl|swift|kt|scala|lua|sql|html|htm|css|scss|less|vue|svelte|r|dart|gradle|makefile|cmake|dockerfile)$/i;
  if (!file.name.includes('.')) return true;
  if (textExts.test(file.name)) return true;
  if (file.type && file.type.startsWith('text/')) return true;
  if (file.type && (file.type.includes('json') || file.type.includes('xml') || file.type.includes('yaml'))) return true;
  return false;
}

// ============ Electron 专属 ============

// 扫描文件夹并批量导入（批量→内部召回）
async function scanAndImportDirectory() {
  const dirPath = await window.electron.selectDirectory();
  if (!dirPath) {
    toast('未选择文件夹', 'info');
    return;
  }

  showProgress('正在扫描文件夹...', dirPath);
  const files = await window.electron.scanDirectory(dirPath);
  if (files.length === 0) {
    hideProgress();
    toast('该文件夹中未找到文本文件', 'warning');
    return;
  }

  toast(`找到 ${files.length} 个文本文件，开始导入...`, 'info');

  const items = [];
  for (const file of files) {
    try {
      const result = await window.electron.readFile(file.path);
      if (result.success) items.push({ content: result.content, name: file.name });
    } catch (e) {
      console.error('读取失败:', file.path, e);
    }
  }

  await importTextsBatch(items);
  toast(`扫描完成: 导入 ${items.length}/${files.length} 个文件`, 'success');
}

// 通过原生对话框选择文件并处理
async function selectAndOpenFiles() {
  const filePaths = await window.electron.selectFiles();
  if (filePaths.length === 0) return;

  if (filePaths.length === 1) {
    const filePath = filePaths[0];
    const fileName = filePath.split(/[\\/]/).pop();
    showProgress('正在读取文件...', fileName);
    const result = await window.electron.readFile(filePath);
    if (result.success) {
      await processText(result.content, fileName);
    } else {
      toast('读取失败: ' + result.error, 'error');
      hideProgress();
    }
  } else {
    const items = [];
    for (const filePath of filePaths) {
      const fileName = filePath.split(/[\\/]/).pop();
      try {
        const result = await window.electron.readFile(filePath);
        if (result.success) items.push({ content: result.content, name: fileName });
      } catch (e) {
        console.error('读取失败:', filePath, e);
      }
    }
    await importTextsBatch(items);
  }

  renderGraph();
}

// 监控文件夹
async function toggleWatch() {
  if (state.isWatching) {
    await window.electron.stopWatch();
    state.isWatching = false;
    state.watchDir = null;
    $('#btn-watch').classList.remove('btn-primary');
    toast('已停止监控文件夹', 'info');
    return;
  }

  const dirPath = await window.electron.selectDirectory();
  if (!dirPath) return;

  const ok = await window.electron.watchDirectory(dirPath);
  if (ok) {
    state.isWatching = true;
    state.watchDir = dirPath;
    $('#btn-watch').classList.add('btn-primary');
    toast(`正在监控: ${dirPath}`, 'success');
  } else {
    toast('监控失败', 'error');
  }
}

// ============ 删除 ============
async function deleteDoc(docId) {
  const doc = state.docs.find(d => d.docId === docId);
  if (!doc) return;
  if (!confirm(`确定删除文档「${doc.title}」及其全部知识点与关联？`)) return;

  // 先保存要删除的知识点 ID，用于后续过滤 edges
  const docPointIds = new Set(state.points.filter(p => p.docId === docId).map(p => p.pointId));

  // 1. IndexedDB 删除（即使失败也继续更新内存状态）
  try {
    await dbDeleteEdgesByDoc(docId);
    await dbDeleteDocEdgesByDoc(docId);
    for (const p of state.points.filter(p => p.docId === docId)) {
      await dbDeletePoint(p.pointId);
    }
    await dbDeleteDoc(docId);
  } catch (e) {
    console.error('IndexedDB 删除失败，继续更新内存状态:', e);
  }

  // 2. 显式 filter 移除对应 docId 的数据（响应式更新）
  state.docs = state.docs.filter(d => d.docId !== docId);
  state.points = state.points.filter(p => p.docId !== docId);
  state.edges = state.edges.filter(e => !docPointIds.has(e.from) && !docPointIds.has(e.to));
  state.docEdges = state.docEdges.filter(de => de.doc_a_id !== docId && de.doc_b_id !== docId);
  state.vectorIndex = state.vectorIndex.filter(v => v.docId !== docId);
  state.docFilter.delete(docId);
  if (state.selectedDocId === docId) state.selectedDocId = null;
  rebuildPointMap();

  if (state.selectedPointId && !getPointMeta(state.selectedPointId)) {
    state.selectedPointId = null;
  }

  // 3. 强制重新渲染图谱 + 文件列表（D3 exit().remove() 会清除多余 DOM）
  renderGraph();
  renderDocFilter();
  updateCount();
  toast('文档已删除', 'success');
}

// 删除单个知识点（及其关联边）
async function deletePoint(pointId) {
  const point = getPointMeta(pointId);
  const affectedDocId = point ? point.docId : null;

  // IndexedDB 删除（即使失败也继续更新内存状态）
  try {
    await dbDeleteEdgesByPoint(pointId);
    await dbDeletePoint(pointId);
  } catch (e) {
    console.error('IndexedDB 删除知识点失败，继续更新内存状态:', e);
  }

  // 显式 filter 移除对应数据（响应式更新）
  state.edges = state.edges.filter(e => e.from !== pointId && e.to !== pointId);
  state.points = state.points.filter(p => p.pointId !== pointId);
  state.vectorIndex = state.vectorIndex.filter(v => v.pointId !== pointId);
  state.pointMap.delete(pointId);

  if (state.selectedPointId === pointId) state.selectedPointId = null;

  renderGraph();
  updateCount();
  toast('知识点已删除', 'success');

  // 异步重算受影响文档的 Doc_Edge
  if (affectedDocId) {
    setTimeout(() => {
      recomputeDocEdge([affectedDocId])
        .then(() => renderGraph())
        .catch(e => console.error('recomputeDocEdge 失败:', e));
    }, 0);
  }
}

// ============ 文档筛选 ============
function toggleDocFilter(docId) {
  if (state.docFilter.has(docId)) {
    state.docFilter.delete(docId);
  } else {
    state.docFilter.add(docId);
  }
  // 若全部勾选或全部不勾选，视为显示全部
  if (state.docFilter.size === 0 || state.docFilter.size === state.docs.length) {
    state.docFilter.clear();
  }
  renderGraph();
}

// 全选/全不选
function toggleAllDocFilter() {
  if (state.docFilter.size === 0) {
    state.docs.forEach(d => state.docFilter.add(d.docId));
  } else {
    state.docFilter.clear();
  }
  renderDocFilter();
  renderGraph();
}

function renderDocFilter() {
  const container = $('#doc-filter-list');
  if (!container) return;
  if (state.docs.length === 0) {
    container.innerHTML = '<div class="doc-filter-empty">暂无文档</div>';
    return;
  }
  const showAll = state.docFilter.size === 0;
  container.innerHTML = state.docs.map(doc => {
    const checked = showAll || state.docFilter.has(doc.docId);
    const color = getDocColor(doc.docId);
    return `
      <label class="doc-filter-item">
        <input type="checkbox" data-doc-id="${escapeHtml(doc.docId)}" ${checked ? 'checked' : ''}>
        <span class="doc-color-dot" style="background:${color}"></span>
        <span class="doc-filter-name" title="${escapeHtml(doc.filename)}">${escapeHtml(truncate(doc.title, 16))}</span>
      </label>`;
  }).join('');

  $$('#doc-filter-list input[type=checkbox]').forEach(cb => {
    cb.onchange = (e) => {
      const docId = e.target.getAttribute('data-doc-id');
      toggleDocFilter(docId);
    };
  });
}

// ============ 局部重建弹窗 ============
function openRebuildModal() {
  if (state.docs.length === 0) {
    toast('没有文档，无法局部重建', 'warning');
    return;
  }
  const list = $('#rebuild-doc-list');
  list.innerHTML = state.docs.map(doc => {
    const color = getDocColor(doc.docId);
    return `
      <label class="doc-filter-item">
        <input type="checkbox" data-doc-id="${escapeHtml(doc.docId)}">
        <span class="doc-color-dot" style="background:${color}"></span>
        <span class="doc-filter-name" title="${escapeHtml(doc.filename)}">${escapeHtml(truncate(doc.title, 18))}</span>
      </label>`;
  }).join('');
  $('#rebuild-modal').classList.remove('hidden');
}

function closeRebuildModal() {
  $('#rebuild-modal').classList.add('hidden');
}

async function performLocalRebuild() {
  const selected = $$('#rebuild-doc-list input[type=checkbox]:checked').map(cb => cb.getAttribute('data-doc-id'));
  if (selected.length === 0) {
    toast('请至少选择一个文档', 'warning');
    return;
  }
  closeRebuildModal();
  showProgress('正在局部重建关联...', `所选 ${selected.length} 个文档`);
  try {
    const count = await rebuildEdgesForDocs(selected);
    hideProgress();
    renderGraph();
    toast(`局部重建完成（${count} 个知识点）`, 'success');
  } catch (e) {
    hideProgress();
    toast('局部重建失败: ' + e.message, 'error', 4000);
  }
}

// ============ D3 图谱渲染 ============
// 文件节点为图谱主节点，Doc_Edge 为连线
function buildGraphData() {
  const nodes = [];
  const edges = [];

  // 可见文档集合（无筛选=全部）
  const visibleDocs = state.docFilter.size === 0
    ? new Set(state.docs.map(d => d.docId))
    : state.docFilter;

  // 节点：每个文档一个节点
  for (const doc of state.docs) {
    if (!visibleDocs.has(doc.docId)) continue;
    const kpCount = state.points.filter(p => p.docId === doc.docId).length;
    nodes.push({
      id: doc.docId,
      type: 'doc',
      label: doc.title || doc.filename,
      filename: doc.filename || '',
      summary: doc.summary || '',
      kpCount,
      docId: doc.docId,
      color: getDocColor(doc.docId),
      selected: doc.docId === state.selectedDocId,
    });
  }

  // 边：Doc_Edge（全部为有效，写入时已满足 MIN_VALID_KP_PAIR）
  for (const de of state.docEdges) {
    if (!visibleDocs.has(de.doc_a_id) || !visibleDocs.has(de.doc_b_id)) continue;
    // 隐藏纯知识库推导的连线（开关开启时）
    if (state.hideOntologyEdges && (de.source_type || 'private') === 'ontology') continue;
    edges.push({
      source: de.doc_a_id,
      target: de.doc_b_id,
      type: 'doc_edge',
      score: de.doc_relation_weight || 0,
      pairCount: de.valid_kp_pair_count || 0,
      id: de.id,
      // 关联来源标记
      sourceType: de.source_type || 'private',
      ontologyPairCount: de.ontology_pair_count || 0,
      privatePairCount: de.private_pair_count || 0,
      avgOntologyScore: de.avg_ontology_score || 0,
      ontologyEvidence: de.ontology_evidence || [],
      // 关联依据明细（用于悬浮 tooltip 展示）
      avgVectorScore: de.avg_vector_score || 0,
      avgKeywordScore: de.avg_keyword_score || 0,
      avgFusedScore: de.avg_fused_score || 0,
      overlapKeywords: de.overlap_keywords || [],
      overlapEntities: de.overlap_entities || [],
      topPairs: de.top_pairs || [],
    });
  }

  return { nodes, edges };
}

function renderGraph() {
  const container = $('#canvas-container');

  // 没有文档时显示空状态
  if (state.docs.length === 0) {
    $('#empty-state').classList.remove('hidden');
    const existingSvg = container.querySelector('svg');
    if (existingSvg) existingSvg.remove();
    if (simulation) { simulation.stop(); simulation = null; }
    return;
  }
  $('#empty-state').classList.add('hidden');

  const { nodes, edges } = buildGraphData();
  const width = container.clientWidth;
  const height = container.clientHeight;

  // 节点半径函数
  const nodeRadius = d => {
    const base = 14;
    return d.selected ? base + 5 : base + Math.min(10, d.kpCount * 0.6);
  };

  // 获取或创建 SVG（不每次销毁重建，保留 zoom 状态）
  let svg = d3.select(container).select('svg');
  if (svg.empty()) {
    svg = d3.select(container).append('svg')
      .attr('width', '100%')
      .attr('height', '100%')
      .attr('viewBox', `0 0 ${width} ${height}`)
      .style('background', 'transparent');

    const g = svg.append('g').attr('class', 'graph-g');

    svgZoom = d3.zoom().scaleExtent([0.1, 5]).on('zoom', (event) => {
      g.attr('transform', event.transform);
    });
    svg.call(svgZoom);

    // 箭头标记（只创建一次）
    const defs = svg.append('defs');
    defs.append('marker')
      .attr('id', 'arrowhead')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 24)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#565f89');

    // 连线层容器
    g.append('g').attr('class', 'link-layer');
    // 节点层容器
    g.append('g').attr('class', 'node-layer');
  } else {
    svg.attr('viewBox', `0 0 ${width} ${height}`);
  }

  const g = svg.select('g.graph-g');

  // ====== 连线层：D3 通用更新模式 (enter/update/exit) ======
  const linkLayer = g.select('.link-layer');
  const linkData = linkLayer.selectAll('line').data(edges, d =>
    `${typeof d.source === 'object' ? d.source.id || d.source : d.source}_${typeof d.target === 'object' ? d.target.id || d.target : d.target}`
  );

  // EXIT: 删除多余连线 DOM
  linkData.exit().remove();

  // ENTER: 新连线
  const linkEnter = linkData.enter().append('line')
    .attr('class', 'graph-link doc-link')
    .attr('marker-end', 'url(#arrowhead)');

  // ENTER + UPDATE 合并
  const allLinks = linkEnter.merge(linkData)
    .attr('stroke-width', d => Math.max(1.5, d.score * 8))
    .attr('stroke-opacity', d => Math.max(0.25, Math.min(0.9, d.score * 1.2)))
    // 知识库推导的连线用虚线 + 琥珀色，混合连线半虚线，便于视觉区分来源
    .attr('stroke', d => {
      if (d.sourceType === 'ontology') return '#e0af68';
      if (d.sourceType === 'mixed') return '#ff9e64';
      return '#565f89';
    })
    .attr('stroke-dasharray', d => {
      if (d.sourceType === 'ontology') return '6 4';
      if (d.sourceType === 'mixed') return '10 3 2 3';
      return null;
    })
    .on('mouseover', (event, d) => {
      showEdgeTooltip(event, d);
      d3.select(event.target).attr('stroke-opacity', 0.95).attr('stroke-width', Math.max(3, d.score * 10));
    })
    .on('mousemove', (event) => updateTooltipPosition(event))
    .on('mouseout', (event, d) => {
      hideTooltip();
      d3.select(event.target).attr('stroke-opacity', Math.max(0.25, Math.min(0.9, d.score * 1.2))).attr('stroke-width', Math.max(1.5, d.score * 8));
    });

  // ====== 节点层：D3 通用更新模式 (enter/update/exit) ======
  const nodeLayer = g.select('.node-layer');
  const nodeData = nodeLayer.selectAll('g.doc-node').data(nodes, d => d.id);

  // EXIT: 删除多余节点 DOM（删除文件后这里移除对应 g 元素）
  nodeData.exit().remove();

  // ENTER: 新节点
  const nodeEnter = nodeData.enter().append('g')
    .attr('class', 'graph-node doc-node')
    .call(d3.drag()
      .on('start', dragStart)
      .on('drag', dragged)
      .on('end', dragEnd));

  nodeEnter.append('circle');
  nodeEnter.append('text').attr('class', 'doc-node-title');
  nodeEnter.append('text').attr('class', 'doc-node-count');

  // ENTER + UPDATE 合并：更新所有节点属性
  const allNodes = nodeEnter.merge(nodeData);

  allNodes.select('circle')
    .attr('r', nodeRadius)
    .attr('fill', d => d.selected ? d.color : (d.color + '55'))
    .attr('stroke', d => d.color)
    .attr('stroke-width', d => d.selected ? 4 : 2.5);

  allNodes.select('.doc-node-title')
    .attr('dy', d => nodeRadius(d) + 16)
    .text(d => truncate(d.label, 16));

  allNodes.select('.doc-node-count')
    .attr('dy', 4)
    .text(d => `${d.kpCount}`);

  // 事件绑定（enter + update 都需要）
  allNodes
    .on('click', (event, d) => {
      event.stopPropagation();
      state.selectedDocId = d.id;
      openDocDetail(d.id);
      renderGraph();
    })
    .on('mouseover', (event, d) => {
      showDocNodeTooltip(event, d);
      allLinks
        .attr('stroke-opacity', l => {
          const connected = nodesMatchLink(l, d.id);
          return connected ? 0.9 : 0.06;
        })
        .attr('stroke-width', l => {
          const connected = nodesMatchLink(l, d.id);
          return connected ? Math.max(3, l.score * 10) : Math.max(1.5, l.score * 8);
        });
    })
    .on('mousemove', (event) => {
      updateTooltipPosition(event);
    })
    .on('mouseout', () => {
      hideTooltip();
      allLinks
        .attr('stroke-opacity', l => Math.max(0.25, Math.min(0.9, l.score * 1.2)))
        .attr('stroke-width', l => Math.max(1.5, l.score * 8));
    })
    .on('contextmenu', (event, d) => {
      event.preventDefault();
      showContextMenu(event, d.id);
    });

  // 点击画布空白：关闭右键菜单 + 取消选中
  svg.on('click', () => {
    hideContextMenu();
    if (state.selectedDocId) {
      state.selectedDocId = null;
      renderGraph();
    }
  });

  // ====== 力模拟：停止旧的，用新数据启动 ======
  if (simulation) simulation.stop();

  simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(edges).id(d => d.id)
      .distance(d => 160)
      .strength(d => 0.15))
    .force('charge', d3.forceManyBody().strength(-400))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(d => nodeRadius(d) + 22))
    .force('x', d3.forceX(width / 2).strength(0.05))
    .force('y', d3.forceY(height / 2).strength(0.05))
    .on('tick', () => {
      allLinks
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);
      allNodes.attr('transform', d => `translate(${d.x},${d.y})`);
    });

  function dragStart(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
  }
  function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
  }
  function dragEnd(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
  }
}

// 判断连线是否与某节点相关
function nodesMatchLink(link, nodeId) {
  const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
  const targetId = typeof link.target === 'object' ? link.target.id : link.target;
  return sourceId === nodeId || targetId === nodeId;
}

// ============ Tooltip ============
// 文档节点 tooltip：标题、文件名、摘要、知识点数
function showDocNodeTooltip(event, d) {
  const tooltip = $('#tooltip');
  const summaryHtml = d.summary
    ? `<div class="tooltip-summary">${escapeHtml(truncate(d.summary, 80))}</div>`
    : '';
  tooltip.innerHTML = `
    <div class="tooltip-title">📄 ${escapeHtml(d.label)}</div>
    ${summaryHtml}
    <div class="tooltip-meta">📁 ${escapeHtml(d.filename || '')} · 📌 ${d.kpCount} 个知识点</div>
  `;
  tooltip.classList.remove('hidden');
  updateTooltipPosition(event);
}

// 兼容旧调用（部分代码可能仍引用 showTooltip）
function showTooltip(event, d) {
  if (d && d.type === 'doc') return showDocNodeTooltip(event, d);
  return showDocNodeTooltip(event, d);
}

// 边的 tooltip：显示关联依据（融合分数 / 向量相似度 / 关键词重合 / 实体 / Top 配对）
function showEdgeTooltip(event, d) {
  const tooltip = $('#tooltip');
  const score = Number(d.score || 0);
  const avgVec = Number(d.avgVectorScore || 0);
  const avgKw = Number(d.avgKeywordScore || 0);
  const avgFused = Number(d.avgFusedScore || 0);
  const avgOnto = Number(d.avgOntologyScore || 0);
  const pairCount = d.pairCount || 0;

  // 关联来源标签
  const sourceType = d.sourceType || 'private';
  const sourceLabels = {
    private: { icon: '📄', text: '私有文档推导', cls: 'source-private' },
    ontology: { icon: '🧩', text: '领域知识库推导', cls: 'source-ontology' },
    mixed: { icon: '🔀', text: '文档 + 知识库', cls: 'source-mixed' },
  };
  const sl = sourceLabels[sourceType] || sourceLabels.private;
  const ontoPairs = Number(d.ontologyPairCount || 0);
  const privatePairs = Number(d.privatePairCount || 0);

  // 重合关键词（前 12 个，避免过长）
  const kws = (d.overlapKeywords || []).slice(0, 12);
  const kwHtml = kws.length
    ? `<div class="tooltip-meta">🔑 重合关键词: ${kws.map(k => `<span class="tag">#${escapeHtml(k)}</span>`).join(' ')}</div>`
    : '';

  // 重合实体（归一化后，前 10 个）
  const ents = (d.overlapEntities || []).slice(0, 10);
  const entHtml = ents.length
    ? `<div class="tooltip-meta">🏷 重合实体: ${ents.map(e => `<span class="tag">${escapeHtml(e)}</span>`).join(' ')}</div>`
    : '';

  // Top 配对（最多 3 条，展示语义最强的知识点对）
  const tops = (d.topPairs || []).slice(0, 3);
  const topHtml = tops.length
    ? `<div class="tooltip-section">📌 强关联知识点对` +
      tops.map((t, i) => {
        const fromLabel = getPointShortLabel(t.from) || t.from;
        const toLabel = getPointShortLabel(t.to) || t.to;
        const tSrc = t.sourceType === 'ontology' ? '🧩' : t.sourceType === 'mixed' ? '🔀' : '📄';
        return `<div class="tooltip-meta tooltip-pair">
          <span class="pair-rank">${i + 1}</span>
          <span class="pair-label">${tSrc} ${escapeHtml(truncate(fromLabel, 20))} ↔ ${escapeHtml(truncate(toLabel, 20))}</span>
          <span class="pair-score">融合 ${(Number(t.score) || 0).toFixed(2)} · 向量 ${(Number(t.vectorScore) || 0).toFixed(2)}</span>
        </div>`;
      }).join('') +
      `</div>`
    : '';

  // 本体推理原始依据（source_text 原文片段，消除黑盒）
  const evidence = (d.ontologyEvidence || []).slice(0, 2);
  const evTypeLabel = { relation: '直接关系', alias: '同义共现', transitive: '传递推理' };
  const evidenceHtml = evidence.length
    ? `<div class="tooltip-section">📖 知识库推理依据` +
      evidence.map(ev => {
        const fromTo = ev.via
          ? `${escapeHtml(ev.from)} → ${escapeHtml(ev.via)} → ${escapeHtml(ev.to)}`
          : ev.from === ev.to
            ? `${escapeHtml(ev.from)}（同义）`
            : `${escapeHtml(ev.from)} → ${escapeHtml(ev.to)}`;
        const srcFile = ev.source_file ? escapeHtml(ev.source_file.split('/').pop()) : '';
        const text = ev.source_text ? escapeHtml(truncate(ev.source_text, 120)) : '<em>无原文</em>';
        return `<div class="evidence-item">
          <div class="evidence-head"><span class="evidence-type">${evTypeLabel[ev.type] || ev.type}</span> ${fromTo} ${srcFile ? `<span class="evidence-src">📄 ${srcFile}</span>` : ''}</div>
          <div class="evidence-text">"${text}"</div>
        </div>`;
      }).join('') +
      `</div>`
    : '';

  tooltip.innerHTML = `
    <div class="tooltip-title">🔗 文档关联</div>
    <div class="tooltip-meta"><span class="source-badge ${sl.cls}">${sl.icon} ${sl.text}</span></div>
    <div class="tooltip-meta tooltip-score">关联权重: <b>${score.toFixed(3)}</b></div>
    <div class="tooltip-meta">有效知识点对数: ${pairCount}（私有 ${privatePairs} · 知识库 ${ontoPairs}）</div>
    <div class="tooltip-divider"></div>
    <div class="tooltip-meta">🧠 向量相似度均值: ${avgVec.toFixed(3)}</div>
    <div class="tooltip-meta">🔤 关键词重合均值: ${avgKw.toFixed(3)}</div>
    <div class="tooltip-meta">🧩 本体推理均值: ${avgOnto.toFixed(3)}</div>
    <div class="tooltip-meta">⚡ 融合分数均值: ${avgFused.toFixed(3)}</div>
    ${kwHtml}
    ${entHtml}
    ${evidenceHtml}
    ${topHtml}
  `;
  tooltip.classList.remove('hidden');
  updateTooltipPosition(event);
}

// 取知识点的简短标签（用于 tooltip 中的配对展示）
function getPointShortLabel(pointId) {
  if (!pointId) return '';
  const pt = state.points.find(p => p.pointId === pointId);
  if (!pt) return '';
  return pt.description || pt.pointId || '';
}

function updateTooltipPosition(event) {
  const tooltip = $('#tooltip');
  const x = event.pageX + 14;
  const y = event.pageY + 14;
  const tooltipWidth = 380;
  const finalX = (x + tooltipWidth > window.innerWidth) ? event.pageX - tooltipWidth - 14 : x;
  tooltip.style.left = finalX + 'px';
  tooltip.style.top = y + 'px';
}

function hideTooltip() {
  $('#tooltip').classList.add('hidden');
}

// ============ 右键菜单 ============
// pointId 参数实际为文档 id（图谱主节点为文档）
function showContextMenu(event, pointId) {
  state.contextMenuDocId = pointId;
  state.contextMenuPointId = pointId;
  const menu = $('#context-menu');
  menu.classList.remove('hidden');
  let x = event.clientX;
  let y = event.clientY;
  if (x + 180 > window.innerWidth) x = window.innerWidth - 180;
  if (y + 120 > window.innerHeight) y = window.innerHeight - 120;
  menu.style.left = x + 'px';
  menu.style.top = y + 'px';
}

function hideContextMenu() {
  $('#context-menu').classList.add('hidden');
  state.contextMenuPointId = null;
  state.contextMenuDocId = null;
}

// ============ 文档详情面板 ============
// 打开文档详情：调用 getDocumentDetail，渲染 doc_info/kp_list/related_doc_list/cross_kp_edges
async function openDocDetail(docId) {
  const modal = $('#doc-detail-modal');
  const titleEl = $('#doc-detail-title');
  const bodyEl = $('#doc-detail-body');
  if (!modal || !bodyEl) return;

  state.selectedDocId = docId;
  titleEl.textContent = '📄 文档详情';
  bodyEl.innerHTML = '<div class="doc-detail-loading">加载中...</div>';
  modal.classList.remove('hidden');

  try {
    const detail = await getDocumentDetail(docId);
    renderDocDetail(detail);
  } catch (e) {
    bodyEl.innerHTML = `<div class="doc-detail-empty">加载失败：${escapeHtml(e.message)}</div>`;
  }
}

function closeDocDetail() {
  const modal = $('#doc-detail-modal');
  if (modal) modal.classList.add('hidden');
}

function renderDocDetail(detail) {
  const bodyEl = $('#doc-detail-body');
  const doc = detail.doc_info;

  // 文档信息
  const docInfoHtml = doc
    ? `
      <div class="doc-detail-section">
        <h3>📄 文档信息</h3>
        <div class="doc-detail-info">
          <div class="doc-detail-row"><span class="doc-detail-label">标题：</span><span class="doc-detail-value">${escapeHtml(doc.title || '')}</span></div>
          <div class="doc-detail-row"><span class="doc-detail-label">文件名：</span><span class="doc-detail-value">${escapeHtml(doc.filename || '')}</span></div>
          <div class="doc-detail-row"><span class="doc-detail-label">摘要：</span><span class="doc-detail-value">${escapeHtml(doc.summary || '无')}</span></div>
        </div>
      </div>`
    : '<div class="doc-detail-empty">文档不存在</div>';

  // 知识点列表
  const kpListHtml = detail.kp_list.length === 0
    ? '<div class="doc-detail-empty">暂无知识点</div>'
    : detail.kp_list.map((p, i) => {
        const kws = (p.keywords || []).map(k => '#' + escapeHtml(k)).join(' ');
        const ents = (p.entities || []).map(e => escapeHtml(e)).join(' · ');
        return `
          <div class="doc-detail-kp">
            <div class="doc-detail-kp-head"><span class="doc-detail-kp-idx">${i + 1}</span><span class="doc-detail-kp-type">${escapeHtml(p.type || 'concept')}</span></div>
            <div class="doc-detail-kp-desc">${escapeHtml(p.description || '')}</div>
            ${kws ? `<div class="doc-detail-kp-meta">🏷️ ${kws}</div>` : ''}
            ${ents ? `<div class="doc-detail-kp-meta">🔗 ${ents}</div>` : ''}
          </div>`;
      }).join('');

  // 关联文档列表
  const relatedHtml = detail.related_doc_list.length === 0
    ? '<div class="doc-detail-empty">暂无关联文档</div>'
    : detail.related_doc_list.map(r => `
        <div class="doc-detail-rel">
          <span class="doc-color-dot" style="background:${getDocColor(r.other_doc_id)}"></span>
          <span class="doc-detail-rel-title" title="${escapeHtml(r.other_doc_filename)}">${escapeHtml(truncate(r.other_doc_title, 22))}</span>
          <span class="doc-detail-rel-meta">权重 ${Number(r.doc_relation_weight).toFixed(3)} · ${r.valid_kp_pair_count} 对</span>
        </div>`).join('');

  // 跨文件知识点边列表
  const crossHtml = detail.cross_kp_edges.length === 0
    ? '<div class="doc-detail-empty">暂无跨文件知识点关联</div>'
    : detail.cross_kp_edges.map(e => {
        const relLabel = RELATION_LABELS[e.relation_type] || e.relation_type || '相关';
        const validBadge = e.is_valid
          ? '<span class="doc-detail-badge valid">有效</span>'
          : '<span class="doc-detail-badge invalid">无效</span>';
        return `
          <div class="doc-detail-cross">
            <div class="doc-detail-cross-pair">
              <span class="doc-detail-cross-desc">${escapeHtml(truncate(e.from_desc, 24))}</span>
              <span class="doc-detail-cross-arrow">→</span>
              <span class="doc-detail-cross-desc">${escapeHtml(truncate(e.to_desc, 24))}</span>
            </div>
            <div class="doc-detail-cross-meta">
              ${validBadge}
              <span>${escapeHtml(relLabel)}</span>
              <span>权重 ${Number(e.weight).toFixed(3)}</span>
            </div>
          </div>`;
      }).join('');

  bodyEl.innerHTML = `
    ${docInfoHtml}
    <div class="doc-detail-section">
      <h3>📌 知识点列表（${detail.kp_list.length}）</h3>
      <div class="doc-detail-kp-list">${kpListHtml}</div>
    </div>
    <div class="doc-detail-section">
      <h3>🔗 关联文档（${detail.related_doc_list.length}）</h3>
      <div class="doc-detail-rel-list">${relatedHtml}</div>
    </div>
    <div class="doc-detail-section">
      <h3>🔀 跨文件知识点边（${detail.cross_kp_edges.length}）</h3>
      <div class="doc-detail-cross-list">${crossHtml}</div>
    </div>
  `;
}

// ============ UI 更新 ============
function updateCount() {
  $('#map-count').textContent = `${state.points.length} 个知识点 · ${state.docs.length} 份文档`;
}

// ============ 清空数据 ============
async function clearAll() {
  if (state.points.length === 0 && state.docs.length === 0) {
    toast('没有数据可清空', 'info');
    return;
  }
  if (!confirm(`确定清空全部数据（${state.docs.length} 份文档、${state.points.length} 个知识点、${state.edges.length} 条知识点边、${state.docEdges.length} 条文档边）？此操作不可恢复。`)) return;

  // IndexedDB 清空（即使失败也继续更新内存状态）
  try {
    await dbClearAll();
  } catch (e) {
    console.error('IndexedDB 清空失败，继续更新内存状态:', e);
  }

  // 显式清空所有状态数组（响应式更新）
  state.docs = [];
  state.points = [];
  state.edges = [];
  state.docEdges = [];
  state.vectorIndex = [];
  state.pointMap = new Map();
  state.docFilter = new Set();
  state.selectedPointId = null;
  state.selectedDocId = null;

  renderGraph();
  renderDocFilter();
  updateCount();
  toast('已清空所有数据', 'success');
}

// ============ 事件绑定 ============
function bindEvents() {
  // 文件上传
  $('#file-input').onchange = (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 0) processFiles(files);
    e.target.value = '';
  };

  $('#file-input-empty').onchange = (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 0) processFiles(files);
    e.target.value = '';
  };

  $('#folder-input').onchange = (e) => {
    const files = Array.from(e.target.files).filter(f => isTextFile(f));
    if (files.length > 0) processFiles(files);
    else toast('文件夹中没有可识别的文本文件', 'warning');
    e.target.value = '';
  };

  // 设置弹窗
  $('#btn-settings').onclick = openSettingsModal;
  $('#settings-cancel').onclick = closeSettingsModal;
  $('#settings-save').onclick = () => {
    saveSettings({
      llmApiUrl: $('#setting-llm-url').value.trim(),
      llmApiKey: $('#setting-llm-key').value.trim(),
      llmModel: $('#setting-llm-model').value.trim(),
      embeddingApiUrl: $('#setting-emb-url').value.trim(),
      embeddingApiKey: $('#setting-emb-key').value.trim(),
      embeddingModel: $('#setting-emb-model').value.trim(),
      threshold: parseFloat($('#setting-threshold').value),
      ontologyWeight: parseFloat($('#setting-ontology-weight').value),
    });
    closeSettingsModal();
    toast('设置已保存（本体权重调整后需全局重建生效）', 'success', 3500);
  };

  $('#setting-threshold').oninput = (e) => {
    $('#threshold-value').textContent = parseFloat(e.target.value).toFixed(2);
  };
  $('#setting-ontology-weight').oninput = (e) => {
    $('#ontology-weight-value').textContent = parseFloat(e.target.value).toFixed(2);
  };

  $('#settings-modal').onclick = (e) => {
    if (e.target.id === 'settings-modal') closeSettingsModal();
  };

  // 领域知识库管理
  $('#btn-ontology').onclick = openOntologyModal;
  $('#ontology-close').onclick = closeOntologyModal;
  $('#ontology-modal').onclick = (e) => {
    if (e.target.id === 'ontology-modal') closeOntologyModal();
  };
  $('#ontology-add').onclick = () => openEntityEditor(-1);
  $('#entity-cancel').onclick = closeEntityEditor;
  $('#entity-save').onclick = saveEntityFromForm;
  $('#ontology-reset').onclick = async () => {
    if (!confirm('确定重新从领域语料构建本体？所有手动增删修改将丢失。')) return;
    const ok = await resetOntology();
    if (ok) {
      renderOntologyTabs();
      renderOntologyList();
      toast('本体已从语料重新构建', 'success');
    } else {
      toast('重置失败', 'error');
    }
  };

  // 隐藏知识库推导连线开关
  $('#btn-hide-ontology').onclick = () => {
    state.hideOntologyEdges = !state.hideOntologyEdges;
    $('#btn-hide-ontology').classList.toggle('active', state.hideOntologyEdges);
    renderGraph();
    toast(state.hideOntologyEdges ? '已隐藏知识库推导连线' : '已显示全部连线', 'info');
  };

  // 文档筛选面板
  const filterPanel = $('#doc-filter-panel');
  $('#btn-doc-filter').onclick = () => {
    filterPanel.classList.toggle('hidden');
  };
  $('#doc-filter-toggle-all').onclick = toggleAllDocFilter;

  // 局部重建
  $('#btn-rebuild-local').onclick = openRebuildModal;
  $('#rebuild-cancel').onclick = closeRebuildModal;
  $('#rebuild-confirm').onclick = performLocalRebuild;
  $('#rebuild-modal').onclick = (e) => {
    if (e.target.id === 'rebuild-modal') closeRebuildModal();
  };

  // 全局完整重建
  $('#btn-rebuild-all').onclick = rebuildAllEdges;

  // 退出选中查看（文档节点选中态）
  const exitFocus = $('#btn-exit-focus');
  if (exitFocus) {
    exitFocus.onclick = () => {
      state.selectedDocId = null;
      state.selectedPointId = null;
      renderGraph();
    };
  }

  // 文档详情弹窗
  const docDetailClose = $('#doc-detail-close');
  if (docDetailClose) docDetailClose.onclick = closeDocDetail;
  const docDetailModal = $('#doc-detail-modal');
  if (docDetailModal) {
    docDetailModal.onclick = (e) => {
      if (e.target.id === 'doc-detail-modal') closeDocDetail();
    };
  }

  // Electron 专属事件
  if (isElectron) {
    $('#btn-scan-dir').onclick = scanAndImportDirectory;
    $('#btn-watch').onclick = toggleWatch;

    // 接收新文件通知（文件夹监控）
    window.electron.onNewFile(async (file) => {
      toast(`检测到新文件: ${file.name}`, 'info');
      try {
        const result = await window.electron.readFile(file.path);
        if (result.success) {
          // 若同名文档已存在，视为文件更新：清除原关联后重新走完整召回校验
          const existing = state.docs.find(d => d.filename === file.name);
          if (existing) {
            showProgress('文件更新，重新解析...', file.name);
            await handleFileUpdate(existing.docId, result.content, file.name);
            hideProgress();
            renderGraph();
            renderDocFilter();
            updateCount();
            toast(`「${file.name}」已更新并重新计算关联`, 'success');
          } else {
            await processText(result.content, file.name);
          }
        }
      } catch (e) {
        console.error('自动导入失败:', file.name, e);
        hideProgress();
      }
    });
  }

  // 清空
  $('#btn-clear').onclick = clearAll;

  // 右键菜单操作（文档节点）
  $('#ctx-doc-detail').onclick = () => {
    const docId = state.contextMenuDocId;
    hideContextMenu();
    if (docId) openDocDetail(docId);
  };

  $('#ctx-doc-rebuild').onclick = async () => {
    const docId = state.contextMenuDocId;
    hideContextMenu();
    if (!docId) return;
    showProgress('正在局部重建关联...', '该文档');
    try {
      const count = await rebuildEdgesForDocs([docId]);
      hideProgress();
      renderGraph();
      toast(`局部重建完成（${count} 个知识点）`, 'success');
    } catch (e) {
      hideProgress();
      toast('局部重建失败: ' + e.message, 'error', 4000);
    }
  };

  $('#ctx-doc-delete').onclick = () => {
    const docId = state.contextMenuDocId;
    hideContextMenu();
    if (docId) deleteDoc(docId);
  };

  // 点击任意位置关闭右键菜单
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#context-menu')) {
      hideContextMenu();
    }
  });

  // Esc 关闭弹窗
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeSettingsModal();
      closeRebuildModal();
      closeDocDetail();
      hideContextMenu();
      if (state.selectedDocId) {
        state.selectedDocId = null;
        renderGraph();
      }
    }
  });

  // 窗口大小变化重绘
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => renderGraph(), 300);
  });
}

// ============ 初始化 ============
async function init() {
  if (isElectron) {
    document.body.classList.add('electron');
  }

  loadSettings();
  await buildOntologyFromCorpus();
  await initDB();

  // 加载新架构数据
  state.docs = await dbGetAllDocs();
  state.points = await dbGetAllPoints();
  state.edges = await dbGetAllEdges();
  state.docEdges = await dbGetAllDocEdges();

  rebuildPointMap();
  loadVectorIndex();

  // 迁移旧数据（maps -> docs/points/edges）
  await migrateOldMaps();

  // 清理无效关联（端点不存在）
  const validPointIds = new Set(state.points.map(p => p.pointId));
  const invalidEdges = state.edges.filter(e => !validPointIds.has(e.from) || !validPointIds.has(e.to));
  if (invalidEdges.length > 0) {
    for (const e of invalidEdges) {
      if (e.edgeId !== undefined) await dbDeleteEdge(e.edgeId);
    }
    state.edges = state.edges.filter(e => validPointIds.has(e.from) && validPointIds.has(e.to));
  }

  // 旧库升级到两级边模型后，若 docEdges 为空但存在有效跨文件 Kp_Edge，则补算一次
  if (state.docEdges.length === 0 && state.edges.some(e => e.isRender)) {
    try {
      await recomputeAllDocEdge();
    } catch (e) {
      console.warn('初始化补算 Doc_Edge 失败:', e);
    }
  }

  bindEvents();
  renderGraph();
  renderDocFilter();
  updateCount();

  if (!state.settings.llmApiKey) {
    setTimeout(() => {
      toast('未配置 API Key，将使用降级方案解析文档。点击 ⚙️ 设置配置 AI 服务', 'warning', 5000);
    }, 1000);
  }
}

init();
