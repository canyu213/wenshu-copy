#!/usr/bin/env python3
"""epub_split.py — 文枢通用入库流程 EPUB 入口（S1'~S4' 合一）

EPUB 无 PDF 页码概念：以"章节"为篇、以"自然段"为锚点空间（book_page = 段号）。
产物对齐 PDF 流程：epub_chapters.json + extracted/ch_XXX.txt + split_works.json
（split_works.json 可直接喂给 kb_builder.py 生成 md 知识库）。

用法：
    python epub_split.py --input 书.epub --output 输出目录 [--volume 第一卷] [--keep-footnotes]

输出：
    输出目录/epub_chapters.json    [{idx, title}] 章节清单
    输出目录/extracted/ch_001.txt   每章纯文本（标题已入 YAML，正文剔除标题行）
    输出目录/split_works.json      [{title, volume, book_start, book_end, pages:[{book_page, text}]}]

排坑记录（第二实证）：
- EPUB 章节标题常用 <p align="center"><font size="6"> 标记（非 h 标签）→ 收集 <b>/<h*> 文本作候选
- 文件内含 [n] 脚注锚点 → 默认清理（--keep-footnotes 保留）
- 标题行必须从正文剔除，否则 kb_builder strip_header 误删导致锚点从 0002 起
"""
import argparse
import json
import pathlib
import re
import sys
from html.parser import HTMLParser

try:
    import ebooklib
    from ebooklib import epub
except ImportError:
    raise SystemExit("缺少依赖 ebooklib，请先安装：pip install ebooklib")

FOOTNOTE_RE = re.compile(r"\[\d+\]")
BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "section", "br"}
SKIP_TAGS = {"script", "style", "head", "title", "meta"}
# 非正文章节黑名单（精确匹配：扉页/目录/版权页；"前言 倦怠的普罗米修斯"是正文第一章，不在此列）
def is_non_body(title: str) -> bool:
    return title in {"扉页", "目录", "版权页"} or "版权" in title


class TextExtractor(HTMLParser):
    """HTML → 纯文本：块级标签换行、脚本/样式剔除、标题候选收集。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip_depth = 0
        self.heading_candidates = []  # [(depth, text)] 章节标题候选

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip_depth += 1
        if self.skip_depth:
            return
        if tag in BLOCK_TAGS:
            self.parts.append("\n")
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "b"):
            self.parts.append("\x00")  # 标记标题候选起点

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
        if self.skip_depth:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "b"):
            self.parts.append("\x00")

    def handle_data(self, data):
        if self.skip_depth:
            return
        self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        # 提取标题候选（\x00 包裹的短文本）
        for seg in re.findall(r"\x00([^\x00]{1,60})\x00", raw):
            t = seg.strip()
            if t and re.match(r"^[\u4e00-\u9fffA-Za-z《》0-9]", t) and len(t) >= 2:
                self.heading_candidates.append(t)
        # 去标记、压缩空白
        raw = raw.replace("\x00", "")
        lines = [re.sub(r"[ \t\u3000]+", " ", l).strip() for l in raw.splitlines()]
        return "\n".join(l for l in lines if l)


def extract_chapters(book) -> list[dict]:
    """提取章节清单：优先 epub.toc（nav，含 filepos 正文锚点），退化文档内标题候选。"""
    chapters = []
    seen = set()
    if getattr(book, "toc", None):
        for item in book.toc:
            title = getattr(item, "title", "") or ""
            if isinstance(title, list):
                title = " ".join(str(t) for t in title)
            title = title.strip()
            # filepos：href 中 #fileposNNNNN → 正文字符偏移
            href = getattr(item, "href", "") or ""
            m = re.search(r"#filepos(\d+)", href)
            filepos = int(m.group(1)) if m else None
            if title and title not in seen:
                seen.add(title)
                chapters.append({"idx": len(chapters) + 1, "title": title, "filepos": filepos})
    if not any(c.get("filepos") for c in chapters):
        # nav 无 filepos：退化为文档内标题候选
        chapters = []
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            parser = TextExtractor()
            parser.feed(item.get_content().decode("utf-8", "ignore"))
            for t in parser.heading_candidates:
                if t not in seen:
                    seen.add(t)
                    chapters.append({"idx": len(chapters) + 1, "title": t, "filepos": None})
    return chapters


def split_by_toc(html: str, chapters: list[dict]) -> list[dict]:
    """按 toc 标题顺序匹配正文位置切片（单文档 epub 通用）。

    策略：filepos 偏移不可靠（实测指向段落中间/越界），改用标题文本顺序匹配——
    从"目录区末尾"（最后一个 filepos 链接之后）开始找，避免匹配到目录列表。
    外二篇作为整章：其后的 toc 子篇标题不再单独切分。
    """
    # 目录区末尾：开头连续 filepos 链接块（相邻间隔 <300 字符；正文脚注链接稀疏，不在此块）
    href_re = re.compile(r'href="[^"]*#filepos\d+"[^>]*>')
    m = href_re.search(html)
    search_from = 0
    if m:
        pos = m.end()
        last_end = m.end()
        while True:
            n = href_re.search(html, pos)
            if not n or n.start() - last_end > 300:
                break
            last_end = n.end()
            pos = n.end()
        search_from = last_end

    segs = []
    last_title = None
    for ch in chapters:
        title = ch["title"]
        if is_non_body(title) or title == last_title:
            continue
        # 外二篇之后（子篇）不再切分
        if last_title and last_title == "外二篇":
            continue
        start = html.find(title, search_from)
        if start < 0:
            continue
        segs.append({"title": title, "pos": start})
        last_title = title
        search_from = start + len(title)
    works = []
    for i, seg in enumerate(segs):
        end = segs[i + 1]["pos"] if i + 1 < len(segs) else len(html)
        works.append({"title": seg["title"], "html": html[seg["pos"]:end]})
    return works


def split_paragraphs(text: str) -> list[str]:
    """自然段拆分（块级换行分隔）。"""
    return [p.strip() for p in re.split(r"\n+", text) if p.strip()]


def main():
    ap = argparse.ArgumentParser(description="文枢 EPUB 入库（章节切分 + 纯文本 + split_works）")
    ap.add_argument("--input", required=True, help="EPUB 路径")
    ap.add_argument("--output", required=True, help="输出目录（生成 extracted/ 与 json）")
    ap.add_argument("--volume", default="第一卷", help="卷名（默认：第一卷）")
    ap.add_argument("--keep-footnotes", action="store_true", help="保留 [n] 脚注锚点（默认清理）")
    args = ap.parse_args()

    in_path = pathlib.Path(args.input)
    out_dir = pathlib.Path(args.output)
    extracted_dir = out_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)

    book = epub.read_epub(str(in_path))
    chapters = extract_chapters(book)
    if not chapters:
        raise SystemExit("[FAIL] 未识别到任何章节（nav 与文档标题均无结果）")

    docs = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    if not docs:
        raise SystemExit("[FAIL] EPUB 无正文文档")
    # 单文档模式：整本书 HTML + toc 定位切片
    html = docs[0].get_content().decode("utf-8", "ignore")
    segs = split_by_toc(html, chapters)
    if not segs:
        # toc 定位失败：退化为整文档 1 篇
        segs = [{"title": in_path.stem, "html": html}]

    works = []
    for i, seg in enumerate(segs, 1):
        parser = TextExtractor()
        parser.feed(seg["html"])
        text = parser.text()
        if not args.keep_footnotes:
            text = FOOTNOTE_RE.sub("", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        paras = split_paragraphs(text)
        # 剔除标题行（标题已入 YAML；否则 kb_builder strip_header 误删第一段 → 锚点从 0002 起）
        if paras and paras[0].strip() == seg["title"]:
            paras = paras[1:]
        pages = [{"book_page": j + 1, "text": p} for j, p in enumerate(paras)]
        works.append({"title": seg["title"], "volume": args.volume,
                      "book_start": 1, "book_end": len(paras), "pages": pages})
        (extracted_dir / f"ch_{i:03d}.txt").write_text(text, encoding="utf-8")

    (out_dir / "epub_chapters.json").write_text(
        json.dumps([{"idx": i + 1, "title": w["title"]} for i, w in enumerate(works)],
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "split_works.json").write_text(
        json.dumps(works, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(w["book_end"] for w in works)
    print(f"[OK] {len(works)} 章 / {total} 段")
    print(f"  章节清单: {out_dir / 'epub_chapters.json'}")
    print(f"  split_works: {out_dir / 'split_works.json'}")
    for w in works[:8]:
        print(f"    {w['title']}: {w['book_end']} 段")
    if len(works) > 8:
        print(f"    ... 共 {len(works)} 章")


if __name__ == "__main__":
    main()
