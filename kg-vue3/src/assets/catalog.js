/**
 * 素材目录（assets/catalog.js）
 * ------------------------------------------------------------
 * 全站素材的唯一声明处。UI 只从这里取数据，不自己拼路径。
 *
 * 为什么用 import.meta.glob 而不是手写 import：
 *   素材是可增删的（往 assets/textures/ 丢一个 svg 就应该能用）。
 *   glob 在**构建期**静态分析出所有文件并生成 URL，
 *   既保证了 Vite 能正确做哈希/打包，又不用手维护一份路径清单。
 *   注意必须是静态字面量 —— import.meta.glob 的参数不能是变量。
 *
 * 素材来源与许可证见同目录 CREDITS.md：
 *   图案 = Hero Patterns (CC BY 4.0，需署名)
 *   摄影 = Unsplash (Unsplash License，无需署名)
 */

// —— 构建期收集素材 URL ——
const textureUrls = import.meta.glob('./textures/*.svg', {
  eager: true, query: '?url', import: 'default'
})
const backdropUrls = import.meta.glob('./backdrops/*.webp', {
  eager: true, query: '?url', import: 'default'
})

/** 从 glob 结果里按文件名（不含扩展名）取 URL */
function urlOf(map, key) {
  const hit = Object.keys(map).find(p => p.endsWith(`/${key}.svg`) || p.endsWith(`/${key}.webp`))
  return hit ? map[hit] : ''
}

/* ============================================================
   一、纹理图案（24 个，来自 Hero Patterns）
   ------------------------------------------------------------
   参数说明：
     size    —— 平铺尺寸（px）。图案 tile 的原始尺寸在 12~600px 之间，
                统一放大到 120~420 会让线条更细腻、更适合做「底纹」；
                原尺寸直接用会显得粗、抢内容。
     opacity —— 图案层不透明度。默认给得很低（0.3~0.55），
                底纹的职责是「有质感」而不是「被看见」。
     fit     —— 适合与摄影背景搭配（photo）还是单独用（solo）。
   ============================================================ */
export const PATTERNS = [
  // —— 科技 / 数字 ——
  { key: 'circuit-board', name: '电路板', group: '科技数字', size: 300, opacity: 0.42, desc: 'PCB 走线，最贴「科技」的底纹' },
  { key: 'connections', name: '连接节点', group: '科技数字', size: 54, opacity: 0.5, desc: '节点与连线，直接呼应知识图谱' },
  { key: 'signal', name: '信号波', group: '科技数字', size: 126, opacity: 0.45, desc: '无线电波，感知/传输意象' },
  { key: 'current', name: '电流', group: '科技数字', size: 114, opacity: 0.42, desc: '流动线条，方向感强' },
  { key: 'pixel-dots', name: '像素点', group: '科技数字', size: 24, opacity: 0.4, desc: '像素点阵，数字感' },
  { key: 'death-star', name: '同心圆环', group: '科技数字', size: 160, opacity: 0.36, desc: '雷达/扫描意象' },
  { key: 'rails', name: '轨道线', group: '科技数字', size: 30, opacity: 0.4, desc: '平行轨道，结构感' },

  // —— 网格 / 结构 ——
  { key: 'graph-paper', name: '方格纸', group: '网格结构', size: 150, opacity: 0.4, desc: '经典方格，编辑器/画布底纹' },
  { key: 'bathroom-floor', name: '等距砖', group: '网格结构', size: 128, opacity: 0.42, desc: '伪 3D 等距网格' },
  { key: 'tiny-checkers', name: '细棋盘', group: '网格结构', size: 20, opacity: 0.35, desc: '极细网格，最接近「蓝图」' },
  { key: 'boxes', name: '方盒', group: '网格结构', size: 40, opacity: 0.4, desc: '模块化块面' },
  { key: 'plus', name: '十字点阵', group: '网格结构', size: 120, opacity: 0.45, desc: '极简十字点阵' },
  { key: 'rounded-plus-connected', name: '连接十字', group: '网格结构', size: 168, opacity: 0.42, desc: '圆角十字 + 连线' },
  { key: 'steel-beams', name: '钢梁', group: '网格结构', size: 84, opacity: 0.36, desc: '工业结构' },
  { key: 'topography', name: '等高线', group: '网格结构', size: 420, opacity: 0.4, desc: '地形等高线，数据意象' },

  // —— 材质 / 质感 ——
  { key: 'texture', name: '颗粒', group: '材质质感', size: 8, opacity: 0.4, desc: '最细的噪点，近看是沙感' },
  { key: 'heavy-rain', name: '斜线雨幕', group: '材质质感', size: 32, opacity: 0.4, desc: '斜向速度线' },
  { key: 'diagonal-stripes', name: '斜条纹', group: '材质质感', size: 64, opacity: 0.35, desc: '扫描线条' },
  { key: 'morphing-diamonds', name: '菱形渐变', group: '材质质感', size: 120, opacity: 0.4, desc: '装饰性几何' },
  { key: 'bamboo', name: '竹节', group: '材质质感', size: 40, opacity: 0.4, desc: '竖向节奏' },
  { key: 'endless-clouds', name: '云纹', group: '材质质感', size: 140, opacity: 0.34, desc: '柔和曲线底纹' },
  { key: 'overlapping-circles', name: '交叠圆', group: '材质质感', size: 160, opacity: 0.4, desc: '集合/交集意象' },
  { key: 'fancy-rectangles', name: '花式矩形', group: '材质质感', size: 150, opacity: 0.36, desc: '装饰矩形' },
  { key: 'polka-dots', name: '圆点', group: '材质质感', size: 34, opacity: 0.36, desc: '轻量点阵' },
]

/* ============================================================
   二、摄影背景（14 张，来自 Unsplash）
   ------------------------------------------------------------
   opacity —— 照片层不透明度。默认 0.35~0.6：
              照片是**氛围**不是**内容**，压到能看出明暗结构即可，
              再高就会与前景文字抢对比度。
   ============================================================ */
export const BACKDROPS = [
  { key: 'mesh-dusk', name: '冷光切面', group: '抽象光影', opacity: 0.55, desc: '蓝色冷光切面' },
  { key: 'mesh-aurora', name: '极光鳍片', group: '抽象光影', opacity: 0.5, desc: '层叠暗色鳍状结构' },
  { key: 'mesh-flow', name: '暗绸', group: '抽象光影', opacity: 0.45, desc: '暗色绸缎曲面' },
  { key: 'mesh-tide', name: '潮汐壳', group: '抽象光影', opacity: 0.5, desc: '曲面壳体' },
  { key: 'mesh-ember', name: '余烬', group: '抽象光影', opacity: 0.45, desc: '鳍片 + 暖色边缘光' },
  { key: 'mesh-violet', name: '紫萼', group: '抽象光影', opacity: 0.5, desc: '暗紫花瓣形体' },
  { key: 'tech-matrix', name: '机柜', group: '数字科技', opacity: 0.4, desc: '机房机柜与线缆' },
  { key: 'tech-board', name: '电路微距', group: '数字科技', opacity: 0.4, desc: '主板微距' },
  { key: 'tech-datastream', name: '数据流', group: '数字科技', opacity: 0.34, desc: '数据编码意象' },
  { key: 'arch-lines', name: '交换设备', group: '数字科技', opacity: 0.38, desc: '网络设备与网线' },
  { key: 'space-earth', name: '夜空地球', group: '星空宇宙', opacity: 0.5, desc: '轨道视角夜景' },
  { key: 'space-nebula', name: '深空星野', group: '星空宇宙', opacity: 0.45, desc: '星野深空' },
  { key: 'mat-marble', name: '罗纹暗面', group: '暗色材质', opacity: 0.5, desc: '斜向罗纹' },
  { key: 'mat-ink', name: '鎏金流线', group: '暗色材质', opacity: 0.45, desc: '暗底鎏金' },
]

/* ============================================================
   三、整套预设（photo + pattern 的搭配方案）
   ------------------------------------------------------------
   为什么还要「整套预设」而不让用户自己拼：
   14 张图 × 24 个图案 = 336 种组合，其中大部分会打架
   （比如「数据流」叠「细棋盘」会糊成一片）。
   这里挑出 8 套经过实际叠加验证的组合，
   每套再暴露「图案尺寸 / 不透明度」两个旋钮给高级用户微调。
   每套的 swatch 用于选择器里画缩略预览（不额外下载缩略图）。
   ============================================================ */
export const ASSET_PRESETS = [
  {
    id: 'deep-grid', name: '深空网格', hint: '默认 · 结构清晰不易抢内容',
    photo: null, pattern: 'graph-paper',
    patternSize: 150, patternOpacity: 0.5, photoOpacity: 0, blur: 0,
    swatch: ['#05060A', '#22D3EE'],
  },
  {
    id: 'circuit-lab', name: '电路实验台', hint: '科技感最强，适合图谱页',
    photo: 'tech-board', pattern: 'circuit-board',
    patternSize: 320, patternOpacity: 0.3, photoOpacity: 0.34, blur: 0,
    swatch: ['#0A0C13', '#2DD4BF'],
  },
  {
    id: 'nebula', name: '深空星野', hint: '氛围型，适合总结/导出页',
    photo: 'space-nebula', pattern: 'polka-dots',
    patternSize: 34, patternOpacity: 0.22, photoOpacity: 0.55, blur: 0,
    swatch: ['#0B1024', '#8B5CF6'],
  },
  {
    id: 'orbit', name: '轨道夜景', hint: '大气，适合个人主页',
    photo: 'space-earth', pattern: 'connections',
    patternSize: 54, patternOpacity: 0.24, photoOpacity: 0.6, blur: 1,
    swatch: ['#0A0F1C', '#FBBF24'],
  },
  {
    id: 'mesh-dark', name: '冷光曲面', hint: '纯摄影，无图案干扰',
    photo: 'mesh-dusk', pattern: null,
    patternSize: 150, patternOpacity: 0, photoOpacity: 0.62, blur: 0,
    swatch: ['#0D1A1F', '#67E8F9'],
  },
  {
    id: 'ribbed', name: '罗纹暗面', hint: '极简克制，长时间阅读不累',
    photo: 'mat-marble', pattern: 'diagonal-stripes',
    patternSize: 90, patternOpacity: 0.16, photoOpacity: 0.42, blur: 2,
    swatch: ['#111318', '#F472B6'],
  },
  {
    id: 'blueprint', name: '蓝图', hint: '等距网格，编辑器/工作台',
    photo: null, pattern: 'bathroom-floor',
    patternSize: 128, patternOpacity: 0.55, photoOpacity: 0, blur: 0,
    swatch: ['#0A0C13', '#60A5FA'],
  },
  {
    id: 'matrix', name: '数据流', hint: '机房质感，后台管理',
    photo: 'tech-matrix', pattern: 'tiny-checkers',
    patternSize: 24, patternOpacity: 0.2, photoOpacity: 0.34, blur: 1,
    swatch: ['#080B10', '#34D399'],
  },
]

/* ============================================================
   四、解析函数
   ============================================================ */

/** 图案 key -> URL（找不到返回空串，调用方需容忍） */
export function patternUrl(key) {
  return key ? urlOf(textureUrls, key) : ''
}

/** 背景 key -> URL */
export function backdropUrl(key) {
  return key ? urlOf(backdropUrls, key) : ''
}

/** 预设 id -> 预设对象 */
export function presetById(id) {
  return ASSET_PRESETS.find(p => p.id === id) || null
}

/**
 * 把一套预设解析成可直接写进 CSS 变量的键值对。
 *
 * 返回的键名与 texture.css 里的槽位一一对应 ——
 * 这是「素材声明」与「素材呈现」之间唯一的契约点，
 * 改槽位名只需要改这里和 texture.css 两处。
 */
export function presetToCssVars(preset) {
  if (!preset) return {}
  const pUrl = patternUrl(preset.pattern)
  const bUrl = backdropUrl(preset.photo)
  return {
    '--tex-pattern': pUrl ? `url("${pUrl}")` : 'none',
    '--tex-pattern-size': `${preset.patternSize || 64}px`,
    '--tex-pattern-opacity': String(preset.pattern ? (preset.patternOpacity ?? 0.4) : 0),
    '--tex-photo': bUrl ? `url("${bUrl}")` : 'none',
    '--tex-photo-opacity': String(bUrl ? (preset.photoOpacity ?? 0.5) : 0),
    '--tex-photo-blur': `${preset.blur || 0}px`,
  }
}

/** 素材署名文案（CC BY 4.0 要求可见，放在「个人主页 → 关于素材」） */
export const CREDITS = {
  patterns: 'Patterns from Hero Patterns (heropatterns.com) by Steve Schoger — CC BY 4.0',
  photos: 'Photographs from Unsplash (unsplash.com) — Unsplash License',
}

export const COUNTS = {
  patterns: Object.keys(textureUrls).length,
  backdrops: Object.keys(backdropUrls).length,
}
