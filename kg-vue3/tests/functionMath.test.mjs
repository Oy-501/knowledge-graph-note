/**
 * 函数图像核心逻辑回归测试。
 *
 * 运行：npm run test:math
 *
 * 覆盖的是"容易算错但不容易肉眼发现"的部分：定义域断裂分段、
 * 极点识别、零点/极值、刻度取整、逐步求值顺序。
 * 这些一旦回归，界面上只会表现为"曲线怪怪的"，很难定位 ——
 * 所以用断言把它们钉住。
 */
import {
  normalizeExpression, compileFunction, sampleFunction,
  findFeatures, niceTicks, collectEvalSteps, formatNumber
} from '../src/utils/functionMath.js'

let pass = 0, fail = 0
const check = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`  ok   ${name}`) }
  else { fail++; console.log(`  FAIL ${name} ${extra}`) }
}

console.log('\n=== 1. 表达式规范化（省略乘号 / 别名 / 科学计数法不误伤）===')
const normCases = [
  ['2x', '2*x'],
  ['2sin(x)', '2*sin(x)'],
  ['(x+1)(x-1)', '(x+1)*(x-1)'],
  ['3(x+2)', '3*(x+2)'],
  ['x(x+1)', 'x*(x+1)'],
  ['2e3', '2e3'],                 // 科学计数法必须原样保留
  ['2e', '2*e'],                  // 2 乘自然常数 e
  ['ln(x)', 'log(x)'],
  ['lg(x)', 'log10(x)'],
  ['y = 2x + 1', '2*x + 1'],
  ['sin(x)cos(x)', 'sin(x)*cos(x)'],
  ['√(x)', 'sqrt(x)'],
  ['x²', 'x^2'],
]
for (const [input, want] of normCases) {
  const got = normalizeExpression(input)
  check(`${input.padEnd(16)} → ${want}`, got === want, `实得: ${got}`)
}

console.log('\n=== 2. 编译与参数识别 ===')
const f1 = compileFunction('a*sin(b*x + c)')
check('参数识别出 a,b,c', f1.ok && f1.params.sort().join() === 'a,b,c', JSON.stringify(f1.params))
check('常量 pi 不算参数', compileFunction('sin(pi*x)').params.length === 0)
check('数学常数 e 不算参数', compileFunction('e^(-x^2)').params.length === 0)
check('函数名不被当参数', compileFunction('sin(x)+log(x)').params.length === 0)
check('错误表达式有可读报错', compileFunction('sin(').ok === false, compileFunction('sin(').error)
check('括号不匹配有提示', /括号/.test(compileFunction('(x+1').error || ''), compileFunction('(x+1').error)

console.log('\n=== 2b. 未知函数必须报错（否则只会画出一张空图）===')
const bad = compileFunction('foo(x)')
check('未知函数被判为错误', bad.ok === false, JSON.stringify(bad))
check('报错里点出函数名 foo', /foo/.test(bad.error || ''), bad.error)
const typo = compileFunction('sinn(x)')
check('拼错给出相近建议 sin', /是否想写|sin/.test(typo.error || ''), typo.error)
check('已知函数不误报', compileFunction('sin(x)+log(x)+abs(x)').ok === true)
check('支持的函数名不误报（log2/log10/atan2/cbrt）',
  compileFunction('log2(x)+log10(x)+atan2(x,1)+cbrt(x)').ok === true)

console.log('\n=== 3. 求值正确性 ===')
const f2 = compileFunction('x^2 - 4*x + 3')
check('x=1 时 x²-4x+3 = 0', Math.abs(f2.fn(1) - 0) < 1e-9)
check('x=3 时 x²-4x+3 = 0', Math.abs(f2.fn(3) - 0) < 1e-9)
check('x=2 时 x²-4x+3 = -1', Math.abs(f2.fn(2) + 1) < 1e-9)
const f3 = compileFunction('a*sin(x)')
check('参数作用域生效 a=2 → 2sin(pi/2)=2', Math.abs(f3.fn(Math.PI / 2, { a: 2 }) - 2) < 1e-9)

console.log('\n=== 4. 采样分段（关键：定义域断裂必须断开）===')
const seg = (expr, opts = {}) => sampleFunction(
  compileFunction(expr).fn,
  { xMin: -10, xMax: 10, samples: 2001, ...opts }
)

const sCont = seg('x^2')
check('x² 应为 1 段（连续）', sCont.segments.length === 1, `实得 ${sCont.segments.length} 段`)

const sInv = seg('1/x')
check('1/x 应断开成 2 段', sInv.segments.length === 2, `实得 ${sInv.segments.length} 段`)

const sTan = seg('tan(x)')
check('tan(x) 在 [-10,10] 应断成多段', sTan.segments.length >= 6, `实得 ${sTan.segments.length} 段`)

const sLog = seg('log(x)')
check('log(x) 负半轴无定义 → 1 段且 x>0', sLog.segments.length === 1 &&
  sLog.segments[0].every(p => p.x > 0), `实得 ${sLog.segments.length} 段`)

const sSqrt = seg('sqrt(x)')
check('sqrt(x) 应只有 x≥0 部分', sSqrt.segments.length === 1 && sSqrt.segments[0][0].x >= 0)

const sFloor = seg('floor(x)')
check('floor(x) 阶梯不应被误断成碎段', sFloor.segments.length === 1,
  `实得 ${sFloor.segments.length} 段——阈值太敏感会把阶梯切断`)

console.log('\n=== 5. 特征分析 ===')
const q = seg('x^2 - 4*x + 3')
const feats = findFeatures(q.segments, q.gaps, { xMin: -10, xMax: 10, span: q.span })
check('x²-4x+3 找到 2 个零点', feats.zeros.length === 2, JSON.stringify(feats.zeros.map(z => z.x.toFixed(3))))
check('零点在 x=1 与 x=3', feats.zeros.every(z => Math.abs(z.x - 1) < 0.02 || Math.abs(z.x - 3) < 0.02),
  JSON.stringify(feats.zeros.map(z => z.x.toFixed(3))))
const q2 = seg('x^2')
check('x² 找到极小值 x≈0', (() => {
  const e = findFeatures(q2.segments, q2.gaps, { xMin: -10, xMax: 10, span: q2.span }).extrema
  return e.some(p => p.kind === 'min' && Math.abs(p.x) < 0.05)
})())
const tasy = findFeatures(sTan.segments, sTan.gaps, { xMin: -10, xMax: 10, span: sTan.span }).asymptotes
check('tan(x) 找到竖直渐近线(≥5)', tasy.length >= 5, `实得 ${tasy.length} 条`)
check('渐近线落在 ±π/2 / ±3π/2 附近',
  tasy.some(a => Math.abs(Math.abs(a.x) - Math.PI / 2) < 0.1) &&
  tasy.some(a => Math.abs(Math.abs(a.x) - 3 * Math.PI / 2) < 0.1),
  JSON.stringify(tasy.map(a => a.x.toFixed(2))))
const inv = findFeatures(sInv.segments, sInv.gaps, { xMin: -10, xMax: 10, span: sInv.span })
check('1/x 识别出 1 条竖直渐近线', inv.asymptotes.length === 1, `实得 ${inv.asymptotes.length}`)
check('1/x 渐近线在 x≈0', inv.asymptotes[0] && Math.abs(inv.asymptotes[0].x) < 0.05,
  JSON.stringify(inv.asymptotes.map(a => a.x.toFixed(3))))
const lg = findFeatures(sLog.segments, sLog.gaps, { xMin: -10, xMax: 10, span: sLog.span })
check('log(x) 左侧判为定义域空洞而非渐近线',
  lg.asymptotes.length === 0 && lg.domainGaps.length >= 1,
  `渐近线 ${lg.asymptotes.length} / 空洞 ${lg.domainGaps.length}`)

console.log('\n=== 6. 刻度生成 ===')
const t = niceTicks(-3.2, 7.8, 8)
check('刻度步长是 1/2/5 × 10^n', [0.5, 1, 2, 5, 10].includes(t.step), `step=${t.step}`)
check('刻度无浮点毛刺', t.ticks.every(v => String(v).length < 8), JSON.stringify(t.ticks))
const t2 = niceTicks(0, 1, 5)
check('0~1 区间步长合理', t2.step === 0.2 || t2.step === 0.25 || t2.step === 0.5, `step=${t2.step}`)
const t3 = niceTicks(0, 0.01, 5)
check('极小量程不产生 0.002 类毛刺', t3.ticks.length > 1, JSON.stringify(t3.ticks))

console.log('\n=== 7. 逐步求值（形成过程）===')
const f4 = compileFunction('2*sin(x) + 1')
const ev = collectEvalSteps(f4.node, { x: Math.PI / 2 })
check('求值结果 2*sin(π/2)+1 = 3', Math.abs(ev.result - 3) < 1e-9, `实得 ${ev.result}`)
check('步骤数 > 3（可讲清先后）', ev.steps.length > 3, `实得 ${ev.steps.length} 步`)
check('后序遍历：sin 先于最后的加法', (() => {
  const iSin = ev.steps.findIndex(s => /^sin\(/.test(s.expr))
  const iAdd = ev.steps.findIndex(s => s.expr.includes('+'))
  return iSin >= 0 && iAdd > iSin
})())
check('每步都带值', ev.steps.every(s => s.value !== undefined))

console.log('\n=== 8. 数值格式化 ===')
check('formatNumber(0.30000000000000004) 不留尾巴',
  !formatNumber(0.30000000000000004, 2).includes('0000'), formatNumber(0.30000000000000004, 2))
check('极大值用科学计数法', formatNumber(1.5e7).includes('e'))
check('NaN 显示为占位符', formatNumber(NaN) === '—')

console.log('\n=== 9. 稳健性矩阵：多函数 × 多采样密度 ===')
// 这一组是防回归的关键。极点（竖直渐近线）能否被正确识别，
// 取决于"有没有采样点足够靠近它"，因此同一函数在不同采样密度下
// 都可能出问题。实战中就在这里翻过两次车：
//   - 判据过松 → 曲线上出现一条穿过极点的竖直连线（把"无定义"画成"有值"）
//   - 判据过严 → 极点附近"陡但连续"的部分被切成碎段
const MATRIX = [
  ['1/x', 2, 1], ['1/x^2', 2, 1], ['1/(x-3)', 2, 1],
  ['tan(x)', 7, 6], ['cot(x)', 6, 5],
  ['floor(x)', 1, 0], ['log(x)', 1, 0], ['x^2', 1, 0],
  ['sqrt(x)', 1, 0], ['abs(x)', 1, 0], ['sin(x)', 1, 0],
  ['e^(-x^2)', 1, 0], ['erf(x)', 1, 0], ['sin(x)/x', 1, 0],
  ['sign(x)', 1, 0],
]
let mTotal = 0
const mBad = []
for (const [expr, expSeg, expAsy] of MATRIX) {
  const cf = compileFunction(expr)
  if (!cf.ok) { mBad.push(`${expr} 编译失败: ${cf.error}`); continue }
  for (const n of [800, 1200, 1600, 2400, 3200]) {
    mTotal++
    const r = sampleFunction(cf.fn, { xMin: -8, xMax: 8, samples: n })
    const ft = findFeatures(r.segments, r.gaps, { xMin: -8, xMax: 8, span: r.span })
    if (r.segments.length !== expSeg || ft.asymptotes.length !== expAsy) {
      mBad.push(`${expr} n=${n}: 段=${r.segments.length}(期望${expSeg}) 渐近线=${ft.asymptotes.length}(期望${expAsy})`)
    }
  }
}
check(`跨 ${MATRIX.length} 个函数 × 5 种采样密度共 ${mTotal} 组，分段与渐近线全部正确`,
  mBad.length === 0, mBad.slice(0, 4).join(' | '))

console.log(`\n===== 结果：${pass} 通过 / ${fail} 失败 =====\n`)
process.exit(fail ? 1 : 0)
