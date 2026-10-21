<!--
  图谱总结页 —— 按「一份报告」而不是「一堆卡片」组织。

  版面主张：先给结论（概览数字），再给叙事主轴（学习主线），
  流程图与 AI 摘要作为佐证并置，枢纽/簇/层级等收进「支撑材料」，
  最后落在结论与建议。

  保留不动的东西：/api/summary/* 的参数与调用、store 键名、Mermaid 缩放控件、
  空态与错误提示。改的只是排版层级与叙事顺序。
-->
<template>
  <div class="sum-view">
    <div class="rpt">
      <!-- ==================== 刊头 ==================== -->
      <header class="rpt-mast">
        <div class="rpt-mast-main">
          <div class="u-kicker">
            <span class="u-kicker__no">NO. 07</span>
            <span class="u-kicker__rule" aria-hidden="true"></span>
            <span>知识图谱总结</span>
          </div>
          <h2>图谱总结</h2>
          <p class="rpt-dek">
            把网状的图谱收敛成<strong>可执行的流程</strong>：先算结构，
            再出一份人看得懂、大模型也读得懂的流程图。
          </p>
        </div>

        <div class="rpt-mast-tools">
          <label class="rpt-field">
            <span class="rpt-label">导出文件名</span>
            <el-input v-model="store.docTitle" size="small" placeholder="知识图谱总结" />
          </label>
          <el-button type="primary" :loading="store.generating" @click="store.generate()">
            {{ store.summary ? '重新生成' : '生成总结' }}
          </el-button>
        </div>
      </header>

      <!-- ==================== 参数与导出 ==================== -->
      <div class="rpt-bar">
        <div class="rpt-bar-group">
          <span class="rpt-label">分组</span>
          <el-radio-group v-model="store.groupBy" size="small" @change="store.generate()">
            <el-radio-button label="level">学习阶段</el-radio-button>
            <el-radio-button label="domain">领域</el-radio-button>
          </el-radio-group>

          <span class="rpt-bar-sep" aria-hidden="true"></span>

          <span class="rpt-label">主线数</span>
          <el-slider v-model="store.maxPaths" :min="1" :max="10" :step="1" size="small"
                     class="rpt-slider" @change="store.generate()" />
          <span class="rpt-bar-num">{{ store.maxPaths }}</span>

          <span v-if="store.generatedAt" class="rpt-stamp">
            {{ store.generatedAt.replace('T', ' ').slice(0, 16) }}
          </span>
        </div>

        <div class="rpt-bar-group rpt-bar-export">
          <span class="rpt-label">导出</span>
          <button v-for="f in exportFormats" :key="f.fmt" type="button"
                  class="u-btn u-btn--text" :class="{ 'is-busy': store.exporting === f.fmt }"
                  :disabled="!!store.exporting"
                  @click="store.exportAs(f.fmt)">
            {{ store.exporting === f.fmt ? '…' : f.label }}
          </button>
        </div>
      </div>

      <!--
        不再进入页面就自动生成。
        生成总结是有实际成本的操作（全图谱结构分析 + 流程图 + AI 摘要），
        每次打开页面都替用户跑一遍既浪费也不礼貌；而且它是写操作，
        首次使用时会直接弹出管理口令框，用户在还没做任何事时就被拦住。
      -->
      <AppEmpty v-if="!store.summary" text="还没有生成总结"
                hint="总结会把网状图谱收敛成可执行的流程：层级 / 领域 / 枢纽 / 学习主线，并生成 Mermaid 流程图与 AI 可读摘要">
        <template #action>
          <el-button type="primary" size="small" :loading="store.generating" @click="store.generate()">
            立即生成总结
          </el-button>
        </template>
      </AppEmpty>

      <div v-else-if="store.isEmpty" class="rpt-empty">
        <AppEmpty :text="store.summary.message || '图谱暂无知识点'"
                  hint="先在知识图谱上传并解析文档，再回来生成总结" />
      </div>

      <div v-else class="rpt-body">
        <!-- ==================== 01 概览 ==================== -->
        <section class="rpt-sec">
          <header class="u-sec-title">
            <span class="u-sec-title__no">01</span>
            <h3>概览</h3>
            <span class="u-sec-title__note">这张图现在长什么样</span>
            <span class="u-sec-title__fill" aria-hidden="true"></span>
          </header>

          <div class="rpt-figures">
            <div v-for="c in statCards" :key="c.label" class="rpt-fig"
                 :style="{ '--tone': c.color }">
              <span class="rpt-fig-label">{{ c.label }}</span>
              <span class="rpt-fig-value">{{ c.value }}</span>
              <span class="rpt-fig-sub">{{ c.sub }}</span>
            </div>
          </div>

          <div v-if="hasRelations" class="rpt-rel">
            <span class="rpt-label">关系类型</span>
            <span v-for="(v, k) in store.overview.relation_distribution" :key="k" class="rpt-rel-item">
              {{ k }}<b>{{ v }}</b>
            </span>
          </div>
        </section>

        <!-- ==================== 02 学习主线（叙事主轴） ==================== -->
        <section class="rpt-sec">
          <header class="u-sec-title">
            <span class="u-sec-title__no">02</span>
            <h3>学习主线</h3>
            <span class="u-sec-title__note">
              沿真实连线走出的阅读顺序<template v-if="paths.length"> · {{ paths.length }} 条</template>
            </span>
            <span class="u-sec-title__fill" aria-hidden="true"></span>
          </header>

          <p v-if="!paths.length" class="rpt-none">
            还没有能构成主线的高分关联。主线只走有知识依据的强关联，
            弱关联不足以支撑学习顺序，所以宁可不给 —— 多上传几份同一主题的文档再生成。
          </p>

          <div v-else class="rpt-paths">
            <article v-for="(p, pi) in paths" :key="pi" class="rpt-path">
              <header class="rpt-path-head">
                <span class="rpt-path-no">{{ pad(pi + 1) }}</span>
                <div class="rpt-path-title">
                  <h4>{{ p.start }}<span class="rpt-arrow" aria-hidden="true">→</span>{{ p.end }}</h4>
                  <span class="rpt-path-meta">{{ p.length }} 步 · {{ (p.domains || []).join(' / ') }}</span>
                </div>
              </header>

              <ol class="rpt-steps">
                <li v-for="(s, si) in p.steps" :key="s.id" class="rpt-step">
                  <span v-if="si > 0" class="rpt-step-rel">{{ s.relation_label_from_prev }}</span>
                  <div class="rpt-step-row">
                    <span class="rpt-step-n">{{ s.order }}</span>
                    <div class="rpt-step-body">
                      <span class="rpt-step-title" :title="s.title">{{ s.title }}</span>
                      <span class="rpt-step-meta">L{{ s.level }} · {{ s.domain }}</span>
                    </div>
                  </div>
                </li>
              </ol>
            </article>
          </div>
        </section>

        <!-- ==================== 03 流程图 + AI 摘要 ==================== -->
        <section class="rpt-sec">
          <header class="u-sec-title">
            <span class="u-sec-title__no">03</span>
            <h3>总结流程图</h3>
            <span class="u-sec-title__note">Mermaid · 人看得懂，大模型也读得懂</span>
            <span class="u-sec-title__fill" aria-hidden="true"></span>
            <span class="u-sec-title__actions rpt-zoom">
              <el-radio-group v-model="zoomIndex" size="small">
                <el-radio-button v-for="(z, i) in zooms" :key="i" :label="i">{{ z.label }}</el-radio-button>
              </el-radio-group>
            </span>
          </header>

          <div class="rpt-split">
            <div class="rpt-graph">
              <MermaidFlow :code="store.mermaid" :zoom="zooms[zoomIndex].value" />
              <p class="rpt-caption">
                <b>FIG. 3</b> —— 节点按学习阶段分组（L1 元概念 → L4 实现工具），
                箭头上的文字是真实关系类型，虚线为知识库桥接通路。
                图较大时在框内滚动查看，或用右上角缩放。
              </p>
            </div>

            <aside class="rpt-digest">
              <div class="rpt-digest-head">
                <span class="rpt-label">AI 可读摘要</span>
                <button type="button" class="u-btn u-btn--text"
                        @click="store.copy(store.aiDigest, 'AI 摘要已复制')">复制</button>
              </div>
              <pre class="rpt-digest-body">{{ store.aiDigest || '（生成总结后出现）' }}</pre>
              <div class="rpt-digest-foot">
                <button type="button" class="u-btn u-btn--text" @click="store.exportAs('digest')">下载 .md</button>
                <span class="rpt-digest-hint">粘贴给任意大模型，即可按这张图继续展开</span>
              </div>
            </aside>
          </div>

          <details class="rpt-src">
            <summary>查看 Mermaid 源码</summary>
            <textarea class="rpt-code" readonly :value="store.mermaid"></textarea>
            <div class="rpt-src-actions">
              <button type="button" class="u-btn u-btn--text"
                      @click="store.copy(store.mermaid, 'Mermaid 源码已复制')">复制源码</button>
              <button type="button" class="u-btn u-btn--text" @click="store.exportAs('mermaid')">下载 .mmd</button>
            </div>
          </details>
        </section>

        <!-- ==================== 04 支撑材料 ==================== -->
        <section class="rpt-sec">
          <header class="u-sec-title">
            <span class="u-sec-title__no">04</span>
            <h3>支撑材料</h3>
            <span class="u-sec-title__note">枢纽 / 簇 / 层级 / 领域 / 桥接 / 孤立点</span>
            <span class="u-sec-title__fill" aria-hidden="true"></span>
          </header>

          <div class="rpt-blocks">
            <!-- 核心枢纽 -->
            <div v-if="hubs.length" class="rpt-block rpt-block--wide">
              <h4 class="rpt-block-title">核心枢纽<span>连接最多，优先掌握</span></h4>
              <ol class="rpt-hubs">
                <li v-for="(h, hi) in hubs.slice(0, 8)" :key="h.id">
                  <span class="rpt-hub-rank">{{ pad(hi + 1) }}</span>
                  <div class="rpt-hub-main">
                    <div class="rpt-hub-line">
                      <span class="rpt-hub-name">{{ h.title }}</span>
                      <span class="rpt-hub-lv" :class="`lv${h.level}`">L{{ h.level }}</span>
                      <span class="rpt-hub-deg">{{ h.degree }} 条连线</span>
                    </div>
                    <div class="rpt-hub-conn">
                      <span v-for="(v, k) in h.relation_breakdown" :key="k" class="rpt-chip">{{ k }} {{ v }}</span>
                    </div>
                  </div>
                </li>
              </ol>
            </div>

            <!-- 知识簇 -->
            <div v-if="clusters.length" class="rpt-block">
              <h4 class="rpt-block-title">知识簇<span>每簇即一块可独立学习的模块</span></h4>
              <div class="rpt-clusters">
                <div v-for="(c, i) in clusters" :key="i" class="rpt-cluster">
                  <div class="rpt-cluster-head">
                    <span class="rpt-cluster-no">{{ pad(i + 1) }}</span>
                    <span class="rpt-cluster-label">{{ c.label }}</span>
                    <span class="rpt-cluster-size">{{ c.size }} 点</span>
                  </div>
                  <div class="rpt-cluster-meta">{{ c.dominant_domain }} · {{ c.file_count }} 个文件</div>
                  <div class="rpt-chips">
                    <span v-for="n in c.top_nodes" :key="n.id" class="rpt-chip" :title="`连接 ${n.degree}`">
                      {{ n.title }}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 层级结构 -->
            <div class="rpt-block">
              <h4 class="rpt-block-title">知识层级<span>L1 元概念 → L4 实现工具</span></h4>
              <div class="rpt-levels">
                <div v-for="lv in levels" :key="lv.level" class="rpt-level" :class="`lv${lv.level}`">
                  <div class="rpt-level-head">
                    <span class="rpt-level-badge">L{{ lv.level }}</span>
                    <span class="rpt-level-label">{{ lv.label }}</span>
                    <span class="rpt-level-count">{{ lv.count }}</span>
                  </div>
                  <div class="rpt-level-samples">{{ lv.samples.slice(0, 6).join('、') || '—' }}</div>
                </div>
              </div>
            </div>

            <!-- 领域分布 -->
            <div class="rpt-block">
              <h4 class="rpt-block-title">领域分布<span>{{ overview.domain_count || 0 }} 个领域</span></h4>
              <div class="rpt-bars">
                <div v-for="d in domains" :key="d.domain" class="rpt-bar-row">
                  <span class="rpt-bar-name" :title="d.domain">{{ d.domain }}</span>
                  <div class="rpt-bar-track">
                    <div class="rpt-bar-fill" :style="{ width: barWidth(d.share) }"></div>
                  </div>
                  <span class="rpt-bar-val">{{ d.count }} · L{{ d.avg_level }}</span>
                </div>
              </div>
            </div>

            <!-- 知识库桥接 -->
            <div v-if="bridges.length" class="rpt-block rpt-block--wide">
              <h4 class="rpt-block-title">
                知识库桥接<span>知识库推理建立的通路（跨文件 / 跨领域）</span>
              </h4>
              <ul class="rpt-bridges">
                <li v-for="(b, i) in bridges.slice(0, 10)" :key="i">
                  <div class="rpt-bridge-path">
                    <span>{{ b.source }}</span>
                    <i>{{ b.relation_label }}</i>
                    <span>{{ b.target }}</span>
                    <span v-if="b.cross_file" class="rpt-chip rpt-chip--warm">跨文件</span>
                    <span class="rpt-bridge-score">{{ b.score }}</span>
                  </div>
                  <div class="rpt-bridge-evidence">{{ b.evidence || b.source_text || '—' }}</div>
                </li>
              </ul>
            </div>

            <!-- 孤立知识点（负面清单，不过滤） -->
            <div class="rpt-block">
              <h4 class="rpt-block-title">
                孤立知识点<span>{{ overview.isolated_count || 0 }} 个，按标题去重列出</span>
              </h4>
              <div v-if="isolated.length" class="rpt-chips">
                <span v-for="n in isolated.slice(0, 24)" :key="n.id" class="rpt-chip rpt-chip--muted">
                  {{ n.title }}
                </span>
              </div>
              <p v-else class="rpt-none rpt-none--tight">没有孤立知识点。</p>
            </div>
          </div>
        </section>

        <!-- ==================== 05 结论与建议 ==================== -->
        <section class="rpt-sec rpt-sec--end">
          <header class="u-sec-title">
            <span class="u-sec-title__no">05</span>
            <h3>结论与建议</h3>
            <span class="u-sec-title__note">按当前数据算出的下一步</span>
            <span class="u-sec-title__fill" aria-hidden="true"></span>
          </header>
          <ol v-if="suggestions.length" class="rpt-notes">
            <li v-for="(s, i) in suggestions" :key="i">
              <span class="rpt-note-no">{{ pad(i + 1) }}</span>
              <p>{{ s }}</p>
            </li>
          </ol>
          <p v-else class="rpt-none">当前没有需要特别处理的问题。</p>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useSummaryStore } from '@/store/summaryStore'
import MermaidFlow from '@/components/MermaidFlow.vue'
import AppEmpty from '@/components/AppEmpty.vue'

const store = useSummaryStore()

// 缩放档：默认 100%。
// 试过把「适应」设成默认：这张图固有尺寸约 4900×5300，缩到框里只剩 9%，
// 节点名字全是 1px 的灰点 —— 「看到全貌」但什么也读不到。
// 所以默认给能读的 100%，由 MermaidFlow 自动滚到图的中心（密集区），
// 「适应」留作整图概览。
const zoomIndex = ref(2)
const zooms = [
  { label: '适应', value: 'fit' },
  { label: '75%', value: 0.75 },
  { label: '100%', value: 1 },
  { label: '130%', value: 1.3 }
]

// 导出改成「文字按钮」而不是六个彩色 el-button：
// 六个等权重按钮会把参数区压成工具栏，而导出是收尾动作，不该抢主线的位置。
const exportFormats = [
  { fmt: 'md', label: 'Markdown' },
  { fmt: 'docx', label: 'Word' },
  { fmt: 'pptx', label: 'PPT' },
  { fmt: 'mermaid', label: 'Mermaid' },
  { fmt: 'digest', label: 'AI 摘要' },
  { fmt: 'json', label: 'JSON' }
]

const overview = computed(() => store.overview || {})
const paths = computed(() => store.summary?.paths || [])
const hubs = computed(() => store.summary?.hubs || [])
const clusters = computed(() => store.summary?.clusters || [])
const levels = computed(() => store.summary?.levels || [])
const domains = computed(() => store.summary?.domains || [])
const bridges = computed(() => store.summary?.bridges || [])
const isolated = computed(() => store.summary?.isolated || [])
const suggestions = computed(() => store.summary?.suggestions || [])
const hasRelations = computed(() => Object.keys(overview.value.relation_distribution || {}).length > 0)

// 数字用「墨色」，语义色只做上方 3px 的刻度条 ——
// 五个彩色大数字会变成仪表盘，而这是一份报告。
const statCards = computed(() => {
  const o = overview.value
  return [
    { label: '知识点', value: o.node_count ?? 0, sub: `${o.domain_count ?? 0} 个领域`, color: 'var(--accent)' },
    { label: '关联连线', value: o.link_count ?? 0, sub: `平均度 ${o.avg_degree ?? 0}`, color: 'var(--violet-text)' },
    { label: '知识簇', value: o.cluster_count ?? 0, sub: `孤立点 ${o.isolated_count ?? 0}`, color: 'var(--amber)' },
    // 「知识库连线」而不是「知识库桥接」：下面「关系类型」里也有一个叫「知识库桥接」的计数
    // （那是 relation_type=bridged），两者口径不同。同屏同名不同数会让人以为统计自相矛盾。
    { label: '知识库连线', value: o.kb_bridge_count ?? 0, sub: `跨文件 ${o.cross_file_bridge_count ?? 0}`, color: 'var(--magenta)' },
    { label: '锚定概念', value: o.kb_anchor_count ?? 0, sub: `来源文件 ${o.file_count ?? 0}`, color: 'var(--text-faint)' }
  ]
})

const maxShare = computed(() =>
  Math.max(0.01, ...domains.value.map(d => d.share))
)

function barWidth(share) {
  return `${Math.max(3, (share / maxShare.value) * 100)}%`
}

function pad(n) {
  return String(n).padStart(2, '0')
}

// 刻意不在这里自动生成总结：
//   1. 生成是昂贵操作（全图结构分析 + Mermaid + AI 摘要），应由用户主动触发；
//   2. 它是写操作，会触发写操作守卫 —— 首次使用会在用户还没做任何事时弹口令框。
// 现在改为：有上次结果就直接显示（store 常驻），没有就显示带按钮的空态。
</script>

<style scoped>
/* ============================================================
   报告版面
   ------------------------------------------------------------
   一条纵向叙事轴：刊头 → 参数 → 01 概览 → 02 主线 → 03 流程图
   → 04 支撑材料 → 05 结论。区块之间用**发丝线 + 栏号**分隔，
   不再用「等权重卡片 + 阴影」—— 十几个同样重的盒子会让眼睛没有落点。

   字号：正文全部走 --fs-* 令牌；只有展示级的三处（大数字 / 区块标题 /
   主线编号）用 calc 在令牌上放大，集中定义在下面，避免散落的硬编码。
   ============================================================ */
.sum-view {
  flex: 1;
  min-width: 0;
  height: 100%;
  overflow-y: auto;
  padding: 26px 28px 64px;
  /* 不写 background：视图根容器必须透明，否则会整块盖住素材背景层 */

  --rpt-rule: color-mix(in srgb, var(--text-primary) 13%, transparent);
  --rpt-rule-soft: color-mix(in srgb, var(--text-primary) 8%, transparent);

  --rpt-fig: calc(var(--fs-xl) * 2 + 2px);      /* 38px 概览大数字 */
  --rpt-sec: calc(var(--fs-xl) + 2px);          /* 20px 区块标题 */
  --rpt-path: calc(var(--fs-xl) + 8px);         /* 26px 主线编号 */
  --rpt-title: calc(var(--fs-xl) + 16px);       /* 34px 刊头主标题 */
}

.rpt {
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
}

/* ============================ 刊头 ============================ */
.rpt-mast {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 32px;
  padding-bottom: 20px;
  border-bottom: 2px solid var(--text-primary);
}
.rpt-mast-main { min-width: 0; }

/* 眉标间距是本页的版面参数；字号/颜色/短横线由 .u-kicker 负责 */
.u-kicker { margin-bottom: 10px; }

/* identity.css 给所有页面 h2 加了衬线 + 朱砂菱形；这里只放大字号 */
.rpt-mast h2 {
  margin: 0 0 8px;
  font-size: var(--rpt-title);
  line-height: 1.15;
}
.rpt-dek {
  margin: 0;
  max-width: 62ch;
  font-size: var(--fs-md);
  line-height: 1.7;
  color: var(--text-secondary);
}
/* 强调不用斜体（中文斜体会发歪），用朱砂下划线 */
.rpt-dek strong {
  font-weight: 600;
  color: var(--text-primary);
  text-decoration: underline;
  text-decoration-color: var(--seal);
  text-decoration-thickness: 2px;
  text-underline-offset: 4px;
}

.rpt-mast-tools {
  flex: none;
  display: flex;
  align-items: flex-end;
  gap: 12px;
}
.rpt-field { display: flex; flex-direction: column; gap: 5px; }
.rpt-field :deep(.el-input) { width: 168px; }

/* ============================ 参数条 ============================ */
.rpt-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px 24px;
  padding: 12px 0;
  border-bottom: 1px solid var(--rpt-rule);
}
.rpt-bar-group { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.rpt-bar-sep { width: 1px; height: 16px; background: var(--rpt-rule); margin: 0 4px; }
.rpt-slider { width: 104px; margin: 0 2px; }
.rpt-bar-num {
  font-family: var(--font-mono);
  font-size: var(--fs-sm);
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
  min-width: 14px;
}
.rpt-stamp {
  margin-left: 6px;
  padding-left: 12px;
  border-left: 1px solid var(--rpt-rule);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-muted);
  letter-spacing: 0.04em;
}

.rpt-label {
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  letter-spacing: 0.1em;
  color: var(--text-muted);
}

/* 导出按钮用 .u-btn--text；这里只保留本页的排布间距 */
.rpt-bar-export .u-btn + .u-btn { margin-left: 14px; }
.u-btn.is-busy { color: var(--mark, var(--seal)); }

/* ============================ 区块框架 ============================ */
.rpt-body { padding-top: 4px; }
.rpt-sec { padding: 30px 0 6px; border-bottom: 1px solid var(--rpt-rule-soft); }
.rpt-sec:last-child { border-bottom: 0; }

/* 分节头用 .u-sec-title（栏号 + 衬线标题 + 发丝线）；这里只覆盖本页字号 */
.u-sec-title h3 { font-size: var(--rpt-sec); }
.rpt-zoom { margin-left: 4px; flex: none; }
/* 缩放按钮必须排成一行：默认的 radio-group 会被 flex 容器压成竖排，
   四个按钮占掉三行高度，页头被撑得很高 */
.rpt-zoom :deep(.el-radio-group) { display: inline-flex; flex-wrap: nowrap; }
.rpt-zoom :deep(.el-radio-button__inner) { padding: 4px 9px; }

.rpt-none {
  margin: 0 0 10px;
  max-width: 74ch;
  font-size: var(--fs-md);
  line-height: 1.75;
  color: var(--text-muted);
}
.rpt-none--tight { margin: 0; }
.rpt-empty { padding: 60px 0; }

/* ============================ 01 概览 ============================ */
/* 大数字之间只用竖发丝线分隔，不加底色 —— 五块灰底会读成一排按钮 */
.rpt-figures {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  border-top: 1px solid var(--rpt-rule-soft);
  border-bottom: 1px solid var(--rpt-rule-soft);
}
.rpt-fig {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 16px 18px 14px;
}
.rpt-fig + .rpt-fig { border-left: 1px solid var(--rpt-rule-soft); }
/* 语义色只出现在这一条 3px 刻度上 */
.rpt-fig::before {
  content: "";
  position: absolute;
  left: 18px;
  top: 0;
  width: 22px;
  height: 3px;
  background: var(--tone, var(--accent));
}
.rpt-fig-label {
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  letter-spacing: 0.08em;
  color: var(--text-muted);
}
.rpt-fig-value {
  font-family: var(--font-display);
  font-size: var(--rpt-fig);
  font-weight: 700;
  line-height: 1.08;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
}
.rpt-fig-sub { font-size: var(--fs-sm); color: var(--text-muted); }

.rpt-rel {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 16px;
  padding: 12px 0 2px;
}
.rpt-rel-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
.rpt-rel-item b {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

/* ============================ 02 学习主线 ============================ */
.rpt-paths {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 22px 40px;
}

.rpt-path {
  padding: 14px 0 6px;
  border-top: 1px solid var(--rpt-rule);
}
.rpt-path-head { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 14px; }
.rpt-path-no {
  font-family: var(--font-display);
  font-size: var(--rpt-path);
  font-weight: 700;
  line-height: 1;
  color: var(--seal);
  font-variant-numeric: tabular-nums;
  /* 编号与标题同基线：26px 的字号要往下压一点才和 15px 的标题对齐 */
  transform: translateY(3px);
}
.rpt-path-title { min-width: 0; }
.rpt-path-title h4 {
  margin: 0;
  font-family: var(--font-display);
  font-size: calc(var(--fs-base) + 1px);
  font-weight: 700;
  line-height: 1.4;
  color: var(--text-primary);
  overflow-wrap: anywhere;
}
.rpt-arrow { margin: 0 8px; color: var(--seal); font-weight: 400; }
.rpt-path-meta {
  display: block;
  margin-top: 3px;
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-muted);
  letter-spacing: 0.03em;
}

.rpt-steps { margin: 0; padding: 0; list-style: none; }
.rpt-step-rel {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0 0 5px 38px;
  font-size: var(--fs-xs);
  color: var(--text-muted);
  letter-spacing: 0.04em;
}
.rpt-step-rel::before {
  content: "";
  width: 13px;
  height: 1px;
  background: var(--seal);
  opacity: 0.5;
}

.rpt-step-row {
  position: relative;
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr);
  gap: 12px;
  padding-bottom: 13px;
}
.rpt-step:last-child .rpt-step-row { padding-bottom: 0; }
/* 纵向电流线（主线的「路径」感）：最后一项不画 */
.rpt-step:not(:last-child) .rpt-step-row::before {
  content: "";
  position: absolute;
  left: 12.5px;
  top: 26px;
  bottom: 0;
  width: 1px;
  background: var(--rpt-rule);
}

.rpt-step-n {
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  border: 1px solid var(--rpt-rule);
  background: var(--surface-1);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}
.rpt-step:first-child .rpt-step-n {
  border-color: var(--seal);
  color: var(--seal);
  font-weight: 700;
}

.rpt-step-body { display: flex; flex-direction: column; gap: 2px; min-width: 0; padding-top: 2px; }
.rpt-step-title {
  font-size: var(--fs-base);
  line-height: 1.45;
  color: var(--text-primary);
  overflow-wrap: anywhere;
}
.rpt-step-meta {
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-muted);
  letter-spacing: 0.03em;
}

/* ============================ 03 流程图 + 摘要 ============================ */
.rpt-split {
  display: grid;
  grid-template-columns: minmax(0, 1.9fr) minmax(300px, 1fr);
  gap: 18px;
  align-items: stretch;
}
.rpt-graph { min-width: 0; display: flex; flex-direction: column; }
/*
  流程图必须**限高**。
  Mermaid 关掉 useMaxWidth 后按自然尺寸出图，一张 36 节点的图固有高度能有几千像素；
  不给上限的话，这一节会把整页撑到近 9000px，后面「支撑材料 / 结论」直接被挤到几屏之外
  —— 一页报告变成一张图的滚动条。限高 + 框内滚动，图才回到「插图」的位置。
  需要看整体时用 75% 缩放，或在框内拖动。
*/
.rpt-graph :deep(.mflow) {
  border-radius: var(--radius-sm);
  /* 固定高度而不是 max-height：「适应」按框高算比例，框高若随内容变化
     会形成「算完缩小 → 框变矮 → 再算更小」的反馈，图会越缩越小。 */
  height: clamp(340px, 52vh, 560px);
}

.rpt-caption {
  margin: 10px 0 0;
  font-size: var(--fs-sm);
  line-height: 1.65;
  color: var(--text-muted);
}
.rpt-caption b {
  font-family: var(--font-mono);
  font-weight: 700;
  color: var(--seal);
  letter-spacing: 0.06em;
  margin-right: 4px;
}

.rpt-digest {
  display: flex;
  flex-direction: column;
  min-height: 0;
  /* 必须限高：AI 摘要有几十上百行，不限高会把这一行的行高顶到四千多像素，
     左边那栏（流程图）跟着被拉伸，整页又变回「一张图的滚动条」。
     限高后 <pre> 自己滚。 */
  max-height: 560px;
  border: 1px solid var(--rpt-rule);
  border-radius: var(--radius-sm);
  background: var(--surface-1);
}
.rpt-digest-head,
.rpt-digest-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 12px;
  flex: none;
}
.rpt-digest-head { border-bottom: 1px solid var(--rpt-rule-soft); }
.rpt-digest-foot { border-top: 1px solid var(--rpt-rule-soft); flex-wrap: wrap; }
.rpt-digest-body {
  margin: 0;
  padding: 12px;
  flex: 1;
  min-height: 0;
  overflow: auto;
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  line-height: 1.7;
  color: var(--text-secondary);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.rpt-digest-hint { font-size: var(--fs-xs); color: var(--text-muted); }

.rpt-src { margin-top: 16px; }
.rpt-src summary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: var(--fs-sm);
  color: var(--text-muted);
  cursor: pointer;
  padding: 2px 0;
}
.rpt-src summary::before {
  content: "＋";
  font-family: var(--font-mono);
  color: var(--seal);
}
.rpt-src[open] summary::before { content: "－"; }
.rpt-src summary:hover { color: var(--text-primary); }
.rpt-code {
  display: block;
  width: 100%;
  height: 200px;
  margin-top: 10px;
  padding: 10px 12px;
  resize: vertical;
  box-sizing: border-box;
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  line-height: 1.6;
  color: var(--text-secondary);
  background: var(--surface-2);
  border: 1px solid var(--rpt-rule);
  border-radius: var(--radius-sm);
}
.rpt-src-actions { display: flex; gap: 18px; margin-top: 8px; }

/* ============================ 04 支撑材料 ============================ */
/* 附录收进两栏，区块之间也只有发丝线 —— 视觉权重明显低于前三节 */
.rpt-blocks {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 26px 40px;
}
.rpt-block { min-width: 0; }
.rpt-block--wide { grid-column: 1 / -1; }
.rpt-block-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 0 0 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--rpt-rule-soft);
  font-size: var(--fs-base);
  font-weight: 600;
  color: var(--text-primary);
}
.rpt-block-title span {
  font-size: var(--fs-xs);
  font-weight: 400;
  color: var(--text-muted);
}

.rpt-hubs { margin: 0; padding: 0; list-style: none; }
.rpt-hubs li {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 10px;
  padding: 9px 0;
  border-bottom: 1px dashed var(--rpt-rule-soft);
}
.rpt-hubs li:last-child { border-bottom: 0; }
.rpt-hub-rank {
  font-family: var(--font-mono);
  font-size: var(--fs-sm);
  color: var(--seal);
  opacity: 0.85;
}
.rpt-hub-main { min-width: 0; }
.rpt-hub-line { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.rpt-hub-name { font-size: var(--fs-base); color: var(--text-primary); }
.rpt-hub-lv {
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-muted);
}
.rpt-hub-lv.lv1 { color: var(--accent); }
.rpt-hub-lv.lv2 { color: var(--violet-text); }
.rpt-hub-lv.lv3 { color: var(--amber); }
.rpt-hub-lv.lv4 { color: var(--magenta); }
.rpt-hub-deg {
  margin-left: auto;
  font-size: var(--fs-xs);
  color: var(--text-muted);
}
.rpt-hub-conn { display: flex; flex-wrap: wrap; gap: 4px 10px; margin-top: 4px; }
.rpt-hub-conn .rpt-chip { border: 0; padding: 0; background: none; }

.rpt-clusters { display: flex; flex-direction: column; gap: 14px; }
.rpt-cluster { padding-left: 12px; border-left: 2px solid var(--rpt-rule); }
.rpt-cluster-head { display: flex; align-items: baseline; gap: 8px; }
.rpt-cluster-no { font-family: var(--font-mono); font-size: var(--fs-xs); color: var(--seal); }
.rpt-cluster-label { font-size: var(--fs-md); font-weight: 600; color: var(--text-primary); }
.rpt-cluster-size { margin-left: auto; font-size: var(--fs-xs); color: var(--text-muted); }
.rpt-cluster-meta { font-size: var(--fs-xs); color: var(--text-muted); margin: 2px 0 6px; }

.rpt-levels { display: flex; flex-direction: column; gap: 10px; }
.rpt-level { padding-left: 10px; border-left: 2px solid var(--rpt-rule); }
.rpt-level.lv1 { border-color: var(--accent); }
.rpt-level.lv2 { border-color: var(--violet); }
.rpt-level.lv3 { border-color: var(--amber); }
.rpt-level.lv4 { border-color: var(--magenta); }
.rpt-level-head { display: flex; align-items: baseline; gap: 8px; }
.rpt-level-badge { font-family: var(--font-mono); font-size: var(--fs-xs); color: var(--text-muted); }
.rpt-level-label { font-size: var(--fs-md); color: var(--text-primary); }
.rpt-level-count {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: var(--fs-md);
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}
.rpt-level-samples {
  margin-top: 2px;
  font-size: var(--fs-xs);
  line-height: 1.6;
  color: var(--text-muted);
}

.rpt-bars { display: flex; flex-direction: column; gap: 7px; }
.rpt-bar-row { display: flex; align-items: center; gap: 10px; }
.rpt-bar-name {
  width: 92px;
  flex: none;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rpt-bar-track {
  flex: 1;
  height: 6px;
  border-radius: 999px;
  background: var(--bg-tertiary);
  overflow: hidden;
}
.rpt-bar-fill {
  height: 100%;
  border-radius: 999px;
  background: var(--accent);
  opacity: 0.75;
}
.rpt-bar-val {
  width: 74px;
  flex: none;
  text-align: right;
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.rpt-bridges { margin: 0; padding: 0; list-style: none; }
.rpt-bridges li { padding: 8px 0; border-bottom: 1px dashed var(--rpt-rule-soft); }
.rpt-bridges li:last-child { border-bottom: 0; }
.rpt-bridge-path {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 6px;
  font-size: var(--fs-md);
  color: var(--text-primary);
}
.rpt-bridge-path i {
  font-style: normal;
  font-size: var(--fs-xs);
  color: var(--violet-text);
  border-bottom: 1px dotted var(--violet-text);
}
.rpt-bridge-score {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-muted);
}
.rpt-bridge-evidence {
  margin-top: 3px;
  font-size: var(--fs-xs);
  line-height: 1.6;
  color: var(--text-muted);
}

.rpt-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.rpt-chip {
  padding: 1px 8px;
  border: 1px solid var(--rpt-rule);
  border-radius: 3px;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  background: var(--surface-1);
}
.rpt-chip--muted { color: var(--text-muted); }
.rpt-chip--warm { color: var(--amber); border-color: var(--amber); }

/* ============================ 05 结论 ============================ */
.rpt-sec--end { padding-bottom: 20px; }
.rpt-notes { margin: 0; padding: 0; list-style: none; max-width: 86ch; }
.rpt-notes li {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 10px;
  padding: 9px 0;
  border-bottom: 1px dashed var(--rpt-rule-soft);
}
.rpt-notes li:last-child { border-bottom: 0; }
.rpt-note-no { font-family: var(--font-mono); font-size: var(--fs-sm); color: var(--seal); }
.rpt-notes p {
  margin: 0;
  font-size: var(--fs-md);
  line-height: 1.8;
  color: var(--text-secondary);
}

/* ============================ 响应式 ============================ */
@media (max-width: 1180px) {
  .rpt-split { grid-template-columns: minmax(0, 1fr); }
  .rpt-digest { max-height: 300px; }
  .rpt-paths { gap: 20px 28px; }
}
@media (max-width: 980px) {
  .sum-view { padding: 20px 18px 48px; }
  .rpt-mast { flex-direction: column; align-items: stretch; gap: 16px; }
  .rpt-mast-tools { justify-content: flex-start; }
  .rpt-figures { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .rpt-fig:nth-child(4) { border-left: 0; }
  .rpt-paths { grid-template-columns: minmax(0, 1fr); }
  .rpt-blocks { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 620px) {
  .sum-view { padding: 16px 14px 40px; }
  /* 窄屏：缩放档单独占一行，标题旁的说明不再和它抢宽度 */
  .u-sec-title { flex-wrap: wrap; }
  .u-sec-title__fill { display: none; }
  .rpt-zoom { flex-basis: 100%; margin: 6px 0 0; }
  .rpt-mast h2 { font-size: calc(var(--fs-xl) + 8px); }
  .rpt-figures { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .rpt-fig { padding: 14px 14px 12px; }
  .rpt-fig::before { left: 14px; }
  .rpt-fig:nth-child(odd) { border-left: 0; }
  .rpt-fig:nth-child(n + 3) { border-top: 1px solid var(--rpt-rule-soft); }
  .rpt-fig-value { font-size: calc(var(--fs-xl) * 1.6); }
  .u-sec-title h3 { font-size: calc(var(--fs-xl) + 1px); }
  .rpt-zoom { margin-left: auto; }
}

/* 动效只在首次出现时轻微上浮，并且完全响应系统的减弱动效设置 */
@media (prefers-reduced-motion: no-preference) {
  .rpt-body > .rpt-sec {
    animation: rpt-in 0.42s var(--ease-out) both;
  }
  .rpt-body > .rpt-sec:nth-child(2) { animation-delay: 0.05s; }
  .rpt-body > .rpt-sec:nth-child(3) { animation-delay: 0.1s; }
  .rpt-body > .rpt-sec:nth-child(4) { animation-delay: 0.14s; }
  .rpt-body > .rpt-sec:nth-child(5) { animation-delay: 0.18s; }
}
@keyframes rpt-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: none; }
}
</style>
