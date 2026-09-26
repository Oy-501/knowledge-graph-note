# 素材来源与许可（Assets Credits）

本目录下的视觉素材**全部来自互联网公开图库**，不是自己画的占位图。
每条都标注了来源、作者与许可证；如许可证要求署名，署名信息在下表。

> 说明：本项目为毕设交付版，本地内嵌全部素材（不依赖 CDN），
> 因此必须保证「可再分发」。下方每个许可证都允许再分发。

---

## 一、纹理图案 · `textures/*.svg`（24 个）

| 项 | 内容 |
|---|---|
| 来源 | [Hero Patterns](https://heropatterns.com/) |
| 作者 | Steve Schoger |
| 许可证 | **CC BY 4.0**（允许商用与再分发，**要求署名**） |
| 署名写法 | Patterns from [Hero Patterns](https://heropatterns.com/) by Steve Schoger, licensed under CC BY 4.0 |
| 获取方式 | 从站点 `js/app.js` 的 pattern 数据中提取原始 SVG，脚本见项目 `.tmp-assets/extract_patterns.py` |
| 本项目的处理 | 把 SVG 内硬编码的 `fill="#000"` / `stroke="#000"` 统一改为 `currentColor`，使同一文件可被 CSS 染成任意主题色；tile 尺寸（`width`/`height`）保持原值不动，否则平铺节奏会错。 |

用到的 24 个：`circuit-board` `topography` `graph-paper` `bathroom-floor` `signal`
`connections` `current` `rails` `boxes` `plus` `rounded-plus-connected` `pixel-dots`
`polka-dots` `death-star` `heavy-rain` `diagonal-stripes` `tiny-checkers` `steel-beams`
`morphing-diamonds` `texture` `endless-clouds` `bamboo` `fancy-rectangles` `overlapping-circles`

---

## 二、摄影背景 · `backdrops/*.webp`（14 张）

| 项 | 内容 |
|---|---|
| 来源 | [Unsplash](https://unsplash.com/) |
| 许可证 | **Unsplash License**（可免费用于商业与非商业用途，**不要求署名**） |
| 获取方式 | 按主题检索 → 经 `unsplash.com/photos/<slug>/download` 解析到 `images.unsplash.com` 直链 → 以 `w=1600/1920 & q=72/80 & fm=webp` 由 Unsplash 端转码下载，脚本见 `.tmp-assets/download_backdrops.py` |
| 本项目的处理 | 仅做尺寸与格式优化（WebP），未裁剪内容、未调色。 |

| 文件 | 主题 | 说明 |
|---|---|---|
| `mesh-aurora.webp` | 抽象光影 | 层叠暗色鳍状结构 |
| `mesh-flow.webp` | 抽象光影 | 暗色绸缎曲面 |
| `mesh-dusk.webp` | 抽象光影 | 蓝色冷光切面（深色科技主背景候选） |
| `mesh-tide.webp` | 抽象光影 | 曲面壳体 |
| `mesh-ember.webp` | 抽象光影 | 竖向鳍片 + 暖色边缘光 |
| `mesh-violet.webp` | 抽象光影 | 暗紫花瓣形体 |
| `tech-matrix.webp` | 数字科技 | 机柜与线缆 |
| `tech-board.webp` | 数字科技 | 电路板微距 |
| `tech-datastream.webp` | 数字科技 | 数据流编码意象 |
| `arch-lines.webp` | 数字科技 | 网络交换设备与网线 |
| `space-nebula.webp` | 星空宇宙 | 深空星野 |
| `space-earth.webp` | 星空宇宙 | 轨道视角夜空地球 |
| `mat-marble.webp` | 暗色材质 | 斜向罗纹暗面 |
| `mat-ink.webp` | 暗色材质 | 暗底鎏金流线 |

作者信息见 `backdrops/manifest.json` 的 `author` 与 `source` 字段。

**已剔除**（下载后看图发现与主题不符，未入库）：
`tech-circuit.webp`（实为公园长椅上的机器人）、`city-night.webp`（白天天际线，过亮）。

---

## 三、程序化生成资产 · `src/styles/texture.css` 内的内联 SVG

以下不是下载素材，而是为补齐「平铺无色偏的噪声与光晕」而生成的，在此如实说明：

| 资产 | 用途 | 生成方式 |
|---|---|---|
| 胶片颗粒噪声 | 叠在照片与纯色上，消除渐变色带（banding） | SVG `feTurbulence` + `feColorMatrix`，data-URI 内联 |
| 光晕 / 极光团 | 大面积氛围光 | CSS `radial-gradient`（无需外部文件） |

之所以照片之外还要噪声层：屏幕上的大面积暗色渐变在 8bit 色深下必然出色带，
叠一层 3~6% 不透明度的颗粒是最省成本且效果最稳的解法。

---

## 四、许可证合规小结

| 用途 | 是否允许 | 依据 |
|---|---|---|
| 毕设演示 / 答辩 | ✅ | 两个许可证均允许 |
| 商业使用 | ✅ | Unsplash 允许；CC BY 4.0 允许（需署名） |
| 代码仓库公开 | ✅ | 均允许再分发 |
| 必须做的事 | **保留本 CREDITS.md，并在产品「关于」处可见 Hero Patterns 署名** | CC BY 4.0 的署名条款 |

`texture.css` 顶部与「个人主页 → 关于素材」已放置署名文案。
