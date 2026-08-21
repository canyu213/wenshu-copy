#!/usr/bin/env python3
"""S5 通用 md 知识库生成器（v2 通用入库流程）。

输入 split_works.json（S4 产物），输出按卷分目录的 md 知识库：
每篇一个 .md，含 YAML 元数据 + 页码锚点（^v{卷}p{页码}）+ 页内自然段。

用法：
    kb_builder.py --split split_works.json --output 知识库目录 [--tags "#毛选,#第1卷"] [--dry-run]
"""
import argparse
import json
import pathlib
import re
import sys
from collections import Counter

# ---------- 常量 ----------

# 卷中文 → 2 位卷号（锚点用 ^v01p0001）
VOL_CODE = {
    "第一卷": "01", "第二卷": "02", "第三卷": "03", "第四卷": "04",
    "第五卷": "05", "第六卷": "06", "第七卷": "07", "第八卷": "08",
}

# Windows 非法文件名字符
INVALID_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize_filename(name: str) -> str:
    """清理篇名为合法文件名。"""
    n = re.sub(INVALID_CHARS, "", name)
    n = n.rstrip("．. ＊*").strip()
    return n or "未命名"


def normalize_text(text: str) -> str:
    """正文清理：去 OCR 空格/多余空白，保留自然段（空行分隔）。"""
    lines = text.split("\n")
    out = []
    for ln in lines:
        s = ln.strip()
        if not s:
            if out and out[-1] != "":
                out.append("")  # 保留空行作为自然段分隔
            continue
        # 压缩中文内部空格（OCR 残留，如"这 个 问 题"），保留英文/数字间空格
        s = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", s)
        s = re.sub(r"[ \t]{2,}", " ", s)
        out.append(s)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


def strip_header(text: str, title: str) -> str:
    """清理页眉/标题行：'篇名'、'篇名＊'、'篇名 页码'，以及紧随的孤立页码行。"""
    lines = text.split("\n")
    if not lines:
        return text

    first = lines[0].strip()
    is_header = False
    if first == title or first == title + "＊" or first == title + "*":
        is_header = True
    else:
        m = re.match(r"^(.*?)\s*\d{1,4}$", first)
        if m and m.group(1).strip() == title:
            is_header = True
    if is_header:
        lines = lines[1:]

    # 删紧随的孤立页码行（页眉页码残留，如 "5"）
    if lines and re.fullmatch(r"\d{1,4}", lines[0].strip()):
        lines = lines[1:]

    return "\n".join(lines)


def build_md(work: dict, tags: list[str], anchor_semantics: str = "page") -> tuple[str, str, str]:
    """为单篇生成 md，返回 (卷目录名, 文件名, 内容)。"""
    title = work["title"].rstrip("＊* ").strip()
    volume = work.get("volume") or ""
    vol_code = VOL_CODE.get(volume, "00")
    book_start = work.get("book_start")
    book_end = work.get("book_end")

    # YAML 元数据（能力边界内：篇名/卷/页码范围必有；year/edition 标 [待补]）
    lines = ["---"]
    lines.append(f"title: {title}")
    lines.append(f"volume: {volume}")
    if book_start is not None and book_end is not None:
        lines.append(f"pages: {book_start}-{book_end}")
    else:
        lines.append("pages: [待补]")
    lines.append("year: [待补]")
    lines.append("edition: [待补]")
    if tags:
        lines.append("tags: " + ", ".join(f'"{t}"' for t in tags))
    lines.append(f"anchor_semantics: {anchor_semantics}")
    lines.append("block_id_format: ^v{卷号2位}p{书内页码4位}")
    lines.append("---")
    lines.append("")

    # 正文
    lines.append(f"# {title}")
    lines.append("")
    lines.append("## 正文")
    lines.append("")

    for p in work["pages"]:
        book_page = p["book_page"]
        text = strip_header(p["text"], title)
        clean = normalize_text(text)
        if not clean:
            continue
        lines.append(f"^v{vol_code}p{int(book_page):04d}")
        lines.append("")
        lines.append(clean)
        lines.append("")

    content = "\n".join(lines)
    fname = sanitize_filename(title) + ".md"
    return volume, fname, content


def main() -> int:
    ap = argparse.ArgumentParser(description="S5 生成 md 知识库")
    ap.add_argument("--split", required=True, help="split_works.json 路径")
    ap.add_argument("--output", required=True, help="知识库输出目录")
    ap.add_argument("--tags", default="", help="领域标签，逗号分隔，如 '#毛选,#第1卷'")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写盘")
    args = ap.parse_args()

    split_path = pathlib.Path(args.split)
    out_dir = pathlib.Path(args.output)
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    if not split_path.exists():
        print(f"[ERROR] split 文件不存在: {split_path}")
        return 1

    works = json.loads(split_path.read_text(encoding="utf-8"))
    # 兼容两种 split_works 结构：{works: [...]}（带 _meta）或纯 list
    meta = works.get("_meta", {}) if isinstance(works, dict) else {}
    works = works.get("works", works) if isinstance(works, dict) else works
    anchor_semantics = meta.get("anchor_semantics", "page")  # page（PDF 页码）/ paragraph（EPUB 段号）
    print(f"[S5] 输入 {len(works)} 篇（锚点语义: {anchor_semantics}）")

    # 预生成全部 md
    generated = []  # [(vol, fname, content)]
    errors = []
    for w in works:
        vol, fname, content = build_md(w, tags, anchor_semantics)
        anchors = len(re.findall(r"^\^v[0-9]{2}p[0-9]{4}$", content, re.M))
        generated.append((vol, fname, content))
        if anchors == 0:
            errors.append(f"无锚点: {w['title']}")

    total_chars = sum(len(c) for _, _, c in generated)
    total_anchors = sum(
        len(re.findall(r"^\^v[0-9]{2}p[0-9]{4}$", c, re.M)) for _, _, c in generated
    )
    vol_stat = Counter(vol for vol, _, _ in generated)
    print(f"[S5] 将生成 {len(generated)} 篇 | 锚点 {total_anchors} | 总字数 {total_chars}")
    for v, c in sorted(vol_stat.items()):
        print(f"  {v or '(未分卷)'}: {c} 篇")

    if errors:
        print(f"[S5] 警告 {len(errors)} 篇无锚点：")
        for e in errors[:10]:
            print(f"  {e}")

    if args.dry_run:
        print("[S5] dry-run 完成，未写盘")
        return 0 if not errors else 2

    # 写盘
    written = 0
    for vol, fname, content in generated:
        vol_dir = out_dir / (vol or "未分卷")
        vol_dir.mkdir(parents=True, exist_ok=True)
        (vol_dir / fname).write_text(content, encoding="utf-8")
        written += 1

    print(f"[S5] 已写 {written} 篇到 {out_dir}")
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
