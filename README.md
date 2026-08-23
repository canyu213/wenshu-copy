# 文枢 · Wenshu

面向人文社科研究的 AI 知识处理工作流（skill 体系），运行于 CodeBuddy / WorkBuddy 等国产 agent 工具。

> 让 AI 替你打工，让人文社科生早点收工。

> **English**: Wenshu (文枢) is an AI knowledge-processing workflow for humanities & social sciences, running inside CodeBuddy / WorkBuddy. It turns literature management, citation formatting, and theoretical lineage mapping into executable workflows with traceable sources. Local-first, MIT licensed.

## 这是什么

把"整理文献、查资料、引文格式、梳理理论脉络、组织论证"这些科研苦力活，做成可执行的工作流。输入文献与需求，输出**可溯源**的知识处理结果。

面向人文社科研究生、高年级本科生，以及有文献管理需求的教师和科研人员。

## 实证验证

以《毛泽东选集》第1-4卷（1991年版，公版文献）为样本完成全量实证：

- 输入：1559 页 PDF
- 产出：137 篇、93.5 万字、1402 个段落级锚点
- 检索问答 5 问全过，证据完整率 100%

回答带页码锚点，可回原文核对，引文不编造。

完整实测记录见 [docs/实证报告_毛选全流程_20260819.md](docs/实证报告_毛选全流程_20260819.md)（含 5 问检索问答原始输出与图谱抽核记录）。

## 方法论

- [段落锚点与可溯源引文](docs/方法论01_段落锚点与可溯源引文_20260819.md)——为什么段落级锚点能保证引文不编造
- [理论谱系与轻量检索](docs/方法论02_理论谱系与轻量检索_20260819.md)——为什么是来源/发展/争论三类关系，为什么不用重型向量库

## 快速开始

1. 克隆开源仓库 ekstasisSH/wenshu 到 agent 工具的 skills 目录
2. 读取开源仓库 docs/ 目录的对接指南（AI 接入必读）
3. 对话触发：`帮我把这篇文献入库` / `格式化这个引文` / `梳理某某概念的谱系`

部分功能需要 API key。不配置的影响：

| 功能 | 需要 key？ | 不配置的表现 |
|---|---|---|
| 文献导入（提取/切分/锚点/质量门） | 否 | 正常可用 |
| 引文格式化（GB/T 7714 + BibTeX） | 否 | 正常可用 |
| 检索问答（向量召回 + 图谱增强） | Embedding | 不可用 |
| 入库摘要（实体/关系） | LLM | 跳过摘要，锚点与检索不受影响 |

先用不需要 key 的功能，确认价值后再配置：`.env` 中设置 LLM（DeepSeek）+ Embedding（硅基流动 bge-m3），
智能体会按 `workflows/执行规范.md` 引导完成。

## 目录结构

```
wenshu/
├── SKILL.md                # 入口：文枢工作流全局规则
├── docs/对接指南.md         # AI 接入必读
├── workflows/              # 6 个工作流
│   ├── 文献导入.md
│   ├── 段落标注.md
│   ├── 引文格式化.md
│   ├── 谱系图谱.md
│   ├── 论证链.md
│   └── 检索问答.md
├── references/             # 6 份规范
│   ├── 元数据方案.md
│   ├── 知识组织规范.md
│   ├── 段落锚点规范.md
│   ├── 引文规范.md
│   ├── 入库规范.md
│   └── 领域适配指南.md
├── scripts/                # 确定性工具（format_reference.py / anchor_injector.py / skill_rag.py）
└── README.md
```

## 能力

| 能力 | 说明 |
|---|---|
| 文献导入 | PDF/EPUB/DOCX 入库，全文提取 + 元数据 + 链接注入 |
| 段落标注 | 段落级 Block ID 锚点，支持精准引用与溯源 |
| 引文格式化 | 核验 + 排版为 GB/T 7714-2025 引文 + BibTeX |
| 谱系图谱 | 来源/发展/争论关系组织为可检索图谱 |
| 论证链 | 图尔敏模型论点-证据链标注与组织 |
| 检索问答 | 向量召回 + 图谱增强 + 锚点溯源（模式 D，自研 RAG） |

## 技术底座

- **LLM**：API 链接模型（DeepSeek / 硅基流动 / OpenAI 兼容）
- **检索/图谱**：skill_rag.py（文枢自研模式 D：embedding API + numpy 本地余弦 + 图谱增强；LightRAG 为对照参考）
- **格式化**：format_reference.py（复用 chinese-reference-formatter-skill，Zechang-Xiong，MIT，见 scripts/LICENSE-format_reference.txt）
- **段落标注**：anchor_injector.py（文枢自研：段落切分 + Block ID 注入 + 校验）
- **检索问答**：skill_rag.py（向量索引 + 谱系图谱 + 锚点溯源问答）
- **输入**：本地 PDF/EPUB/DOCX（单篇或整本专著），入库生成可检索知识库

## 交互演示

[concept-galaxy 交互演示](https://ekstasissh.github.io/wenshu-concept-galaxy/)：以《毛泽东选集》第1-4卷（1991年版）为样本，把知识运行时（概念谱系、来源/发展/争论关系）具象化为可交互 3D 模型。

## 数据与复现

文枢**不附带任何文献全文与衍生数据**（版权合规）。数据产物（全文提取、向量索引、图谱数据）默认不入库，按以下路径自行复现：

1. 自备源文献 PDF（如《毛泽东选集》第1-4卷 1991 年版，图书馆/正版渠道获取）
2. 跑通流水线：`scripts/pdf_extract.py` 提取全文 → `scripts/split_works.py` 按篇切分 → `scripts/anchor_injector.py` 段落锚点注入 → `scripts/kb_builder.py` + `scripts/kb_index.py` 构建向量索引
3. 检索问答：`scripts/skill_rag.py`（向量召回 + 图谱增强 + 锚点溯源）

## 合规承诺

AI 辅助非代写；引文可溯源、不编造；遵守学术诚信。

## 许可证

MIT

## 版本

v1.0.7（2026-08-22）：表述修正——数据源改为实际输入方式（本地 PDF/EPUB/DOCX），清除 Zotero/Obsidian 误导性表述

v1.0.6（2026-08-22）：平台展示适配——SKILL.md 人读区纯文本化（去 markdown 符号）、人味化重写、简介栏文案备好

v1.0.5（2026-08-22）：平台展示适配——name=wenshu（显示名）+ skill_identifier 固定 ID、简介段前置、人读区去表格化、删文档树代码块

v1.0.4（2026-08-22）：SKILL.md 人读化架构——智能体执行指令下放 workflows/执行规范.md，平台介绍页仅呈现人读部分

v1.0.3（2026-08-22）：文档读者分层重构——阅读指南 + 人读区去 AI 痕迹 + 智能体执行区效率化 + 配置影响矩阵

v1.0.2（2026-08-22）：toc_parse 目录解析增强——教材体例（单页码目录/罗马数字/章标题扫描/页眉过滤/标题匹配合并）、纲要体例（导言前缀/章号容忍/正文句过滤/截断标题补全）、专著适配（OCR 变体归并/去重保留最早页/目录行尾章号前移）、回归测试 24 用例

v1.0.1（2026-08-22）：平台适配增强——入口路由场景化（AskUserQuestion + 触发词降级）、工作流速览、快速开始、文档导航、完成提示、执行质检清单、名字由来叙事段

v1.0.0（2026-08-22）：功能完整首发——六段流水线（提取→目录解析→偏移检测→分篇切分→知识库→质量门）、EPUB 支持、单篇自动路径、双实证（毛选 1559 页 + 3 篇异构文献全绿）、开源双仓、SkillHub 公开发布

v0.1.5（2026-08-19）：新增 docs/方法论02_理论谱系与轻量检索_20260819.md（能力二"理论谱系"原理：三类关系/模式 D 轻量检索/图谱增强）——方法论系列三份齐

v0.1.4（2026-08-19）：新增 docs/方法论01_段落锚点与可溯源引文_20260819.md（能力一"可溯源"原理：锚点设计/溯源链路/引文核验）

v0.1.3（2026-08-19）：新增 docs/实证报告_毛选全流程_20260819.md（入库/检索问答/谱系图谱全链路实证，含 5 问重跑记录）

v0.1.2（2026-08-19）：README 补充实证验证数据（1559 页 → 137 篇 → 1402 锚点）与用户定位

v0.1.1（2026-08-19）：自研 skill_rag.py 转正（LightRAG 降为对照参考）；slogan 更新；毛选全量复现与 galaxy 演示上线

v0.1.0（2026-08-16）：references/ + workflows/ 产出，skill 骨架搭建
