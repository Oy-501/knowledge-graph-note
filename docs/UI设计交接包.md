# UI 设计交接包（给外部设计工具 / AI 使用）

> 这份文件是**自包含**的：外部工具或 AI 只看得到这一个文件，
> 因此规范、色值、组件代码都写在下面，不需要再参考项目里的其他文件。
>
> 使用方式：把本文件整个交给工具，并附一句
> 「按这份设计系统产出界面，严格遵守 token、原语与禁忌清单」。

---

## 一、这是什么产品

一个**本地运行的知识图谱笔记应用**（Electron + Vue3 + FastAPI）。
功能：上传文档 → 抽取知识点 → 生成图谱 → 写笔记 → 知识库校验 → 图谱总结导出。

气质定位：**安静精密的学术仪器**。参考 Linear / Raycast / Obsidian ——
克制、信息密度高、用排版而不是装饰来表达层级。

## 二、三条不可违反的原则

1. **个性属于「标识」，不属于「容器」。**
   一个模块一种颜色，只占几像素（2px 下划线 / 7px 菱形），只出现在「你在哪」的位置。
   按钮、卡片、表格**全站只有一套写法**，不许按页面换色。
2. **静止的东西不该发光。**
   hover / 选中只允许「描边加粗 + 同色 brightness 提亮」，禁止 drop-shadow、扫光、渐变边缘光。
   光只用来表示「现在被操作的是这里」。
3. **强调有预算。**
   一屏最多 1 个实心主按钮（loud），其余为 tonal / outline / ghost。人人喊等于没人喊。

## 三、Token（直接取用）

### 色彩（亮色主题）

| 用途 | 变量 | 色值 |
|---|---|---|
| 应用外框 | `--bg-deep` | `#E7EAF2` |
| 主面板 | `--bg-primary` | `#F2F4F9` |
| 卡片 / 抬升面板 | `--bg-secondary` | `#FFFFFF` |
| 嵌套块 / 胶囊底 | `--bg-tertiary` | `#E9EDF5` |
| 悬浮态 | `--bg-hover` | `#DFE4EF` |
| 激活按压 | `--bg-active` | `#D3DAE8` |
| 正文 / 标题 | `--text-primary` | `#101725` |
| 次级信息 | `--text-secondary` | `#4A5670` |
| 辅助说明 | `--text-muted` | `#57637C` |
| 极弱提示 / 禁用 | `--text-faint` | `#8C97AB` |
| 交互主色（青） | `--accent` | `#0C6B84` |
| 实心填充面 | `--accent-fill` | `#0E7490` |
| 淡底 | `--accent-soft` | `rgba(8,145,178,.11)` |
| 边框 | `--border` | `#CFD6E4` |
| 弱边框 | `--border-light` | `#DFE4EE` |
| 成功 | `--success-fill` | `#0F7B5C` |
| 警告 | `--warning-fill` | `#B45309` |
| 危险 | `--danger-fill` | `#BE2E3E` |
| 信息 | `--info-fill` | `#0E7490` |
| 身份色（朱砂，非交互） | `--seal` | `#b8362a` |
| 辅色·紫（仅数据语义） | `--violet-text` | `#7C3AED` |
| 辅色·琥珀 | `--amber` | `#A34A08` |

**暗色主题**下 `--accent` 为 `#22D3EE`、`--accent-fill` 为 `#22D3EE`、
`--seal` 为 `#dc4a32`，其余按对比度重映射。

半透明表面（卡片用，让背景透上来）：
`--surface-1` = 卡片底 90%、`--surface-2` = 82%、`--surface-3` = 88%。

### 字号（六档，不许出现别的值）

`--fs-xs` 11px（仅角标/序号）· `--fs-sm` 12px · `--fs-md` 13px ·
`--fs-base` 14px · `--fs-lg` 16px · `--fs-xl` 18px

### 圆角与尺寸

- `--radius-sm` **6px**（控件）· `--radius` **10px**（卡片）· `--radius-lg` **14px**（浮层）
- `--ctrl-h` **30px**（按钮基准高度）· `--panel-width` 288px · `--toolbar-height` 56px
- **禁止** 4 / 8 / 12 这类中间值。

### 字体

- 正文：`-apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif`
- 数据 / 编号：`'JetBrains Mono', 'Fira Code', Consolas, monospace`
- 标题 ≥18px：`'Noto Serif SC', 'Songti SC', serif`（衬线，只用于展示）

### 动效

`--ease-out: cubic-bezier(0.22,0.61,0.36,1)` · `--dur-fast: 0.15s` · `--dur-base: 0.25s`

## 四、组件原语（照抄，不要自己另写一套）

```css
.u-surface { background: var(--surface-1); border: 1px solid var(--border-light);
             border-radius: var(--radius); }
.u-surface--flat   { background: transparent; border: 0; border-radius: 0; }
.u-surface--inset  { background: var(--surface-3); border-color: transparent;
                     border-radius: var(--radius-sm); }

.u-btn { display:inline-flex; align-items:center; justify-content:center; gap:6px;
         height: var(--ctrl-h); padding: 0 12px; border: 1px solid transparent;
         border-radius: var(--radius-sm); font-size: var(--fs-sm);
         color: var(--text-secondary); cursor:pointer;
         transition: background-color .15s var(--ease-out),
                     border-color .15s var(--ease-out),
                     color .15s var(--ease-out), transform .15s var(--ease-out); }
.u-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.u-btn:active:not(:disabled) { transform: translateY(1px); }
.u-btn:disabled { opacity: .45; cursor: not-allowed; }

.u-btn--solid   { background: var(--accent-fill); color: #fff; }      /* 一屏最多一个 */
.u-btn--solid:hover:not(:disabled) { filter: brightness(1.06); }
.u-btn--seal    { background: var(--seal); color: #fff; }             /* 品牌级动作 */
.u-btn--tonal   { background: var(--accent-soft); color: var(--accent); }
.u-btn--outline { border-color: var(--border); color: var(--text-primary); }
.u-btn--ghost   { color: var(--text-secondary); }
.u-btn--ghost:hover:not(:disabled) { background: var(--bg-hover); }
.u-btn--text    { height:auto; padding:2px 0; border-radius:0;
                  border-bottom:1px solid transparent; }              /* 导出/复制 */
.u-btn--sm      { height: calc(var(--ctrl-h) - 4px); padding: 0 9px;
                  font-size: var(--fs-xs); }

.u-chip { display:inline-flex; gap:5px; padding:1px 8px;
          border:1px solid var(--border-light); border-radius:3px;
          background: var(--surface-1); font-size: var(--fs-xs);
          color: var(--text-secondary); }
.u-chip--on { border-color: var(--accent); color: var(--accent);
              background: var(--accent-soft); }
```

### 眉标与分节标题

```html
<div class="u-kicker">
  <span class="u-kicker__no">NO. 07</span>   <!-- 吃 --mark 模块色 -->
  <span class="u-kicker__rule"></span>       <!-- 26px 短横线 -->
  <span>知识图谱总结</span>
</div>

<header class="u-sec-title">
  <span class="u-sec-title__no">03</span>    <!-- 吃 --mark -->
  <h3>总结流程图</h3>
  <span class="u-sec-title__note">说明文字</span>
  <span class="u-sec-title__fill"></span>    <!-- 发丝线 -->
  <span class="u-sec-title__actions">…</span>
</header>
```

发丝线用**显式元素**不用 `::after`（右侧有操作时，线要停在操作之前）。

## 五、模块标识色（`--mark`）

每个页面一个标识色，只出现在四处：导航当前页 2px 下划线、页面标题前 7px 菱形、
眉标栏号、分节栏号。

| 模块 | 色 |
|---|---|
| 知识图谱 / 个人主页 / 函数图像 | 青 `#0C6B84` |
| 知识工作台 / 背景 CSS / 界面设计 | 紫 `#7C3AED` |
| 知识库 | 琥珀 `#A34A08` |
| 图谱总结 | 朱砂 `#b8362a` |
| 后台管理 | 墨（不给色相） |

## 六、画布（图谱主体）

- 背景：28px 细网格 + 暗色专属暗角，**不要彩色光斑、不要极光漂移**
- 节点 hover：`stroke-width: 2` + 同色 `brightness(1.18)`，禁止 drop-shadow
- 标签 12px 起

## 七、可达性

- 正文对比度 ≥ 4.5:1，大字 ≥ 3:1
- 焦点环 `:focus-visible` 2px 品牌色 + 2px offset（仅键盘导航出现）
- 状态**不单靠颜色**传达：额外用内描边或 3px 左侧色条
- `@media (prefers-reduced-motion: reduce)` 关闭全部动画

## 八、禁忌清单（违反即不合格）

| 不要 | 原因 |
|---|---|
| 自己另写 `.my-card` / `.xx-btn` | 全站已有唯一实现，复用原语 |
| 给按钮、卡片、输入框换色做个性 | 容器变 = 功能语义变 |
| 用 `drop-shadow` 做 hover / 选中 | 静止发光 = 装饰 |
| 给按钮加 `translateY` 悬浮 | 满屏都在动；位移只给卡片 |
| 一屏两个以上实心按钮 | 没有焦点 |
| 引入 4 / 8 / 12 圆角 | 中间值说不出理由 |
| 用 `::after` 画分节发丝线 | 会跑到右侧按钮的空白里 |
| 拿朱砂当交互色 | 与危险色同属红区，语义会失效 |
| 紫色用在按钮 / 滑块 / 选中态 | 紫是数据语义，不是交互色 |

## 九、页面骨架

```
┌ 顶部导航（52px）：印章 + 页签（当前页 2px 下划线）
├ 左面板（288px）：文件 / 控制 / 分析
├ 主区：图谱画布 或 内容视图（h2 前有 7px 菱形）
└ 右侧抽屉 / 弹窗（圆角 14px）
```

视图根容器背景**透明**（卡片才用半透明面），否则素材背景会被整块盖住。
