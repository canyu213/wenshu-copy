# 文枢 · ChatGPT Adapter

这是 `ekstasisSH/wenshu` v1.1.3 的 ChatGPT 适配层，目标不是重写文枢算法，而是把其执行模型从“本地 Agent + Bash + `.env`”改为“ChatGPT Skills + 会话文件 + 已连接数据源 + Web + 可选 Python 沙箱”。

## 核心变化

- 明确需求直接执行，不再强制五选一菜单。
- 当前对话文件和用户指定连接源优先，不重复索取本地路径。
- 普通检索问答不要求先配置 DeepSeek / Embedding / LightRAG。
- 长期 API key 不作为聊天配置步骤；`.env` 不是默认启动条件。
- Python 脚本保留为确定性处理器：整书拆分、批量锚点、稳定引文排版、全库质检、反链和快照等场景使用。
- 临时会话路径与持久化目标分离；写入 GitHub/Drive 等目标需用户明确要求或批准。
- ChatGPT 聊天引用使用实际文件/网页证据；生成 Obsidian 产物时继续保留 `[[文件#^blockID]]`。

## 版本

- Adapter: `1.2.3-chatgpt`
- Upstream baseline: `ekstasisSH/wenshu@e58159abd5ca980928f5806dc81c16bfd271c8bb`

## 目录

- `SKILL.md`：ChatGPT Skill 入口与全局规则。
- `workflows/`：六个业务工作流 + ChatGPT 执行总纲。
- `references/`：原版规范 + ChatGPT 脚本处理原则 + 模型路由。
- `scripts/`：原版确定性 Python 工具；仅在批量、整书、可重复校验或高级索引场景使用。

## 测试入口

推荐用以下场景验收：

1. `@wenshu 帮我整理我刚上传的这篇 PDF` —— 不应再次询问本地路径。
2. `@wenshu 核验并格式化这条不完整参考文献` —— 应先核验后排版。
3. `@wenshu 在我上传的这些文献里回答……` —— 不应要求先配 Embedding key。
4. `@wenshu 把这本整书 PDF 按篇拆分并生成稳定锚点` —— 应切换到阶段化/确定性路径。
5. `@wenshu 把结果保存到 GitHub` —— 应先读取目标仓库现状，再执行持久化写入。
