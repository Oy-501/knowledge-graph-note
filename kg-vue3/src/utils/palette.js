/**
 * palette.js —— 图谱与语义配色的**唯一来源**
 * ------------------------------------------------------------
 * 为什么需要这个文件：
 * 改版前同一套品牌色（#4F6F8F / #7CB8A0 / #D4A574…）被硬编码在
 * 6 个组件里共 20+ 处 —— GraphCanvas、WorkbenchMiniGraph、
 * KbOntologyCanvas、NodeDetailDrawer、KnowledgeQA、MermaidFlow。
 * 结果换一次主题必须逐个文件找，而且必然漏掉一两处，
 * 表现为「图谱换了色但知识库页还是旧的」，很难发现。
 *
 * 现在所有颜色只在这里定义一次，组件 import 使用。
 * 这里的值是**霓虹色板**，与 styles/main.css 的令牌保持一致 ——
 * 改色时两边要一起改（CSS 变量给样式表用，JS 常量给 D3/Mermaid 用，
 * 因为这两者拿不到 CSS 变量的计算值来画图形）。
 *
 * ⚠️ 注意：这里的色值必须与 main.css 的 dark 主题对齐，
 * 因为图谱画布、Mermaid 渲染在深色背景下是常态。
 */

/* ============================================================
   一、图谱节点类型配色
   ------------------------------------------------------------
   每项给 [起始色, 结束色]，用于生成 SVG 线性渐变。
   深浅两档而不是单色：节点球面感靠渐变撑，
   单色圆点在深色画布上会显得很"扁"。
   ============================================================ */
export const NODE_COLORS = {
  /** 用户知识点（文档里抽出来的） */
  user: ['#22D3EE', '#0E7490'],
  /** 知识库节点（权威源） */
  kb: ['#8B5CF6', '#5B21B6'],
  /** 笔记节点（手写的） */
  note: ['#FBBF24', '#B45309'],
  /** 文档/文件节点 */
  doc: ['#60A5FA', '#1D4ED8'],
}

/** 单色版（用于不需要渐变的场合：小圆点、图例、列表色块） */
export const NODE_SOLID = {
  user: '#22D3EE',
  kb: '#8B5CF6',
  note: '#FBBF24',
  doc: '#60A5FA',
}

/* ============================================================
   二、领域 / 层级配色
   ------------------------------------------------------------
   领域色是一组「色相均匀分布」的颜色，用于区分不同领域。
   刻意避开纯红与纯绿：它们在中文界面上容易与「涨/跌」「通过/失败」
   的语义色混淆，而领域本身没有好坏之分。
   ============================================================ */
export const DOMAIN_COLORS = [
  '#22D3EE', // 青
  '#8B5CF6', // 紫
  '#FBBF24', // 琥珀
  '#F472B6', // 品红
  '#34D399', // 青绿
  '#60A5FA', // 蓝
  '#FB923C', // 橙
  '#A78BFA', // 淡紫
]

/** 知识层级（1 基础 → 4 应用）配色：由冷到暖，暗示由基础到应用 */
export const LEVEL_COLORS = {
  1: '#22D3EE',
  2: '#8B5CF6',
  3: '#FBBF24',
  4: '#F472B6',
}

/* ============================================================
   三、关系类型配色
   ------------------------------------------------------------
   与 utils/relationClassifier.js 的 relation_type 对应。
   后端也会下发 relation_color，后端有值时优先用后端的（见 LinkTooltip）。
   这里的值用于后端没给色的兜底，以及图谱连线染色。
   ============================================================ */
export const RELATION_COLORS = {
  is_a: '#60A5FA',
  part_of: '#34D399',
  depends_on: '#FBBF24',
  prerequisite: '#FBBF24',
  implementation: '#22D3EE',
  contrast: '#FB7185',
  analogy: '#F472B6',
  synonym: '#A78BFA',
  theory: '#22D3EE',
  contains: '#34D399',
  default: '#64748B',
}

/* ============================================================
   四、语义状态色（与 CSS 令牌同名同值）
   ============================================================ */
export const SEMANTIC = {
  success: '#34D399',
  warning: '#FBBF24',
  danger: '#FB7185',
  info: '#67E8F9',
  muted: '#64748B',
}

/* ============================================================
   五、工具函数
   ============================================================ */

/** 在 SVG <defs> 里登记一个线性渐变，返回渐变 id 供 fill 引用 */
export function ensureGradient(defs, id, from, to) {
  if (!defs) return id
  let g = defs.querySelector(`#${id}`)
  if (g) return id
  const NS = 'http://www.w3.org/2000/svg'
  g = document.createElementNS(NS, 'linearGradient')
  g.setAttribute('id', id)
  g.setAttribute('x1', '0%')
  g.setAttribute('y1', '0%')
  g.setAttribute('x2', '0%')
  g.setAttribute('y2', '100%')
  const a = document.createElementNS(NS, 'stop')
  a.setAttribute('offset', '0%')
  a.setAttribute('stop-color', from)
  const b = document.createElementNS(NS, 'stop')
  b.setAttribute('offset', '100%')
  b.setAttribute('stop-color', to)
  g.appendChild(a)
  g.appendChild(b)
  defs.appendChild(g)
  return id
}

/** 按领域名稳定取色（同名永远同色，与出现顺序无关） */
export function domainColor(name, index = 0) {
  if (!name) return DOMAIN_COLORS[index % DOMAIN_COLORS.length]
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0
  return DOMAIN_COLORS[h % DOMAIN_COLORS.length]
}

/**
 * 分数 → 语义色（校验准确率、知识点置信度等都用这一套）
 *
 * 为什么抽成函数：同一个「>=80 绿 / >=50 橙 / 否则红」的三元表达式
 * 被复制在 4 个组件里（ValidationPanel、WorkbenchLeftPanel、
 * WorkbenchMiniGraph、NodeDetailDrawer），而且用的是旧品牌的
 * #4caf50 / #e8a020 / #e84c4c —— 换主题时这 4 处必然漏改。
 *
 * 返回的是 **CSS 变量字符串**而不是十六进制：
 * 这个函数专给 DOM 用（Vue 的 :style 绑定），返回变量名才能跟着主题走。
 * 之前返回 SEMANTIC 里的十六进制，那是按深色主题挑的值，
 * 在亮色主题下压在白底上只有 2.7:1，直接不达标。
 * 需要十六进制给 Canvas/SVG 用的场合请用 SEMANTIC。
 */
export function scoreColor(score, thresholds = [80, 50]) {
  const [high, mid] = thresholds
  if (score >= high) return 'var(--success)'
  if (score >= mid) return 'var(--warning)'
  return 'var(--danger)'
}

/**
 * '#22D3EE' + 0.8 -> 'rgba(34, 211, 238, 0.8)'
 *
 * 为什么需要它：D3 的 attr('stroke', ...) 只认字符串颜色，
 * 拿不到 CSS 变量的计算值，所以透明度只能在这里拼。
 * 直接写 'rgba(124,184,160,.8)' 那种字面量正是这次改版要消灭的东西 ——
 * 色板一改，散落的字面量就全部失配。
 */
export function hexAlpha(hex, alpha = 1) {
  const h = String(hex).replace('#', '')
  const full = h.length === 3 ? h.split('').map(c => c + c).join('') : h
  const n = parseInt(full, 16)
  if (Number.isNaN(n)) return hex
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

/** Mermaid 主题变量：跟随应用的亮/暗主题，避免流程图在深色页面上"白得刺眼" */
export function mermaidThemeVars(isDark) {
  if (isDark) {
    return {
      background: '#0A0C13',
      primaryColor: '#11141F',
      primaryTextColor: '#E8EDF7',
      primaryBorderColor: '#22D3EE',
      secondaryColor: '#181C2A',
      tertiaryColor: '#181C2A',
      lineColor: '#64748B',
      textColor: '#A3B0C7',
      clusterBkg: '#11141F',
      clusterBorder: 'rgba(255,255,255,0.10)',
      edgeLabelBackground: '#0A0C13',
    }
  }
  return {
    background: '#FFFFFF',
    primaryColor: '#FFFFFF',
    primaryTextColor: '#101725',
    primaryBorderColor: '#0891B2',
    secondaryColor: '#F2F4F9',
    tertiaryColor: '#F2F4F9',
    lineColor: '#94A3B8',
    textColor: '#4A5670',
    clusterBkg: '#F2F4F9',
    clusterBorder: '#CFD6E4',
    edgeLabelBackground: '#FFFFFF',
  }
}
