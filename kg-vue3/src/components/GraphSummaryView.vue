<template>
  <div class="sum-view">
    <!-- 顶部：说明 + 控制 + 导出 -->
    <header class="sum-head">
      <div class="sum-head-main">
        <h2>图谱总结</h2>
        <p>
          把网状的图谱总结成<strong>可执行的流程</strong>：先算结构（层级 / 领域 / 枢纽 / 知识簇 /
          学习主线 / 知识库桥接），再生成 <strong>Mermaid 流程图</strong>与<strong>AI 可读摘要</strong> ——
          流程图既能给人看，也能直接投喂大模型继续学习；总结可一键导出为文档或 PPT。
        </p>
      </div>
      <div class="sum-head-actions">
        <el-input v-model="store.docTitle" size="small" style="width:170px"
                  placeholder="导出文件名" />
        <el-button type="primary" :loading="store.generating" @click="store.generate()">
          生成总结
        </el-button>
      </div>
    </header>

    <!-- 生成参数 + 导出 -->
    <section class="sum-bar">
      <div class="sum-bar-group">
        <span class="sb-label">流程图分组</span>
        <el-radio-group v-model="store.groupBy" size="small" @change="store.generate()">
          <el-radio-button label="level">按学习阶段</el-radio-button>
          <el-radio-button label="domain">按领域</el-radio-button>
        </el-radio-group>
        <span class="sb-label">主线数</span>
        <el-slider v-model="store.maxPaths" :min="1" :max="10" :step="1" size="small"
                   style="width:110px" @change="store.generate()" />
        <span v-if="store.generatedAt" class="sb-time">生成于 {{ store.generatedAt.replace('T', ' ') }}</span>
      </div>
      <div class="sum-bar-group">
        <span class="sb-label">导出</span>
        <el-button size="small" :loading="store.exporting === 'md'" @click="store.exportAs('md')">Markdown</el-button>
        <el-button size="small" :loading="store.exporting === 'docx'" @click="store.exportAs('docx')">Word 文档</el-button>
        <el-button size="small" type="warning" :loading="store.exporting === 'pptx'" @click="store.exportAs('pptx')">PPT 演示</el-button>
        <el-button size="small" :loading="store.exporting === 'mermaid'" @click="store.exportAs('mermaid')">Mermaid</el-button>
        <el-button size="small" :loading="store.exporting === 'digest'" @click="store.exportAs('digest')">AI 摘要</el-button>
        <el-button size="small" :loading="store.exporting === 'json'" @click="store.exportAs('json')">JSON</el-button>
      </div>
    </section>

    <el-empty v-if="!store.summary" description="还没有总结，点击右上角「生成总结」" />

    <div v-else-if="store.isEmpty" class="sum-empty">
      <el-empty :description="store.summary.message || '图谱暂无知识点'" />
    </div>

    <div v-else class="sum-body">
      <!-- 左：结构化总结 -->
      <div class="sum-left">
        <!-- 总览 -->
        <section class="sum-card">
          <h3>总览</h3>
          <div class="sum-stat-grid">
            <div v-for="c in statCards" :key="c.label" class="sum-stat">
              <div class="ss-val" :style="{ color: c.color }">{{ c.value }}</div>
              <div class="ss-label">{{ c.label }}</div>
              <div class="ss-sub">{{ c.sub }}</div>
            </div>
          </div>
          <div class="sum-rel-row">
            <span class="sb-label">关系分布</span>
            <el-tag v-for="(v, k) in store.overview.relation_distribution" :key="k"
                    size="small" effect="plain">{{ k }} · {{ v }}</el-tag>
          </div>
        </section>

        <!-- 学习主线（流程） -->
        <section class="sum-card" v-if="store.summary.paths?.length">
          <h3>
            学习主线
            <span class="sum-count">{{ store.summary.paths.length }} 条</span>
            <span class="sum-note">沿真实连线走出的阅读顺序</span>
          </h3>
          <div v-for="(p, pi) in store.summary.paths" :key="pi" class="sum-path">
            <div class="sp-head">
              <span class="sp-title">主线 {{ pi + 1 }}：{{ p.start }} → {{ p.end }}</span>
              <span class="sp-meta">{{ p.length }} 步 · {{ p.domains.join('、') }}</span>
            </div>
            <div class="sp-steps">
              <template v-for="(s, si) in p.steps" :key="s.id">
                <div class="sp-step" :class="`lv${s.level}`">
                  <span class="sps-order">{{ s.order }}</span>
                  <span class="sps-title" :title="s.title">{{ s.title }}</span>
                  <span class="sps-meta">L{{ s.level }} · {{ s.domain }}</span>
                </div>
                <span v-if="si < p.steps.length - 1" class="sp-arrow" :title="p.steps[si + 1].relation_label_from_prev">
                  <i>{{ p.steps[si + 1].relation_label_from_prev }}</i>→
                </span>
              </template>
            </div>
          </div>
        </section>

        <!-- 核心枢纽 -->
        <section class="sum-card" v-if="store.summary.hubs?.length">
          <h3>核心枢纽知识点 <span class="sum-note">连接最多，优先掌握</span></h3>
          <div class="sum-hub" v-for="h in store.summary.hubs.slice(0, 8)" :key="h.id">
            <div class="sh-head">
              <span class="sh-title">{{ h.title }}</span>
              <span class="sh-badge" :class="`lv${h.level}`">L{{ h.level }} {{ h.level_label }}</span>
              <span class="sh-domain">{{ h.domain }}</span>
              <span class="sh-degree">连接 {{ h.degree }}</span>
            </div>
            <div class="sh-conn">连到：{{ h.connected_titles.join('、') }}</div>
            <div class="sh-rel">
              <span v-for="(v, k) in h.relation_breakdown" :key="k" class="kb-chip">{{ k }} {{ v }}</span>
            </div>
          </div>
        </section>

        <!-- 知识簇 -->
        <section class="sum-card" v-if="store.summary.clusters?.length">
          <h3>知识簇 <span class="sum-count">{{ store.summary.clusters.length }} 个</span>
            <span class="sum-note">每簇即一块可独立学习的模块</span></h3>
          <div class="sum-clusters">
            <div v-for="(c, i) in store.summary.clusters" :key="i" class="sum-cluster">
              <div class="sc-head">
                <span class="sc-label">簇 {{ i + 1 }}｜{{ c.label }}</span>
                <span class="sc-size">{{ c.size }} 点</span>
              </div>
              <div class="sc-meta">{{ c.dominant_domain }} · {{ c.file_count }} 个文件 · {{ c.domains.join('、') }}</div>
              <div class="sc-nodes">
                <span v-for="n in c.top_nodes" :key="n.id" class="kb-chip"
                      :title="`连接 ${n.degree}`">{{ n.title }}</span>
              </div>
            </div>
          </div>
        </section>

        <!-- 层级 + 领域 -->
        <div class="sum-two-col">
          <section class="sum-card">
            <h3>知识层级结构</h3>
            <div class="sum-levels">
              <div v-for="lv in store.summary.levels" :key="lv.level" class="sum-level"
                   :class="`lv${lv.level}`">
                <div class="sl-head">
                  <span class="sl-badge">L{{ lv.level }}</span>
                  <span class="sl-label">{{ lv.label }}</span>
                  <span class="sl-count">{{ lv.count }}</span>
                </div>
                <div class="sl-samples">{{ lv.samples.slice(0, 6).join('、') || '—' }}</div>
              </div>
            </div>
          </section>
          <section class="sum-card">
            <h3>领域分布</h3>
            <div class="sum-bars">
              <div v-for="d in store.summary.domains" :key="d.domain" class="sum-bar-row">
                <span class="sb-name" :title="d.domain">{{ d.domain }}</span>
                <div class="sb-track">
                  <div class="sb-fill" :style="{ width: barWidth(d.share) }"></div>
                </div>
                <span class="sb-val">{{ d.count }} · L{{ d.avg_level }}</span>
              </div>
            </div>
          </section>
        </div>

        <!-- 知识库桥接 -->
        <section class="sum-card" v-if="store.summary.bridges?.length">
          <h3>知识库桥接 <span class="sum-count">{{ store.summary.bridges.length }} 条</span>
            <span class="sum-note">知识库推理建立的知识通路（跨文件/跨领域）</span></h3>
          <div v-for="(b, i) in store.summary.bridges.slice(0, 12)" :key="i" class="sum-bridge">
            <span class="sbr-path">
              {{ b.source }} <i>{{ b.relation_label }}</i> {{ b.target }}
            </span>
            <span v-if="b.cross_file" class="sbr-tag">跨文件</span>
            <span class="sbr-score">{{ b.score }}</span>
            <div class="sbr-evidence">{{ b.evidence || b.source_text || '—' }}</div>
          </div>
        </section>

        <!-- 孤立 + 建议 -->
        <div class="sum-two-col">
          <section class="sum-card">
            <h3>孤立知识点 <span class="sum-count">{{ store.summary.isolated?.length || 0 }} 个</span></h3>
            <div class="sum-isolated">
              <span v-for="n in (store.summary.isolated || []).slice(0, 24)" :key="n.id"
                    class="kb-chip muted">{{ n.title }}</span>
              <span v-if="!store.summary.isolated?.length" class="sum-empty-text">无</span>
            </div>
          </section>
          <section class="sum-card">
            <h3>结论与建议</h3>
            <ol class="sum-suggestions">
              <li v-for="(s, i) in store.summary.suggestions" :key="i">{{ s }}</li>
            </ol>
          </section>
        </div>
      </div>

      <!-- 右：流程图 + AI 可读源码 -->
      <div class="sum-right">
        <section class="sum-card sticky">
          <h3>
            总结流程图
            <span class="sum-note">Mermaid · 机器可读</span>
            <span class="sum-inline-tools">
              <el-radio-group v-model="zoomIndex" size="small">
                <el-radio-button v-for="(z, i) in zooms" :key="i" :label="i">{{ z.label }}</el-radio-button>
              </el-radio-group>
            </span>
          </h3>
          <MermaidFlow :code="store.mermaid" :zoom="zooms[zoomIndex].value" />
          <p class="sum-hint">
            节点按学习阶段（L1 元概念 → L4 实现工具）分组，箭头上的文字是真实的关系类型；
            虚线＝知识库桥接通路。
          </p>

          <el-tabs v-model="codeTab" class="sum-code-tabs">
            <el-tab-pane label="流程图源码 (Mermaid)" name="mermaid">
              <textarea class="sum-code" readonly :value="store.mermaid"></textarea>
              <div class="sum-code-actions">
                <el-button size="small" @click="copyOrDownloadMermaid">复制 Mermaid</el-button>
                <el-button size="small" @click="store.exportAs('mermaid')">下载 .mmd</el-button>
              </div>
            </el-tab-pane>
            <el-tab-pane label="AI 可读摘要" name="digest">
              <textarea class="sum-code" readonly :value="store.aiDigest"></textarea>
              <div class="sum-code-actions">
                <el-button size="small" type="primary" @click="store.copy(store.aiDigest, 'AI 摘要已复制')">
                  复制 AI 摘要
                </el-button>
                <el-button size="small" @click="store.exportAs('digest')">下载 .md</el-button>
              </div>
            </el-tab-pane>
          </el-tabs>
          <p class="sum-hint">
            把上面任意一段粘贴到 ChatGPT / Claude / 飞书 / Notion / VSCode（支持 Mermaid 的地方），
            AI 就能按这张流程图继续展开、出题、写讲义。
          </p>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useSummaryStore } from '@/store/summaryStore'
import MermaidFlow from '@/components/MermaidFlow.vue'

const store = useSummaryStore()
const codeTab = ref('mermaid')
const zoomIndex = ref(1)
const zooms = [
  { label: '75%', value: 0.75 },
  { label: '100%', value: 1 },
  { label: '130%', value: 1.3 }
]

const statCards = computed(() => {
  const o = store.overview
  return [
    { label: '知识点', value: o.node_count ?? 0, sub: `${o.domain_count ?? 0} 个领域`, color: 'var(--accent)' },
    { label: '关联连线', value: o.link_count ?? 0, sub: `平均度 ${o.avg_degree ?? 0}`, color: 'var(--mint-strong)' },
    { label: '知识簇', value: o.cluster_count ?? 0, sub: `孤立点 ${o.isolated_count ?? 0}`, color: 'var(--apricot-strong)' },
    { label: '知识库桥接', value: o.kb_bridge_count ?? 0, sub: `跨文件 ${o.cross_file_bridge_count ?? 0}`, color: '#8E7BA8' },
    { label: '锚定概念', value: o.kb_anchor_count ?? 0, sub: `来源文件 ${o.file_count ?? 0}`, color: 'var(--info)' }
  ]
})

const maxShare = computed(() =>
  Math.max(0.01, ...(store.summary?.domains || []).map(d => d.share))
)

function barWidth(share) {
  return `${Math.max(3, (share / maxShare.value) * 100)}%`
}

async function copyOrDownloadMermaid() {
  await store.copy(store.mermaid, 'Mermaid 源码已复制')
}

onMounted(() => {
  // 进入页面即自动生成一次，省去一次点击
  store.generate()
})
</script>

<style scoped>
.sum-view {
  flex: 1;
  min-width: 0;
  padding: 16px 20px 40px;
  height: 100%;
  overflow-y: auto;
  background: var(--bg-primary);
}
.sum-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.sum-head-main h2 { margin: 0 0 6px; font-size: 18px; color: var(--text-primary); }
.sum-head-main p { margin: 0; max-width: 760px; font-size: 12.5px; line-height: 1.65; color: var(--text-secondary); }
.sum-head-actions { display: flex; align-items: center; gap: 8px; }

.sum-bar {
  display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
  gap: 12px; margin: 12px 0 14px; padding: 10px 12px;
  background: var(--bg-secondary); border: 1px solid var(--border-light);
  border-radius: var(--radius); box-shadow: var(--shadow-sm);
}
.sum-bar-group { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.sb-label { font-size: 12px; color: var(--text-muted); }
.sb-time { font-size: 11px; color: var(--text-muted); }

.sum-body { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(340px, 0.85fr); gap: 14px; }
@media (max-width: 1180px) { .sum-body { grid-template-columns: 1fr; } }
.sum-left { min-width: 0; display: flex; flex-direction: column; gap: 14px; }
.sum-right { min-width: 0; }
.sum-two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 900px) { .sum-two-col { grid-template-columns: 1fr; } }

.sum-card {
  background: var(--bg-secondary); border: 1px solid var(--border-light);
  border-radius: var(--radius); padding: 14px 16px; box-shadow: var(--shadow-sm);
}
.sum-card.sticky { position: sticky; top: 0; }
.sum-card h3 {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  margin: 0 0 12px; font-size: 13.5px; color: var(--text-primary);
}
.sum-count {
  font-size: 11px; color: var(--text-muted); background: var(--bg-tertiary);
  border-radius: var(--radius-full); padding: 1px 8px;
}
.sum-note { font-size: 11px; font-weight: 400; color: var(--text-muted); }
.sum-inline-tools { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.sum-hint { font-size: 11.5px; color: var(--text-muted); line-height: 1.6; margin: 8px 0 0; }
.sum-empty { padding: 40px 0; }
.sum-empty-text { font-size: 12px; color: var(--text-muted); }

.sum-stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; }
.sum-stat { background: var(--bg-tertiary); border-radius: var(--radius-sm); padding: 10px 12px; }
.ss-val { font-size: 22px; font-weight: 700; line-height: 1.15; }
.ss-label { font-size: 12px; color: var(--text-primary); margin-top: 2px; }
.ss-sub { font-size: 11px; color: var(--text-muted); }
.sum-rel-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 12px; }

.sum-path { border-left: 3px solid var(--accent); padding: 8px 0 8px 10px; margin-bottom: 12px; }
.sp-head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.sp-title { font-size: 12.5px; font-weight: 600; color: var(--text-primary); }
.sp-meta { font-size: 11px; color: var(--text-muted); }
.sp-steps { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
.sp-step {
  display: flex; flex-direction: column; gap: 1px;
  background: var(--bg-tertiary); border: 1px solid var(--border-light);
  border-radius: var(--radius-sm); padding: 5px 8px; max-width: 190px;
}
.sp-step.lv1 { border-color: var(--accent); }
.sp-step.lv2 { border-color: var(--mint); }
.sp-step.lv3 { border-color: var(--apricot); }
.sp-step.lv4 { border-color: #B9A7CC; }
.sps-order {
  font-size: 10px; color: var(--text-muted);
}
.sps-title { font-size: 12px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sps-meta { font-size: 10px; color: var(--text-muted); }
.sp-arrow { font-size: 10px; color: var(--apricot-strong); display: flex; align-items: center; gap: 2px; }
.sp-arrow i { font-style: normal; color: var(--text-muted); font-size: 9.5px; }

.sum-hub { border-bottom: 1px dashed var(--border-light); padding: 8px 0; }
.sum-hub:last-child { border-bottom: none; }
.sh-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.sh-title { font-size: 12.5px; font-weight: 600; color: var(--text-primary); }
.sh-badge { font-size: 10.5px; border-radius: var(--radius-full); padding: 1px 7px; color: #fff; }
.sh-badge.lv1 { background: var(--accent); }
.sh-badge.lv2 { background: var(--mint-strong); }
.sh-badge.lv3 { background: var(--apricot-strong); }
.sh-badge.lv4 { background: #8E7BA8; }
.sh-domain { font-size: 11px; color: var(--text-muted); }
.sh-degree { font-size: 11px; color: var(--accent); margin-left: auto; }
.sh-conn { font-size: 11.5px; color: var(--text-secondary); margin: 4px 0; }
.sh-rel { display: flex; gap: 5px; flex-wrap: wrap; }

.sum-clusters { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
@media (max-width: 900px) { .sum-clusters { grid-template-columns: 1fr; } }
.sum-cluster { background: var(--bg-tertiary); border-radius: var(--radius-sm); padding: 9px 11px; }
.sc-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.sc-label { font-size: 12px; font-weight: 600; color: var(--text-primary); }
.sc-size { font-size: 11px; color: var(--accent); }
.sc-meta { font-size: 11px; color: var(--text-muted); margin: 3px 0 6px; }
.sc-nodes { display: flex; flex-wrap: wrap; gap: 4px; }

.sum-levels { display: flex; flex-direction: column; gap: 8px; }
.sum-level { border-left: 3px solid var(--border); padding-left: 9px; }
.sum-level.lv1 { border-color: var(--accent); }
.sum-level.lv2 { border-color: var(--mint); }
.sum-level.lv3 { border-color: var(--apricot); }
.sum-level.lv4 { border-color: #B9A7CC; }
.sl-head { display: flex; align-items: center; gap: 8px; }
.sl-badge { font-size: 10.5px; color: var(--text-muted); }
.sl-label { font-size: 12px; color: var(--text-primary); }
.sl-count { margin-left: auto; font-size: 12px; font-weight: 700; color: var(--accent); }
.sl-samples { font-size: 11px; color: var(--text-muted); margin-top: 2px; line-height: 1.5; }

.sum-bars { display: flex; flex-direction: column; gap: 6px; }
.sum-bar-row { display: flex; align-items: center; gap: 8px; font-size: 11.5px; }
.sb-name { width: 96px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sb-track { flex: 1; height: 8px; background: var(--bg-tertiary); border-radius: var(--radius-full); overflow: hidden; }
.sb-fill { height: 100%; background: linear-gradient(90deg, var(--accent), var(--mint)); border-radius: var(--radius-full); }
.sb-val { width: 74px; text-align: right; color: var(--text-muted); }

.sum-bridge { border-left: 3px solid var(--mint); padding: 6px 0 6px 9px; margin-bottom: 8px; }
.sbr-path { font-size: 12px; color: var(--text-primary); }
.sbr-path i { font-style: normal; color: var(--mint-strong); }
.sbr-tag {
  font-size: 10px; color: var(--apricot-strong); background: var(--apricot-soft);
  border-radius: var(--radius-full); padding: 1px 6px; margin-left: 6px;
}
.sbr-score { font-size: 11px; color: var(--text-muted); margin-left: 6px; }
.sbr-evidence { font-size: 11px; color: var(--text-muted); margin-top: 3px; line-height: 1.55; }

.sum-isolated { display: flex; flex-wrap: wrap; gap: 5px; }
.sum-suggestions { margin: 0; padding-left: 18px; }
.sum-suggestions li { font-size: 12px; color: var(--text-secondary); line-height: 1.7; }

.kb-chip {
  font-size: 11px; border-radius: var(--radius-full); padding: 1px 8px;
  background: var(--bg-secondary); border: 1px solid var(--border-light);
  color: var(--text-secondary);
}
.kb-chip.muted { color: var(--text-muted); }

.sum-code-tabs { margin-top: 14px; }
.sum-code {
  width: 100%; height: 210px; resize: vertical;
  font-family: var(--font-mono); font-size: 11px; line-height: 1.55;
  color: var(--text-secondary); background: var(--bg-tertiary);
  border: 1px solid var(--border-light); border-radius: var(--radius-sm);
  padding: 8px 10px; box-sizing: border-box;
}
.sum-code-actions { display: flex; gap: 8px; margin-top: 8px; }
</style>
