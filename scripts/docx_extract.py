#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DOCX 入库提取（通用化版，源：个人知识库实战脚本 unified_import.py process_docx 段）

提取 DOCX 正文与基础元数据（标题/发布日期/公文号），输出文本或 md 知识库文件。

用法：
  python docx_extract.py --input 文件.docx                  # 打印正文
  python docx_extract.py --input 文件.docx --meta           # 打印元数据 JSON
  python docx_extract.py --dir 目录 --output 输出目录        # 批量生成 md（YAML + 正文）

依赖：python-docx（pip install python-docx）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

DATE_PATTERNS = [
    r"(20[0-9]{2})年(1[0-2]|0?[1-9])月(3[01]|[12]\d|0?[1-9])日",
    r"(20[0-9]{2})-(1[0-2]|0[1-9])-(3[01]|[12]\d|0[1-9])",
    r"发布时间：(.{10,20})",
]
DOC_NUMBER_PATTERNS = [
    r"([\u4e00-\u9fff]+?〔20[0-9]{2}〕\d+号)",
    r"([\u4e00-\u9fff]+?\[20[0-9]{2}\]\d+号)",
]


def extract_text(docx_path: Path) -> str:
    """提取 DOCX 正文（按段落拼接，跳过空段）。"""
    try:
        import docx as docx_lib
    except ImportError:
        raise SystemExit("缺少依赖 python-docx，请先安装：pip install python-docx")
    doc = docx_lib.Document(str(docx_path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_metadata(text: str, filename: str) -> dict:
    """提取基础元数据：标题/发布日期/公文号。"""
    meta = {"title": "", "publish_date": "", "doc_number": "", "type": "文档", "tags": []}
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if lines:
        meta["title"] = lines[0][:80]

    for p in DATE_PATTERNS:
        m = re.search(p, text)
        if m:
            meta["publish_date"] = m.group(0)[:15]
            break

    for p in DOC_NUMBER_PATTERNS:
        m = re.search(p, text)
        if m:
            meta["doc_number"] = m.group(1)
            break

    return meta


def safe_filename(title: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", title).strip() or "untitled"


def to_md(text: str, meta: dict) -> str:
    """生成 md 知识库文件（YAML frontmatter + 正文）。"""
    yaml_lines = ["---", f"title: {meta['title']}"]
    if meta["publish_date"]:
        yaml_lines.append(f"publish_date: {meta['publish_date']}")
    if meta["doc_number"]:
        yaml_lines.append(f"doc_number: {meta['doc_number']}")
    yaml_lines += ["type: 文档", "tags: []", "---", ""]
    return "\n".join(yaml_lines) + text + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="DOCX 入库提取（正文 + 基础元数据）")
    ap.add_argument("--input", default=None, help="单个 .docx 文件")
    ap.add_argument("--dir", default=None, help="批量处理目录")
    ap.add_argument("--output", default=None, help="输出目录（批量时生成 md 文件）")
    ap.add_argument("--meta", action="store_true", help="打印元数据 JSON")
    args = ap.parse_args()

    if not args.input and not args.dir:
        print("Error: 需要 --input 或 --dir")
        return 2

    files = [Path(args.input)] if args.input else list(Path(args.dir).glob("*.docx"))
    if not files:
        print("没有找到 .docx 文件")
        return 1

    for f in files:
        if not f.exists():
            print(f"Error: 文件不存在 {f}")
            return 2
        try:
            text = extract_text(f)
        except SystemExit as e:
            print(e)
            return 1

        meta = extract_metadata(text, f.name)
        if args.meta:
            print(json.dumps({"file": f.name, **meta}, ensure_ascii=False, indent=2))
            continue

        if args.output:
            out_dir = Path(args.output)
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / f"{safe_filename(meta['title'])}.md"
            out.write_text(to_md(text, meta), encoding="utf-8")
            print(f"  [OK] {out} ({len(text)} 字符)")
        else:
            print(f"=== {f.name} ===")
            print(text[:2000])
            if len(text) > 2000:
                print(f"...（共 {len(text)} 字符）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
