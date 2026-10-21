0 [&>*:last-child]:mb-0">
三栏应用布局已完成落地，全部源码位于 /workspace/knowledge-graph-notes.vue。
实际修改路径
入口与配置：src/main.ts（注册静态路由）、src/router/routes.ts（8 条静态路由，/ 直接渲染知识图谱）、config.json（8 条 routes、10 个 components）
设计令牌：src/styles/tokens.css（亮/暗双主题、六档字号、6/10/14 圆角、30px 控件、--ease/--dur 缓动），并桥接到 src/framework/theme.css 的 --app-* 变量
壳与共享原语：src/App.vue、components/AppTopbar.vue、AppNav.vue、AppDrawer.vue、AppPalette.vue、PageHeader.vue、SectionLabel.vue、ScoreBars.vue、UIcon.vue
图谱视图：components/GraphToolPanel.vue、GraphCanvas.vue、views/GraphView.vue
其余视图：WorkbenchView / LibraryView / SummaryView / FunctionView / BackgroundCssView / ProfileView / AdminView
静态模拟数据：src/data/mock.ts
对照验收
顶栏 48px 只保留产品名、搜索框（占位「搜索节点/文件/操作… ⌘K」）、新建主按钮、主题切换、头像，8 个视图 tab 与 kbd 角标已全部移除。
左导航 240px，顶部为「当前视图名 + 折叠按钮」，8 个 36px 导航项，选中态为左 3px 主色竖条 + --bg-hover；折叠用 transform 隐藏文字（DOM 不重排），状态写入 localStorage（kgn.navCollapsed），底部为主题切换与账号。
图谱视图 = 280px 工具面板（上传 / 四维权重 / 分析 / 回顾 / 问答按序纵向排布）+ 自适应画布（28px 细网格 + 暗角，节点 hover 用 stroke-width 2 + brightness(1.18)）；两栏间 1px 分隔线、4px 拖拽手柄，范围 180~400px，双击复位。
点击画布节点或工作台笔记右侧滑出 320px 抽屉（transition: width 0.2s ease-out，无遮罩），含标题、类型 badge、来源文件、α/β/γ/δ 条形图与关联节点；关闭按钮 / Esc / 画布空白均可收起，抽屉展开时主区域收缩。
⌘K（及 Ctrl+K）打开 560px 命令面板，按「视图 / 节点 / 文件 / 操作」分组即时过滤，↑↓ 移动、回车执行、Esc 关闭，选中项有描边焦点；操作含上传文件、强制重排、切换主题、清空画布。
8 个视图共用同一套顶栏 + 左导航 + 主内容框架，模块标识色只出现在导航下划线、标题菱形、眉标栏号、分节栏号四处，后台管理为墨色。
移动端 <768px：左导航变为底部 tab 栏，抽屉改为全屏 modal，图谱分栏改为上下堆叠。
验证状态
代码实现：已完成
远程 TypeScript 检查：check_typescript 返回「✓ No TypeScript errors found」
远程构建：第一次 build_react_project 返回「✓ Vue build succeeded」，dist/index.html 已生成；随后做了少量 CSS / transition 类名修正，第二次构建返回「Remote validation is unavailable… no HTTP request was sent」，因此最终构建状态未能远程复核，建议在预览中确认一次。
构建状态：未完成（远程构建复核阶段服务不可达；此前一次构建已成功，但早于最后的 CSS 修正）
三栏应用布局已经按《UI 设计交接包》中的 token 与组件原语实现完成，源码位于 /workspace/knowledge-graph-notes.vue。
布局落地情况
顶栏 48px：只包含产品名「知识图谱笔记」、居中的全局搜索框（占位“搜索节点/文件/操作… ⌘K”，圆角 6px，底色 --bg-hover）、新建主按钮、主题切换和账号头像。8 个视图 tab 与 kbd 角标已全部移除。
左侧导航 240px：顶部是当前视图名和折叠按钮，8 个 36px 高的导航项，选中态为左 3px 主色竖条加 --bg-hover 底色，不使用胶囊按钮；底部为主题切换和账号。折叠到 64px 用 transform 实现、不重排 DOM，状态写入 <code class="rounded bg-muted px-1.5 py-0.5 font