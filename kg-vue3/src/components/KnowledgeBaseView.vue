<template>
  <div class="kb-view">
    <header class="kb-head">
      <div class="kb-head-main">
        <h2>知识库</h2>
        <p>知识库是系统的知识权威源：文档先<strong>锚定</strong>到知识库知识点，再由知识库<strong>概念空间</strong>决定文件之间、知识点之间的关联 —— 不是拿文本向量比相似度，没被知识库覆盖的内容不产生关联。</p>
      </div>
      <div class="kb-head-actions">
        <span class="kb-threshold">关联阈值<el-slider v-model="kbStore.rebuildThreshold" :min="0.05" :max="0.5" :step="0.05" style="width:120px" size="small" /></span>
        <el-button type="primary" :loading="kbStore.rebuilding" @click="onRebuild">重建知识关联</el-button>
      </div>
    </header>
    <el-tabs v-model="activeTab" class="kb-tabs">
      <el-tab-pane label="概览" name="overview">
        <div class="kb-stat-grid">
          <div class="kb-stat" v-for="card in statCards" :key="card.label"><div class="ks-val">{{ card.value }}</div><div class="ks-label">{{ card.label }}</div><div class="ks-sub">{{ card.sub }}</div></div>
        </div>
        <div class="kb-two-col">
          <section class="kb-card"><h3>领域分布 <span class="kb-count">{{ kbStore.domains.length }}</span></h3><div class="kb-bars"><div v-for="d in kbStore.domains" :key="d.domain" class="kb-bar-row"><span class="kb-bar-name" :title="d.domain">{{ d.domain }}</span><div class="kb-bar-track"><div class="kb-bar-fill" :style="{ width: barWidth(d.count) }"></div></div><span class="kb-bar-val">{{ d.count }}</span></div><div v-if="!kbStore.domains.length" class="kb-empty">暂无知识点</div></div></section>
          <section class="kb-card"><h3>知识层级分布</h3><div class="kb-levels"><div v-for="lv in levelRows" :key="lv.key" class="kb-level-row"><span class="kl-badge" :style="{ background: lv.color }">L{{ lv.key }}</span><span class="kl-label">{{ lv.label }}</span><span class="kl-val">{{ lv.value }}</span></div></div><h3 style="margin-top:14px">来源构成</h3><div class="kb-sources"><el-tag v-for="(count, key) in (kbStore.stats?.sources || {})" :key="key" size="small" effect="plain" class="kb-src-tag">{{ key }} · {{ count }}</el-tag></div></section>
        </div>
        <section class="kb-card"><h3>知识库本体图<span class="kb-count">{{ kbStore.graph.nodes.length }} 点 / {{ kbStore.graph.links.length }} 边</span><span class="kb-inline-tools"><el-select v-model="graphDomain" size="small" style="width:150px" clearable placeholder="全部领域" @change="loadGraph"><el-option v-for="d in kbStore.domains" :key="d.domain" :label="d.domain" :value="d.domain" /></el-select><el-radio-group v-model="colorMode" size="small"><el-radio-button label="domain">按领域</el-radio-button><el-radio-button label="level">按层级</el-radio-button></el-radio-group></span></h3><KbOntologyCanvas :nodes="kbStore.graph.nodes" :links="kbStore.graph.links" :color-mode="colorMode" :height="380" /><p class="kb-hint">虚线边＝由条目自身的「相关术语 / 桥接句」自动推导；实线边＝用户上传或手工维护。</p></section>
      </el-tab-pane>
      <el-tab-pane label="上传理解" name="ingest">
        <div class="kb-two-col">
          <section class="kb-card"><h3>上传知识库文件</h3><div class="kb-dropzone" :class="{ dragover: dragging }" @click="pickFile" @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="onDrop"><div class="dz-icon">📚</div><div class="dz-text">拖拽知识库文件到此处，或点击选择</div><div class="dz-sub">支持 .md（条目式/表格）· .csv/.tsv（含表头）· .json · .txt</div><input ref="fileRef" type="file" hidden accept=".md,.markdown,.txt,.csv,.tsv,.json" @change="onFileChange" /></div><div class="kb-formats"><div class="kb-fmt-title">识别规则</div><ul><li><b>markdown</b>：<code>## 实体 (别名)</code> + <code>别名:</code>/<code>关系:</code>/<code>bridge_sentence:</code>/<code>domain:</code></li><li><b>csv/tsv</b>：表头含 实体 / 别名 / 领域 / 层级 / 定义 / 关系</li><li><b>json</b>：<code>[{"entity": "...", "definition": "..."}]</code></li><li><b>txt</b>：每行 <code>实体：定义</code></li></ul></div><el-checkbox v-model="overwriteDefs" size="small">定义冲突时用上传内容覆盖知识库既有定义</el-checkbox><div v-if="pendingFile" class="kb-pending"><span class="kp-pending-text">《{{ pendingFile.name }}》已生成预览报告（尚未入库）</span><el-button size="small" type="primary" :loading="kbStore.importing" @click="confirmPending">导入知识库</el-button><el-button size="small" @click="pendingFile = null">取消</el-button></div></section>
          <section class="kb-card"><h3>或粘贴文本理解</h3><el-input v-model="pasteText" type="textarea" :rows="7" placeholder="把知识库内容粘贴到这里…" /><div class="kb-paste-actions"><el-button :loading="kbStore.previewing" @click="onPreview">预览理解</el-button><el-button type="primary" :loading="kbStore.importing" :disabled="!pasteText.trim()" @click="onImportPaste">导入知识库</el-button></div></section>
        </div>
        <section class="kb-card" v-if="kbStore.report"><h3>理解报告<span class="kb-count">{{ kbStore.report.format }}</span><span class="kb-inline-tools"><el-tag v-if="kbStore.report.dry_run" type="warning" size="small" effect="dark">预览（未入库）</el-tag></span></h3><p class="kb-summary">{{ kbStore.report.summary }}</p><div class="kb-report-grid"><div class="kb-report-block"><div class="krb-title ok">新增知识点 {{ kbStore.report.new_entries?.length || 0 }}</div><div class="krb-body"><span v-for="e in kbStore.report.new_entries" :key="e.entity" class="kb-chip ok" :title="e.definition">{{ e.entity }}</span><span v-if="!kbStore.report.new_entries?.length" class="kb-empty">无</span></div></div><div class="kb-report-block"><div class="krb-title info">同义合并 {{ kbStore.report.merged_entries?.length || 0 }}</div><div class="krb-body"><span v-for="m in kbStore.report.merged_entries" :key="m.entity" class="kb-chip info" :title="`新增别名：${(m.added_aliases || []).join('、') || '—'}｜新增关系：${(m.added_related || []).join('、') || '—'}`">{{ m.entity }}</span><span v-if="!kbStore.report.merged_entries?.length" class="kb-empty">无</span></div></div><div class="kb-report-block"><div class="krb-title warn">定义冲突 {{ kbStore.report.conflicts?.length || 0 }}</div><div class="krb-body"><div v-for="c in kbStore.report.conflicts" :key="c.entity" class="kb-conflict"><div class="kc-entity">{{ c.entity }} <span class="kc-res">{{ c.resolution }}</span></div><div class="kc-line"><b>知识库</b>：{{ c.existing }}</div><div class="kc-line"><b>上传</b>：{{ c.incoming }}</div></div><span v-if="!kbStore.report.conflicts?.length" class="kb-empty">无</span></div></div><div class="kb-report-block"><div class="krb-title">未采纳 {{ kbStore.report.rejected?.length || 0 }}<span class="kb-relations-note">新增关系 {{ (kbStore.report.relations_added?.length || 0) + (kbStore.report.relations_derived || 0) }}</span></div><div class="krb-body"><span v-for="(r, i) in kbStore.report.rejected" :key="i" class="kb-chip muted" :title="r.reason">{{ r.entity }}（{{ r.reason }}）</span><span v-if="!kbStore.report.rejected?.length" class="kb-empty">无</span></div></div></div><div class="kb-report-tail">知识库现有 {{ kbStore.report.stats?.kb_total || 0 }} 个知识点 · {{ kbStore.report.stats?.relations_total || 0 }} 条关系</div></section>
        <section class="kb-card"><h3>上传历史 <span class="kb-count">{{ kbStore.imports.length }}</span></h3><el-table :data="kbStore.imports" size="small" @row-click="onOpenImport" style="cursor:pointer"><el-table-column prop="name" label="文件" min-width="180" show-overflow-tooltip /><el-table-column prop="format" label="格式" width="90" /><el-table-column prop="entry_total" label="识别" width="70" /><el-table-column prop="new_count" label="新增" width="70" /><el-table-column prop="merged_count" label="合并" width="70" /><el-table-column prop="conflict_count" label="冲突" width="70" /><el-table-column prop="relation_count" label="关系" width="70" /><el-table-column prop="created_at" label="时间" min-width="150"><template #default="{ row }">{{ fmtTime(row.created_at) }}</template></el-table-column></el-table></section>
      </el-tab-pane>
      <el-tab-pane label="知识点" name="entries">
        <section class="kb-card"><h3>知识点管理<span class="kb-count">{{ kbStore.entryTotal }}</span><span class="kb-inline-tools"><el-input v-model="kbStore.entryFilter.keyword" size="small" style="width:170px" placeholder="搜索知识点" clearable @keyup.enter="searchEntries" /><el-select v-model="kbStore.entryFilter.domain" size="small" style="width:140px" placeholder="全部领域" clearable><el-option v-for="d in kbStore.domains" :key="d.domain" :label="d.domain" :value="d.domain" /></el-select><el-select v-model="kbStore.entryFilter.level" size="small" style="width:110px"><el-option label="全部层级" :value="0" /><el-option v-for="l in [1,2,3,4]" :key="l" :label="`L${l}`" :value="l" /></el-select><el-button size="small" @click="searchEntries">筛选</el-button><el-button size="small" type="primary" @click="openEditor(null)">新增知识点</el-button></span></h3><el-table :data="kbStore.entries" size="small" v-loading="kbStore.loadingEntries"><el-table-column prop="entity" label="知识点" min-width="150" show-overflow-tooltip><template #default="{ row }"><span class="kb-entity" @click="showNeighbors(row)">{{ row.entity }}</span></template></el-table-column><el-table-column label="别名" min-width="140"><template #default="{ row }"><span v-if="row.aliases?.length">{{ row.aliases.join('、') }}</span><span v-else class="kb-empty">—</span></template></el-table-column><el-table-column prop="domain" label="领域" width="120" show-overflow-tooltip /><el-table-column prop="level" label="层级" width="70"><template #default="{ row }">L{{ row.level }}</template></el-table-column><el-table-column prop="relation_count" label="关系" width="70" /><el-table-column prop="definition" label="定义" min-width="220" show-overflow-tooltip /><el-table-column prop="source" label="来源" width="130" show-overflow-tooltip /><el-table-column label="操作" width="130" fixed="right"><template #default="{ row }"><el-button link size="small" @click="openEditor(row)">编辑</el-button><el-button link size="small" type="danger" @click="onDeleteEntry(row)">删除</el-button></template></el-table-column></el-table><div class="kb-pager"><el-button size="small" :disabled="entryOffset === 0" @click="pageTo(-1)">上一页</el-button><span class="kb-page-info">{{ entryOffset + 1 }} - {{ Math.min(entryOffset + 50, kbStore.entryTotal) }} / {{ kbStore.entryTotal }}</span><el-button size="small" :disabled="entryOffset + 50 >= kbStore.entryTotal" @click="pageTo(1)">下一页</el-button></div></section>
      </el-tab-pane>
      <el-tab-pane label="知识关联" name="linking">
        <section class="kb-card"><h3>知识锚定测试 <span class="kb-count">文本 → 命中的知识点</span></h3><el-input v-model="matchText" type="textarea" :rows="4" placeholder="粘贴一段文本，看看知识库认出了哪些知识点（这就是「锚定」）" /><div class="kb-paste-actions"><el-button :loading="kbStore.matching" @click="onMatch">知识锚定</el-button><span v-if="kbStore.matchResult" class="kb-match-meta">命中 {{ kbStore.matchResult.matched }} 个知识点 · {{ kbStore.matchResult.hits }} 次出现 · 知识库覆盖率 {{ (kbStore.matchResult.coverage * 100).toFixed(1) }}%</span></div><div class="kb-match-list" v-if="kbStore.matchResult?.concepts?.length"><div v-for="c in kbStore.matchResult.concepts" :key="c.entity" class="kb-match-item"><span class="km-name">{{ c.entity }}</span><span class="km-meta">{{ c.domain }} · L{{ c.level }} · 出现 {{ c.count }} 次</span><span v-if="c.via_alias" class="km-alias">经别名「{{ c.matched_text }}」命中</span><div class="km-def">{{ c.definition }}</div></div></div><p v-else-if="kbStore.matchResult" class="kb-hint">该文本没有命中任何知识库知识点 —— 按知识边界规则，它不会参与任何关联。</p></section>
        <section class="kb-card"><h3>文件知识画像<span class="kb-count">{{ kbStore.fileProfiles.length }}</span><span class="kb-inline-tools"><span class="kb-hint">平均知识库覆盖率 {{ (kbStore.avgCoverage * 100).toFixed(1) }}%</span></span></h3><div class="kb-profile-grid"><div v-for="f in kbStore.fileProfiles" :key="f.file_id" class="kb-profile" :class="{ uncovered: !f.concept_count }"><div class="kp-head"><span class="kp-name" :title="f.name">{{ f.name }}</span><el-tag size="small" :type="f.concept_count ? 'success' : 'info'" effect="plain">{{ f.concept_count }} 个知识点</el-tag></div><el-progress :percentage="Math.round((f.coverage || 0) * 100)" :stroke-width="6" :show-text="false" :color="f.concept_count ? 'var(--mint)' : 'var(--text-muted)'" /><div class="kp-coverage">知识库覆盖率 {{ ((f.coverage || 0) * 100).toFixed(1) }}% · {{ f.node_count }} 个文档节点</div><div class="kp-concepts"><span v-for="c in f.top_concepts" :key="c.entity" class="kb-chip info" :title="`权重 ${c.weight}｜出现 ${c.count} 次`">{{ c.entity }}</span><span v-if="!f.top_concepts?.length" class="kb-empty">未被知识库覆盖</span></div></div></div></section>
        <section class="kb-card"><h3>文件间知识关联<span class="kb-count">{{ kbStore.fileLinks.length }} 条 · 阈值 {{ kbStore.rebuildThreshold }}</span></h3><p class="kb-hint">综合分 = 共享知识点 50% + 知识库关系桥接 35% + 领域/层级一致性 15%。字面相似但知识库不认的文件不会出现在这里。</p><div v-for="l in sortedFileLinks" :key="l.id" class="kb-link-item"><div class="kl-head"><span class="kl-files"><b>{{ l.source_name }}</b> × <b>{{ l.target_name }}</b></span><span class="kl-score">{{ (l.kb_similarity * 100).toFixed(1) }}%</span></div><div class="kl-scores">共享 {{ (l.direct_score * 100).toFixed(0) }}% · 桥接 {{ (l.bridge_score * 100).toFixed(0) }}% · 领域层级 {{ (l.domain_score * 100).toFixed(0) }}%</div><div class="kl-block" v-if="l.shared_concepts?.length"><span class="kl-label">共同知识点</span><span v-for="c in l.shared_concepts" :key="c" class="kb-chip ok">{{ c }}</span></div><div class="kl-block" v-if="l.bridges?.length"><span class="kl-label">知识库通路</span><div v-for="(b, i) in l.bridges.slice(0, 4)" :key="i" class="kl-bridge"><span class="klb-path">{{ b.from }} <i>{{ b.relation_type }}</i> {{ b.to }}</span><span class="klb-hops">{{ b.hops }} 跳</span><span class="klb-evidence">{{ b.evidence }}</span></div></div></div><div v-if="!kbStore.fileLinks.length" class="kb-empty">暂无文件间知识关联（上传更多文档，或下调关联阈值后重建）</div><div v-if="kbStore.uncoveredFiles.length" class="kb-uncovered">⚠ 以下文件未被知识库覆盖，按知识边界规则不参与关联：{{ kbStore.uncoveredFiles.map(f => f.name).join('、') }}</div></section>
      </el-tab-pane>
    </el-tabs>
    <el-dialog v-model="editorVisible" :title="editorForm.id ? '编辑知识点' : '新增知识点'" width="560px"><el-form :model="editorForm" label-width="72px" size="small"><el-form-item label="知识点"><el-input v-model="editorForm.entity" placeholder="如：JavaScript" /></el-form-item><el-form-item label="别名"><el-input v-model="editorAliasText" placeholder="多个别名用 、或 , 分隔" /></el-form-item><el-form-item label="领域"><el-input v-model="editorForm.domain" placeholder="如：frontend" /></el-form-item><el-form-item label="层级"><el-radio-group v-model="editorForm.level"><el-radio-button v-for="l in [1,2,3,4]" :key="l" :label="l">L{{ l }}</el-radio-button></el-radio-group></el-form-item><el-form-item label="定义"><el-input v-model="editorForm.definition" type="textarea" :rows="4" /></el-form-item><el-form-item label="相关术语"><el-input v-model="editorRelatedText" placeholder="多个术语用 、或 , 分隔" /></el-form-item></el-form><template #footer><el-button @click="editorVisible = false">取消</el-button><el-button type="primary" @click="saveEntry">保存</el-button></template></el-dialog>
    <el-dialog v-model="neighborVisible" :title="`「${neighborEntity}」在知识库中的邻域`" width="560px"><div v-for="n in neighbors" :key="n.entity" class="kb-neighbor"><div class="kn-head"><span class="kn-name">{{ n.entity }}</span><el-tag size="small" effect="plain">{{ n.relation_type }}</el-tag><span class="kn-weight">强度 {{ n.weight }}</span></div><div class="kn-evidence">{{ n.evidence || n.definition }}</div></div><div v-if="!neighbors.length" class="kb-empty">该知识点在知识库中没有关系边</div></el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useKbStore } from '@/store/kbStore'
import { useGraphStore } from '@/store/graphStore'
import { kbAPI } from '@/api/index'
import KbOntologyCanvas from '@/components/KbOntologyCanvas.vue'

const kbStore = useKbStore()
const graphStore = useGraphStore()
const activeTab = ref('overview')
const colorMode = ref('domain')
const graphDomain = ref('')
const dragging = ref(false)
const fileRef = ref(null)
const overwriteDefs = ref(false)
const pasteText = ref('')
const matchText = ref('')
const entryOffset = ref(0)
const editorVisible = ref(false)
const editorForm = ref({ id: null, entity: '', domain: 'general', level: 3, definition: '' })
const editorAliasText = ref('')
const editorRelatedText = ref('')
const neighborVisible = ref(false)
const neighborEntity = ref('')
const neighbors = ref([])
const LEVEL_META = { 1: { label: '元概念', color: 'var(--accent)' }, 2: { label: '核心理论', color: 'var(--mint)' }, 3: { label: '应用实践', color: 'var(--apricot)' }, 4: { label: '实现工具', color: '#9C7BB8' } }
const statCards = computed(() => {
  const s = kbStore.stats || {}
  return [
    { label: '知识点', value: s.entries ?? '—', sub: `${s.aliases ?? 0} 个别名可锚定` },
    { label: '知识库关系', value: s.relations ?? '—', sub: `推导边 ${s.sources?.['relation:derived'] ?? 0} 条` },
    { label: '已覆盖文件', value: `${s.files_covered ?? 0}/${s.files ?? 0}`, sub: `覆盖率 ${((s.coverage_rate || 0) * 100).toFixed(0)}%` },
    { label: '文件知识关联', value: s.file_links ?? '—', sub: `节点级锚定连线 ${s.kb_node_links ?? 0} 条` },
    { label: '平均覆盖知识点', value: s.avg_concepts_per_file ?? '—', sub: '每个文件锚定的知识点数' }
  ]
})
const levelRows = computed(() => {
  const levels = kbStore.stats?.levels || {}
  return [1, 2, 3, 4].map(k => ({ key: k, label: LEVEL_META[k].label, color: LEVEL_META[k].color, value: levels[String(k)] || 0 }))
})
const sortedFileLinks = computed(() => [...kbStore.fileLinks].sort((a, b) => b.kb_similarity - a.kb_similarity))
const maxDomainCount = computed(() => Math.max(1, ...kbStore.domains.map(d => d.count)))
function barWidth(count) { return `${Math.max(2, (count / maxDomainCount.value) * 100)}%` }
function fmtTime(iso) { if (!iso) return '—'; return iso.replace('T', ' ').slice(0, 16) }
function loadGraph() { kbStore.loadGraph({ domain: graphDomain.value, limit: 150 }) }
function searchEntries() { entryOffset.value = 0; kbStore.loadEntries({ offset: 0 }) }
function pageTo(direction) { entryOffset.value = Math.max(0, entryOffset.value + direction * 50); kbStore.loadEntries({ offset: entryOffset.value }) }
const pendingFile = ref(null)
function pickFile() { fileRef.value?.click() }
function onFileChange(e) { const file = e.target.files?.[0]; e.target.value = ''; if (file) handleFile(file) }
function onDrop(e) { dragging.value = false; const file = e.dataTransfer.files?.[0]; if (file) handleFile(file) }
async function handleFile(file) {
  const report = await kbStore.uploadKb(file, { dryRun: true, overwrite: overwriteDefs.value })
  if (report) { pendingFile.value = file; ElMessage.info('已生成理解报告，确认无误后点「导入知识库」') }
}
async function confirmPending() {
  if (!pendingFile.value) return
  await kbStore.uploadKb(pendingFile.value, { dryRun: false, overwrite: overwriteDefs.value })
  await afterImport()
}
async function onPreview() {
  if (!pasteText.value.trim()) return
  const report = await kbStore.previewText(pasteText.value, '粘贴文本知识库', true)
  if (report) ElMessage.info('已生成理解报告，确认无误后点「导入知识库」')
}
async function onImportPaste() {
  if (!pasteText.value.trim()) return
  await kbStore.previewText(pasteText.value, '粘贴文本知识库', false)
  await afterImport()
}
async function afterImport() {
  pendingFile.value = null
  await kbStore.loadFiles()
  await kbStore.loadGraph({ domain: graphDomain.value, limit: 150 })
  try { await graphStore.loadFromBackend?.() } catch (e) { /* 图谱刷新失败不阻断知识库流程 */ }
}
async function onOpenImport(row) { await kbStore.loadImportDetail(row.id); activeTab.value = 'ingest'; ElMessage.success(`已载入《${row.name}》的理解报告`) }
function openEditor(row) {
  if (row) {
    editorForm.value = { id: row.id, entity: row.entity, domain: row.domain || 'general', level: row.level || 3, definition: row.definition || '' }
    editorAliasText.value = (row.aliases || []).join('、')
    editorRelatedText.value = (row.related_terms || []).join('、')
  } else {
    editorForm.value = { id: null, entity: '', domain: 'general', level: 3, definition: '' }
    editorAliasText.value = ''
    editorRelatedText.value = ''
  }
  editorVisible.value = true
}
function splitList(text) { return (text || '').split(/[、,，;；\s]+/).map(s => s.trim()).filter(Boolean) }
async function saveEntry() {
  if (!editorForm.value.entity.trim()) { ElMessage.warning('请填写知识点名称'); return }
  const payload = { entity: editorForm.value.entity.trim(), domain: editorForm.value.domain || 'general', level: editorForm.value.level, definition: editorForm.value.definition, aliases: splitList(editorAliasText.value), related_terms: splitList(editorRelatedText.value), credibility: 6 }
  if (editorForm.value.id) await kbStore.updateEntry(editorForm.value.id, payload)
  else await kbStore.createEntry(payload)
  editorVisible.value = false
  await kbStore.loadFiles()
}
async function onDeleteEntry(row) {
  try { await ElMessageBox.confirm(`删除知识点「${row.entity}」会同时删除它的知识库关系边，已锚定该知识点的文档节点不会被删除。确认删除？`, '删除知识点', { type: 'warning' }) } catch (e) { return }
  await kbStore.deleteEntry(row.id)
}
async function showNeighbors(row) {
  neighborEntity.value = row.entity
  neighborVisible.value = true
  const data = await kbAPI.neighbors(row.entity, 20)
  neighbors.value = data.neighbors || []
}
async function onMatch() {
  if (!matchText.value.trim()) { ElMessage.warning('请先粘贴一段文本'); return }
  await kbStore.matchText(matchText.value)
}
async function onRebuild() {
  await kbStore.rebuild({ threshold: kbStore.rebuildThreshold })
  await afterImport()
  await kbStore.loadFiles()
}
onMounted(async () => { await kbStore.refreshAll() })
</script>

<style scoped>
.kb-view { flex: 1; min-width: 0; padding: 16px 20px 40px; height: 100%; overflow-y: auto; background: var(--bg-primary); }
.kb-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 8px; }
.kb-head-main h2 { margin: 0 0 6px; font-size: 18px; color: var(--text-primary); }
.kb-head-main p { margin: 0; max-width: 720px; font-size: 12.5px; line-height: 1.6; color: var(--text-secondary); }
.kb-head-actions { display: flex; align-items: center; gap: 14px; }
.kb-threshold { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-secondary); }
.kb-tabs { margin-top: 6px; }
.kb-card { background: var(--bg-secondary); border: 1px solid var(--border-light); border-radius: var(--radius); padding: 14px 16px; margin-bottom: 14px; box-shadow: var(--shadow-sm); }
.kb-card h3 { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 0 0 12px; font-size: 13.5px; color: var(--text-primary); }
.kb-count { font-size: 11px; font-weight: 500; color: var(--text-muted); background: var(--bg-tertiary); border-radius: var(--radius-full); padding: 1px 8px; }
.kb-inline-tools { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.kb-hint { font-size: 11.5px; color: var(--text-muted); margin: 6px 0 0; line-height: 1.6; }
.kb-empty { font-size: 12px; color: var(--text-muted); }
.kb-summary { font-size: 12.5px; color: var(--text-primary); margin: 0 0 12px; }
.kb-stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 14px; }
.kb-stat { background: var(--bg-secondary); border: 1px solid var(--border-light); border-radius: var(--radius); padding: 12px 14px; box-shadow: var(--shadow-sm); }
.ks-val { font-size: 22px; font-weight: 700; color: var(--accent); line-height: 1.2; }
.ks-label { font-size: 12px; color: var(--text-primary); margin-top: 2px; }
.ks-sub { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
.kb-two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 900px) { .kb-two-col { grid-template-columns: 1fr; } }
.kb-bars { display: flex; flex-direction: column; gap: 6px; }
.kb-bar-row { display: flex; align-items: center; gap: 8px; font-size: 11.5px; }
.kb-bar-name { width: 110px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kb-bar-track { flex: 1; height: 8px; background: var(--bg-tertiary); border-radius: var(--radius-full); overflow: hidden; }
.kb-bar-fill { height: 100%; background: linear-gradient(90deg, var(--accent), var(--mint)); border-radius: var(--radius-full); }
.kb-bar-val { width: 34px; text-align: right; color: var(--text-muted); }
.kb-levels { display: flex; flex-direction: column; gap: 6px; }
.kb-level-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.kl-badge { color: #fff; font-size: 11px; border-radius: var(--radius-sm); padding: 1px 7px; }
.kl-label { color: var(--text-secondary); }
.kl-val { margin-left: auto; color: var(--text-primary); font-weight: 600; }
.kb-sources { display: flex; flex-wrap: wrap; gap: 6px; }
.kb-src-tag { font-size: 10.5px; }
.kb-dropzone { border: 1.5px dashed var(--border); border-radius: var(--radius); padding: 22px 14px; text-align: center; cursor: pointer; background: var(--bg-tertiary); transition: all var(--dur-fast) var(--ease-out); }
.kb-dropzone:hover, .kb-dropzone.dragover { border-color: var(--accent); background: var(--accent-soft); }
.dz-icon { font-size: 24px; }
.dz-text { font-size: 12.5px; color: var(--text-primary); margin-top: 6px; }
.dz-sub { font-size: 11px; color: var(--text-muted); margin-top: 3px; }
.kb-formats { margin: 12px 0 10px; }
.kb-fmt-title { font-size: 12px; color: var(--text-primary); margin-bottom: 4px; }
.kb-formats ul { margin: 0; padding-left: 18px; }
.kb-formats li { font-size: 11.5px; color: var(--text-secondary); line-height: 1.7; }
.kb-formats code { font-family: var(--font-mono); font-size: 11px; background: var(--bg-tertiary); border-radius: 4px; padding: 0 4px; }
.kb-paste-actions { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
.kb-pending { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 12px; padding: 8px 10px; background: var(--info-soft); border-radius: var(--radius-sm); }
.kp-pending-text { font-size: 11.5px; color: var(--text-primary); flex: 1; }
.kb-report-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 900px) { .kb-report-grid { grid-template-columns: 1fr; } }
.kb-report-block { background: var(--bg-tertiary); border-radius: var(--radius-sm); padding: 10px 12px; }
.krb-title { font-size: 12px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.krb-title.ok { color: var(--success); }
.krb-title.info { color: var(--info); }
.krb-title.warn { color: var(--warning); }
.krb-body { display: flex; flex-wrap: wrap; gap: 5px; }
.kb-chip { font-size: 11px; border-radius: var(--radius-full); padding: 1px 8px; background: var(--bg-secondary); border: 1px solid var(--border-light); color: var(--text-secondary); cursor: default; }
.kb-chip.ok { border-color: var(--success); color: var(--success); background: var(--success-soft); }
.kb-chip.info { border-color: var(--info); color: var(--info); background: var(--info-soft); }
.kb-chip.muted { color: var(--text-muted); }
.kb-conflict { width: 100%; font-size: 11px; color: var(--text-secondary); line-height: 1.6; }
.kc-entity { font-weight: 600; color: var(--text-primary); }
.kc-res { font-weight: 400; color: var(--warning); margin-left: 6px; }
.kc-line { color: var(--text-muted); }
.kb-report-tail { margin-top: 10px; font-size: 11.5px; color: var(--text-muted); }
.kb-relations-note { margin-left: 8px; font-weight: 400; color: var(--text-muted); }
.kb-entity { color: var(--accent); cursor: pointer; text-decoration: underline dotted; }
.kb-pager { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
.kb-page-info { font-size: 11.5px; color: var(--text-muted); }
.kb-match-meta { font-size: 11.5px; color: var(--text-muted); }
.kb-match-list { margin-top: 10px; display: flex; flex-direction: column; gap: 8px; }
.kb-match-item { background: var(--bg-tertiary); border-radius: var(--radius-sm); padding: 8px 10px; }
.km-name { font-size: 12.5px; font-weight: 600; color: var(--accent); }
.km-meta { font-size: 11px; color: var(--text-muted); margin-left: 8px; }
.km-alias { font-size: 11px; color: var(--apricot-strong); margin-left: 8px; }
.km-def { font-size: 11.5px; color: var(--text-secondary); margin-top: 3px; line-height: 1.55; }
.kb-profile-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.kb-profile { border: 1px solid var(--border-light); border-radius: var(--radius-sm); padding: 10px 12px; background: var(--bg-tertiary); }
.kb-profile.uncovered { opacity: 0.72; border-style: dashed; }
.kp-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.kp-name { font-size: 12.5px; font-weight: 600; color: var(--text-primary); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kp-coverage { font-size: 11px; color: var(--text-muted); margin: 6px 0; }
.kp-concepts { display: flex; flex-wrap: wrap; gap: 4px; }
.kb-link-item { border-left: 3px solid var(--accent); background: var(--bg-tertiary); border-radius: var(--radius-sm); padding: 10px 12px; margin-bottom: 10px; }
.kl-head { display: flex; align-items: center; justify-content: space-between; }
.kl-files { font-size: 12.5px; color: var(--text-primary); }
.kl-score { font-size: 14px; font-weight: 700; color: var(--accent); }
.kl-scores { font-size: 11px; color: var(--text-muted); margin: 3px 0 7px; }
.kl-block { margin-top: 6px; }
.kl-label { font-size: 11px; color: var(--text-muted); margin-right: 6px; }
.kl-bridge { display: flex; align-items: baseline; gap: 8px; font-size: 11px; color: var(--text-secondary); line-height: 1.6; }
.klb-path { color: var(--text-primary); white-space: nowrap; }
.klb-path i { color: var(--mint-strong); font-style: normal; }
.klb-hops { color: var(--text-muted); white-space: nowrap; }
.klb-evidence { color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; }
.kb-uncovered { margin-top: 10px; font-size: 11.5px; color: var(--warning); background: var(--warning-soft); border-radius: var(--radius-sm); padding: 8px 10px; }
.kb-neighbor { border-bottom: 1px dashed var(--border-light); padding: 7px 0; }
.kb-neighbor:last-child { border-bottom: none; }
.kn-head { display: flex; align-items: center; gap: 8px; }
.kn-name { font-size: 12.5px; font-weight: 600; color: var(--text-primary); }
.kn-weight { font-size: 11px; color: var(--text-muted); margin-left: auto; }
.kn-evidence { font-size: 11.5px; color: var(--text-secondary); margin-top: 3px; line-height: 1.55; }
</style>
