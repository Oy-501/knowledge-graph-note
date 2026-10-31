<!-- 学习提醒：今日到期复习、自评推进间隔（SM-2）、可解释推荐与信息来源。 -->
<template>
  <div class="learn-view">
    <header class="learn-head">
      <div>
        <h2>学习提醒</h2>
        <p>加入复习计划的知识到期后会在这里提醒你回看；今日推荐按学习掌握度、遗忘程度与来源质量排序。</p>
      </div>
      <div class="learn-actions">
        <button @click="copyMarkdown">复制 Markdown</button>
        <button @click="downloadMarkdown">下载 .md</button>
        <button @click="openGist">GitHub Gist</button>
        <span v-if="notice" class="learn-notice">{{ notice }}</span>
      </div>
    </header>

    <div class="learn-stats">
      <div class="u-surface"><strong>{{ stats.total }}</strong><span>在学</span></div>
      <div class="u-surface"><strong>{{ stats.due }}</strong><span>今日到期</span></div>
      <div class="u-surface"><strong>{{ stats.mastered }}</strong><span>已掌握</span></div>
    </div>

    <section class="learn-block">
      <h3>今日待复习</h3>
      <div v-if="loading" class="learn-empty">加载中…</div>
      <div v-else-if="!items.length" class="learn-empty">
        今天没有到期内容。上传并通过判定的知识会自动出现在这里。
      </div>
      <article v-for="item in items" :key="item.id" class="learn-item u-surface">
        <div class="learn-meta">
          <strong>{{ item.title || '未命名知识点' }}</strong>
          <small>第 {{ item.review_count + 1 }} 次 · 当前间隔 {{ item.interval_days }} 天</small>
        </div>
        <div class="learn-grades">
          <button @click="grade(item, 2)">没记住</button>
          <button @click="grade(item, 3)">一般</button>
          <button @click="grade(item, 5)">熟练</button>
        </div>
      </article>
    </section>

    <section class="learn-block">
      <div class="rec-head">
        <h3>今日推荐</h3>
        <small>推荐分由 5 个可验证指标加权求和，点开每条可看代入值与贡献。</small>
      </div>

      <div v-if="rec.formula" class="formula-card u-surface">
        <strong class="formula-expr">{{ rec.formula.expression }}</strong>
        <p class="formula-range">取值范围 {{ rec.formula.range }}，权重合计 1；所有分项都取自当前学习数据。</p>
        <div class="formula-terms">
          <span v-for="term in rec.formula.terms" :key="term.key" :title="term.detail">
            {{ term.key }} · {{ term.name }}
          </span>
        </div>
        <details class="formula-detail">
          <summary>公式定义与依据</summary>
          <ul>
            <li v-for="term in rec.formula.terms" :key="term.key">
              <b>{{ term.key }} {{ term.name }}</b>：{{ term.definition }}。{{ term.detail }}
            </li>
          </ul>
          <ul class="formula-basis">
            <li v-for="basis in rec.formula.basis" :key="basis.claim">
              <a :href="basis.url" target="_blank" rel="noopener noreferrer">{{ basis.claim }}</a>
              —— {{ basis.source }}
            </li>
          </ul>
        </details>
      </div>

      <div v-if="recLoading" class="learn-empty">正在计算推荐…</div>
      <div v-else-if="!rec.items.length" class="learn-empty">
        {{ rec.message || '暂无可推荐的知识点，先上传文档或加入复习计划。' }}
      </div>

      <article v-for="item in rec.items" :key="item.node_id" class="rec-item u-surface">
        <div class="rec-top">
          <span class="rec-rank">#{{ item.rank }}</span>
          <strong class="rec-title">{{ item.title }}</strong>
          <span class="rec-score">{{ item.score.toFixed(3) }}</span>
          <button v-if="!item.tracked" class="rec-add" @click="addToPlan(item)">加入复习</button>
          <small v-else class="rec-tracked">
            已加入复习{{ item.overdue_days > 0 ? ` · 逾期 ${Math.round(item.overdue_days)} 天` : '' }}
          </small>
        </div>

        <p class="rec-reason">{{ item.reason }}</p>

        <div class="rec-bars">
          <span v-for="key in componentKeys" :key="key" class="rec-bar">
            <i>{{ termLabel(key) }}</i>
            <b>{{ item.contributions[key].toFixed(2) }}</b>
          </span>
        </div>

        <details class="rec-detail">
          <summary>评分明细与代入值</summary>
          <table>
            <thead>
              <tr><th>分项</th><th>代入值</th><th>权重</th><th>贡献</th></tr>
            </thead>
            <tbody>
              <tr v-for="key in componentKeys" :key="key">
                <td>{{ termLabel(key) }}</td>
                <td>{{ item.components[key].toFixed(3) }}</td>
                <td>{{ rec.weights[key] }}</td>
                <td>{{ item.contributions[key].toFixed(3) }}</td>
              </tr>
              <tr class="rec-total">
                <td>合计</td><td>—</td><td>1.00</td><td>{{ item.score.toFixed(3) }}</td>
              </tr>
            </tbody>
          </table>
        </details>

        <div class="rec-sources">
          <span class="rec-src-label">信息来源：</span>
          <template v-if="item.sources.length">
            <span v-for="source in item.sources" :key="source.title + source.url" class="rec-src">
              <a v-if="source.url" :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.title }}</a>
              <span v-else>{{ source.title }}</span>
              <em>{{ source.provider }} · {{ Math.round(source.confidence * 100) }}%</em>
              <span v-if="source.snippet" class="rec-src-snippet">{{ source.snippet }}</span>
            </span>
          </template>
          <span v-else class="rec-src-empty">暂无来源，建议补充原文或联网校验</span>
        </div>
      </article>

      <div v-if="rec.evaluation" class="eval-card u-surface">
        <strong>推荐有效性回测</strong>
        <template v-if="rec.evaluation.insufficient">
          <p>{{ rec.evaluation.reason }}</p>
        </template>
        <template v-else>
          <p>
            Precision@{{ rec.evaluation.k }} = <b>{{ rec.evaluation.precision_at_k }}</b>，
            随机基线 {{ rec.evaluation.random_baseline }}，
            Lift = <b>{{ rec.evaluation.lift }}×</b>
            （样本 {{ rec.evaluation.sample_size }}，命中 {{ rec.evaluation.hits }} / {{ rec.evaluation.positives }} 条到期项）
          </p>
          <p class="eval-note">{{ rec.evaluation.method }}。{{ rec.evaluation.note }}</p>
        </template>
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { learningAPI } from '@/api'

const stats = ref({ total: 0, due: 0, mastered: 0 })
const items = ref([])
const loading = ref(false)

const rec = ref({ items: [], formula: null, weights: {}, evaluation: null })
const recLoading = ref(false)
const notice = ref('')

const componentKeys = ['weakness', 'urgency', 'centrality', 'frontier', 'source']
const TERM_LABELS = {
  weakness: '遗忘缺口',
  urgency: '到期紧迫',
  centrality: '图谱核心度',
  frontier: '学习前沿',
  source: '来源质量'
}

function termLabel(key) {
  return TERM_LABELS[key] || key
}

async function load() {
  loading.value = true
  try {
    const [summary, due] = await Promise.all([learningAPI.stats(), learningAPI.due(50)])
    stats.value = summary
    items.value = due.items || []
  } finally {
    loading.value = false
  }
  await loadRecommendations()
}

async function loadRecommendations() {
  recLoading.value = true
  try {
    rec.value = await learningAPI.recommendations(6)
  } catch (error) {
    rec.value = { items: [], formula: null, weights: {}, evaluation: null,
      message: '推荐加载失败：' + (error?.message || '未知错误') }
  } finally {
    recLoading.value = false
  }
}

async function grade(item, quality) {
  await learningAPI.review(item.id, quality)
  await load()
}

async function addToPlan(item) {
  await learningAPI.add({ node_id: item.node_id, title: item.title })
  notice.value = '已加入复习计划'
  setTimeout(() => { notice.value = '' }, 2000)
  await load()
}

function buildMarkdown() {
  const payload = rec.value
  const lines = [`# 学习推荐 · ${new Date().toLocaleDateString('zh-CN')}`, '']
  if (payload.formula) {
    lines.push(`> 推荐公式：${payload.formula.expression}`, '')
  }
  if (payload.evaluation && !payload.evaluation.insufficient) {
    lines.push(`> 回测：Precision@${payload.evaluation.k} = ${payload.evaluation.precision_at_k}，Lift = ${payload.evaluation.lift}×（样本 ${payload.evaluation.sample_size}）`, '')
  }
  for (const item of payload.items) {
    lines.push(`## ${item.rank}. ${item.title}（推荐分 ${item.score.toFixed(3)}）`, '')
    lines.push(`- 推荐理由：${item.reason}`)
    if (item.domain) lines.push(`- 领域：${item.domain}`)
    const parts = componentKeys.map(key => `${termLabel(key)} ${item.contributions[key].toFixed(2)}`)
    lines.push(`- 分项贡献：${parts.join('，')}`)
    if (item.sources.length) {
      lines.push('- 信息来源：')
      for (const source of item.sources) {
        const suffix = source.provider ? ` — ${source.provider}（${Math.round(source.confidence * 100)}%）` : ''
        lines.push(source.url ? `  - [${source.title}](${source.url})${suffix}` : `  - ${source.title}${suffix}`)
      }
    } else {
      lines.push('- 信息来源：暂无（建议补充原文或联网校验）')
    }
    lines.push('')
  }
  if (payload.formula) {
    lines.push('## 公式说明', '')
    for (const term of payload.formula.terms) {
      lines.push(`- **${term.key} ${term.name}**：${term.definition}。${term.detail}`)
    }
    lines.push('', '## 公式依据', '')
    for (const basis of payload.formula.basis) {
      lines.push(`- [${basis.claim}](${basis.url}) — ${basis.source}`)
    }
  }
  return lines.join('\n')
}

async function copyMarkdown() {
  const text = buildMarkdown()
  try {
    await navigator.clipboard.writeText(text)
    notice.value = 'Markdown 已复制'
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    notice.value = 'Markdown 已复制'
  }
  setTimeout(() => { notice.value = '' }, 2000)
}

function downloadMarkdown() {
  const blob = new Blob([buildMarkdown()], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `学习推荐-${new Date().toISOString().slice(0, 10)}.md`
  link.click()
  URL.revokeObjectURL(url)
  notice.value = '已下载 Markdown'
  setTimeout(() => { notice.value = '' }, 2000)
}

function openGist() {
  // 无 GitHub 凭据时走「先复制/下载，再打开 Gist 新建页粘贴」的路径，
  // 避免为了分享强制用户配置 token 或 OAuth。
  copyMarkdown()
  window.open('https://gist.github.com/', '_blank', 'noopener,noreferrer')
}

onMounted(load)
</script>

<style scoped>
.learn-view { padding: 20px 24px; display: flex; flex-direction: column; gap: 18px; }
.learn-head { display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.learn-head h2 { margin: 0; font-size: var(--fs-lg, 20px); }
.learn-head p { margin: 4px 0 0; color: var(--text-secondary); font-size: var(--fs-sm, 13px); max-width: 640px; }
.learn-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.learn-actions button { border: 1px solid var(--btn-border, var(--border-subtle, #e5e7eb)); background: transparent; border-radius: 8px; padding: 5px 12px; cursor: pointer; font-size: 12px; color: var(--btn-fg, var(--text-secondary)); }
.learn-actions button:hover { border-color: var(--accent, #6366f1); color: var(--accent, #6366f1); }
.learn-notice { font-size: 12px; color: var(--accent, #6366f1); }
.learn-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; max-width: 520px; }
.learn-stats > div { padding: 14px; border-radius: 10px; display: flex; flex-direction: column; gap: 2px; }
.learn-stats strong { font-size: 22px; }
.learn-stats span { color: var(--text-secondary); font-size: 12px; }
.learn-block h3 { margin: 0 0 10px; font-size: var(--fs-md, 15px); }
.learn-item { padding: 14px; border-radius: 10px; display: flex; justify-content: space-between; gap: 16px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }
.learn-meta { display: flex; flex-direction: column; gap: 4px; }
.learn-meta small { color: var(--text-secondary); font-size: 12px; }
.learn-grades { display: flex; gap: 8px; }
.learn-grades button { border: 1px solid var(--btn-border, var(--border-subtle, #e5e7eb)); background: transparent; border-radius: 999px; padding: 4px 12px; cursor: pointer; font-size: 12px; color: var(--btn-fg, var(--text-secondary)); }
.learn-grades button:first-child { color: var(--mark, #b8362a); }
.learn-empty { padding: 28px; text-align: center; color: var(--text-secondary); font-size: var(--fs-sm, 13px); }

.rec-head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.rec-head small { color: var(--text-secondary); font-size: 12px; }
.formula-card { padding: 14px 16px; border-radius: 10px; display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.formula-expr { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 14px; }
.formula-range { margin: 0; color: var(--text-secondary); font-size: 12px; }
.formula-terms { display: flex; gap: 8px; flex-wrap: wrap; }
.formula-terms span { font-size: 11px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border-subtle, #e5e7eb); color: var(--text-secondary); }
.formula-detail summary, .rec-detail summary { cursor: pointer; font-size: 12px; color: var(--text-secondary); }
.formula-detail ul { margin: 8px 0 0; padding-left: 18px; font-size: 12px; line-height: 1.7; color: var(--text-secondary); }
.formula-basis { border-top: 1px dashed var(--border-subtle, #e5e7eb); padding-top: 8px; }
.formula-basis a { color: var(--accent, #6366f1); }

.rec-item { padding: 14px; border-radius: 10px; display: flex; flex-direction: column; gap: 10px; margin-bottom: 10px; }
.rec-top { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.rec-rank { font-size: 12px; color: var(--text-secondary); font-weight: 600; }
.rec-title { font-size: 14px; }
.rec-score { margin-left: auto; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; color: var(--accent, #6366f1); }
.rec-add { border: 1px solid var(--border-subtle, #e5e7eb); background: transparent; border-radius: 999px; padding: 3px 10px; font-size: 12px; cursor: pointer; color: var(--text-secondary); }
.rec-tracked { font-size: 11px; color: var(--text-secondary); }
.rec-reason { margin: 0; font-size: 12px; color: var(--text-secondary); }
.rec-bars { display: flex; gap: 6px; flex-wrap: wrap; }
.rec-bar { display: inline-flex; gap: 6px; align-items: baseline; font-size: 11px; padding: 2px 8px; border-radius: 999px; background: var(--surface-subtle, rgba(127, 127, 127, 0.08)); }
.rec-bar i { font-style: normal; color: var(--text-secondary); }
.rec-bar b { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-weight: 600; }
.rec-detail table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 12px; }
.rec-detail th, .rec-detail td { padding: 5px 8px; border-bottom: 1px solid var(--border-subtle, #e5e7eb); text-align: left; }
.rec-detail th { color: var(--text-secondary); font-weight: 500; }
.rec-detail td:nth-child(n+2), .rec-detail th:nth-child(n+2) { text-align: right; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.rec-total td { font-weight: 600; }
.rec-sources { display: flex; gap: 8px; flex-wrap: wrap; align-items: flex-start; font-size: 12px; }
.rec-src-label { color: var(--text-secondary); }
.rec-src { display: inline-flex; flex-direction: column; gap: 2px; padding: 4px 8px; border-radius: 8px; border: 1px solid var(--border-subtle, #e5e7eb); max-width: 320px; }
.rec-src a { color: var(--accent, #6366f1); text-decoration: none; }
.rec-src a:hover { text-decoration: underline; }
.rec-src em { font-style: normal; font-size: 10px; color: var(--text-secondary); }
.rec-src-snippet { font-size: 10px; color: var(--text-secondary); line-height: 1.4; }
.rec-src-empty { color: var(--text-secondary); }
.eval-card { padding: 14px 16px; border-radius: 10px; display: flex; flex-direction: column; gap: 6px; }
.eval-card p { margin: 0; font-size: 12px; line-height: 1.6; }
.eval-note { color: var(--text-secondary); }
</style>
