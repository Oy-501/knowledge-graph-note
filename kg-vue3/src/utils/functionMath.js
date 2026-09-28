/**
 * 函数表达式解析、采样与特征分析。
 *
 * 为什么单独抽一层：绘图组件只负责"把点连成线"，
 * 而"哪些点根本不存在""哪里要断开""有哪些特征点"这些都是数学问题，
 * 混在渲染代码里既难测也难复用。
 *
 * 依赖 mathjs 的 AST（而不是 eval）：既拿到完整函数库，
 * 又能把表达式拆成子节点用于「逐步求值」展示，且不执行任意代码。
 */
import { parse } from 'mathjs'
// 再取一次命名空间用于「函数名是否存在」的校验。
// 为什么需要：mathjs 的 parse 不校验函数是否存在，`foo(x)` 能解析成功，
// 但求值全为 NaN —— 用户只看到一张空图，完全不知道错在哪。
import * as mathAll from 'mathjs'

/* ------------------------------------------------------------------ 常量与别名 */

/** 常见数学别名 → mathjs 能识别的写法（降低输入门槛） */
const ALIASES = [
  [/\bln\s*\(/g, 'log('],
  [/\blg\s*\(/g, 'log10('],
  [/\btg\s*\(/g, 'tan('],
  [/\bctg\s*\(/g, 'cot('],
  [/\barcsin\s*\(/g, 'asin('],
  [/\barccos\s*\(/g, 'acos('],
  [/\barctan\s*\(/g, 'atan('],
  [/\barsh\s*\(/g, 'asinh('],
  [/\barch\s*\(/g, 'acosh('],
  [/\bπ/g, 'pi'],
  [/√\s*\(/g, 'sqrt('],
  [/∛\s*\(/g, 'cbrt('],
  [/×/g, '*'],
  [/÷/g, '/'],
  [/−/g, '-'],          // U+2212 减号
  [/–/g, '-'],
  [/²/g, '^2'],
  [/³/g, '^3'],
]

/** 会把后面括号当作「调用」的名字（这些不插入乘号） */
const CALLABLE = new Set([
  'sin', 'cos', 'tan', 'cot', 'sec', 'csc',
  'asin', 'acos', 'atan', 'atan2', 'acot', 'asec', 'acsc',
  'sinh', 'cosh', 'tanh', 'coth', 'sech', 'csch',
  'asinh', 'acosh', 'atanh', 'acoth',
  'log', 'log2', 'log10', 'exp', 'sqrt', 'cbrt', 'nthRoot',
  'abs', 'sign', 'floor', 'ceil', 'round', 'fix',
  'pow', 'mod', 'gcd', 'lcm', 'factorial', 'gamma', 'erf',
  'min', 'max', 'hypot', 'random', 'square', 'cube',
])

/** 物理/数学常用常量（不当作参数） */
export const KNOWN_CONSTANTS = new Set([
  'pi', 'e', 'tau', 'phi', 'Infinity', 'inf', 'NaN', 'i',
])

/* ------------------------------------------------------------------ 表达式规范化 */

/**
 * 把用户输入整理成 mathjs 可解析的表达式。
 *
 * 主要做两件事，都是为了让输入更接近"数学书写习惯"：
 *   1. 别名替换（ln / lg / tg / π / √ / × 等）
 *   2. 补全省略的乘号：`2x` → `2*x`，`2sin(x)` → `2*sin(x)`，
 *      `(x+1)(x-1)` → `(x+1)*(x-1)`
 *
 * 补乘号要小心两个坑：
 *   - `2e3` 是科学计数法，不能变成 `2*e3`
 *   - `sin(x)` 里的 `sin(` 不能变成 `sin*(x)`
 */
export function normalizeExpression(input) {
  let s = String(input ?? '').trim()
  if (!s) return ''

  for (const [re, to] of ALIASES) s = s.replace(re, to)

  // 去掉首尾可能出现的等号左侧写法："y = 2x+1" → "2x+1"
  s = s.replace(/^\s*[a-zA-Z]\s*=\s*/, '')

  // 数字后紧跟字母或左括号 → 补乘号（排除科学计数法 2e3 / 2E-3）
  // 前置断言 (?<![\w.]) 很关键：否则会把 log10( 里的 "0(" 也插成 "log10*("
  s = s.replace(/(?<![\w.])(\d)(?![eE][+-]?\d)([a-zA-Z(])/g, '$1*$2')

  // 右括号后紧跟字母、数字或左括号 → 补乘号
  s = s.replace(/\)\s*\(/g, ')*(')
  s = s.replace(/\)(\d)/g, ')*$1')
  s = s.replace(/\)([a-zA-Z])/g, ')*$1')

  // 字母名后跟左括号有歧义：`x(x+1)` 该补乘号，`sin(x)` 是函数调用。
  // 规则：已知函数名 → 保持调用；**单字母**标识符 → 视作变量，补乘号；
  // 其余多字母名字 → 保持调用形态，交给后面的「未知函数」校验去报错。
  //
  // 为什么多字母不补乘号：曾经一律补乘号，于是 `foo(x)` 变成 `foo*(x)`，
  // `foo` 被当成参数（默认 1），用户看到一条 y=x 的直线且毫无报错 —— 比报错更糟。
  // 保持调用形态，才能把"这个函数不存在"准确说出来。
  s = s.replace(/([a-zA-Z_]\w*)\s*\(/g, (m, name) => {
    if (CALLABLE.has(name)) return m
    return name.length === 1 ? `${name}*(` : m
  })

  // 变量与变量之间：a b → a*b（仅限单字母，避免误伤多字母标识符）
  s = s.replace(/\b([a-zA-Z])\s+([a-zA-Z])\b/g, '$1*$2')

  return s
}

/* ------------------------------------------------------------------ 编译 */

/**
 * 编译表达式为单变量函数。
 *
 * @returns {{ok:true, fn:(x:number)=>number, node:object, expr:string, params:string[]}}
 *        | {{ok:false, error:string}}
 */
export function compileFunction(input, variables = ['x']) {
  const expr = normalizeExpression(input)
  if (!expr) return { ok: false, error: '表达式为空' }

  let node
  try {
    node = parse(expr)
  } catch (e) {
    return { ok: false, error: cleanParseError(e.message) }
  }

  // 计算自由符号：既不是变量、也不是常量/函数名的，当作可调参数
  const used = new Set()
  node.traverse((n, path, parent) => {
    if (n.type === 'SymbolNode') {
      // 函数名在本 AST 里也是 SymbolNode（作为 FunctionNode.fn），需排除
      if (parent && parent.type === 'FunctionNode' && parent.fn === n) return
      used.add(n.name)
    }
  })

  const params = [...used].filter(
    name => !variables.includes(name) && !KNOWN_CONSTANTS.has(name)
  )

  // 校验函数名：拼错时要立刻说清楚，而不是画出一张空图
  const unknownFns = []
  node.traverse((n) => {
    if (n.type === 'FunctionNode') {
      const name = n.fn?.name
      if (name && typeof mathAll[name] !== 'function') unknownFns.push(name)
    }
  })
  if (unknownFns.length) {
    const uniq = [...new Set(unknownFns)]
    const hints = uniq.map(n => {
      const near = suggestName(n)
      return near ? `「${n}」→ 是否想写「${near}」` : `「${n}」`
    })
    return { ok: false, error: `不支持这个函数：${hints.join('；')}。点右上角「函数速查」可看全部可用函数` }
  }

  const compiled = node.compile()
  const fn = (x, scope = {}) => {
    const s = { ...scope }
    variables.forEach((v, i) => { s[v] = Array.isArray(x) ? x[i] : x })
    const out = compiled.evaluate(s)
    // 复数结果（如 sqrt(-1)）在实数平面上无意义，按"无定义"处理
    if (out && typeof out === 'object') return NaN
    return typeof out === 'number' ? out : Number(out)
  }

  return { ok: true, fn, node, expr, params, variables }
}

// 常用函数优先：编辑距离相同时应优先建议这些，而不是同距离的冷门名。
// 真实例子：`sinn` 到 `sin` 与 `sign` 的距离都是 1，
// 单纯取"先遍历到的"会建议 `sign`，而用户显然想写 `sin`。
const COMMON_FUNCTIONS = new Set([
  'sin', 'cos', 'tan', 'cot', 'sec',
  'asin', 'acos', 'atan', 'sinh', 'cosh', 'tanh',
  'log', 'log2', 'log10', 'exp', 'sqrt', 'cbrt',
  'abs', 'sign', 'floor', 'ceil', 'round', 'mod', 'pow',
  'min', 'max', 'hypot', 'gamma', 'erf', 'factorial',
])

/** 在 mathjs 的函数名里找最相近的一个，用于拼写建议 */
function suggestName(name) {
  const lower = name.toLowerCase()
  let best = null
  let bestScore = Infinity

  for (const c of Object.keys(mathAll)) {
    if (typeof mathAll[c] !== 'function' || c.length > 12) continue
    const d = editDistance(lower, c.toLowerCase())
    // 评分：距离为主，常用性与长度只做平局裁决
    const score = d * 100 + (COMMON_FUNCTIONS.has(c) ? 0 : 10) + Math.min(c.length, 20)
    if (score < bestScore) { bestScore = score; best = c }
  }

  const dist = Math.floor(bestScore / 100)
  // 差距太大就别乱建议，免得误导
  return best && dist <= Math.max(1, Math.floor(name.length / 3)) ? best : null
}

/** 编辑距离（只用于拼写建议，字符串很短） */
function editDistance(a, b) {
  const dp = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)])
  for (let j = 0; j <= b.length; j++) dp[0][j] = j
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      dp[i][j] = Math.min(
        dp[i - 1][j] + 1,
        dp[i][j - 1] + 1,
        dp[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
      )
    }
  }
  return dp[a.length][b.length]
}

/** 把 mathjs 的英文报错翻译成人能看懂的话 */
function cleanParseError(msg = '') {
  const m = String(msg)
  if (/Unexpected end of expression/i.test(m)) return '表达式不完整（可能少了一个右括号）'
  if (/Parenthesis\s*\)\s*expected/i.test(m)) return '括号不匹配，请检查左右括号数量'
  if (/Value expected/i.test(m)) return '运算符附近缺少数值，请检查是否多写了符号'
  if (/Undefined symbol/i.test(m)) {
    const name = m.match(/Undefined symbol (\w+)/)?.[1]
    return name ? `无法识别「${name}」：它既不是变量 x，也不是支持的函数` : '含有无法识别的符号'
  }
  return m.replace(/^Error:\s*/, '')
}

/* ------------------------------------------------------------------ 采样与分段 */

/**
 * 判断相邻两个采样点之间是否跨过了一个极点（竖直渐近线）。
 *
 * 单看 Δy 大小是不能判断的——这正是踩过的坑：
 *   - 阈值取大（等于越界丢弃线）→ 极点恰好落在两采样点之间时判不出来，
 *     曲线上会出现一条穿过极点的竖直连线，把"无定义"画成了"有值"
 *   - 阈值取小（如 0.6×量程）→ 极点附近"陡但连续"的部分被切成碎段
 *     （1/x 在 n=1200 时被切成 4 段）
 *
 * 区分两者的关键是**符号**：
 *   - 跨极点：两侧必然异号，且两侧都已经冲出常规量程
 *   - 陡但连续：一路上 |y| 都在涨，符号不变
 * 所以判据用「符号翻转 + 两侧都很大」，而不是单纯的 Δy。
 * 另外保留一条 Δy 极大的兜底（同号但跳得离谱，例如阶梯型跳变）。
 */
function isPoleCrossing(a, b, span, dropLimit) {
  if (Math.abs(b.y - a.y) > dropLimit) return true
  const signFlip = (a.y > 0) !== (b.y > 0)
  if (!signFlip) return false
  return Math.abs(a.y) > span && Math.abs(b.y) > span
}

/**
 * 在 [xMin, xMax] 上采样并切成若干连续段，同时记录「断裂区间」。
 *
 * 为什么要分段：像 1/x、tan(x)、log(x) 这类函数在定义域断裂处
 * **不能连起来**——连起来会出现一条根本不存在的竖线，
 * 把"无定义"画成了"有一条陡线"，数学上错误、视觉上误导。
 *
 * 判定策略（第一版用"相邻点 Δy 超过阈值就断"，结果是 1/x 被切成 12 段碎线，
 * 因为极点附近函数本来就陡但连续）——
 * 改成**先按幅度丢弃越界点，再把丢弃处记为断裂**：
 *
 *   1. 用有限值的分位数算出稳健量程 span（不被极点附近的极大值带偏）
 *   2. |y| > span*8 的点直接丢弃 —— 这种点本来就在可读范围之外，
 *      丢掉它等于承认"这里冲到无穷去了"
 *   3. 丢弃造成的空洞 → 记为一个 gap；相邻保留点之间若 Δy > span*4
 *      也断开（兜住"采样点恰好跨过极点、两边都还没越界"的情况）
 *
 * 这样 1/x 只断 1 次（2 段）、floor(x) 的阶梯不会被误切、tan(x) 的每个极点都断。
 */
export function sampleFunction(fn, { xMin, xMax, samples = 1200, scope = {}, ySpanHint = 0 } = {}) {
  const step = (xMax - xMin) / (samples - 1)
  const raw = new Array(samples)

  for (let i = 0; i < samples; i++) {
    const x = xMin + step * i
    let y
    try {
      y = fn(x, scope)
    } catch {
      y = NaN
    }
    raw[i] = { x, y }
  }

  // 稳健量程：分位数而非极值，避免被极点附近的超大值带偏
  const finite = raw.map(p => p.y).filter(Number.isFinite).sort((a, b) => a - b)
  let span = 1
  if (finite.length >= 4) {
    const q = (p) => finite[Math.min(finite.length - 1, Math.floor(p * (finite.length - 1)))]
    span = q(0.98) - q(0.02)
    if (!(span > 0)) span = Math.abs(finite[finite.length - 1] - finite[0]) || 1
  } else if (finite.length) {
    span = Math.abs(finite[finite.length - 1] - finite[0]) || 1
  }
  if (ySpanHint > 0) span = Math.max(span, ySpanHint * 0.25)

  const dropLimit = span * 8

  const segments = []
  const gaps = []
  let current = null
  let lastKept = null          // 上一个被保留的点（用于跨 gap 判定）
  let lastKeptIndex = -1
  let pendingGapStart = null   // 本次连续丢弃的起始 x

  for (let i = 0; i < samples; i++) {
    const p = raw[i]
    const valid = Number.isFinite(p.y) && Math.abs(p.y) <= dropLimit

    if (!valid) {
      if (pendingGapStart === null) pendingGapStart = p.x
      current = null
      continue
    }

    // 有中断：把这段空洞记下来
    if (pendingGapStart !== null) {
      gaps.push({
        xStart: pendingGapStart,
        xEnd: p.x,
        mid: (pendingGapStart + p.x) / 2,
        before: lastKept,
        after: p,
      })
      pendingGapStart = null
      lastKeptIndex = -1       // 断开后不再跨空洞比较 Δy
    } else if (current && lastKeptIndex === i - 1 && lastKept &&
               isPoleCrossing(lastKept, p, span, dropLimit)) {
      // 相邻采样点之间跨过了极点：拆成两段，中间不连线
      gaps.push({ xStart: lastKept.x, xEnd: p.x, mid: (lastKept.x + p.x) / 2,
                  before: lastKept, after: p, narrow: true })
      current = null
    }

    if (!current) {
      current = []
      segments.push(current)
    }
    current.push(p)
    lastKept = p
    lastKeptIndex = i
  }

  // 尾部空洞（例如定义域在右端就结束了）
  if (pendingGapStart !== null && lastKept) {
    gaps.push({ xStart: pendingGapStart, xEnd: xMax, mid: (pendingGapStart + xMax) / 2,
                before: lastKept, after: null, tail: true })
  }

  return { segments, gaps, raw, span, dropLimit, sampleCount: samples }
}

/* ------------------------------------------------------------------ 特征分析 */

/**
 * 找零点、极值、断裂位置。
 * 全部基于采样点做数值近似——够用来做教学标注，不追求符号精确。
 */
export function findFeatures(segments, gaps = [], { xMin = -10, xMax = 10, span = 0 } = {}) {
  const zeros = []
  const extrema = []

  for (const seg of segments) {
    for (let i = 1; i < seg.length; i++) {
      const a = seg[i - 1], b = seg[i]
      if (a.y === 0) zeros.push({ x: a.x, y: 0 })
      else if (a.y * b.y < 0) {
        const t = a.y / (a.y - b.y)
        zeros.push({ x: a.x + (b.x - a.x) * t, y: 0 })
      }
      if (i >= 2) {
        const p = seg[i - 2]
        if ((a.y > p.y && a.y > b.y) || (a.y < p.y && a.y < b.y)) {
          extrema.push({ x: a.x, y: a.y, kind: a.y > p.y ? 'max' : 'min' })
        }
      }
    }
  }

  // 断裂分类：两侧都被"冲到很大"的是竖直渐近线；否则只是定义域空洞
  // （比如 log(x) 的 x≤0 部分——那里不是渐近线，是压根没定义）
  // 判据基准用「稳健量程 span」而不是「保留点里的最大绝对值」：
  // 后者会被极点附近的极大值抬高，导致 tan(x) 的多数渐近线判不出来。
  // span 来自分位数，代表函数"主体"的量级，用它判断"是否冲到很远"更可靠。
  const mags = segments.flatMap(s => s.map(p => Math.abs(p.y))).filter(Number.isFinite)
  const scale = span > 0 ? span : (mags.length ? Math.max(...mags) : 1)
  const asymptotes = []
  const domainGaps = []

  for (const g of gaps) {
    const beforeMag = g.before ? Math.abs(g.before.y) : 0
    const afterMag = g.after ? Math.abs(g.after.y) : 0
    // 门槛取 1×span：采样越稀疏，断点两端离极点越远、|y| 越小，
    // 门槛定太高（曾用 2×span）会把真实渐近线漏判成"定义域空洞"
    const bigBefore = beforeMag > scale
    const bigAfter = afterMag > scale
    // 单边缺失（定义域到边界为止）不算渐近线
    const bothSides = g.before && g.after
    if (bothSides && bigBefore && bigAfter) asymptotes.push({ x: g.mid })
    else if (!g.narrow) domainGaps.push({ xStart: g.xStart, xEnd: g.xEnd })
  }

  const dedupe = (arr, tol) => {
    const out = []
    for (const item of [...arr].sort((a, b) => a.x - b.x)) {
      if (!out.length || Math.abs(item.x - out[out.length - 1].x) > tol) out.push(item)
    }
    return out
  }
  const tol = (xMax - xMin) / 60

  return {
    zeros: dedupe(zeros, tol).slice(0, 24),
    extrema: dedupe(extrema, tol).slice(0, 24),
    asymptotes: dedupe(asymptotes, tol).slice(0, 16),
    domainGaps,
  }
}

/* ------------------------------------------------------------------ 逐步求值（形成过程） */

/**
 * 把「算 f(x)」拆成有先后顺序的步骤。
 *
 * 用的是后序遍历：先算子节点，再算父节点 —— 这正是人笔算的顺序。
 * 每步带上该子表达式、它的值、以及在表达式树里的深度，
 * 界面就能按顺序讲清楚「先算 sin(x)，再乘 2，最后加 1」。
 */
export function collectEvalSteps(node, scope, maxSteps = 40) {
  const steps = []

  function walk(n, depth) {
    if (steps.length > maxSteps) return null

    if (n.type === 'OperatorNode' || n.type === 'FunctionNode' ||
        n.type === 'ParenthesisNode' || n.type === 'ArrayNode') {
      for (const arg of n.args || []) walk(arg, depth + 1)
    } else if (n.type === 'ParenthesisNode' && n.content) {
      walk(n.content, depth + 1)
    }

    let value
    try {
      value = n.compile().evaluate(scope)
    } catch {
      value = NaN
    }
    if (value && typeof value === 'object') value = NaN

    // 常量与变量本身不必单独列一步（否则噪音太多），只列运算
    const trivial = n.type === 'ConstantNode' || n.type === 'SymbolNode'
    steps.push({
      expr: n.toString({ parenthesis: 'auto' }),
      value,
      depth,
      trivial,
      kind: kindOf(n),
    })
    return value
  }

  let result
  try {
    result = node.compile().evaluate(scope)
  } catch {
    result = NaN
  }
  walk(node, 0)

  return { steps, result }
}

function kindOf(n) {
  if (n.type === 'ConstantNode') return '常量'
  if (n.type === 'SymbolNode') return '变量'
  if (n.type === 'FunctionNode') return `函数 ${n.fn?.name || ''}`.trim()
  if (n.type === 'OperatorNode') return `运算 ${n.op || ''}`.trim()
  if (n.type === 'ParenthesisNode') return '括号'
  return n.type
}

/* ------------------------------------------------------------------ 坐标轴刻度 */

/**
 * 生成"好看"的刻度（1/2/5 × 10^n 步长），并给出对应的小数位。
 * 直接均分会出现 0.3333 / 3.6667 这种刻度，既难读也不像数学书。
 */
export function niceTicks(min, max, target = 8) {
  if (!(max > min)) return { ticks: [min], step: 1, decimals: 0 }

  const rawStep = (max - min) / target
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)))
  const norm = rawStep / mag
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag

  const start = Math.ceil(min / step) * step
  const ticks = []
  for (let v = start; v <= max + step * 1e-6; v += step) {
    // 消除浮点累积误差（0.1+0.2 类问题会让刻度变成 0.30000000000000004）
    ticks.push(Number((Math.round(v / step) * step).toFixed(12)))
  }

  const decimals = Math.max(0, -Math.floor(Math.log10(step)))
  return { ticks, step, decimals: Math.min(decimals, 8) }
}

/** 数值格式化：避免 1e-7 这种尾巴糊在坐标轴上 */
export function formatNumber(v, decimals = 2) {
  if (!Number.isFinite(v)) return '—'
  const abs = Math.abs(v)
  if (abs !== 0 && (abs < 1e-4 || abs >= 1e6)) return v.toExponential(2)
  const fixed = v.toFixed(decimals)
  return fixed.replace(/\.?0+$/, '') || '0'
}

/* ------------------------------------------------------------------ 函数目录（"显示所有函数"） */

/**
 * 函数目录：分组列出常用函数与示例。
 * 目的不是穷举 mathjs 的全部函数，而是让用户**看得见能用什么**——
 * 不知道存在 log2 的人不会去用 log2。
 */
export const FUNCTION_CATALOG = [
  {
    group: '三角函数',
    items: [
      { name: 'sin(x)', desc: '正弦，周期 2π', sample: 'sin(x)' },
      { name: 'cos(x)', desc: '余弦，周期 2π', sample: 'cos(x)' },
      { name: 'tan(x)', desc: '正切，x=π/2+kπ 处无定义', sample: 'tan(x)' },
      { name: 'cot(x)', desc: '余切', sample: 'cot(x)' },
      { name: 'sec(x)', desc: '正割 1/cos(x)', sample: 'sec(x)' },
      { name: 'csc(x)', desc: '余割 1/sin(x)', sample: 'csc(x)' },
    ],
  },
  {
    group: '反三角',
    items: [
      { name: 'asin(x)', desc: '反正弦，定义域 [-1,1]', sample: 'asin(x)' },
      { name: 'acos(x)', desc: '反余弦，定义域 [-1,1]', sample: 'acos(x)' },
      { name: 'atan(x)', desc: '反正切，值域 (-π/2, π/2)', sample: 'atan(x)' },
      { name: 'atan2(y,x)', desc: '四象限反正切', sample: 'atan2(x,1)' },
    ],
  },
  {
    group: '双曲函数',
    items: [
      { name: 'sinh(x)', desc: '双曲正弦', sample: 'sinh(x)' },
      { name: 'cosh(x)', desc: '双曲余弦', sample: 'cosh(x)' },
      { name: 'tanh(x)', desc: '双曲正切，值域 (-1,1)', sample: 'tanh(x)' },
      { name: 'asinh(x)', desc: '反双曲正弦', sample: 'asinh(x)' },
      { name: 'acosh(x)', desc: '反双曲余弦，x≥1', sample: 'acosh(x)' },
      { name: 'atanh(x)', desc: '反双曲正切，|x|<1', sample: 'atanh(x)' },
    ],
  },
  {
    group: '指数与对数',
    items: [
      { name: 'exp(x)', desc: '自然指数 e^x', sample: 'exp(x)' },
      { name: 'log(x)', desc: '自然对数 ln x，x>0', sample: 'log(x)' },
      { name: 'log2(x)', desc: '以 2 为底，x>0', sample: 'log2(x)' },
      { name: 'log10(x)', desc: '常用对数，x>0', sample: 'log10(x)' },
      { name: 'log(x, b)', desc: '以 b 为底的对数', sample: 'log(x, 2)' },
      { name: 'e^x', desc: '自然指数（等价 exp(x)）', sample: 'e^x' },
      { name: '2^x', desc: '任意底指数', sample: '2^x' },
    ],
  },
  {
    group: '幂与根式',
    items: [
      { name: 'x^2', desc: '平方（抛物线）', sample: 'x^2' },
      { name: 'x^3', desc: '立方', sample: 'x^3' },
      { name: 'x^n', desc: '任意次幂', sample: 'x^3' },
      { name: 'sqrt(x)', desc: '平方根，x≥0', sample: 'sqrt(x)' },
      { name: 'cbrt(x)', desc: '立方根，允许负数', sample: 'cbrt(x)' },
      { name: 'nthRoot(x,n)', desc: 'n 次方根', sample: 'nthRoot(x,3)' },
      { name: 'abs(x)', desc: '绝对值', sample: 'abs(x)' },
      { name: '1/x', desc: '反比例，x=0 处无定义', sample: '1/x' },
      { name: 'hypot(x,1)', desc: '√(x²+1²)', sample: 'hypot(x,1)' },
    ],
  },
  {
    group: '取整与符号',
    items: [
      { name: 'floor(x)', desc: '向下取整（阶梯）', sample: 'floor(x)' },
      { name: 'ceil(x)', desc: '向上取整', sample: 'ceil(x)' },
      { name: 'round(x)', desc: '四舍五入', sample: 'round(x)' },
      { name: 'fix(x)', desc: '向零截断', sample: 'fix(x)' },
      { name: 'sign(x)', desc: '符号函数', sample: 'sign(x)' },
      { name: 'mod(x,3)', desc: '取余 / 锯齿波', sample: 'mod(x,3)' },
      { name: 'min(x,1)', desc: '取较小值（有截断）', sample: 'min(x,1)' },
      { name: 'max(x,-1)', desc: '取较大值', sample: 'max(x,-1)' },
    ],
  },
  {
    group: '特殊函数与常数',
    items: [
      { name: 'gamma(x)', desc: '伽马函数（阶乘延拓）', sample: 'gamma(x)' },
      { name: 'factorial(x)', desc: '阶乘', sample: 'factorial(floor(abs(x)))' },
      { name: 'erf(x)', desc: '误差函数（S 型）', sample: 'erf(x)' },
      { name: 'sin(x)/x', desc: 'sinc 型，x=0 处无定义', sample: 'sin(x)/x' },
      { name: 'e^(-x^2)', desc: '高斯钟形', sample: 'e^(-x^2)' },
      { name: 'pi', desc: '圆周率 π', sample: 'pi' },
      { name: 'e', desc: '自然常数 e', sample: 'e' },
      { name: 'tau', desc: '2π', sample: 'tau' },
      { name: 'phi', desc: '黄金比', sample: 'phi' },
    ],
  },
]

/** 预设示例：覆盖各种"曲线形态"，方便快速看到效果 */
export const PRESETS = [
  { label: '抛物线', expr: 'x^2' },
  { label: '正弦波', expr: 'sin(x)' },
  { label: '阻尼振荡', expr: 'e^(-x/5)*sin(2x)' },
  { label: '高斯钟形', expr: 'e^(-x^2)' },
  { label: '反比例', expr: '1/x' },
  { label: '对数', expr: 'log(x)' },
  { label: '正切（多渐近线）', expr: 'tan(x)' },
  { label: '绝对值', expr: 'abs(x)' },
  { label: '阶跃·取整', expr: 'floor(x)' },
  { label: 'sinc', expr: 'sin(x)/x' },
  { label: 'S 型（erf）', expr: 'erf(x)' },
  { label: '心脏线半支', expr: 'sqrt(1-x^2)' },
  { label: '摆线近似', expr: 'x - sin(x)' },
  { label: '参数族', expr: 'a*sin(b*x + c)' },
]
