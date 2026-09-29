# GraphRAG 官方基准测试语料

> 来源：`microsoft/graphrag-benchmarking-datasets`（GitHub 官方，2025-02 发布）
> 用途：本系统（知识图谱笔记）的上传 / 切割 / 跨文件语义关联 / 图谱渲染 / 问答验证测试语料
> 下载日期：2026-09-29

## 目录内容

| 数据 | 文件数 | 内容 | 适合测试什么 |
|---|---|---|---|
| `HotPotQA Filtered Input Text/` | 5491 | 英文百科段落（人名/事件/电影等实体描述） | 批量上传、跨文件语义关联（同名实体多文档）、大图渲染压力 |
| `MSFT Input Text/` | 41 | 微软历年财报电话会转录（FY14Q4~FY24Q4） | 长文档切割（每篇数万字）、时间序列关联 |
| `Kevin Scott Podcast Transcripts Input Text/` | 12 | 播客访谈转录（从 1669 个分片中保留的均匀抽样） | 短文档关联、口语化文本解析 |

配套问题 CSV（`*Questions.csv`）：每行是"问题 + 答案 + 依据文档 id"，可用来**验证图谱检索/问答链路**：
- `HotPotQA Filtered Questions.csv` — 多文档跳跃问答（需跨 2+ 文档推理）
- `MSFT Multi/Single Transcript Questions.csv` — 财报问答
- `Kevin Scott Questions.csv` — 播客问答

## 使用建议

1. **批量上传压力测试**：选 `MSFT Input Text/txt/TranscriptFY24Q4.txt`（约数万字）→ 验证大文件切割（SPLIT_TARGET_LINES=6000）与分片追溯
2. **跨文件关联验证**：`HotPotQA` 中同一人物出现在多个文档 → 上传 5~10 篇后检查图谱是否出现跨文件连线、有无孤立节点（应为 0）
3. **渲染压力**：一次性上传 100+ 篇 HotPotQA 文档 → 验证 D3 力导向图 >800 节点时的 alphaDecay 防卡顿与分片渲染
4. **问答验证**：取 `HotPotQA Filtered Questions.csv` 前 10 行，检查系统能否借助图谱定位到答案所在文档

## 注意

- HotPotQA 为英文文本；MSFT 转录含大量数字（金额/日期），可顺带验证知识点判定中的"数字类断言"
- 原始压缩包在 `microsoft/graphrag-benchmarking-datasets` 仓库 `data/` 目录，其中 `HotPotQA Filtered Input Text.zip` 实际为 **gzip 压缩的 tar**（GitHub 显示 .zip 但魔数为 1F 8B 08），解压时需用 gzip/tar 而非 zipfile
