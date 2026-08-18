#!/usr/bin/env python3
"""S7 通用 md 知识库 → LightRAG 检索索引（v2 通用入库流程，可选环节）。

从 S5 产出的 md 知识库读取"## 正文"，按 ^v{卷}p{页码} 锚点切 chunk，
每个 chunk 内容前缀带锚点标记（[[文件路径#^v01p0282]]），供 References 溯源。
LLM 自动实体抽取建图谱（insert_custom_chunks 三阶段）。

配置：从 .env 读取 LLM（DeepSeek）/ embedding（硅基流动）/ rerank（硅基流动）。

用法（在 lightRAG 目录下用其 venv 运行）：
    kb_index.py --kb 知识库目录 --output 索引工作目录 [--limit N] [--query 测试问题]
"""
import argparse
import asyncio
import os
import pathlib
import re
import sys
from functools import partial

from dotenv import load_dotenv

# .env 加载：优先脚本同目录，其次当前工作目录（lightRAG 目录运行）
load_dotenv(pathlib.Path(__file__).resolve().parent / ".env")
load_dotenv()

from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.rerank import cohere_rerank
from lightrag.utils import EmbeddingFunc

ANCHOR_RE = re.compile(r"^\^v(\d{2})p(\d{4})$", re.M)


def parse_md(f: pathlib.Path) -> tuple[str, str, list[dict]]:
    """解析单篇 md：返回 (title, 相对路径, 锚点块列表[{anchor, content}])。"""
    text = f.read_text(encoding="utf-8")
    m = re.search(r"^title:.*$", text, re.M)
    title = m.group(0).split(":", 1)[1].strip() if m else f.stem

    # 取"## 正文"之后的部分
    idx = text.find("## 正文")
    body = text[idx:] if idx >= 0 else text

    # 按锚点切块
    blocks = []
    lines = body.split("\n")
    cur_anchor = None
    cur_lines = []
    for ln in lines:
        am = ANCHOR_RE.match(ln.strip())
        if am:
            if cur_anchor and cur_lines:
                blocks.append({"anchor": cur_anchor, "content": "\n".join(cur_lines).strip()})
            cur_anchor = ln.strip()
            cur_lines = []
        else:
            if cur_anchor is not None:
                cur_lines.append(ln)
    if cur_anchor and cur_lines:
        blocks.append({"anchor": cur_anchor, "content": "\n".join(cur_lines).strip()})

    rel = str(f.relative_to(f.parent.parent))  # 卷目录/文件名.md
    return title, rel, blocks


async def build_index(kb_dir: pathlib.Path, out_dir: str, limit: int, extra_queries: list[str]):
    llm_key = os.getenv("LLM_BINDING_API_KEY")
    llm_host = os.getenv("LLM_BINDING_HOST", "https://api.deepseek.com/v1")
    llm_model = os.getenv("LLM_MODEL", "deepseek-chat")
    emb_key = os.getenv("EMBEDDING_BINDING_API_KEY")
    emb_host = os.getenv("EMBEDDING_BINDING_HOST", "https://api.siliconflow.cn/v1")
    emb_model = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    emb_dim = int(os.getenv("EMBEDDING_DIM", "1024"))
    rk_key = os.getenv("RERANK_BINDING_API_KEY", emb_key)
    rk_host = os.getenv("RERANK_BINDING_HOST", "https://api.siliconflow.cn/v1/rerank")
    rk_model = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")

    async def llm_model_func(prompt, system_prompt=None, **kwargs):
        return await openai_complete_if_cache(
            model=llm_model, prompt=prompt, system_prompt=system_prompt,
            base_url=llm_host, api_key=llm_key, **kwargs,
        )

    rag = LightRAG(
        working_dir=out_dir,
        llm_model_func=llm_model_func,
        llm_model_max_async=4,   # 降低并发，避免 embedding worker 超时
        embedding_func_max_async=4,
        embedding_func=EmbeddingFunc(
            embedding_dim=emb_dim,
            max_token_size=8192,
            func=partial(
                openai_embed.func if hasattr(openai_embed, "func") else openai_embed,
                model=emb_model, base_url=emb_host, api_key=emb_key,
            ),
        ),
        rerank_model_func=partial(
            cohere_rerank, api_key=rk_key, model=rk_model, base_url=rk_host
        ),
    )
    await rag.initialize_storages()

    # 断点续跑：读 doc_status，跳过已 processed 的 doc
    done_set = set()
    status_path = pathlib.Path(out_dir) / "kv_store_doc_status.json"
    if status_path.exists():
        try:
            st = json.loads(status_path.read_text(encoding="utf-8"))
            for doc_key, info in st.items():
                if isinstance(info, dict) and info.get("status") == "processed":
                    done_set.add(doc_key)
        except Exception as e:
            print(f"[S7] doc_status 读取失败（忽略，全量重跑）: {e}")
    if done_set:
        print(f"[S7] 断点续跑：已跳过 {len(done_set)} 篇（processed）")

    files = sorted(kb_dir.rglob("*.md"))[:limit] if limit else sorted(kb_dir.rglob("*.md"))
    print(f"[S7] 待入库 {len(files)} 篇")
    failed_list = []

    for i, f in enumerate(files, 1):
        title, rel, blocks = parse_md(f)
        if not blocks:
            print(f"  [{i}/{len(files)}] 跳过（无锚点块）: {f.name}")
            continue
        doc_id = f"doc_{title}"
        if doc_id in done_set:
            print(f"  [{i}/{len(files)}] 已入库，跳过: {title}")
            continue
        full_text = "\n".join(b["content"] for b in blocks)
        # 每块内容前缀带锚点标记，供 References 溯源
        chunks = [
            f"[[{rel}#{b['anchor']}]]\n{b['content']}" for b in blocks
        ]
        try:
            await rag.ainsert_custom_chunks(full_text, chunks, doc_id=doc_id)
            print(f"  [{i}/{len(files)}] 已入库: {title}（{len(blocks)} 块）")
        except Exception as e:
            failed_list.append((title, str(e)[:120]))
            print(f"  [{i}/{len(files)}] ❌ 失败: {title} → {str(e)[:80]}")

    if failed_list:
        print(f"\n[S7] 失败 {len(failed_list)} 篇（可重跑续传）：")
        for t, e in failed_list:
            print(f"  {t}: {e}")
    else:
        print("\n[S7] 全部入库完成")

    # 查询验证
    print("\n[S7] 查询验证")
    for q in extra_queries:
        resp = await rag.aquery(
            q, param=QueryParam(mode="hybrid", top_k=8, enable_rerank=True)
        )
        print(f"\nQ: {q}")
        print(f"A: {resp[:300]}")
        refs = re.findall(r"\[\[([^\]]+)\]\]", resp)
        if refs:
            print(f"References: {refs[:5]}")


def main():
    ap = argparse.ArgumentParser(description="S7 md 知识库 → LightRAG 索引")
    ap.add_argument("--kb", required=True, help="md 知识库目录")
    ap.add_argument("--output", required=True, help="LightRAG 工作目录")
    ap.add_argument("--limit", type=int, default=0, help="只入库前 N 篇（0=全量）")
    ap.add_argument("--query", action="append", default=[], help="测试问题（可多次）")
    args = ap.parse_args()

    kb_dir = pathlib.Path(args.kb)
    if not kb_dir.is_dir():
        print(f"[ERROR] 知识库目录不存在: {kb_dir}")
        return 1

    if not args.query:
        args.query = ["实践论的核心观点是什么"]

    asyncio.run(build_index(kb_dir, args.output, args.limit, args.query))
    return 0


if __name__ == "__main__":
    sys.exit(main())
