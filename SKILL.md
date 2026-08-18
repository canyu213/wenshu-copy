---
name: wenshu
description: 文枢——面向人文社科研究的 AI 知识处理工作流。Use when the user needs 文献导入、段落标注、引文格式化、谱系图谱、论证链等人文社科知识处理能力。运行于 CodeBuddy / WorkBuddy 等国产 agent 工具。
license: MIT
metadata:
  author: ekstasisSH
  version: "0.1.0"
  repository: https://github.com/ekstasisSH/wenshu
  tags: humanities, knowledge-base, citation, rag, academic-writing
---

# 文枢 · 人文社科知识处理工作流

## Overview

文枢把"整理文献、查资料、引文格式、梳理理论脉络"这些科研苦力活，做成一包能直接运行在 agent 工具（CodeBuddy / WorkBuddy）里的工作流。输入文献与需求，输出可溯源的知识处理结果。

**核心承诺**：让 AI 替你打工，让人文社科生早点收工。**核心底线**：AI 辅助非代写，引文可溯源，不编造。

## 能力清单

| 工作流 | 文件 | 做什么 |
|---|---|---|
| 文献导入 | `workflows/文献导入.md` | PDF/EPUB/DOCX 入库，全文提取 + 元数据 + 链接注入 |
| 段落标注 | `workflows/段落标注.md` | 段落级 Block ID 锚点，支持精准引用 |
| 引文格式化 | `workflows/引文格式化.md` | 核验 + 排版为 GB/T 7714-2025 引文 + BibTeX |
| 谱系图谱 | `workflows/谱系图谱.md` | 来源/发展/争论关系组织为可检索图谱 |
| 论证链 | `workflows/论证链.md` | 图尔敏模型论点-证据链标注与组织 |
| 检索问答 | `workflows/检索问答.md` | 向量召回 + 图谱增强 + 锚点溯源（模式 D，自研 RAG） |

## 工作流入口

按用户需求路由到对应工作流：

```
文献入库需求 → workflows/文献导入.md
引文/参考文献需求 → workflows/引文格式化.md
概念/理论脉络梳理 → workflows/谱系图谱.md
论证/证据组织需求 → workflows/论证链.md
知识库检索/问答需求 → workflows/检索问答.md
（入库时自动执行段落标注，无需单独触发）
```

## 规范引用

执行任何工作流前，读取对应 references/ 规范：

| 规范 | 文件 | 适用工作流 |
|---|---|---|
| 元数据方案 | `references/元数据方案.md` | 全部 |
| 知识组织规范 | `references/知识组织规范.md` | 文献导入、谱系图谱 |
| 段落锚点规范 | `references/段落锚点规范.md` | 段落标注、引文格式化 |
| 引文规范 | `references/引文规范.md` | 引文格式化 |
| 入库规范 | `references/入库规范.md` | 文献导入 |
| 领域适配指南 | `references/领域适配指南.md` | 新领域库搭建 |

## 技术底座

- **LLM**：API 链接模型（DeepSeek / 硅基流动 / 其他 OpenAI 兼容），智能体负责编排
- **检索/图谱**：skill_rag.py（文枢自研模式 D：embedding API + numpy 本地余弦 + 图谱增强；LightRAG 为对照参考）
- **格式化**：format_reference.py（MIT 复用，确定性排版）
- **段落标注**：anchor_injector.py（文枢自研，段落切分 + Block ID 注入 + 校验）
- **检索问答**：skill_rag.py（向量索引 + 谱系图谱 + 锚点溯源问答）
- **数据源**：Zotero（文献管理）/ Obsidian（笔记）

## 合规红线（不可妥协）

1. **AI 辅助非代写**：AI 做检索、润色、格式、初稿框架；不代写研究假设、核心论点、结论
2. **引文可溯源**：所有引用必须核验 + 可回溯原文；无页码标"待查"，禁止编造
3. **不编造**：查不到的文献/字段/关系如实报告"未找到/待考证"
4. **单一事实源**：不从多份文件复制同一字段值；`cited_by` 等反链由脚本维护，不手改

## 文档结构

```
wenshu/
├── SKILL.md                    ← 本文件（入口）
├── docs/对接指南.md             ← AI 接入必读
├── workflows/                  ← 6 个工作流
├── references/                 ← 6 份规范
├── scripts/                    ← 确定性工具（format_reference.py / anchor_injector.py / skill_rag.py）
└── README.md                   ← 项目说明
```

## 版本记录

- v0.1.0（2026-08-16）：references/ + workflows/ 产出，skill 骨架搭建
- v0.1.1（2026-08-19）：自研 skill_rag.py 转正（LightRAG 降为对照参考）；slogan 更新；毛选全量复现与 galaxy 演示上线
