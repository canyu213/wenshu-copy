#!/usr/bin/env python3
"""文枢检索问答工具（skill_rag.py）——模式 D：skill 原生 RAG。

不依赖 LightRAG 等外部框架。自研轻量版：
  向量层：锚点块 → embedding API → vectors.npy（numpy 本地余弦检索）
  图谱层：DeepSeek 逐篇抽取实体/关系 → concept_graph.json（独立产物）
  问答层：向量召回 + 图谱增强上下文 → DeepSeek 组织回答（锚点溯源）

用法（在配置了 .env 的目录下运行：LLM_BINDING_* + EMBEDDING_BINDING_*）：
  python skill_rag.py --build --kb 知识库目录 --out 索引目录 [--titles 篇1,篇2]
  python skill_rag.py --graph-build --kb ... --out ... [--titles 篇1,篇2]
  python skill_rag.py --query "问题" --kb ... --out ... [--top-k 8]

产物：
  out/vectors.npy + chunks_meta.json    ← 向量索引
  out/concept_graph.json                ← 谱系图谱（独立产物，可增量）
"""
import argparse
import json
import os
import pathlib
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).resolve().parent / ".env")
load_dotenv(pathlib.Path.cwd() / ".env")  # 显式加载运行目录（cwd）的 .env

# ---------- 配置（从 .env） ----------
LLM_KEY = os.getenv("LLM_BINDING_API_KEY")
LLM_HOST = os.getenv("LLM_BINDING_HOST", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
EMB_KEY = os.getenv("EMBEDDING_BINDING_API_KEY")
EMB_HOST = os.getenv("EMBEDDING_BINDING_HOST", "https://api.siliconflow.cn/v1")
EMB_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMB_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))

ANCHOR_RE = re.compile(r"^\^v(\d{2})p(\d{4})$", re.M)
EMB_BATCH = 16   # 每批向量化文本数
EMB_CONC = 8     # 并发批数


# ---------- embedding API ----------
def embed_texts(texts: list[str]) -> list[list[float]]:
    url = f"{EMB_HOST}/embeddings"
    req = urllib.request.Request(
        url,
        data=json.dumps({"model": EMB_MODEL, "input": texts}).encode(),
        headers={"Authorization": f"Bearer {EMB_KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        raise RuntimeError(
            f"embedding 调用失败 url={url} model={EMB_MODEL} "
            f"key={'set' if EMB_KEY else 'EMPTY'} err={e}"
        ) from e
    out = [None] * len(texts)
    for item in data["data"]:
        out[item["index"]] = item["embedding"]
    return out


def embed_batch_with_retry(texts: list[str], retries: int = 3) -> list[list[float]]:
    for i in range(retries):
        try:
            return embed_texts(texts)
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))


# ---------- LLM API ----------
def llm_chat(prompt: str, max_tokens: int = 1200) -> str:
    req = urllib.request.Request(
        f"{LLM_HOST}/chat/completions",
        data=json.dumps({
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }).encode(),
        headers={"Authorization": f"Bearer {LLM_KEY}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]


# ---------- 索引构建 ----------
def parse_md(f: pathlib.Path) -> tuple[str, str, list[dict]]:
    """解析单篇 md：返回 (title, 相对路径, 锚点块列表)。"""
    text = f.read_text(encoding="utf-8")
    m = re.search(r"^title:.*$", text, re.M)
    title = m.group(0).split(":", 1)[1].strip() if m else f.stem
    idx = text.find("## 正文")
    body = text[idx:] if idx >= 0 else text

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
        elif cur_anchor is not None:
            cur_lines.append(ln)
    if cur_anchor and cur_lines:
        blocks.append({"anchor": cur_anchor, "content": "\n".join(cur_lines).strip()})

    rel = str(f.relative_to(f.parent.parent))
    return title, rel, blocks


def split_long_block(content: str, max_len: int = 900) -> list[str]:
    """大块自动分段（chunks 粒度均衡）：超长段按句边界拆分，避免单篇命中偏斜。

    外二篇 203 段场景：单块 >max_len 时按「。！？；」句边界切成 ≤max_len 的块。
    不改变锚点（同 anchor 多块），只影响检索粒度。
    """
    if len(content) <= max_len:
        return [content]
    parts = []
    buf = ""
    for seg in re.split(r"(?<=[。！？；])", content):
        buf += seg
        if len(buf) >= max_len:
            parts.append(buf)
            buf = ""
    if buf:
        parts.append(buf)
    if len(parts) == 1:
        # 无句号兜底：按固定长度硬切
        parts = [content[i:i + max_len] for i in range(0, len(content), max_len)]
    return parts or [content[:max_len]]


def build_index(kb_dir: pathlib.Path, out_dir: pathlib.Path, titles: list[str] | None = None):
    """对指定篇目构建向量索引。titles 为 None 则全量。超长块自动分段（粒度均衡）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    want = set(titles) if titles else None

    chunks = []  # {title, rel, anchor, content}
    for f in sorted(kb_dir.rglob("*.md")):
        title, rel, blocks = parse_md(f)
        if want is not None and title not in want:
            continue
        for b in blocks:
            if b["content"]:
                for piece in split_long_block(b["content"]):
                    chunks.append({"title": title, "rel": rel, "anchor": b["anchor"], "content": piece})
    print(f"[索引] 收集 {len(chunks)} 块（{len(set(c['title'] for c in chunks))} 篇，超长块已分段）")

    texts = [f"{c['content'][:800]}" for c in chunks]
    vecs = np.zeros((len(texts), EMB_DIM), dtype=np.float32)
    batches = [texts[i:i + EMB_BATCH] for i in range(0, len(texts), EMB_BATCH)]
    t0 = time.time()

    def work(bidx_batch):
        bidx, batch = bidx_batch
        return bidx, embed_batch_with_retry(batch)

    with ThreadPoolExecutor(max_workers=EMB_CONC) as ex:
        for bidx, result in ex.map(work, enumerate(batches)):
            for j, v in enumerate(result):
                vecs[bidx * EMB_BATCH + j] = v
            print(f"  [{bidx+1}/{len(batches)}] 批完成 ({len(result)} 块)")

    print(f"[索引] 向量化完成 {len(texts)} 块，耗时 {time.time()-t0:.0f}s")

    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1
    vecs = vecs / norms
    np.save(out_dir / "vectors.npy", vecs)
    meta = [{"title": c["title"], "rel": c["rel"], "anchor": c["anchor"], "content": c["content"]} for c in chunks]
    (out_dir / "chunks_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[索引] 已存 {out_dir}")


# ---------- 图谱层 ----------
GRAPH_PROMPT = """你是文枢谱系图谱抽取助手。从以下文献正文中抽取实体与关系。

实体类型：concept（概念）/ work（著作）/ scholar（人物）/ theory（理论）
关系类型：source（B 源自 A）/ develop（B 在 A 基础上发展）/ debate（B 与 A 对立、批判或比较）

要求：
1. 只从文本中抽取，严禁编造；抽取对象必须在正文中出现
2. 每条关系必须附 evidence（原文片段，20-80 字）
3. 无法归入三类的关系，归入最接近类型并在 description 注明
4. 每篇抽取 5-15 个实体、5-15 条关系即可（抓核心）

输出严格 JSON（不要多余文字）：
{"entities": [{"name": "...", "type": "concept|work|scholar|theory", "description": "..."}],
 "relationships": [{"src": "...", "tgt": "...", "type": "source|develop|debate", "evidence": "原文片段", "description": "..."}]}"""


def graph_extract(title: str, full_text: str) -> dict:
    """对单篇调用 DeepSeek 抽取，返回 {entities, relationships}。"""
    prompt = f"文献标题：{title}\n\n{GRAPH_PROMPT}\n\n=== 正文 ===\n{full_text[:6000]}"
    resp = llm_chat(prompt, max_tokens=1600)
    data = None
    resp = resp.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", resp, re.S)
    if m:
        try:
            data = json.loads(m.group(1))
        except Exception:
            pass
    if data is None:
        start = resp.find("{")
        if start >= 0:
            depth = 0
            for i in range(start, len(resp)):
                if resp[i] == "{":
                    depth += 1
                elif resp[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            data = json.loads(resp[start:i + 1])
                        except Exception:
                            data = None
                        break
    if not data:
        raise ValueError(f"图谱解析失败: {title}")
    return {"entities": data.get("entities", []), "relationships": data.get("relationships", [])}


def _norm_name(name: str) -> str:
    """实体名归一化：去书名号、去空格。"""
    n = name.strip().strip("《》").strip()
    return re.sub(r"\s+", "", n)


def _finalize_graph(graph: dict, kb_dir: pathlib.Path):
    """图谱后处理：实体归一化（合并异形）+ 篇目自指补充（不造关系）。"""
    ents, rels = graph["entities"], graph["relationships"]

    # 1. 实体归一化 + 合并异形
    idx = {}
    merged = []
    for e in ents:
        n = _norm_name(e.get("name", ""))
        if n in idx:
            cur = idx[n]
            d = e.get("description", "")
            if d and d not in cur.get("description", ""):
                cur["description"] = (cur.get("description", "") + "；" + d)[:200]
            continue
        e2 = dict(e)
        e2["name"] = n
        idx[n] = e2
        merged.append(e2)

    # 2. 关系 src/tgt 归一化 + 去自环
    rels2 = []
    for r in rels:
        r2 = dict(r)
        r2["src"] = _norm_name(r.get("src", ""))
        r2["tgt"] = _norm_name(r.get("tgt", ""))
        if r2["src"] and r2["tgt"] and r2["src"] != r2["tgt"]:
            rels2.append(r2)

    # 3. 篇目自指补充（137 篇 title 作为 work 实体，不造关系）
    added = 0
    for f in kb_dir.rglob("*.md"):
        t, _, _ = parse_md(f)
        n = _norm_name(t)
        if n not in idx:
            idx[n] = {"name": n, "type": "work", "description": f"（知识库篇目自指）{t}"}
            merged.append(idx[n])
            added += 1

    graph["entities"] = merged
    graph["relationships"] = rels2
    graph["normalized"] = True
    return added


def build_graph(kb_dir: pathlib.Path, out_dir: pathlib.Path, titles: list[str] | None = None):
    """逐篇抽取实体/关系，产出 concept_graph.json（断点续跑）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    graph_path = out_dir / "concept_graph.json"
    prog_path = out_dir / "graph_progress.json"

    graph = {"version": 1, "generated": time.strftime("%Y-%m-%d"),
             "scope": "文枢 skill_rag", "entities": [], "relationships": []}
    if graph_path.exists():
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    done = set()
    if prog_path.exists():
        done = set(json.loads(prog_path.read_text(encoding="utf-8")))

    works = {}
    for f in sorted(kb_dir.rglob("*.md")):
        title, rel, blocks = parse_md(f)
        if titles and title not in titles:
            continue
        works[title] = "\n".join(b["content"] for b in blocks)

    pending = [t for t in works if t not in done]
    print(f"[图谱] 已有 {len(done)} 篇，剩余 {len(pending)} 篇")
    if not pending:
        print("[图谱] 全部完成")
        return

    def work_title(title):
        # 重试退避递增（3/6/9s），失败不阻塞其他篇
        for attempt in range(3):
            try:
                return title, graph_extract(title, works[title])
            except Exception as e:
                if attempt == 2:
                    return title, {"error": f"{str(e)[:80]}（重试{attempt+1}次仍失败）"}
                time.sleep(3 * (attempt + 1))

    t0 = time.time()
    failed = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for title, result in ex.map(work_title, pending):
            if "error" in result:
                print(f"  ❌ {title}: {result['error']}")
                failed.append(title)
                continue
            graph["entities"].extend(result["entities"])
            graph["relationships"].extend(result["relationships"])
            done.add(title)
            graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=1), encoding="utf-8")
            prog_path.write_text(json.dumps(sorted(done)), encoding="utf-8")
            print(f"  ✅ {title}: {len(result['entities'])} 实体 / {len(result['relationships'])} 关系")

    if failed:
        # 失败篇单独记录：下次 --graph-build 自动重试（不在 done 集），也可 --titles 精确续跑
        failed_path = out_dir / "graph_failed.json"
        failed_path.write_text(json.dumps(sorted(failed), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[图谱] {len(failed)} 篇失败（已记录 {failed_path}；下次运行自动重试）")

    seen = set()
    uniq_entities = []
    for e in graph["entities"]:
        key = (e.get("name", ""), e.get("type", ""))
        if key not in seen:
            seen.add(key)
            uniq_entities.append(e)
    graph["entities"] = uniq_entities
    # 归一化 + 篇目自指补充
    added = _finalize_graph(graph, kb_dir)
    graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[图谱] 完成：{len(graph['entities'])} 实体 / {len(graph['relationships'])} 关系"
          f"（新增篇目自指 {added}），耗时 {time.time()-t0:.0f}s")


def graph_context(query: str, out_dir: pathlib.Path) -> str:
    """从图谱提取与问题相关的实体关系，作为问答增强上下文。"""
    gpath = out_dir / "concept_graph.json"
    if not gpath.exists():
        return ""
    graph = json.loads(gpath.read_text(encoding="utf-8"))
    names = [e["name"] for e in graph["entities"] if e["name"] and e["name"] in query]
    if not names:
        return ""
    lines = []
    for r in graph["relationships"]:
        if r.get("src") in names or r.get("tgt") in names:
            lines.append(f"{r['src']} -[{r['type']}]-> {r['tgt']} ｜依据：{r.get('evidence','')[:50]}")
    return "\n".join(lines[:8]) if lines else ""


# ---------- 检索 ----------
def search(query: str, out_dir: pathlib.Path, top_k: int = 8) -> list[dict]:
    vecs = np.load(out_dir / "vectors.npy")
    meta = json.loads((out_dir / "chunks_meta.json").read_text(encoding="utf-8"))
    q = np.array(embed_batch_with_retry([query])[0], dtype=np.float32)
    q = q / (np.linalg.norm(q) + 1e-9)
    scores = vecs @ q
    top = np.argsort(-scores)[:top_k]
    return [{"score": float(scores[i]), **meta[i]} for i in top]


# ---------- 问答 ----------
def answer(query: str, hits: list[dict], graph_ctx: str = "") -> str:
    ctx = []
    for h in hits:
        ctx.append("[" + h["rel"] + "#" + h["anchor"] + "]\n" + h["content"])
    lines = []
    lines.append("你是文枢知识库问答助手。基于以下检索到的文献片段回答问题。")
    lines.append("")
    lines.append("要求：")
    lines.append("1. 只依据给定片段，不要编造")
    lines.append("2. 回答中用 [[路径#锚点]] 标注引用来源")
    lines.append("3. 回答中的每一论断都必须在片段中有对应依据；片段支撑不足的部分，"
                 "简要说明哪些内容无法从片段确认（不臆测）")
    if graph_ctx:
        lines.append("4. 同时参考以下概念关系（来自谱系图谱）：")
        lines.append(graph_ctx)
    lines.append("")
    lines.append("检索片段：")
    lines.extend(ctx[:6])
    lines.append("")
    lines.append("问题：" + query)
    prompt = "\n".join(lines)
    return llm_chat(prompt)


def main():
    ap = argparse.ArgumentParser(description="文枢检索问答（skill_rag）")
    ap.add_argument("--build", action="store_true", help="构建向量索引")
    ap.add_argument("--graph-build", action="store_true", help="构建图谱（逐篇抽取）")
    ap.add_argument("--query", default="", help="问答问题")
    ap.add_argument("--kb", default=".", help="md 知识库目录")
    ap.add_argument("--out", default="skill_rag_index", help="索引/图谱输出目录")
    ap.add_argument("--titles", default="", help="限制篇目（逗号分隔，默认全量）")
    ap.add_argument("--top-k", type=int, default=8)
    args = ap.parse_args()

    kb_dir = pathlib.Path(args.kb)
    out_dir = pathlib.Path(args.out)
    titles = [t.strip() for t in args.titles.split(",") if t.strip()] or None

    if args.build:
        build_index(kb_dir, out_dir, titles)
        return 0

    if args.graph_build:
        build_graph(kb_dir, out_dir, titles)
        return 0

    if args.query:
        hits = search(args.query, out_dir, args.top_k)
        print(f"\n[检索] top-{len(hits)} 命中：")
        for i, h in enumerate(hits, 1):
            print(f"  {i}. [{h['score']:.3f}] {h['title']} {h['anchor']}（{h['rel']}）")
        gctx = graph_context(args.query, out_dir)
        if gctx:
            print(f"\n[图谱] 相关关系：\n{gctx}")
        ans = answer(args.query, hits, gctx)
        print(f"\n[回答]\n{ans}")
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
