---
name: wenshu
description: Use when the user needs humanities or social-science literature processing, traceable source verification, document ingestion, paragraph anchors, GB/T 7714 references, theory genealogy, argument-evidence organization, or grounded knowledge-base Q&A.
license: MIT
metadata:
  version: "1.2.3-chatgpt"
  upstream: "ekstasisSH/wenshu@e58159abd5ca980928f5806dc81c16bfd271c8bb"
---

# 文枢 · ChatGPT Adapter

文枢用于人文社科知识处理。核心原则：**语义判断交给模型，可机械验证的环节交给确定性规则；所有重要结论都保留来源边界。**

## 路由

用户意图明确时直接执行，不先弹功能菜单：

| 意图 | 读取 |
|---|---|
| 导入、整理 PDF/EPUB/DOCX/Markdown | `workflows/文献导入.md` |
| 段落锚点、Block ID、可引用切分 | `workflows/段落标注.md` |
| 核验/格式化参考文献、BibTeX | `workflows/引文格式化.md` |
| 理论脉络、概念来源/发展/争论 | `workflows/谱系图谱.md` |
| 论点、证据、反驳、论证结构 | `workflows/论证链.md` |
| 对用户文献库检索、问答、综述证据 | `workflows/检索问答.md` |

始终先读 `workflows/执行规范.md`。涉及批量、整书、锚点、全库质检或可重复格式化时，再读 `references/脚本处理原则.md`。涉及多阶段任务、复杂推理、最终验收或用户询问模型分配时，读取 `references/model-routing.md`。

## 模型路由摘要

- **Luna Max**：默认执行；包括常规任务，以及谱系图谱、论证链、跨文献问答的第一轮分析。
- **Sol Medium**：生成阶段仅作为升级路径；只有 Luna Max 或确定性脚本仍无法可靠消解高歧义来源冲突、多文献多跳关系、复杂 OCR/目录冲突、困难引文消歧时才使用。
- **Sol Medium 最终独立 review / 验收**：最终结果必须经过一次单独的 Sol review pass；若 Sol 前面参与过生成，也必须重新独立审查，不能把生成结论直接当作验收结论。
- 单步骤超过 180 分钟不得静默换模；先保留上下文并取得用户明确批准。完整规则见 `references/model-routing.md`。

## ChatGPT 原生优先级

1. 当前对话中已提供的文件或内容。
2. 用户明确指向的已连接数据源或文件库。
3. 公共、可核验的网页来源。
4. 仅当任务需要批量性、确定性、可重复验证或大文件阶段化处理时，使用 Python 脚本/沙箱路径。

不要要求用户重复提供当前对话里已经存在的文件、路径或信息。

## 证据契约

- 不凭题名猜作者、年份、页码、DOI、ISBN、出版信息或理论关系。
- 元数据冲突无法消解时标记“有歧义”；找不到时标记“未找到/待查”。
- 文献内部证据优先使用 ChatGPT 原生文件引用；生成 Obsidian 知识库时同时保留 `[[文件#^blockID]]`。
- 理论谱系中的来源、发展、争论关系必须有原文或可靠来源支撑。
- 论证链只抽取、组织和标注已有论证；研究假设、核心论点和最终结论由用户决定。

## 写入纪律

- 临时处理可在会话工作区完成；临时路径不是永久存储。
- 用户未指定持久化位置时，把最终产物作为会话结果/附件返回。
- 只有用户明确要求或已批准时，才写入 GitHub、Drive、Notion 等持久化目标。
- 批量改变知识库前先生成预览或 dry-run 结果；验证通过后再执行实际写入。

## 密钥与外部模型

默认工作流不得要求用户在聊天中粘贴长期 API key，也不得把 `.env` 当作启动前提。若某个可选脚本确实需要外部 Embedding/LLM 服务，先尝试 ChatGPT 原生路径；只有用户明确选择高级外部索引模式时才说明其额外依赖。
