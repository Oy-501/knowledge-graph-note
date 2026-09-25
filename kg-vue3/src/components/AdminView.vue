<template>
  <div class="ad-view">
    <!-- 口令闸门 -->
    <div v-if="!token" class="ad-gate">
      <div class="ad-gate-card">
        <h2>后台管理</h2>
        <p>查看知识点判定依据、审阅候选知识点、回溯所有用户操作。请输入管理口令进入。</p>
        <el-input v-model="tokenInput" type="password" show-password placeholder="管理口令"
                  @keyup.enter="tryEnter" />
        <el-button type="primary" :loading="checking" style="margin-top:12px" @click="tryEnter">
          进入后台
        </el-button>
        <p class="ad-gate-tip">口令在后端 <code>.env</code> 的 <code>ADMIN_TOKEN</code> 配置（默认 kg-admin，请尽快修改）。</p>
      </div>
    </div>

    <template v-else>
      <header class="ad-head">
        <div>
          <h2>后台管理</h2>
          <p>这里是「用户操作依据」的完整台账：谁做了什么、为什么这样做、系统判定用了哪些证据。</p>
        </div>
        <div class="ad-head-actions">
          <el-button size="small" :loading="loading" @click="refreshAll">刷新</el-button>
          <el-button size="small" @click="logout">退出后台</el-button>
        </div>
      </header>

      <el-tabs v-model="tab" class="ad-tabs">
        <!-- ============ 概览 ============ -->
        <el-tab-pane label="概览" name="overview">
          <div class="ad-stat-grid">
            <div v-for="c in scaleCards" :key="c.label" class="ad-stat">
              <div class="as-val" :style="{ color: c.color }">{{ c.value }}</div>
              <div class="as-label">{{ c.label }}</div>
              <div class="as-sub">{{ c.sub }}</div>
            </div>
          </div>
          <div class="ad-two-col">
            <section class="ad-card">
              <h3>候选知识点判定</h3>
              <div class="ad-meter">
                <div v-for="m in candidateMeters" :key="m.label" class="ad-meter-row">
                  <span class="am-label">{{ m.label }}</span>
                  <div class="am-track"><div class="am-fill" :style="{ width: m.pct, background: m.color }"></div></div>
                  <span class="am-val">{{ m.value }}</span>
                </div>
              </div>
              <div class="ad-thresholds" v-if="overview?.thresholds">
                <el-tag size="small" effect="plain">自动采纳 ≥ {{ overview.thresholds.auto_accept }}</el-tag>
                <el-tag size="small" effect="plain" type="danger">驳回 &lt; {{ overview.thresholds.reject_below }}</el-tag>
                <el-tag size="small" effect="plain" :type="overview.thresholds.web_enabled ? 'success' : 'info'">
                  联网判定 {{ overview.thresholds.web_enabled ? '已启用' : '未启用' }}
                </el-tag>
                <el-tag size="small" effect="plain" type="warning">联网失败 {{ candidateStats.web_unavailable || 0 }} 条</el-tag>
              </div>
            </section>
            <section class="ad-card">
              <h3>近 {{ activity.window_days || 7 }} 天操作</h3>
              <div v-if="activity.total" class="ad-bars">
                <div v-for="(v, k) in activity.actions" :key="k" class="ad-bar-row">
                  <span class="ab-name">{{ actionLabels[k] || k }}</span>
                  <div class="ab-track"><div class="ab-fill" :style="{ width: barWidth(v) }"></div></div>
                  <span class="ab-val">{{ v }}</span>
                </div>
              </div>
              <el-empty v-else description="暂无操作记录" :image-size="60" />
              <p class="ad-hint">异常/警告记录：{{ activity.abnormal || 0 }} 条</p>
            </section>
          </div>
          <section class="ad-card" v-if="verdictStats">
            <h3>判定分数分布</h3>
            <div class="ad-bars">
              <div v-for="(v, k) in verdictStats.score_buckets" :key="k" class="ad-bar-row">
                <span class="ab-name">{{ k }}</span>
                <div class="ab-track"><div class="ab-fill" :style="{ width: bucketWidth(v) }"></div></div>
                <span class="ab-val">{{ v }}</span>
              </div>
            </div>
            <p class="ad-hint">
              人工复核覆盖 {{ ((verdictStats.human_rate || 0) * 100).toFixed(1) }}% ·
              自动判定占 {{ ((verdictStats.auto_rate || 0) * 100).toFixed(1) }}%
            </p>
          </section>
        </el-tab-pane>

        <!-- ============ 知识点审阅 ============ -->
        <el-tab-pane label="知识点审阅" name="review">
          <section class="ad-card">
            <h3>
              候选知识点
              <span class="ad-count">{{ candTotal }}</span>
              <span class="ad-tools">
                <el-select v-model="filters.status" size="small" style="width:110px" @change="loadCandidates">
                  <el-option label="全部状态" value="" />
                  <el-option label="待审" value="open" />
                  <el-option label="已采纳" value="accepted" />
                  <el-option label="已驳回" value="rejected" />
                </el-select>
                <el-select v-model="filters.decision" size="small" style="width:110px" @change="loadCandidates">
                  <el-option label="全部判定" value="" />
                  <el-option label="建议采纳" value="accept" />
                  <el-option label="需人工确认" value="pending" />
                  <el-option label="建议驳回" value="reject" />
                </el-select>
                <el-select v-model="filters.web" size="small" style="width:130px" @change="loadCandidates">
                  <el-option label="联网校验不限" value="" />
                  <el-option label="联网成功" value="ok" />
                  <el-option label="联网不可用" value="unavailable" />
                </el-select>
                <el-input v-model="filters.keyword" size="small" style="width:150px"
                          placeholder="搜索知识点" clearable @keyup.enter="loadCandidates" />
                <el-button size="small" @click="loadCandidates">筛选</el-button>
              </span>
            </h3>

            <div class="ad-bulk">
              <el-button size="small" type="primary" plain :loading="busy === 'verify'"
                         @click="rerunVerify">重跑智能判定（含联网）</el-button>
              <el-button size="small" type="success" plain :loading="busy === 'accept'"
                         @click="bulk('accept')">批量采纳当前筛选（前 100 条）</el-button>
              <el-button size="small" type="danger" plain :loading="busy === 'reject'"
                         @click="bulk('reject')">批量驳回</el-button>
            </div>

            <el-table :data="candidates" size="small" v-loading="loadingCands"
                      @row-click="openDetail" style="cursor:pointer">
              <el-table-column prop="entity" label="知识点" min-width="150" show-overflow-tooltip />
              <el-table-column label="判定" width="118">
                <template #default="{ row }">
                  <el-tag size="small" :type="decisionTagType(row.decision)" effect="dark">
                    {{ decisionLabel(row.decision) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="分数" width="70">
                <template #default="{ row }">{{ row.score ?? '—' }}</template>
              </el-table-column>
              <el-table-column label="联网" width="86">
                <template #default="{ row }">
                  <span class="ad-web" :class="row.web">{{ webLabel(row.web) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="来源文件" min-width="130">
                <template #default="{ row }">
                  {{ fileNames[row.file_id] || '—' }}
                  <span v-if="row.chunk_index" class="ad-chunk">第{{ row.chunk_index + 1 }}片</span>
                </template>
              </el-table-column>
              <el-table-column label="阶段" width="80">
                <template #default="{ row }">
                  <span class="ad-stage" :class="row.stage">{{ row.stage === 'human' ? '人工' : '自动' }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="reason" label="依据摘要" min-width="240" show-overflow-tooltip />
            </el-table>

            <div class="ad-pager">
              <el-button size="small" :disabled="candOffset === 0" @click="page(-1)">上一页</el-button>
              <span>{{ candOffset + 1 }} - {{ Math.min(candOffset + 30, candTotal) }} / {{ candTotal }}</span>
              <el-button size="small" :disabled="candOffset + 30 >= candTotal" @click="page(1)">下一页</el-button>
            </div>
          </section>
        </el-tab-pane>

        <!-- ============ 操作审计 ============ -->
        <el-tab-pane label="操作审计" name="audit">
          <section class="ad-card">
            <h3>
              操作台账
              <span class="ad-count">{{ auditTotal }}</span>
              <span class="ad-tools">
                <el-select v-model="auditFilters.action" size="small" style="width:140px" @change="loadAudit">
                  <el-option label="全部动作" value="" />
                  <el-option v-for="a in auditActions" :key="a" :label="actionLabels[a] || a" :value="a" />
                </el-select>
                <el-select v-model="auditFilters.actor" size="small" style="width:110px" @change="loadAudit">
                  <el-option label="全部来源" value="" />
                  <el-option label="用户" value="user" />
                  <el-option label="管理员" value="admin" />
                  <el-option label="系统" value="system" />
                </el-select>
                <el-input v-model="auditFilters.keyword" size="small" style="width:150px"
                          placeholder="搜索摘要/对象" clearable @keyup.enter="loadAudit" />
                <el-button size="small" @click="loadAudit">筛选</el-button>
              </span>
            </h3>
            <el-table :data="auditLogs" size="small" v-loading="loadingAudit"
                      @row-click="openAudit" style="cursor:pointer">
              <el-table-column prop="id" label="#" width="70" />
              <el-table-column label="时间" width="140">
                <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
              </el-table-column>
              <el-table-column label="动作" width="110">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.status === 'ok' ? 'info' : 'warning'" effect="plain">
                    {{ row.action_label }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="actor" label="来源" width="80" />
              <el-table-column prop="summary" label="依据摘要（做了什么 / 为什么）" min-width="320" show-overflow-tooltip />
              <el-table-column label="耗时" width="80">
                <template #default="{ row }">{{ row.duration_ms ? row.duration_ms + 'ms' : '—' }}</template>
              </el-table-column>
            </el-table>
            <div class="ad-pager">
              <el-button size="small" :disabled="auditOffset === 0" @click="auditPage(-1)">上一页</el-button>
              <span>{{ auditOffset + 1 }} - {{ Math.min(auditOffset + 30, auditTotal) }} / {{ auditTotal }}</span>
              <el-button size="small" :disabled="auditOffset + 30 >= auditTotal" @click="auditPage(1)">下一页</el-button>
            </div>
          </section>
        </el-tab-pane>

        <!-- ============ 用户与文件 ============ -->
        <el-tab-pane label="用户与文件" name="users">
          <section class="ad-card">
            <h3>用户</h3>
            <el-table :data="users" size="small">
              <el-table-column label="用户" min-width="140">
                <template #default="{ row }">
                  <span class="ad-user">{{ row.display_name || row.username }}</span>
                  <span class="ad-user-id">#{{ row.id }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="files" label="文件" width="80" />
              <el-table-column prop="nodes" label="知识点" width="90" />
              <el-table-column prop="candidates" label="候选" width="80" />
              <el-table-column prop="audit_rows" label="操作数" width="90" />
              <el-table-column label="最近活动" width="150">
                <template #default="{ row }">{{ fmtTime(row.last_active) }}</template>
              </el-table-column>
            </el-table>
          </section>
          <section class="ad-card">
            <h3>文件与解析情况</h3>
            <el-table :data="adminFiles" size="small">
              <el-table-column prop="name" label="文件" min-width="180" show-overflow-tooltip />
              <el-table-column prop="node_count" label="知识点" width="90" />
              <el-table-column label="候选判定" min-width="200">
                <template #default="{ row }">
                  <el-tag v-for="(v, k) in row.candidate_stats" :key="k" size="small" effect="plain"
                          style="margin-right:4px">{{ statusLabel(k) }} {{ v }}</el-tag>
                  <span v-if="!row.candidate_stats || !Object.keys(row.candidate_stats).length">—</span>
                </template>
              </el-table-column>
              <el-table-column prop="parse_note" label="解析备注（切割/截断）" min-width="280" show-overflow-tooltip />
            </el-table>
          </section>
        </el-tab-pane>
      </el-tabs>

      <!-- 候选详情抽屉：完整证据链 -->
      <el-drawer v-model="detailVisible" size="620px" :title="detail?.entity || '候选详情'">
        <div v-if="detail" class="ad-detail">
          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="判定">
              <el-tag size="small" :type="decisionTagType(detail.decision)" effect="dark">
                {{ decisionLabel(detail.decision) }}
              </el-tag>
              <span class="ad-score">{{ detail.score }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="阶段">{{ detail.stage === 'human' ? '人工判定' : '智能判定' }}</el-descriptions-item>
            <el-descriptions-item label="领域">{{ detail.domain }}</el-descriptions-item>
            <el-descriptions-item label="层级">L{{ detail.level }}</el-descriptions-item>
            <el-descriptions-item label="来源文件">{{ detail.file_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="位置">
              第{{ (detail.chunk_index || 0) + 1 }}片 · 第{{ detail.line_start }}行
            </el-descriptions-item>
          </el-descriptions>

          <h4>判定依据（证据链）</h4>
          <div class="ad-evidence">
            <div v-for="(e, i) in (detail.evidence || [])" :key="i" class="ad-ev"
                 :class="{ neg: !e.positive, zero: !e.weight }">
              <span class="aev-type">{{ evidenceType(e.type) }}</span>
              <span class="aev-weight" :class="{ pos: e.weight > 0, neg: e.weight < 0 }">
                {{ e.weight > 0 ? '+' : '' }}{{ e.weight }}
              </span>
              <span class="aev-detail">{{ e.detail }}</span>
              <a v-if="e.url" :href="e.url" target="_blank" class="aev-link">来源</a>
            </div>
            <div v-if="!detail.evidence?.length" class="ad-hint">暂无证据（未判定）</div>
          </div>

          <h4>原文明细</h4>
          <div class="ad-source">{{ detail.source_text || '（无）' }}</div>

          <h4>人工裁决</h4>
          <el-input v-model="reviewNote" type="textarea" :rows="2" placeholder="裁决说明（会写入审计，作为依据留档）" />
          <div class="ad-review-actions">
            <el-button type="success" :loading="busy === 'accept1'" @click="review('accept')">采纳并入库</el-button>
            <el-button type="danger" :loading="busy === 'reject1'" @click="review('reject')">驳回</el-button>
            <el-button :loading="busy === 'pending1'" @click="review('pending')">转待审</el-button>
            <el-button @click="rerunOne">重跑智能判定</el-button>
          </div>
          <p v-if="detail.reviewed_by" class="ad-hint">
            最近裁决：{{ detail.reviewed_by }} · {{ fmtTime(detail.reviewed_at) }}
            <span v-if="detail.review_note"> · {{ detail.review_note }}</span>
          </p>
        </div>
      </el-drawer>

      <!-- 审计详情抽屉 -->
      <el-drawer v-model="auditVisible" size="560px" :title="auditDetail?.action_label || '操作详情'">
        <div v-if="auditDetail" class="ad-detail">
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="摘要">{{ auditDetail.summary }}</el-descriptions-item>
            <el-descriptions-item label="来源">{{ auditDetail.actor }} · 用户 #{{ auditDetail.user_id }}</el-descriptions-item>
            <el-descriptions-item label="时间">{{ fmtTime(auditDetail.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="对象">
              {{ auditDetail.target_type }}#{{ auditDetail.target_id }} {{ auditDetail.target_name }}
            </el-descriptions-item>
          </el-descriptions>
          <h4>依据明细</h4>
          <pre class="ad-json">{{ JSON.stringify(auditDetail.detail, null, 2) }}</pre>
        </div>
      </el-drawer>
    </template>
  </div>
</template>

<script setup>
/**
 * AdminView.vue
 * 后台管理：口令闸门 + 概览 + 候选知识点审阅（含证据链）+ 操作审计（含依据明细）+ 用户与文件。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminAPI } from '@/api/index'

const TOKEN_KEY = 'kg-admin-token'
const token = ref('')
const tokenInput = ref('')
const checking = ref(false)

const tab = ref('overview')
const loading = ref(false)
const busy = ref('')

const overview = ref(null)
const verdictStats = ref(null)
const candidates = ref([])
const candTotal = ref(0)
const candOffset = ref(0)
const loadingCands = ref(false)
const fileNames = ref({})
const auditLogs = ref([])
const auditTotal = ref(0)
const auditOffset = ref(0)
const auditActions = ref([])
const loadingAudit = ref(false)
const users = ref([])
const adminFiles = ref([])
const detail = ref(null)
const detailVisible = ref(false)
const auditDetail = ref(null)
const auditVisible = ref(false)
const reviewNote = ref('')

const filters = ref({ status: 'open', decision: '', web: '', keyword: '' })
const auditFilters = ref({ action: '', actor: '', keyword: '' })

const candidateStats = computed(() => overview.value?.candidates || {})
const activity = computed(() => overview.value?.activity || {})
const actionLabels = computed(() => auditLabels.value || {})
const auditLabels = ref({})

const scaleCards = computed(() => {
  const s = overview.value?.scale || {}
  return [
    { label: '用户', value: s.users ?? 0, sub: '个', color: 'var(--accent)' },
    { label: '文件', value: s.files ?? 0, sub: '个', color: 'var(--mint-strong)' },
    { label: '知识点', value: s.nodes ?? 0, sub: '个', color: 'var(--apricot-strong)' },
    { label: '连线', value: s.links ?? 0, sub: '条', color: '#8E7BA8' },
    { label: '知识库条目', value: s.kb_entries ?? 0, sub: '条', color: 'var(--info)' },
    { label: '审计记录', value: s.audit_rows ?? 0, sub: '条', color: 'var(--text-muted)' },
  ]
})

const candidateMeters = computed(() => {
  const c = candidateStats.value
  const total = Math.max(1, c.total || 1)
  return [
    { label: '已采纳', value: c.accepted ?? 0, pct: `${((c.accepted || 0) / total) * 100}%`, color: 'var(--mint-strong)' },
    { label: '待审', value: c.pending ?? 0, pct: `${((c.pending || 0) / total) * 100}%`, color: 'var(--apricot-strong)' },
    { label: '已驳回', value: c.rejected ?? 0, pct: `${((c.rejected || 0) / total) * 100}%`, color: 'var(--danger)' },
  ]
})

const maxAction = computed(() => Math.max(1, ...Object.values(activity.value.actions || {})))
const maxBucket = computed(() => Math.max(1, ...Object.values(verdictStats.value?.score_buckets || {})))

const barWidth = (v) => `${Math.max(2, (v / maxAction.value) * 100)}%`
const bucketWidth = (v) => `${Math.max(2, (v / maxBucket.value) * 100)}%`

const decisionLabel = (d) => ({ accept: '建议采纳', reject: '建议驳回', pending: '需人工确认' }[d] || d)
const decisionTagType = (d) => ({ accept: 'success', reject: 'danger', pending: 'warning' }[d] || 'info')
const webLabel = (w) => ({ ok: '已联网', unavailable: '未联网', skipped: '未启用' }[w] || w)
const statusLabel = (s) => ({ open: '待审', accepted: '采纳', rejected: '驳回' }[s] || s)
const evidenceType = (t) => ({
  kb: '知识库', graph: '图谱', rule: '文本规则', web: '联网检索', 'web-sample': '检索样例'
}[t] || t)

function fmtTime(iso) {
  return iso ? iso.replace('T', ' ').slice(0, 16) : '—'
}

// ---- 口令 ----
async function tryEnter() {
  if (!tokenInput.value.trim()) {
    ElMessage.warning('请输入管理口令')
    return
  }
  checking.value = true
  try {
    await adminAPI.auth(tokenInput.value.trim())
    token.value = tokenInput.value.trim()
    localStorage.setItem(TOKEN_KEY, token.value)
    ElMessage.success('已进入后台')
    await refreshAll()
  } catch (e) {
    ElMessage.error(e.message || '口令不正确')
  } finally {
    checking.value = false
  }
}

function logout() {
  token.value = ''
  tokenInput.value = ''
  localStorage.removeItem(TOKEN_KEY)
}

// ---- 数据加载 ----
async function refreshAll() {
  loading.value = true
  try {
    const [ov, vs, us, fs] = await Promise.all([
      adminAPI.overview(token.value),
      adminAPI.verdictStats(token.value),
      adminAPI.users(token.value),
      adminAPI.adminFiles(token.value)
    ])
    overview.value = ov
    verdictStats.value = vs
    users.value = us.users || []
    adminFiles.value = fs.files || []
    await Promise.all([loadCandidates(), loadAudit()])
  } catch (e) {
    ElMessage.error(e.message || '加载失败（口令可能已失效）')
    if (String(e.message || '').includes('口令')) logout()
  } finally {
    loading.value = false
  }
}

async function loadCandidates() {
  loadingCands.value = true
  try {
    const data = await adminAPI.candidates(token.value, {
      ...filters.value, limit: 30, offset: candOffset.value
    })
    candidates.value = data.candidates || []
    candTotal.value = data.total || 0
    fileNames.value = data.files || {}
  } catch (e) {
    ElMessage.error(e.message || '候选加载失败')
  } finally {
    loadingCands.value = false
  }
}

function page(dir) {
  candOffset.value = Math.max(0, candOffset.value + dir * 30)
  loadCandidates()
}

async function loadAudit() {
  loadingAudit.value = true
  try {
    const data = await adminAPI.audit(token.value, {
      ...auditFilters.value, limit: 30, offset: auditOffset.value
    })
    auditLogs.value = data.logs || []
    auditTotal.value = data.total || 0
    auditActions.value = data.actions || []
    auditLabels.value = data.labels || {}
  } catch (e) {
    ElMessage.error(e.message || '审计加载失败')
  } finally {
    loadingAudit.value = false
  }
}

function auditPage(dir) {
  auditOffset.value = Math.max(0, auditOffset.value + dir * 30)
  loadAudit()
}

async function openDetail(row) {
  try {
    const data = await adminAPI.candidateDetail(token.value, row.id)
    detail.value = data.candidate
    reviewNote.value = ''
    detailVisible.value = true
  } catch (e) {
    ElMessage.error(e.message || '详情加载失败')
  }
}

async function openAudit(row) {
  try {
    const data = await adminAPI.auditDetail(token.value, row.id)
    auditDetail.value = data.log
    auditVisible.value = true
  } catch (e) {
    ElMessage.error(e.message || '详情加载失败')
  }
}

// ---- 裁决 ----
async function review(action) {
  if (!detail.value) return
  busy.value = action === 'accept' ? 'accept1' : action === 'reject' ? 'reject1' : 'pending1'
  try {
    const res = await adminAPI.review(token.value, detail.value.id, {
      action, note: reviewNote.value, reviewer: 'admin', ingest: action === 'accept'
    })
    ElMessage.success(`已${action === 'accept' ? '采纳' : action === 'reject' ? '驳回' : '转待审'}` +
      (res.ingested_kb_entry_id ? `，知识库条目 #${res.ingested_kb_entry_id}` : ''))
    detailVisible.value = false
    await refreshAll()
  } catch (e) {
    ElMessage.error(e.message || '裁决失败')
  } finally {
    busy.value = ''
  }
}

async function rerunOne() {
  if (!detail.value) return
  busy.value = 'verify1'
  try {
    const res = await adminAPI.verify(token.value, { ids: [detail.value.id], use_web: true })
    ElMessage.success(`已重跑判定：${JSON.stringify(res.stats)}`)
    await openDetail({ id: detail.value.id })
    await refreshAll()
  } catch (e) {
    ElMessage.error(e.message || '重跑失败')
  } finally {
    busy.value = ''
  }
}

async function rerunVerify() {
  busy.value = 'verify'
  try {
    const res = await adminAPI.verify(token.value, {
      status: filters.value.status || 'open', limit: 50, use_web: true
    })
    ElMessage.success(`判定完成：采纳 ${res.stats.accept} / 待审 ${res.stats.pending} / 驳回 ${res.stats.reject}`)
    await refreshAll()
  } catch (e) {
    ElMessage.error(e.message || '重跑失败')
  } finally {
    busy.value = ''
  }
}

async function bulk(action) {
  try {
    await ElMessageBox.confirm(
      `将对当前筛选条件下最多 100 条候选执行「${action === 'accept' ? '采纳并入库' : '驳回'}」，操作会写入审计。确认继续？`,
      '批量操作', { type: 'warning' }
    )
  } catch { return }
  busy.value = action
  try {
    const res = await adminAPI.bulkReview(token.value, {
      status: filters.value.status, decision: filters.value.decision,
      limit: 100, action, note: '后台批量操作', reviewer: 'admin', ingest: action === 'accept'
    })
    ElMessage.success(`已处理 ${res.count} 条`)
    await refreshAll()
  } catch (e) {
    ElMessage.error(e.message || '批量操作失败')
  } finally {
    busy.value = ''
  }
}

onMounted(() => {
  const saved = localStorage.getItem(TOKEN_KEY)
  if (saved) {
    token.value = saved
    tokenInput.value = saved
    refreshAll()
  }
})
</script>

<style scoped>
.ad-view { flex: 1; min-width: 0; padding: 16px 20px 40px; height: 100%; overflow-y: auto; background: var(--bg-primary); }

.ad-gate { display: flex; align-items: center; justify-content: center; height: 100%; }
.ad-gate-card {
  width: 420px; padding: 26px 28px; text-align: center;
  background: var(--bg-secondary); border: 1px solid var(--border-light);
  border-radius: var(--radius-lg); box-shadow: var(--shadow-md);
}
.ad-gate-card h2 { margin: 0 0 8px; font-size: 18px; color: var(--text-primary); }
.ad-gate-card p { font-size: 12.5px; color: var(--text-secondary); line-height: 1.7; margin: 0 0 16px; }
.ad-gate-tip { font-size: 11px; color: var(--text-muted); margin-top: 14px !important; }
.ad-gate-tip code { background: var(--bg-tertiary); padding: 1px 5px; border-radius: 4px; font-family: var(--font-mono); }

.ad-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.ad-head h2 { margin: 0 0 6px; font-size: 18px; color: var(--text-primary); }
.ad-head p { margin: 0; max-width: 680px; font-size: 12.5px; color: var(--text-secondary); line-height: 1.6; }
.ad-head-actions { display: flex; gap: 8px; }
.ad-tabs { margin-top: 8px; }

.ad-card {
  background: var(--bg-secondary); border: 1px solid var(--border-light);
  border-radius: var(--radius); padding: 14px 16px; margin-bottom: 14px; box-shadow: var(--shadow-sm);
}
.ad-card h3 { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 0 0 12px; font-size: 13.5px; color: var(--text-primary); }
.ad-card h4 { margin: 16px 0 8px; font-size: 12.5px; color: var(--text-primary); }
.ad-count { font-size: 11px; color: var(--text-muted); background: var(--bg-tertiary); border-radius: var(--radius-full); padding: 1px 8px; }
.ad-tools { margin-left: auto; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ad-hint { font-size: 11.5px; color: var(--text-muted); line-height: 1.6; margin: 10px 0 0; }

.ad-stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 14px; }
.ad-stat { background: var(--bg-secondary); border: 1px solid var(--border-light); border-radius: var(--radius); padding: 12px 14px; box-shadow: var(--shadow-sm); }
.as-val { font-size: 22px; font-weight: 700; line-height: 1.15; }
.as-label { font-size: 12px; color: var(--text-primary); margin-top: 2px; }
.as-sub { font-size: 11px; color: var(--text-muted); }

.ad-two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 1000px) { .ad-two-col { grid-template-columns: 1fr; } }

.ad-meter, .ad-bars { display: flex; flex-direction: column; gap: 7px; }
.ad-meter-row, .ad-bar-row { display: flex; align-items: center; gap: 8px; font-size: 11.5px; }
.am-label, .ab-name { width: 96px; color: var(--text-secondary); }
.am-track, .ab-track { flex: 1; height: 8px; background: var(--bg-tertiary); border-radius: var(--radius-full); overflow: hidden; }
.am-fill, .ab-fill { height: 100%; border-radius: var(--radius-full); }
.ab-fill { background: linear-gradient(90deg, var(--accent), var(--mint)); }
.am-val, .ab-val { width: 40px; text-align: right; color: var(--text-muted); }
.ad-thresholds { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 12px; }

.ad-bulk { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
.ad-pager { display: flex; align-items: center; gap: 10px; margin-top: 10px; font-size: 11.5px; color: var(--text-muted); }

.ad-web { font-size: 11px; }
.ad-web.ok { color: var(--success); }
.ad-web.unavailable { color: var(--warning); }
.ad-web.skipped { color: var(--text-muted); }
.ad-chunk { font-size: 10px; color: var(--text-muted); margin-left: 4px; }
.ad-stage { font-size: 11px; }
.ad-stage.human { color: var(--apricot-strong); }
.ad-stage.auto { color: var(--text-muted); }
.ad-user { font-size: 12.5px; color: var(--text-primary); }
.ad-user-id { font-size: 11px; color: var(--text-muted); margin-left: 6px; }

.ad-detail :deep(.el-descriptions) { margin-bottom: 8px; }
.ad-score { margin-left: 8px; font-weight: 700; color: var(--accent); }
.ad-evidence { display: flex; flex-direction: column; gap: 6px; }
.ad-ev {
  display: flex; align-items: baseline; gap: 8px; font-size: 11.5px;
  padding: 6px 9px; border-radius: var(--radius-sm); background: var(--bg-tertiary);
  border-left: 3px solid var(--mint);
}
.ad-ev.neg { border-left-color: var(--danger); }
.ad-ev.zero { border-left-color: var(--border); color: var(--text-muted); }
.aev-type { font-size: 10.5px; color: var(--text-muted); min-width: 54px; }
.aev-weight { font-family: var(--font-mono); font-size: 11px; min-width: 38px; }
.aev-weight.pos { color: var(--success); }
.aev-weight.neg { color: var(--danger); }
.aev-detail { flex: 1; color: var(--text-secondary); line-height: 1.55; }
.aev-link { font-size: 10.5px; color: var(--accent); }
.ad-source {
  max-height: 160px; overflow-y: auto; font-size: 11.5px; line-height: 1.7;
  color: var(--text-secondary); background: var(--bg-tertiary);
  border-radius: var(--radius-sm); padding: 8px 10px; white-space: pre-wrap;
}
.ad-review-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.ad-json {
  max-height: 420px; overflow: auto; font-family: var(--font-mono); font-size: 11px;
  line-height: 1.55; color: var(--text-secondary); background: var(--bg-tertiary);
  border-radius: var(--radius-sm); padding: 10px; white-space: pre-wrap; word-break: break-all;
}
</style>
