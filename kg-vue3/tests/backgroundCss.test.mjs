/**
 * 背景 CSS 生成引擎回归测试。
 *
 * 运行：npm run test:bgcss
 *
 * 覆盖三类容易错、且错了不容易发现的地方：
 *   ① 自然语言的**否定与优先级** —— 「不要铺满」不能判成 cover；
 *      整句说法（「不拉伸」）不能被拆成单个关键词
 *   ② 几何推算的**数值** —— 裁剪百分比、background-position 反推公式
 *   ③ 图片统计的**方向正确性** —— 细节在左上，重心就必须在左上
 *
 * 这些一旦回归，界面上只会表现为「生成的代码怪怪的」，很难定位，
 * 所以用断言钉住。这些断言都是能独立验算的，不是照抄实现。
 */

import {
  parseIntent, analyzePixels, cropForecast, recommendPosition,
  generateCss, DEVICES, SCENARIOS,
} from '../src/utils/backgroundCss.js'

let pass = 0
let fail = 0
const failures = []

function check(name, cond, extra = '') {
  if (cond) { pass++; return }
  fail++
  failures.push(`${name}${extra ? ' → ' + extra : ''}`)
  console.log(`  ✗ ${name}${extra ? '  → ' + extra : ''}`)
}

function eq(name, actual, expected) {
  check(name, actual === expected, `期望 ${JSON.stringify(expected)}，实得 ${JSON.stringify(actual)}`)
}

function near(name, actual, expected, tol = 0.01) {
  check(name, Math.abs(actual - expected) <= tol, `期望 ≈${expected}，实得 ${actual}`)
}

/* ============================================================ 1. 意图：否定 */

console.log('\n=== 1. 否定词不能被当成肯定 ===')

eq('「不要铺满」不判 cover，应落到 contain',
  parseIntent('不要铺满').fill, 'contain')
eq('「不拉伸图片」判 contain',
  parseIntent('全屏背景但不拉伸图片').fill, 'contain')
eq('「完整显示不要裁剪」判 contain',
  parseIntent('要完整显示，不要裁剪').fill, 'contain')
eq('「铺满不留白」判 cover',
  parseIntent('铺满整个区域不留白').fill, 'cover')
eq('「不平铺」不判 repeat',
  parseIntent('不要平铺').fill, 'cover')
eq('「不要遮罩」不产生遮罩',
  parseIntent('全屏大图，不要遮罩').overlay, false)
eq('「不要全屏」不判整屏高',
  parseIntent('横幅图，不要全屏').fullscreen, false)

/* ============================================================ 2. 意图：典型句 */

console.log('\n=== 2. 四个典型场景的描述解析 ===')

const hero = parseIntent(SCENARIOS[0].text)
eq('英雄区：场景', hero.usage, 'hero')
eq('英雄区：铺满→cover', hero.fill, 'cover')
eq('英雄区：整屏高', hero.fullscreen, true)
eq('英雄区：底部遮罩', hero.overlay, true)
eq('英雄区：主体保护开启', hero.protect, true)

const mob = parseIntent(SCENARIOS[1].text)
eq('移动端优先：策略', mob.strategy, 'mobile-first')
eq('移动端优先：提及文字→自动遮罩', mob.overlay, true)
eq('移动端优先：文字居中', mob.textPos, 'center')

const pat = parseIntent(SCENARIOS[2].text)
eq('图案：场景', pat.usage, 'pattern')
eq('图案：平铺', pat.fill, 'repeat')
eq('图案：密一点', pat.patternScale?.factor, 0.6)

const prot = parseIntent(SCENARIOS[3].text)
eq('内容保护：不裁剪→contain', prot.fill, 'contain')
eq('内容保护：焦点在左', prot.focal, '0% 50%')
eq('内容保护：焦点被锁定', prot.focalLocked, true)

/* ============================================================ 3. 意图：其它槽位 */

console.log('\n=== 3. 其它槽位 ===')

eq('桌面优先策略', parseIntent('桌面优先的横幅').strategy, 'desktop-first')
eq('视差→attachment fixed', parseIntent('全屏图做视差').attachment, 'fixed')
eq('暗色适配', parseIntent('要适配暗色模式').darkMode, true)
eq('高分屏开关', parseIntent('用高分屏双倍图').hiDpi, true)
eq('只要属性', parseIntent('只要属性，不要包类名').bare, true)

// 自动补遮罩的边界：大图上放文字就补，不限于「整屏高」
// （固定高度的横幅同样是把文字压在图上，同样需要对比度）
eq('固定高度横幅 + 文字 → 自动补遮罩',
  parseIntent('横幅图，高 320px，文字在左边').overlay, true)
// 反过来，小卡片不该补：那里的文字多半在图片外面
eq('小卡片 + 文字 → 不自动补遮罩',
  parseIntent('卡片缩略图，高 120px，标题在下方').overlay, false)
eq('高度 480px', parseIntent('高 480px 的横幅').height?.value, '480px')
eq('半屏', parseIntent('占半屏高度').height?.value, '50vh')
eq('类名指定', parseIntent('类名 hero-banner 的全屏图').className, 'hero-banner')
eq('横向平铺', parseIntent('横向平铺的分隔纹').fill, 'repeat-x')

// 不相关句子不该误判焦点（`在上` 不能命中）
eq('「现在上传图片」不误判焦点在上',
  parseIntent('现在上传图片').focal, null)
eq('「重点在左边」判左侧',
  parseIntent('重点在左边').focal, '0% 50%')
eq('「主体在右下方」命中右侧（先于底部）',
  parseIntent('主体在右下方').focal, '100% 50%')

// 「文字/标题在哪」讲的是文字摆放，不是图片主体在哪 —— 两者绝不能混
const textPosOnly = parseIntent('全屏大图，标题在底部，副标题在下方')
eq('「标题在底部」只定文字位置，不锁图片焦点', textPosOnly.focalLocked, false)
eq('「标题在底部」仍解析出文字位置=底部', textPosOnly.textPos, 'bottom')
eq('英雄区描述不锁死焦点（交给图片分析）', hero.focalLocked, false)
eq('英雄区描述的焦点槽位为空', hero.focal, null)
// 反过来：明确说主体在哪时，必须锁
eq('「主体在下方」确实锁焦', parseIntent('全屏图，主体在下方').focalLocked, true)
// 「居中」这条最容易漏：裸匹配「居中」会被「文字居中」骗到
eq('「文字居中」不锁图片焦点', parseIntent('全屏图，文字居中').focalLocked, false)
eq('「水平居中」不锁图片焦点', parseIntent('全屏图，文字水平居中').focalLocked, false)
eq('「主体居中」才锁焦点', parseIntent('全屏图，主体居中').focalLocked, true)

/* ============================================================ 4. 裁剪预测 */

console.log('\n=== 4. 裁剪 / 留白预测（可手工验算）===')
// 16:9 的图放进 16:9 的容器：完全不裁
const f0 = cropForecast(16 / 9, 16 / 9)
near('16:9 图 → 16:9 容器，无裁剪', f0.lost, 0, 0.001)

// 16:9 图放进手机竖屏 390×844（比例 0.4621）：
// cover 按高度贴合 → 缩放后宽 1500，可见宽 390 → 可见比例 390/1500 = 0.26
const f1 = cropForecast(16 / 9, 390 / 844)
eq('16:9 图 → 手机竖屏，裁的是宽度', f1.axis, 'horizontal')
near('可见宽度比例 0.26', f1.visible, 390 / 1500, 0.002)
near('裁掉约 74%', f1.lost, 0.74, 0.01)

// 9:16 竖图放进 21:9 超宽屏（2560/1080 = 2.370）
const f2 = cropForecast(9 / 16, 2560 / 1080)
eq('竖图 → 超宽屏，裁的是高度', f2.axis, 'vertical')
near('可见高度比例 = 0.5625/2.370 = 0.237', f2.visible, 0.5625 / 2.3704, 0.002)

// contain 留白：16:9 图进手机竖屏 → 空白 74%
near('contain 在手机竖屏留白 74%', cropForecast(16 / 9, 390 / 844).emptyArea, 0.74, 0.01)

/* ============================================================ 5. 位置反推 */

console.log('\n=== 5. background-position 反推（公式可手工验算）===')
// P = (f − v/2) / (1 − v)
near('主体 25%、可见 50% → 0%（靠左）', recommendPosition(0.25, 0.5), 0)
near('主体 50%、可见 50% → 50%（居中）', recommendPosition(0.5, 0.5), 50)
near('主体 75%、可见 50% → 100%（靠右）', recommendPosition(0.75, 0.5), 100)
near('几乎不裁剪时直接回退主体位置', recommendPosition(0.3, 0.999), 30)
near('主体 40%、可见 20% → 37.5% 取整 38', recommendPosition(0.4, 0.2), 38)
// 边界：结果必须落在 0~100
check('结果不越界（上界）', recommendPosition(1, 0.3) <= 100)
check('结果不越界（下界）', recommendPosition(0, 0.3) >= 0)

/* ============================================================ 6. 图片统计 */

console.log('\n=== 6. 像素统计的方向正确性 ===')

/** 生成一张纯色图 */
function solid(w, h, [r, g, b]) {
  const data = new Uint8ClampedArray(w * h * 4)
  for (let i = 0; i < w * h; i++) {
    data[i * 4] = r; data[i * 4 + 1] = g; data[i * 4 + 2] = b; data[i * 4 + 3] = 255
  }
  return data
}

/** 把一张图的某个矩形区域画成棋盘格（制造高频细节） */
function checker(data, w, h, x0, y0, x1, y1, cell = 2) {
  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) {
      const on = (Math.floor(x / cell) + Math.floor(y / cell)) % 2 === 0
      const v = on ? 250 : 5
      const i = (y * w + x) * 4
      data[i] = v; data[i + 1] = v; data[i + 2] = v
    }
  }
}

const W = 64, H = 64

// 纯灰图 → 无细节 → 判为 flat，焦点取中心
const flat = analyzePixels({ data: solid(W, H, [128, 128, 128]), width: W, height: H, grid: 8 })
eq('纯色图判为 flat', flat.isFlat, true)
near('纯色图焦点落中心 x', flat.focus.x, 0.5, 0.001)
near('纯色图焦点落中心 y', flat.focus.y, 0.5, 0.001)

// 左上角四分之一有细节 → 重心必须在左上
const d1 = solid(W, H, [128, 128, 128])
checker(d1, W, H, 0, 0, W / 2, H / 2)
const a1 = analyzePixels({ data: d1, width: W, height: H, grid: 8 })
check('有细节的图不判 flat', a1.isFlat === false)
check('细节在左上 → 重心偏左', a1.focus.x < 0.4, `focus.x=${a1.focus.x.toFixed(3)}`)
check('细节在左上 → 重心偏上', a1.focus.y < 0.4, `focus.y=${a1.focus.y.toFixed(3)}`)
near('左上细节的重心 ≈ 0.25', a1.focus.x, 0.25, 0.06)

// 右下角四分之一有细节 → 重心必须翻到右下
const d2 = solid(W, H, [128, 128, 128])
checker(d2, W, H, W / 2, H / 2, W, H)
const a2 = analyzePixels({ data: d2, width: W, height: H, grid: 8 })
check('细节在右下 → 重心偏右', a2.focus.x > 0.6, `focus.x=${a2.focus.x.toFixed(3)}`)
check('细节在右下 → 重心偏下', a2.focus.y > 0.6, `focus.y=${a2.focus.y.toFixed(3)}`)

// 上下翻转必须让重心的 y 对称翻转（这是最容易被常量写死骗过的一条）
near('左右镜像后重心对称', a1.focus.x + a2.focus.x, 1.0, 0.02)
near('上下镜像后重心对称', a1.focus.y + a2.focus.y, 1.0, 0.02)

// 亮度
const bright = analyzePixels({ data: solid(W, H, [255, 255, 255]), width: W, height: H })
near('纯白亮度 = 1', bright.meanLuma, 1, 0.001)
const dark = analyzePixels({ data: solid(W, H, [0, 0, 0]), width: W, height: H })
near('纯黑亮度 = 0', dark.meanLuma, 0, 0.001)
// 纯红：BT.601 亮度 = 0.299，直接平均三通道会错算成 0.333
const red = analyzePixels({ data: solid(W, H, [255, 0, 0]), width: W, height: H })
near('纯红亮度 = 0.299（BT.601 权重）', red.meanLuma, 0.299, 0.002)

// 主色
const blue = analyzePixels({ data: solid(W, H, [0, 0, 255]), width: W, height: H })
eq('纯蓝图主色 R', blue.dominant.r, 0)
eq('纯蓝图主色 B', blue.dominant.b, 255)

/* ============================================================ 7. 生成代码 */

console.log('\n=== 7. 生成的 CSS 结构 ===')

const url = 'https://example.com/photo.jpg'
const A = (w, h) => ({ width: w, height: h, ratio: w / h, pixels: null })

const heroCss = generateCss({ url, intent: hero, analysis: A(1920, 1080) })
check('英雄区：background-size: cover', /background-size: cover;/.test(heroCss.css))
check('英雄区：写入图片地址', heroCss.css.includes(url))
check('英雄区：整屏高同时给 vh 与 svh',
  /min-height: 100vh;/.test(heroCss.css) && /min-height: 100svh;/.test(heroCss.css))
check('英雄区：有遮罩层 ::after', /::after\s*\{/.test(heroCss.css))
check('英雄区：遮罩不挡点击', /pointer-events: none;/.test(heroCss.css))
check('英雄区：输出媒体查询', /@media/.test(heroCss.css))
check('英雄区：横屏矮视口规则', /orientation: landscape/.test(heroCss.css))

// 16:9 图 + 手机竖屏 → 必须给出裁剪预警，且带具体百分比
const heroWarn = heroCss.warnings.join(' ')
check('英雄区：提示会被裁掉多少', /裁掉约 \d+%/.test(heroWarn), heroWarn.slice(0, 120))

const protCss = generateCss({ url, intent: prot, analysis: A(1200, 1600) })
check('内容保护：background-size: contain', /background-size: contain;/.test(protCss.css))
check('内容保护：焦点按描述写死为 0% 50%', /background-position: 0% 50%;/.test(protCss.css))
check('内容保护：无 cover 专属的断点位置块',
  !/min-width: 640px/.test(protCss.css))

// 裁剪预警只对 cover 有意义：平铺 / contain 下根本不裁
const cropWarn = (r) => /cover 会裁掉/.test(r.warnings.join(' '))
check('cover 模式会报裁剪', cropWarn(generateCss({ url, intent: hero, analysis: A(1920, 1080) })))
check('平铺模式不报 cover 裁剪',
  !cropWarn(generateCss({ url, intent: pat, analysis: A(1920, 1080) })))
check('contain 模式不报 cover 裁剪',
  !cropWarn(generateCss({ url, intent: prot, analysis: A(1920, 1080) })))
check('渐变背景不报裁剪',
  !cropWarn(generateCss({ url: 'linear-gradient(#123, #456)', intent: parseIntent('全屏渐变'), analysis: null })))

const patCss = generateCss({ url, intent: pat, analysis: A(64, 64) })
check('图案：repeat', /background-repeat: repeat;/.test(patCss.css))
check('图案：尺寸用 px 而非百分比', /background-size: \d+px/.test(patCss.css), patCss.css.match(/background-size:[^;]*/)?.[0])
check('图案：尺寸不出现 %', !/background-size: \d+%/.test(patCss.css))
// 图本身够小 → 按图片原始像素平铺；「密一点」的 0.6 系数同样生效：64 × 0.6 = 38
check('图案：小图按原始像素平铺并应用密度系数', /background-size: 38px 38px;/.test(patCss.css),
  patCss.css.match(/background-size:[^;]*/)?.[0])

// 显式指定尺寸：必须原样写成 px
const patSized = parseIntent('平铺底纹，尺寸 48px')
eq('图案：解析出显式尺寸 48', patSized.patternScale?.value, 48)
const patSizedCss = generateCss({ url, intent: patSized, analysis: A(64, 64) })
check('图案：显式尺寸写成 48px 48px', /background-size: 48px 48px;/.test(patSizedCss.css),
  patSizedCss.css.match(/background-size:[^;]*/)?.[0])
check('图案：显式尺寸也不出现百分比', !/background-size: \d{1,3}%/.test(patSizedCss.css))

// 大图（>512px）+「密一点」：走缩放系数分支，240 × 0.6 = 144
const patDenseCss = generateCss({ url, intent: pat, analysis: A(1000, 1000) })
check('图案：大图 + 密一点 → 240×0.6 = 144px', /background-size: 144px auto;/.test(patDenseCss.css),
  patDenseCss.css.match(/background-size:[^;]*/)?.[0])

const bareCss = generateCss({ url, intent: parseIntent('只要属性，全屏铺满'), analysis: A(1920, 1080) })
check('裸属性模式：不输出选择器块', !/^\.\w+\s*\{/m.test(bareCss.css.split('*/')[1] || ''))
check('裸属性模式：仍然给出属性', /background-size: cover;/.test(bareCss.css))

// 跨域降级：没有像素时不能崩，且要明说原因
const tainted = generateCss({
  url, intent: hero,
  analysis: { width: 1920, height: 1080, ratio: 16 / 9, pixels: null, tainted: true },
})
check('跨域降级：仍能生成代码', /background-size: cover;/.test(tainted.css))
check('跨域降级：说明像素分析不可用', /跨域/.test(tainted.warnings.join(' ')))

// 竖构图 + 超宽屏
const vertical = generateCss({ url, intent: hero, analysis: A(1080, 1920) })
check('竖构图：给出超宽屏规则', /min-aspect-ratio: 21\/9/.test(vertical.css))
check('竖构图：提示超宽屏会被裁掉', /超宽屏/.test(vertical.warnings.join(' ')))

// 渐变直接当图片地址用
const grad = generateCss({
  url: 'linear-gradient(180deg, #123, #456)',
  intent: parseIntent('全屏渐变背景'),
  analysis: null,
})
check('渐变：识别为 CSS 值而非图片地址', grad.isCssValue === true)
check('渐变：不加 url() 包裹', grad.css.includes('background-image: linear-gradient(180deg, #123, #456);'))

/* ============================================================ 7b. 输入消毒 */

console.log('\n=== 7b. 用户输入不能逃出 CSS 上下文 ===')

// URL 里的引号会提前闭合 url("...")
const evilUrl = generateCss({
  url: 'https://x/a"b.jpg',
  intent: parseIntent('全屏铺满'),
  analysis: A(1920, 1080),
})
check('URL 里的引号被转义', evilUrl.css.includes('a\\"b.jpg'),
  evilUrl.css.match(/background-image:[^;]*/)?.[0])
check('转义后 url() 仍是完整的', /url\("https:\/\/x\/a\\"b\.jpg"\);/.test(evilUrl.css))

// 描述里的 */ 会提前闭合注释，让后面整片变成顶层垃圾 CSS
const evilText = generateCss({
  url,
  intent: parseIntent('全屏铺满 */ body { display: none } /*'),
  analysis: A(1920, 1080),
})
check('描述里的 */ 被消毒', !/\*\/\s*body/.test(evilText.css))
check('描述里的 /* 也被消毒', !/\/\*\s*$/.test(evilText.css.split('\n')[0]))
const opens = (evilText.css.match(/\/\*/g) || []).length
const closes = (evilText.css.match(/\*\//g) || []).length
eq('注释开闭数量一致（没有提前闭合）', opens, closes)

/* ============================================================ 7c. 注释不能自相矛盾 */

console.log('\n=== 7c. 头部注释必须与实际生效的判定一致 ===')

/** 造一份只带像素统计的 analysis */
function pxAnalysis(isFlat) {
  return {
    width: 1600, height: 900, ratio: 1600 / 900,
    pixels: {
      meanLuma: 0.5,
      dominant: { r: 17, g: 34, b: 51 },
      focus: { x: 0.2, y: 0.3 },
      isFlat,
    },
  }
}

const flatCss = generateCss({ url, intent: parseIntent('全屏铺满'), analysis: pxAnalysis(true) })
check('细节均匀时不报「主体重心」', !/主体重心/.test(flatCss.css),
  flatCss.css.split('\n').find((l) => l.includes('平均亮度')))
check('细节均匀时说明「未据此定位」', /未据此定位/.test(flatCss.css))
check('细节均匀时焦点依据写明用居中', /焦点依据：.*居中/.test(flatCss.css))

const detailCss = generateCss({ url, intent: parseIntent('全屏铺满'), analysis: pxAnalysis(false) })
check('按重心定位时确实报告重心', /主体重心 20%,30%/.test(detailCss.css),
  detailCss.css.split('\n').find((l) => l.includes('平均亮度')))

/* ============================================================ 8. 稳健性矩阵 */

console.log('\n=== 8. 多描述 × 多图片比例矩阵（不崩、不产出空代码）===')

const DESCS = [
  '全屏英雄区，铺满不留白，标题在底部',
  '不要拉伸，完整显示整张图',
  '卡片封面，重点在左边，不要裁到主体',
  '细密格子底纹，平铺，密一点',
  '移动端优先的横幅，手机上一屏高',
  '横向平铺的分隔纹，高 120px',
  '桌面优先，适配暗色模式的高分屏图',
  '只要属性，占半屏，加个遮罩文字才看得清',
  '视差固定背景，主体在下方',
  '普普通通一张背景图',
]

const RATIOS = [
  ['超宽', 2560, 1080], ['横图', 1920, 1080], ['方图', 1000, 1000],
  ['竖图', 1080, 1920], ['极限竖', 600, 2400],
]

let combos = 0
let problems = 0
for (const desc of DESCS) {
  const intent = parseIntent(desc)
  for (const [label, w, h] of RATIOS) {
    combos++
    try {
      const r = generateCss({ url: 'https://example.com/x.jpg', intent, analysis: A(w, h) })
      if (!r.css || r.css.length < 60) { problems++; console.log(`  ✗ ${label} / ${desc.slice(0, 12)} → 代码过短`) }
      if (/undefined|null|NaN/.test(r.css)) { problems++; console.log(`  ✗ ${label} / ${desc.slice(0, 12)} → 出现 undefined/null/NaN`) }
      // 生成的 CSS 花括号必须配平，否则粘贴进项目会直接报错
      const open = (r.css.match(/\{/g) || []).length
      const close = (r.css.match(/\}/g) || []).length
      if (open !== close) { problems++; console.log(`  ✗ ${label} / ${desc.slice(0, 12)} → 花括号不配平 ${open}/${close}`) }
    } catch (e) {
      problems++
      console.log(`  ✗ ${label} / ${desc.slice(0, 12)} → 抛错 ${e.message}`)
    }
  }
}
check(`矩阵 ${combos} 组全部正常`, problems === 0, `${problems} 组有问题`)

// 每条规则都必须能说清理由，否则界面上无法解释
check('每条意图判定都带说明', DESCS.every((d) => parseIntent(d).notes.length >= 2))

// 未知场景要能被提示出来
check('无法识别的描述会提示补充信息', parseIntent('随便来个背景').unmatched.length > 0)
check('全部识别时不提示补充', parseIntent('全屏英雄区图，铺满不留白').unmatched.length === 0)

/* ============================================================ 9. 常量自洽 */

console.log('\n=== 9. 常量自洽 ===')
check('设备列表非空', DEVICES.length >= 5)
check('每个设备都有宽高', DEVICES.every((d) => d.w > 0 && d.h > 0 && d.label))
check('场景列表有 4 条', SCENARIOS.length === 4)
check('每个场景都能被解析出 fill', SCENARIOS.every((s) => parseIntent(s.text).fill))

/* ============================================================ 汇总 */

console.log(`\n===== 结果：${pass} 通过 / ${fail} 失败 =====`)
if (fail) {
  console.log('\n失败清单：')
  failures.forEach((f) => console.log('  - ' + f))
}
console.log()
process.exit(fail ? 1 : 0)
