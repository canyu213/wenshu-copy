# 文枢 · Wenshu

面向人文社科研究的 AI 知识处理工作流（skill 体系），运行于 CodeBuddy / WorkBuddy 等国产 agent 工具。

> 让 AI 替你打工，让人文社科生早点下班。

> **English**: Wenshu (文枢) is an AI knowledge-processing workflow for humanities & social sciences, running inside CodeBuddy / WorkBuddy. It turns literature management, citation formatting, and theoretical lineage mapping into executable workflows with traceable sources. Local-first, MIT licensed.

## 这是什么

把"整理文献、查资料、引文格式、梳理理论脉络、组织论证"这些科研苦力活，做成可执行的工作流。输入文献与需求，输出**可溯源**的知识处理结果。

## 快速开始

1. 克隆本仓库到 agent 工具的 skills 目录（`git clone https://github.com/ekstasisSH/wenshu`）
2. 配置 API：`.env` 中设置 LLM（DeepSeek 等）+ Embedding（硅基流动 bge-m3）
3. 读取 `docs/对接指南.md`（AI 接入必读）
4. 对话触发：`帮我把这篇文献入库` / `格式化这个引文` / `梳理某某概念的谱系`

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
- **格式化**：format_reference.py（MIT 复用）
- **段落标注**：anchor_injector.py（文枢自研：段落切分 + Block ID 注入 + 校验）
- **检索问答**：skill_rag.py（向量索引 + 谱系图谱 + 锚点溯源问答）
- **数据源**：Zotero / Obsidian

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

v0.1.0（2026-08-16）：references/ + workflows/ 产出，skill 骨架搭建
