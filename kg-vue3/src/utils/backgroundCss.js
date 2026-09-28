/**
 * 背景 CSS 生成引擎
 * =================
 * 把「一句自然语言 + 一张图」翻译成可直接粘贴的 CSS 背景代码。
 *
 * 三条设计原则，决定了下面每一处取舍：
 *
 * 1. **不调远程模型，全部本地规则解析。**
 *    结果稳定、可复现、离线可用。更重要的是每条判断都能说出「为什么」——
 *    工具类需求要的是可解释、可预期，而不是每次都可能不一样的输出。
 *    匹配分两级：先看有没有 `不拉伸` / `完整显示` 这类**成套说法**，
 *    再退化为单个关键词。顺序不能反，否则「不要平铺」会被拆成
 *    「不」+「平铺」两条互不相干的信息。
 *
 * 2. **图片分析只做算得准的事，不做语义识别。**
 *    亮度、细节密度重心、主色、各断点裁剪比例——这些都能从像素算出来，
 *    所以能给出「主体重心在 38%,44%」这种可验证的表述。
 *    识别不出「这是个人」就不说，绝不编造。
 *
 * 3. **读不到像素时降级，而不是报错。**
 *    跨域图片会让 canvas 被污染（getImageData 抛 SecurityError）。
 *    这时退回只看宽高比，并明确标注「像素分析不可用」——
 *    让用户知道结论的可靠边界在哪。
 *
 * 除 analyzeImage 这个显式 DOM 包装外全是纯函数，可直接在 Node 里单测。
 */

/* ================================================================ 设备与断点 */

/** 预览用的设备预设。尺寸取自真实机型，预览才有意义。 */
export const DEVICES = [
  { key: 'phone', label: '手机竖屏', w: 390, h: 844, hint: 'iPhone 14' },
  { key: 'phone-land', label: '手机横屏', w: 844, h: 390, hint: '同一台手机横过来' },
  { key: 'tablet', label: '平板', w: 820, h: 1180, hint: 'iPad Air' },
  { key: 'laptop', label: '笔记本', w: 1366, h: 768, hint: '最常见的笔记本' },
  { key: 'desktop', label: '桌面', w: 1920, h: 1080, hint: '1080p' },
  { key: 'ultrawide', label: '超宽屏', w: 2560, h: 1080, hint: '21:9' },
]

/**
 * 媒体查询分组。
 *
 * 每一项都自带一个「代表视口」——它决定了该断点下图片会被裁掉多少，
 * 进而决定 background-position 取什么值。把代表视口和断点写在一起，
 * 是因为改断点时几乎必然要一起改它，分开两处必然忘。
 */
const MEDIA_MOBILE_FIRST = [
  { query: '(min-width: 640px)', label: '平板及以上', vp: { w: 768, h: 1024 } },
  { query: '(min-width: 1024px)', label: '桌面及以上', vp: { w: 1366, h: 768 } },
  { query: '(min-width: 1536px)', label: '超宽屏', vp: { w: 2560, h: 1080 } },
]

const MEDIA_DESKTOP_FIRST = [
  { query: '(max-width: 1023px)', label: '平板及以下', vp: { w: 900, h: 1200 } },
  { query: '(max-width: 639px)', label: '手机', vp: { w: 390, h: 844 } },
]

/** 基准块（未加媒体查询时）的代表视口：跟随响应式策略 */
const BASE_VIEWPORT = {
  'mobile-first': { w: 390, h: 844 },
  'desktop-first': { w: 1920, h: 1080 },
}

/* ================================================================ 语义词典 */

/** 否定词：紧邻关键词前出现时，表示该关键词被否定 */
const NEG_ONE = ['不', '别', '勿', '非', '免', '无']
const NEG_TWO = ['不要', '不用', '不必', '无需', '请勿', '不许']

function isNegated(text, index) {
  const one = text.slice(Math.max(0, index - 1), index)
  const two = text.slice(Math.max(0, index - 2), index)
  return NEG_ONE.includes(one) || NEG_TWO.includes(two)
}

/**
 * 在文本里找关键词。
 *
 * 同时返回 hit（有未被否定的出现）与 negated（有被否定的出现）。
 * 两个都给而不是只给一个：「不拉伸、也不要留白」同时传达了
 * 「别 cover」「别 contain」两条信息，只取一个就丢了。
 */
function probe(text, keywords) {
  let hit = false
  let negated = false
  const where = []
  for (const kw of keywords) {
    let i = text.indexOf(kw)
    while (i !== -1) {
      if (isNegated(text, i)) negated = true
      else { hit = true; where.push(kw) }
      i = text.indexOf(kw, i + 1)
    }
  }
  return { hit, negated, where }
}

/**
 * 按顺序匹配整句规则，先命中者胜。
 *
 * 关键点：**被否定的匹配不算命中**。
 * 直接用 `re.test()` 会漏掉否定——「不要铺满」里 `铺满` 照样命中 cover 规则，
 * 于是用户说「不要铺满」反而得到 cover，正好反了。
 * 所以这里逐个匹配位置检查是否被否定，全部被否定时该条规则作废，
 * 往下走别的规则，或落到 `fillNeg.negated → contain` 的兜底分支。
 *
 * 注意「不要裁剪」这类**否定词本身写在规则里**的情况：匹配从 `不` 开始，
 * 起点之前没有否定词，因此不会被误判——这正是想要的行为。
 */
function matchRules(text, rules) {
  for (const r of rules) {
    const flags = r.re.flags.includes('g') ? r.re.flags : r.re.flags + 'g'
    const g = new RegExp(r.re.source, flags)
    let m
    while ((m = g.exec(text)) !== null) {
      if (!isNegated(text, m.index)) return r
      // 零宽匹配会让 exec 原地踏步，手动推进一步
      if (m[0].length === 0) g.lastIndex++
    }
  }
  return null
}

/* 填充方式：整句规则，顺序即优先级 */
const FILL_RULES = [
  {
    value: 'contain',
    why: '描述要求「完整显示 / 不裁剪 / 不拉伸」，取 contain：整张图完整放进容器、不变形，代价是可能留白',
    re: /不(要|得|可|应)?(被)?(拉伸|拉长|拉扯|裁|裁剪|裁切|裁掉|切割|变形)|不失真|不变形|保持比例|原比例|完整(显示|可见|呈现|展示)|全部(可见|显示)|全图(可见|显示)|contain|letterbox|适应容器/,
  },
  {
    value: 'repeat-x',
    why: '提到横向平铺，取 repeat-x：只在水平方向重复（常用于分隔纹样）',
    re: /横向(平铺|重复)|水平(平铺|重复)|repeat-x/,
  },
  {
    value: 'repeat-y',
    why: '提到纵向平铺，取 repeat-y：只在垂直方向重复',
    re: /纵向(平铺|重复)|垂直(平铺|重复)|竖向(平铺|重复)|repeat-y/,
  },
  {
    value: 'repeat',
    why: '提到平铺 / 重复，取 repeat：按图案自身尺寸重复铺满，不走 cover 那套缩放逻辑',
    re: /平铺|重复铺|四方连续|无缝(拼接|纹理)|tile|repeat(?!-)/,
  },
  {
    value: 'stretch',
    why: '明确要求拉伸铺满，取 100% 100%：会改变图片比例。除非图片是抽象渐变或纹理，否则不推荐',
    re: /拉伸铺|硬拉|变形铺满|铺开铺满|squeeze|stretch/,
  },
  {
    value: 'cover',
    why: '描述要求铺满 / 不留白，取 cover：等比放大到刚好盖住容器、不变形，多余部分裁掉',
    re: /铺满|填满|充满|覆盖|占满|满屏|撑满|不留(白|空白|空隙)|不露白|cover/,
  },
]

/* 用途场景 */
const USAGE_RULES = [
  { value: 'pattern', re: /平铺|底纹|纹理|图案|花纹|格子|暗纹|背景纹|纹样/ },
  { value: 'hero', re: /英雄|首屏|主视觉|开屏|全屏图|大图|落地页头|hero|主画面/ },
  { value: 'banner', re: /横幅|通栏|条幅|banner|栏目头|顶部条/ },
  { value: 'card', re: /卡片|头像|缩略图|封面小图|列表图|卡面|小图/ },
  { value: 'section', re: /区块|段落背景|内容区|正文背景|section|栏目背景/ },
]

/**
 * 焦点位置。
 *
 * 每条都要求出现「主体词」——不能只匹配 `在上`。
 * 只匹配方位时，`现在上传` 这种句子里的 `在上` 会被误判成「焦点在顶部」，
 * 这是纯关键词匹配最典型的误报。
 *
 * 主体词里**刻意不含 `文字` / `标题` / `文案`**：
 * 那些词讲的是「文字摆哪儿」，与「图片主体在哪儿」是两件事。
 * 混在一起的话，「标题在底部」会被同时判成
 * 「图片主体在底部」+「文字在底部」——前者会让焦点被错误锁死，
 * 图片分析算出来的重心就白算了。
 */
const SUBJ = '(?:主体|人物|人脸|重点|重心|焦点|视觉中心|内容|主图|对象|物件)'
const AT = '(?:在|位于|处于|放到?|靠|偏)'
const FOCAL_RULES = [
  { value: '50% 0%', label: '顶部', re: new RegExp(`${SUBJ}[^，,。；]{0,4}${AT}(?:最)?(?:上|上面|上方|上边|上部|顶部|顶端)|靠上|上对齐|顶端对齐`) },
  { value: '50% 100%', label: '底部', re: new RegExp(`${SUBJ}[^，,。；]{0,4}${AT}(?:最)?(?:下|下面|下方|下边|下部|底部|底下)|靠下|下对齐|底部对齐|地平线`) },
  { value: '0% 50%', label: '左侧', re: new RegExp(`${SUBJ}[^，,。；]{0,4}${AT}(?:最)?(?:左|左边|左侧|左面|左部|左方)|靠左|左对齐`) },
  { value: '100% 50%', label: '右侧', re: new RegExp(`${SUBJ}[^，,。；]{0,4}${AT}(?:最)?(?:右|右边|右侧|右面|右部|右方)|靠右|右对齐`) },
  // 这条原先只写了裸的「居中」，于是「文字居中」会把**图片焦点**锁成居中。
  // 与上面四条同理，必须要求主体词；纯方位词汇一律不算。
  { value: '50% 50%', label: '居中', re: new RegExp(`${SUBJ}[^，,。；]{0,4}${AT}(?:最)?(?:中|中间|中央|居中|中心)|主体居中|构图居中|画面居中`) },
]

/* 文字位置（决定遮罩往哪个方向压暗） */
const TEXT_POS_RULES = [
  { value: 'top', re: /(文字|标题|文案|副标题)[^，,。；]{0,4}(在|位于|放|靠|偏)?(最)?(上|上方|上面|顶部)|标题在上/ },
  { value: 'center', re: /(文字|标题|文案)[^，,。；]{0,4}(在|位于|放|靠)?(中间|中央|正中)|居中标题|文字居中/ },
  { value: 'left', re: /(文字|标题|文案)[^，,。；]{0,4}(在|位于|放|靠|偏)?(左|左边|左侧)|左对齐标题/ },
  { value: 'right', re: /(文字|标题|文案)[^，,。；]{0,4}(在|位于|放|靠|偏)?(右|右边|右侧)|右对齐标题/ },
]

/**
 * 「保住主体」类说法。
 *
 * 这些词必须**先从用于判断填充方式的文本里剔除掉**，原因：
 * `不要裁到主体` 讲的是**焦点保护**，不是「用 contain 完整显示」。
 * 若不剔除，contain 规则里的 `不要…裁…` 会抢先命中，于是
 * 「全屏铺满不留白，不要裁到主体」——最常见的英雄区描述——会被判成 contain，
 * 整个输出方向就反了（该 cover 的给了 contain，还凭空多出一堆留白警告）。
 */
const PROTECT_PHRASES = [
  '不要裁到', '别裁到', '不要裁掉', '别裁掉', '不要切到', '不要切掉', '别切到',
  '保证主体可见', '保住主体', '主体可见', '人物可见', '重点可见',
  'logo', '标志',
]


const USAGE_LABEL = {
  hero: '全屏英雄区',
  banner: '横幅 / 通栏',
  card: '卡片 / 缩略图',
  pattern: '平铺图案',
  section: '区块背景',
  block: '普通背景块',
}

const FILL_LABEL = {
  cover: '铺满裁剪 cover',
  contain: '完整显示 contain',
  stretch: '拉伸铺满',
  repeat: '平铺重复 repeat',
  'repeat-x': '横向平铺 repeat-x',
  'repeat-y': '纵向平铺 repeat-y',
}

const TEXT_POS_LABEL = { top: '顶部', center: '居中', bottom: '底部', left: '左侧', right: '右侧' }

/**
 * 焦点来源文案之一，抽成常量是因为**生成头部注释时要拿它做判断**：
 * 只有在真的按细节重心定位时，报出重心百分比才有意义。
 * 两处各写一遍字符串，改一处忘一处就会开始说假话。
 */
const FOCUS_FROM_DETAIL = '按图片细节重心自动定位'

/* ================================================================ 意图解析 */

/**
 * 把自然语言解析成意图槽位。
 *
 * `notes` 记录每一条判定的依据，界面直接展示——用户能看到「为什么这么写」，
 * 而不是拿到一段无法质疑的代码。
 * `unmatched` 列出「本想识别但没找到」的项，提示用户补充描述。
 */
export function parseIntent(input = '') {
  const raw = String(input || '')
  const text = raw
    .replace(/[，、；：]/g, ',')
    .replace(/（/g, '(')
    .replace(/）/g, ')')
    .replace(/\s+/g, ' ')
    .toLowerCase()

  const notes = []

  /* ---- 用途 ---- */
  const usageRule = matchRules(text, USAGE_RULES)
  const usage = usageRule ? usageRule.value : 'block'
  if (usageRule) notes.push(`场景判定为「${USAGE_LABEL[usage]}」`)

  /* ---- 填充方式 ---- */
  // 先把「保住主体」类说法摘掉再判断填充，否则 contain 规则会抢先命中（原因见 PROTECT_PHRASES）
  let fillText = text
  for (const p of PROTECT_PHRASES) fillText = fillText.split(p).join(' ')

  const fillRule = matchRules(fillText, FILL_RULES)
  let fill = fillRule ? fillRule.value : null
  const fillNeg = probe(fillText, ['铺满', '填满', '覆盖', '裁剪', '拉伸', '变形'])
  if (fillRule) {
    notes.push(fillRule.why)
  } else if (fillNeg.negated) {
    fill = 'contain'
    notes.push('出现否定说法（如「不拉伸 / 不裁剪」），按 contain 处理：保住整张图，宁可留白')
  }
  if (!fill) {
    fill = usage === 'pattern' ? 'repeat' : 'cover'
    notes.push(`未明说填充方式，按场景默认取 ${fill}`)
  }

  /* 显式否定了平铺，但前面又判成平铺 → 纠正 */
  const repeatProbe = probe(fillText, ['平铺', '重复'])
  if (repeatProbe.negated && fill.startsWith('repeat')) {
    fill = 'cover'
    notes.push('描述里出现「不平铺」，已从 repeat 改为 cover')
  }

  /* ---- 全屏 ---- */
  const fsProbe = probe(text, ['全屏', '满屏', '整屏', '整个屏幕', '占满屏', '100vh', '全视口', '一屏高', '整屏高', '满一屏'])
  let fullscreen = fsProbe.hit && !fsProbe.negated
  if (fsProbe.negated) notes.push('描述里否定了全屏，改用内容高度')

  /* ---- 显式高度 ---- */
  const height = parseHeight(text)
  if (height) notes.push(`识别到高度约束：${height.label}`)

  if (!fullscreen && !height && usage === 'hero') {
    fullscreen = true
    notes.push('场景是英雄区且未指定高度，按整屏处理')
  }

  /* ---- 焦点 ---- */
  const focalRule = matchRules(text, FOCAL_RULES)
  const focal = focalRule ? focalRule.value : null
  if (focalRule) notes.push(`焦点按描述固定为「${focalRule.label}」`)

  const protectProbe = probe(text, [...PROTECT_PHRASES, '人脸可见', '保住人脸'])
  const protect = protectProbe.hit && !protectProbe.negated
  if (protect) notes.push('要求保住主体：焦点会按图片细节重心自动定位——主体不在正中时，这一步就是「不被裁掉」的关键')

  /* ---- 遮罩 ---- */
  const ovProbe = probe(text, ['遮罩', '蒙层', '蒙版', '压暗', '暗化', '叠一层', '加一层', '渐变层', 'overlay', '文字清楚', '文字清晰', '文字可读', '突出文字', '突出标题', '看得清'])
  let overlay = ovProbe.hit && !ovProbe.negated
  if (ovProbe.negated) notes.push('描述里否定了遮罩，不加覆盖层')
  // 大图上压着文字 → 默认补一层轻度遮罩。这是最常见的可读性问题，也是
  // 用户最不会主动提的一项（他们会说「文字放底部」，但不会说「帮我保证对比度」）。
  const isBigImage = fullscreen || usage === 'hero' || usage === 'banner'
  if (!overlay && !ovProbe.negated && isBigImage && /文字|标题|文案|白字|正文/.test(text)) {
    overlay = true
    notes.push('大图上要放文字，默认补一层轻度遮罩——这是最常见的可读性问题')
  }

  let overlayStrength = 0.5
  if (/淡|轻|浅|轻微|弱|一点点/.test(text)) overlayStrength = 0.32
  if (/重|深|强|很暗|足够暗|明显/.test(text)) overlayStrength = 0.72
  const ovNum = text.match(/(?:遮罩|蒙层|压暗)[^\d]{0,6}(\d{1,2})\s*%/)
  if (ovNum) overlayStrength = Math.min(0.95, Number(ovNum[1]) / 100)

  /* ---- 文字位置 ---- */
  const textPosRule = matchRules(text, TEXT_POS_RULES)
  const textPos = textPosRule ? textPosRule.value : 'bottom'

  /* ---- 响应式策略 ---- */
  const mfProbe = probe(text, ['移动端优先', '手机优先', '小屏优先', '先小屏', 'mobile first', 'mobile-first'])
  const dfProbe = probe(text, ['桌面优先', '大屏优先', '先大屏', 'pc优先', 'desktop first', 'desktop-first'])
  let strategy = 'mobile-first'
  if (dfProbe.hit && !dfProbe.negated) {
    strategy = 'desktop-first'
    notes.push('按「桌面优先」输出：媒体查询用 max-width 逐级降级')
  } else if (mfProbe.hit) {
    notes.push('按「移动端优先」输出：媒体查询用 min-width 逐级增强')
  } else {
    notes.push('未指定优先级，默认移动端优先——先保证小屏可用，再逐级增强')
  }

  /* ---- 其它开关 ---- */
  const atkFixed = probe(text, ['固定', '视差', '不跟随滚动', 'fixed', 'parallax', '附着'])
  const atkScroll = probe(text, ['跟随滚动', '随滚动', '滚动', 'scroll'])
  let attachment = 'scroll'
  if (atkFixed.hit) {
    attachment = 'fixed'
    notes.push('要求固定 / 视差，用 background-attachment: fixed')
  } else if (atkScroll.hit) {
    attachment = 'scroll'
  }

  const darkProbe = probe(text, ['暗色', '深色', '夜间', 'dark mode', 'prefers-color-scheme'])
  const darkMode = darkProbe.hit && !darkProbe.negated
  if (darkMode) notes.push('需要暗色适配，输出 prefers-color-scheme 分支')

  const hidpiProbe = probe(text, ['高分屏', '视网膜', 'retina', 'hidpi', '双倍图', '2x'])
  const hiDpi = hidpiProbe.hit && !hidpiProbe.negated

  const bareProbe = probe(text, ['只要属性', '不要包类', '裸属性', 'inline', '直接给样式', '不用选择器'])
  const bare = bareProbe.hit

  /* ---- 图案尺寸 ---- */
  let patternScale = null
  const sizeNum = text.match(/(?:尺寸|大小|每格|格子|单格)[^\d]{0,6}(\d{1,4})\s*(?:px|像素)/)
  if (sizeNum) patternScale = { value: Number(sizeNum[1]) }
  else if (/小一点|小些|密一点|密些|细密|更细/.test(text)) patternScale = { factor: 0.6, label: '更密' }
  else if (/大一点|大些|疏一点|疏些|更大/.test(text)) patternScale = { factor: 1.6, label: '更疏' }

  /* ---- 类名 ---- */
  const cnMatch = raw.match(/(?:类名|class)\s*[:：]?\s*([.#]?[\w-]+)/i)
  const className = cnMatch
    ? cnMatch[1].replace(/^\./, '')
    : (usage === 'hero' ? 'hero-bg'
      : usage === 'pattern' ? 'pattern-bg'
        : usage === 'banner' ? 'banner-bg'
          : usage === 'card' ? 'card-bg'
            : 'bg-image')

  const unmatched = []
  if (!usageRule) unmatched.push('场景（英雄区 / 卡片 / 平铺图案…）')
  if (!fillRule && !fillNeg.negated) unmatched.push('填充方式（铺满 / 完整显示）')

  return {
    text: raw,
    usage,
    fill,
    fullscreen,
    height,
    focal,
    focalLocked: Boolean(focalRule),
    protect,
    overlay,
    overlayStrength,
    textPos,
    strategy,
    attachment,
    darkMode,
    hiDpi,
    bare,
    patternScale,
    className,
    notes,
    unmatched,
  }
}

/** 解析「高 480px」「半屏」「两屏高」这类高度描述 */
function parseHeight(text) {
  const px = text.match(/(?:高|高度|height)\D{0,4}(\d{1,4})\s*(?:px|像素)/)
  if (px) return { value: `${px[1]}px`, label: `${px[1]}px 高` }
  const vh = text.match(/(?:高|高度)\D{0,4}(\d{1,3})\s*(?:vh|视口高)/)
  if (vh) return { value: `${vh[1]}vh`, label: `${vh[1]}vh` }
  const rem = text.match(/(?:高|高度)\D{0,4}(\d{1,3})\s*rem/)
  if (rem) return { value: `${rem[1]}rem`, label: `${rem[1]}rem` }
  if (/半屏|屏幕的?(一半|1\/2)/.test(text)) return { value: '50vh', label: '半屏高' }
  if (/一屏半/.test(text)) return { value: '150vh', label: '一屏半高' }
  if (/两屏|2\s*屏/.test(text)) return { value: '200vh', label: '两屏高' }
  return null
}

/* ================================================================ 图片分析 */

/**
 * 像素统计（纯函数，可在 Node 里单测）。
 *
 * `data` 是 RGBA 平铺数组，`width`/`height` 是它自身的尺寸。
 * 调用方应先把图缩到 128px 左右再传进来——原因见 analyzeImage。
 *
 * 产出：
 *   meanLuma   平均亮度（0~1）→ 决定要不要遮罩、遮罩多深
 *   focus      细节密度重心（0~1）→ 决定 background-position
 *   vertical / horizontal  三带细节占比 → 用来解释「为什么是这个位置」
 *   dominant   主色 → 图片加载前的兜底背景色
 *   isFlat     近似纯色 / 大面积留白 → 焦点分析无意义，需降级
 */
export function analyzePixels({ data, width, height, grid = 8 }) {
  if (!data || !width || !height) return { ok: false, reason: 'no-pixels' }

  const cellW = width / grid
  const cellH = height / grid

  // BT.601 亮度权重：人眼对绿最敏感，三通道直接平均会高估蓝色的亮度
  const lumaAt = (x, y) => {
    const i = (y * width + x) * 4
    return (0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]) / 255
  }

  const cells = []
  const buckets = new Map()
  let rSum = 0, gSum = 0, bSum = 0, pxCount = 0
  let lumaSum = 0, lumaCount = 0

  for (let gy = 0; gy < grid; gy++) {
    for (let gx = 0; gx < grid; gx++) {
      const x0 = Math.floor(gx * cellW), y0 = Math.floor(gy * cellH)
      const x1 = Math.min(width, Math.floor((gx + 1) * cellW))
      const y1 = Math.min(height, Math.floor((gy + 1) * cellH))
      if (x1 <= x0 || y1 <= y0) continue

      let lSum = 0, lN = 0, dSum = 0, dN = 0, satSum = 0

      for (let y = y0; y < y1; y++) {
        for (let x = x0; x < x1; x++) {
          const l = lumaAt(x, y)
          lSum += l; lN++
          // 细节 = 与右邻、下邻的亮度差。用一阶差分近似梯度，
          // 比方差更贴合「这里有没有线条/边缘」的直觉。
          if (x + 1 < width) { dSum += Math.abs(l - lumaAt(x + 1, y)); dN++ }
          if (y + 1 < height) { dSum += Math.abs(l - lumaAt(x, y + 1)); dN++ }

          const i = (y * width + x) * 4
          const r = data[i], g = data[i + 1], b = data[i + 2]
          rSum += r; gSum += g; bSum += b; pxCount++

          const mx = Math.max(r, g, b), mn = Math.min(r, g, b)
          satSum += mx === 0 ? 0 : (mx - mn) / mx

          const key = ((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4)
          const bk = buckets.get(key) || { n: 0, r: 0, g: 0, b: 0 }
          bk.n++; bk.r += r; bk.g += g; bk.b += b
          buckets.set(key, bk)
        }
      }

      lumaSum += lSum; lumaCount += lN
      cells.push({
        cx: (gx + 0.5) / grid,
        cy: (gy + 0.5) / grid,
        luma: lN ? lSum / lN : 0,
        detail: dN ? dSum / dN : 0,
        sat: lN ? satSum / lN : 0,
      })
    }
  }

  // 细节重心：权 = 细节密度 ×（0.35 + 饱和度）。
  // 加饱和度是因为纯灰的高对比区域（成段文字、网格线）不该压过彩色主体。
  let wx = 0, wy = 0, wSum = 0
  for (const c of cells) {
    const w = c.detail * (0.35 + c.sat)
    if (w > 0) { wx += c.cx * w; wy += c.cy * w; wSum += w }
  }
  const focus = wSum > 0
    ? { x: clamp01(wx / wSum), y: clamp01(wy / wSum) }
    : { x: 0.5, y: 0.5 }

  const cellCount = cells.length || 1
  const detailAvg = cells.reduce((s, c) => s + c.detail, 0) / cellCount
  const isFlat = detailAvg < 0.012

  const share = (pick) => {
    const total = cells.reduce((s, c) => s + c.detail, 0)
    if (total <= 0) return [1 / 3, 1 / 3, 1 / 3]
    const acc = [0, 0, 0]
    for (const c of cells) acc[pick(c)] += c.detail
    return acc.map((v) => v / total)
  }

  let best = null
  for (const bk of buckets.values()) if (!best || bk.n > best.n) best = bk
  const dominant = best
    ? { r: Math.round(best.r / best.n), g: Math.round(best.g / best.n), b: Math.round(best.b / best.n) }
    : { r: 0, g: 0, b: 0 }
  const meanColor = pxCount
    ? { r: Math.round(rSum / pxCount), g: Math.round(gSum / pxCount), b: Math.round(bSum / pxCount) }
    : { r: 0, g: 0, b: 0 }

  return {
    ok: true,
    grid,
    meanLuma: lumaCount ? lumaSum / lumaCount : 0,
    meanColor,
    dominant,
    focus,
    isFlat,
    detailAvg,
    vertical: share((c) => (c.cy < 1 / 3 ? 0 : c.cy < 2 / 3 ? 1 : 2)),
    horizontal: share((c) => (c.cx < 1 / 3 ? 0 : c.cx < 2 / 3 ? 1 : 2)),
  }
}

function clamp01(v) {
  return v < 0 ? 0 : v > 1 ? 1 : v
}

/**
 * 对 Image / <img> 做分析（唯一的 DOM 包装）。
 *
 * 为什么先缩到 128px：原图可能是 4000×3000 = 1200 万像素，
 * 逐像素扫描会让主线程卡住几百毫秒。缩到 128px 后约 1.6 万像素，
 * 统计意义完全够——我们要的是分布，不是每个原始像素。
 *
 * 跨域图会污染 canvas，getImageData 抛 SecurityError。这时**降级返回尺寸**，
 * 让上层继续工作：宽高比依然准确，只是没法算主体位置。
 */
export async function analyzeImage(img, { grid = 8, sampleSide = 128 } = {}) {
  const width = img?.naturalWidth || img?.width || 0
  const height = img?.naturalHeight || img?.height || 0
  if (!width || !height) return { ok: false, reason: 'no-size' }

  const base = { width, height, ratio: width / height, megapixels: (width * height) / 1e6 }

  try {
    const scale = Math.min(1, sampleSide / Math.max(width, height))
    const sw = Math.max(1, Math.round(width * scale))
    const sh = Math.max(1, Math.round(height * scale))
    const canvas = document.createElement('canvas')
    canvas.width = sw
    canvas.height = sh
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    if (!ctx) return { ...base, ok: true, pixels: null, degraded: 'no-canvas' }
    ctx.drawImage(img, 0, 0, sw, sh)
    const imageData = ctx.getImageData(0, 0, sw, sh)
    return { ...base, ok: true, pixels: analyzePixels({ data: imageData.data, width: sw, height: sh, grid }) }
  } catch (e) {
    return {
      ...base,
      ok: true,
      pixels: null,
      tainted: true,
      degraded: e?.name === 'SecurityError' ? 'cross-origin' : 'decode',
      reason: String(e?.name || e?.message || e),
    }
  }
}

/* ================================================================ 几何推算 */

/**
 * 预测某个容器比例下的裁剪 / 留白。
 *
 * cover 与 contain 的几何都是确定的，所以这里能给出**具体百分比**，
 * 而不是「可能会裁掉一些」这种没法验证的话。
 *
 * 设 boxRatio = 容器宽/高，imgRatio = 图宽/高。把容器高归一化为 1：
 *   cover  → 缩放取两轴所需的最大值，故一轴贴合、另一轴溢出
 *            容器相对更宽（boxRatio ≥ imgRatio）时按宽度贴合、高度溢出，
 *            可见高度占比 = imgRatio / boxRatio
 *   contain→ 缩放取最小值，长边方向留白
 *            留白面积占比 = 1 −（短边填充比）
 */
export function cropForecast(imgRatio, boxRatio) {
  if (!(imgRatio > 0) || !(boxRatio > 0)) {
    return { axis: 'none', lost: 0, visible: 1, emptyArea: 0 }
  }
  const widerBox = boxRatio >= imgRatio
  const shortRatio = widerBox ? imgRatio / boxRatio : boxRatio / imgRatio
  return {
    axis: widerBox ? 'vertical' : 'horizontal',
    visible: shortRatio,
    lost: 1 - shortRatio,
    emptyArea: 1 - shortRatio,
  }
}

/**
 * 由「主体在图片中的相对位置」反推 background-position 百分比。
 *
 * 容易搞错的地方：`background-position: 38%` **不是**「把图片 38% 处放到容器中央」，
 * CSS 的百分比定位是「图片的 P% 处 对齐 容器的 P% 处」。
 * 设被裁那一轴的可见比例为 v，可推出可视窗口在图片中的起点为 P×(1−v)；
 * 要让主体 f 落在窗口正中，解得 P = (f − v/2) / (1 − v)。
 *
 * v→1（几乎不裁剪）时分母趋 0，此时任何 P 都能看到主体，直接回退 f。
 */
export function recommendPosition(focusFraction, visibleFraction) {
  const f = clamp01(Number.isFinite(focusFraction) ? focusFraction : 0.5)
  const v = Math.min(1, Math.max(0.0001, Number.isFinite(visibleFraction) ? visibleFraction : 1))
  const denom = 1 - v
  if (denom < 0.02) return Math.round(f * 100)
  return Math.round(clamp01((f - v / 2) / denom) * 100)
}

/** 给定焦点与裁剪情况，算出 background-position */
function computePosition(focus, forecast) {
  if (forecast.axis === 'horizontal') {
    // 裁宽度 → 横向按重心算；纵向没被裁，重心直接对齐即可
    return `${recommendPosition(focus.x, forecast.visible)}% ${Math.round(focus.y * 100)}%`
  }
  if (forecast.axis === 'vertical') {
    return `${Math.round(focus.x * 100)}% ${recommendPosition(focus.y, forecast.visible)}%`
  }
  return '50% 50%'
}

/* ================================================================ CSS 生成 */

/**
 * 生成完整 CSS。
 *
 * @param {object} args
 * @param {string} args.url        图片地址（也可直接写 linear-gradient(...)）
 * @param {string} [args.url2x]    2 倍图地址，用于高分屏
 * @param {object} args.intent     parseIntent 的结果
 * @param {object} [args.analysis] analyzeImage 的结果
 * @param {object} [args.override] 界面上手动改过的槽位，优先级最高
 */
export function generateCss({ url = '', url2x = '', intent, analysis = null, override = {} }) {
  const it = { ...intent, ...pickDefined(override) }
  const warnings = []
  const reasons = [...(it.notes || [])]

  const isCssValue = /gradient\(|^#|^rgba?\(|^hsl/i.test(String(url).trim())
  const selector = it.bare ? '' : `.${it.className}`
  const px = analysis?.pixels || null
  const imgRatio = analysis?.ratio || null
  const isRepeat = String(it.fill).startsWith('repeat')

  /* ---- 兜底背景色：图片加载前不至于闪白 ---- */
  let fallbackColor
  if (px) {
    fallbackColor = toHex(px.dominant)
    if (isNearWhite(px.dominant) || isNearBlack(px.dominant)) fallbackColor = toHex(px.meanColor)
  } else {
    fallbackColor = 'var(--bg-secondary, #22262E)'
  }

  /* ---- 焦点 ---- */
  let focus = { x: 0.5, y: 0.5 }
  let focusSource = '居中兜底'
  if (it.focalLocked && it.focal) {
    const [fx, fy] = it.focal.split(' ').map((s) => (parseFloat(s) || 0) / 100)
    focus = { x: fx, y: fy }
    focusSource = '按描述指定'
  } else if (px && !px.isFlat) {
    focus = { x: px.focus.x, y: px.focus.y }
    focusSource = FOCUS_FROM_DETAIL
  } else if (px && px.isFlat) {
    focusSource = '图片细节分布均匀（近似纯色 / 极简图），焦点无意义，用居中'
  } else if (analysis?.tainted) {
    focusSource = '跨域图读不到像素，无法定位主体，已用居中兜底'
  }

  // 跨域降级必须**独立于焦点是否被描述锁定**地告知用户：
  // 即使用户写了「主体在左边」把位置锁死了，主色、亮度、裁剪预警
  // 这些同样依赖像素的结论也都拿不到，用户有权知道结论的可靠边界。
  if (analysis?.tainted) {
    warnings.push('这张图跨域，浏览器不允许读取像素，因此主色、亮度、主体位置都无法分析，兜底背景色改用了主题变量。若要自动保护主体，请用「本地上传」选同一张图再生成。')
  }

  /* ---- 遮罩强度与亮度匹配 ---- */
  if (it.overlay && px) {
    if (px.meanLuma < 0.35) {
      warnings.push(`图片平均亮度只有 ${Math.round(px.meanLuma * 100)}%，本身已偏暗。遮罩会自动调浅，但浅色文字在这张图上的对比度仍然偏低，建议改用白色粗体。`)
    } else if (px.meanLuma > 0.75) {
      warnings.push(`图片平均亮度 ${Math.round(px.meanLuma * 100)}%，整体很亮。此时深色文字比白色文字更易读；若必须用白字，遮罩需要加重。`)
    }
  }

  /* ---- 基准块声明 ---- */
  const base = []
  if (it.overlay) base.push('position: relative;')
  if (isCssValue) {
    base.push(`background-image: ${url};`)
  } else {
    base.push(`background-image: url("${cssString(url)}");`)
    if (it.hiDpi && url2x) {
      base.push('/* 高分屏换 2x 图源；上一行 1x 作为不支持 image-set 时的兜底 */')
      base.push(`background-image: image-set(url("${cssString(url)}") 1x, url("${cssString(url2x)}") 2x);`)
    }
  }
  base.push(`background-color: ${fallbackColor};`)

  const fill = []
  if (isRepeat) {
    fill.push(`background-repeat: ${it.fill === 'repeat' ? 'repeat' : it.fill};`)
    fill.push(`background-size: ${patternSizeDecl(it, analysis)};`)
    fill.push('background-position: center;')
  } else {
    fill.push('background-repeat: no-repeat;')
    fill.push(`background-size: ${it.fill === 'stretch' ? '100% 100%' : it.fill === 'contain' ? 'contain' : 'cover'};`)
    const baseForecast = imgRatio
      ? cropForecast(imgRatio, BASE_VIEWPORT[it.strategy].w / BASE_VIEWPORT[it.strategy].h)
      : { axis: 'none', visible: 1 }
    const basePos = (it.focalLocked && it.focal) ? it.focal : computePosition(focus, baseForecast)
    fill.push(`background-position: ${basePos};`)
  }

  if (it.attachment === 'fixed') {
    fill.push('background-attachment: fixed;')
    warnings.push('background-attachment: fixed 在 iOS Safari 和部分安卓浏览器上不支持（会退化成滚动），下面另有一组移动端兜底规则。')
  }

  if (it.fullscreen) {
    fill.push('min-height: 100vh;')
    fill.push('min-height: 100svh;   /* svh 不受移动端地址栏收放影响，比 vh 准 */')
  } else if (it.height) {
    fill.push(`min-height: ${it.height.value};`)
  }

  /* ---- 各断点的位置修正（内容敏感保护的核心） ---- */
  const breakpointBlocks = []
  if (imgRatio && !it.bare && !isRepeat && it.fill === 'cover') {
    const list = it.strategy === 'mobile-first' ? MEDIA_MOBILE_FIRST : MEDIA_DESKTOP_FIRST
    const baseForecast = cropForecast(imgRatio, BASE_VIEWPORT[it.strategy].w / BASE_VIEWPORT[it.strategy].h)
    let prev = (it.focalLocked && it.focal) ? it.focal : computePosition(focus, baseForecast)

    for (const bp of list) {
      const f = cropForecast(imgRatio, bp.vp.w / bp.vp.h)
      const pos = (it.focalLocked && it.focal) ? it.focal : computePosition(focus, f)
      if (pos === prev) continue
      prev = pos
      const note = f.lost > 0.05
        ? `/* ${bp.label}：cover 会裁掉约 ${Math.round(f.lost * 100)}% 的${f.axis === 'vertical' ? '高度' : '宽度'}，位置据此修正 */`
        : `/* ${bp.label}：几乎不裁剪，位置与基准一致 */`
      breakpointBlocks.push({ query: bp.query, label: bp.label, note, decls: [`background-position: ${pos};`] })
    }
  }

  /* ---- 横屏矮视口 ---- */
  const extraBlocks = []
  if (it.fullscreen) {
    extraBlocks.push({
      query: '(orientation: landscape) and (max-height: 520px)',
      label: '手机横屏（矮视口）',
      note: '/* 横屏时 100svh 只有 390px 左右，整屏高会把内容挤扁，给个可用的下限 */',
      decls: ['min-height: 360px;'],
    })
  }

  /* ---- 超宽屏（竖构图最容易翻车的组合） ---- */
  if (imgRatio && imgRatio < 1.2 && it.fill === 'cover' && it.fullscreen) {
    const f = cropForecast(imgRatio, 2560 / 1080)
    extraBlocks.push({
      query: '(min-aspect-ratio: 21/9)',
      label: '超宽屏',
      note: `/* 竖构图在超宽屏下 cover 会裁掉约 ${Math.round(f.lost * 100)}% 的高度，改用较高尺度并配合位置补救 */`,
      decls: ['background-size: auto 120%;'],
    })
    warnings.push(`这张图偏竖构图（比例 ${imgRatio.toFixed(2)}）。21:9 超宽屏上用 cover 会裁掉约 ${Math.round(f.lost * 100)}% 的高度，已额外输出超宽屏规则；更稳妥的做法是再准备一张横构图图源，用 <picture> 按屏宽切换。`)
  }

  /* ---- 暗色适配 ---- */
  if (it.darkMode) {
    extraBlocks.push({
      query: '(prefers-color-scheme: dark)',
      label: '系统暗色',
      note: '/* 暗色下换更深的兜底色 */',
      decls: [`background-color: ${px ? shade(toHex(px.dominant), -0.45) : '#0E141A'};`],
    })
  }

  /* ---- 风险预警：尺寸、裁剪、留白、比例 ---- */
  if (analysis && !isCssValue) {
    if (it.fullscreen && analysis.width < 1280) {
      warnings.push(`图片只有 ${analysis.width}px 宽，用作整屏背景（桌面通常 1920px）会被放大到约 ${(1920 / analysis.width).toFixed(1)} 倍，明显发虚。建议换 ≥1920px 的图源。`)
    }
    // 只有 cover 才会裁掉内容。contain / repeat 模式下报「cover 会裁掉 74%」
    // 既是无关信息、又会把人带偏（明明要求了不裁剪，却收到裁剪警告）。
    const worst = it.fill === 'cover' ? worstDeviceCrop(imgRatio) : null
    if (worst && worst.lost > 0.4) {
      warnings.push(`在「${worst.label}」（${worst.w}×${worst.h}）下 cover 会裁掉约 ${Math.round(worst.lost * 100)}% 的${worst.axis === 'vertical' ? '高度' : '宽度'}，这是所有设备里最严重的一档。位置已按主体重心修正，但被裁掉的部分找不回来——若主体范围很大，建议换图或让该断点改用 contain。`)
    }
    if (it.fullscreen && it.fill === 'contain') {
      const f = cropForecast(imgRatio, 390 / 844)
      if (f.emptyArea > 0.45) {
        warnings.push(`要求「不裁剪」但同时是整屏高，这两者有本质冲突：手机竖屏（390×844）下 contain 会留出约 ${Math.round(f.emptyArea * 100)}% 的空白。要么接受留白（可给容器加同色系底色），要么改成固定高度（如 480px）。`)
      }
    }
    if (imgRatio > 3) warnings.push('图片非常宽扁（宽高比 > 3），在手机竖屏下几乎必然裁掉大部分宽度。')
    if (imgRatio < 0.4) warnings.push('图片非常细高（宽高比 < 0.4），在横屏与桌面下会裁掉大部分高度。')
    if (it.overlay && it.textPos === 'bottom' && px && px.focus.y > 0.75) {
      warnings.push('注意：遮罩压暗的是底部，而图片的细节重心也偏下（' + Math.round(px.focus.y * 100) + '%），两者会叠在一起——文字可能正好压在主体上。建议把文字改到顶部，或把遮罩方向反过来。')
    }
  }

  /* ---- 拼装 ---- */
  const out = []
  out.push('/* ============================================================')
  out.push('   由「背景 CSS 生成器」生成')
  // 描述是用户自由输入的，直接塞进注释里，一个 `*/` 就能提前闭合注释，
  // 让后面所有内容变成顶层垃圾 CSS（粘贴进项目后会整片报错）。必须消毒。
  if (it.text) out.push(`   输入：${cssComment(it.text)}`)
  out.push(`   判定：${USAGE_LABEL[it.usage] || it.usage} · ${FILL_LABEL[it.fill] || it.fill} · ${it.fullscreen ? '整屏高' : it.height ? it.height.label : '高度自适应'}`)
  if (analysis) {
    out.push(`   图片：${analysis.width}×${analysis.height}（比例 ${imgRatio.toFixed(2)}）`)
    if (px) {
      // 「主体重心」只在**真的拿它定位**时报。否则会出现自相矛盾的一段：
      // 依据写「细节分布均匀，用居中」，却把重心百分比也印出来，
      // 读代码的人会以为那个数字生效了。
      const usedForFocus = focusSource === FOCUS_FROM_DETAIL
      out.push('         平均亮度 ' + Math.round(px.meanLuma * 100) + '%' +
        ' · 主色 ' + toHex(px.dominant) +
        (usedForFocus
          ? ` · 主体重心 ${Math.round(px.focus.x * 100)}%,${Math.round(px.focus.y * 100)}%`
          : ' · 细节分布均匀，未据此定位'))
    }
    if (analysis.tainted) out.push('         跨域图，像素分析不可用（仅用了宽高比）')
  }
  out.push(`   焦点依据：${focusSource}`)
  out.push('   ============================================================ */')
  out.push('')

  if (it.bare) {
    out.push('/* 只要属性 —— 请粘贴进你自己的选择器 */')
    out.push(...base.map(trim), ...fill.map(trim))
  } else {
    out.push(`${selector} {`)
    out.push(...base.map(indent), ...fill.map(indent), '}')
  }

  if (it.overlay) {
    // 「只要属性」模式下没有选择器，::after 没法裸着写 —— 这里单独补回去
    let ovSelector = selector
    if (!ovSelector) {
      ovSelector = `.${it.className}`
      warnings.push('遮罩必须挂在元素上（用 ::after），所以「只要属性」模式下仍额外给出了一个带选择器的遮罩块，可直接用或改选择器。')
    }
    out.push('')
    out.push(`/* 文字可读性遮罩（文字位置：${TEXT_POS_LABEL[it.textPos]}） */`)
    out.push(`${ovSelector}::after {`)
    out.push('  content: "";')
    out.push('  position: absolute;')
    out.push('  inset: 0;')
    out.push('  pointer-events: none;   /* 别挡住底下内容的点击 */')
    out.push(`  background: ${overlayStops(it.textPos, it.overlayStrength)};`)
    out.push('}')
  }

  for (const b of [...breakpointBlocks, ...extraBlocks]) {
    out.push('')
    out.push(`/* ${b.label} */`)
    out.push(`@media ${b.query} {`)
    if (b.note) out.push(indentAll(b.note))
    out.push(indentAll(bareInner(it, selector, b.decls)))
    out.push('}')
  }

  return {
    css: out.join('\n'),
    // 裸属性模式之外，界面里做实时预览时也需要「纯声明」来包进演示选择器
    baseDecls: [...base, ...fill],
    warnings,
    reasons,
    className: it.className,
    focus,
    focusSource,
    fallbackColor,
    isCssValue,
    analysis,
  }
}

/* ---- 消毒：用户输入要进 CSS 时必须转义 ---- */

/**
 * 放进 CSS 字符串字面量（`url("...")`）里。
 * URL 里出现 `"` 会提前闭合字符串，出现换行会让声明断成两行——
 * 两者都会让生成的 CSS 直接失效。
 */
function cssString(s) {
  return String(s ?? '')
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '\\"')
    .replace(/[\r\n]+/g, '')
}

/** 放进 CSS 注释里。`*/` 会提前闭合注释；`/*` 会让后续内容嵌套失效。 */
function cssComment(s) {
  return String(s ?? '').replace(/\*\//g, '* /').replace(/\/\*/g, '/ *')
}

/* ---- 生成用的小工具 ---- */

function pickDefined(o = {}) {
  const out = {}
  for (const [k, v] of Object.entries(o)) {
    if (v !== undefined && v !== null && v !== '') out[k] = v
  }
  return out
}

const trim = (s) => s.trim()
const indent = (s) => (s.startsWith('  ') ? s : '  ' + s)
const indentAll = (s) => s.split('\n').map((l) => '  ' + l).join('\n')

function bareInner(it, selector, decls) {
  if (it.bare) return decls.map((d) => d.trim()).join('\n')
  return `${selector} {\n${decls.map(indent).join('\n')}\n}`
}

function patternSizeDecl(it, analysis) {
  if (it.patternScale?.value) {
    const v = it.patternScale.value
    if (it.fill === 'repeat-y') return `auto ${v}px`
    if (it.fill === 'repeat-x') return `${v}px auto`
    return `${v}px ${v}px`
  }
  const factor = it.patternScale?.factor || 1
  // 平铺尺寸用 px 而不是百分比：百分比会随容器变化，图案大小就不稳定了。
  // 图本身够小就按原始像素平铺（最清晰），否则给一个可读的默认值。
  if (analysis?.width && analysis.width <= 512) {
    const w = Math.round(analysis.width * factor)
    if (it.fill === 'repeat-y') return `auto ${w}px`
    if (it.fill === 'repeat-x') return `${w}px auto`
    return `${w}px ${Math.round(w * (analysis.height / analysis.width))}px`
  }
  const w = Math.round(240 * factor)
  return `${w}px auto`
}

function overlayStops(textPos, strength) {
  const a = Math.max(0.1, Math.min(0.95, Number(strength) || 0.5))
  const soft = round2(a * 0.25)
  const hard = round2(a)
  if (textPos === 'top') return `linear-gradient(0deg, rgba(0, 0, 0, ${soft}), rgba(0, 0, 0, ${hard}))`
  if (textPos === 'center') return `radial-gradient(ellipse at center, rgba(0, 0, 0, ${hard}) 0%, rgba(0, 0, 0, ${soft}) 70%)`
  if (textPos === 'left') return `linear-gradient(90deg, rgba(0, 0, 0, ${hard}), rgba(0, 0, 0, ${soft}))`
  if (textPos === 'right') return `linear-gradient(270deg, rgba(0, 0, 0, ${hard}), rgba(0, 0, 0, ${soft}))`
  return `linear-gradient(180deg, rgba(0, 0, 0, ${soft}), rgba(0, 0, 0, ${hard}))`
}

function worstDeviceCrop(imgRatio) {
  if (!imgRatio) return null
  let worst = null
  for (const d of DEVICES) {
    const f = cropForecast(imgRatio, d.w / d.h)
    if (!worst || f.lost > worst.lost) worst = { ...f, label: d.label, w: d.w, h: d.h }
  }
  return worst
}

const round2 = (n) => Math.round(n * 100) / 100

function toHex({ r, g, b }) {
  return '#' + [r, g, b]
    .map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0'))
    .join('')
    .toUpperCase()
}

/** 提亮 / 压暗（amount 为 -1~1） */
function shade(hex, amount) {
  const m = /^#?([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(hex)
  if (!m) return hex
  const out = [1, 2, 3].map((i) => {
    const v = parseInt(m[i], 16)
    const t = amount < 0 ? v * (1 + amount) : v + (255 - v) * amount
    return Math.max(0, Math.min(255, Math.round(t)))
  })
  return '#' + out.map((v) => v.toString(16).padStart(2, '0')).join('').toUpperCase()
}

const isNearWhite = ({ r, g, b }) => r > 240 && g > 240 && b > 240
const isNearBlack = ({ r, g, b }) => r < 16 && g < 16 && b < 16

/* ================================================================ 场景预设 */

/** 四个典型场景的示例描述，界面上做成一点即填的一行 */
export const SCENARIOS = [
  {
    key: 'hero',
    label: '全屏英雄区',
    text: '全屏英雄区背景图，铺满不留白，标题在底部，不要裁到主体',
    why: 'cover + 整屏高（vh 与 svh 双写）+ 底部遮罩 + 按图片重心自动定位焦点',
  },
  {
    key: 'mobile',
    label: '移动端优先',
    text: '移动端优先的横幅，手机上一屏高，文字居中，图片要清楚',
    why: 'min-width 逐级增强 + svh 单位 + 居中径向遮罩',
  },
  {
    key: 'pattern',
    label: '图案平铺',
    text: '细密的格子底纹图案，密一点，平铺',
    why: 'repeat + 按图片自身尺寸推导 px（不用百分比，否则图案大小随容器变）',
  },
  {
    key: 'protect',
    label: '内容敏感保护',
    text: '卡片封面图，要完整显示不要裁剪，重点在左边',
    why: 'contain + 左侧焦点 + 输出裁剪 / 留白百分比预警',
  },
]
