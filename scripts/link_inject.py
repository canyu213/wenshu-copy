#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""关键词语义链接注入（通用化版，源：个人知识库实战脚本 semantic_match_links.py + upgrade_inject_links.py）

扫描文献的 title / keywords / abstract / core_viewpoint，
按关键词映射表匹配 → 生成 related_classics_extra 链接（写入 YAML）。

用法：
  python link_inject.py --kb <知识库根> --map <映射表.json> [--papers <文献目录>] [--force] [--report <路径>]

映射表格式（JSON）：
  {
    "关键词": {"lib": "目标子目录", "subpath": "目录内相对路径", "short_only": false}
  }
  - short_only=true 时该关键词仅匹配标题与关键词字段（短词防误配）

默认 dry-run（输出 all_matches.json + 预览）；--force 实际写入。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


def extract_yaml_field(text: str, field_name: str) -> str:
    m = re.search(rf"^{field_name}:\s*(.*?)(\n\s*\n|\n---|$)", text, re.M | re.I)
    return m.group(1).strip() if m else ""


def extract_yaml_multiline_field(text: str, field_name: str) -> str:
    """提取多行字段（如 keywords:\n  - a\n  - b）。"""
    m = re.search(rf"^{field_name}:\s*\n((?:\s+- .*\n?)+)", text, re.M | re.I)
    if m:
        return "\n".join(re.findall(r"- (.+)", m.group(1)))
    return extract_yaml_field(text, field_name)


def resolve_relative_path(paper_path: str, lib_name: str, subpath: str) -> str:
    """拼接目标文件相对路径（从论文所在目录出发）。"""
    paper_dir = os.path.dirname(paper_path)
    target = os.path.normpath(os.path.join(paper_dir, lib_name, subpath))
    return target.replace("\\", "/")


def match_keywords_in_text(text: str, keyword_regex: re.Pattern) -> bool:
    return bool(keyword_regex.search(text))


def process_paper(filepath: str, kb: str, kw_map: dict, dry_run: bool = True) -> dict:
    """扫描单篇论文，返回匹配结果。"""
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    title = extract_yaml_field(text, "title")
    keywords = extract_yaml_multiline_field(text, "keywords")
    abstract = extract_yaml_field(text, "abstract")
    viewpoint = extract_yaml_field(text, "core_viewpoint")
    combined_full = f"{title} {keywords} {abstract} {viewpoint}"
    combined_short = f"{title} {keywords}"

    matches = []
    for keyword, cfg in kw_map.items():
        short_only = cfg.get("short_only", False)
        if short_only:
            ok = match_keywords_in_text(combined_short, re.compile(re.escape(keyword)))
        else:
            ok = match_keywords_in_text(combined_full, re.compile(re.escape(keyword)))
        if ok:
            rel = resolve_relative_path(filepath, cfg["lib"], cfg.get("subpath", ""))
            matches.append({"keyword": keyword, "target": rel, "lib": cfg["lib"]})

    return {
        "file": os.path.relpath(filepath, kb).replace("\\", "/"),
        "title": title,
        "matches": matches,
    }


def inject_extra_field(filepath: str, extra_paths: list[str], dry_run: bool = True) -> tuple[bool, str]:
    """向 YAML 注入 related_classics_extra（合并去重，不覆盖 related_classics）。"""
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    existing = extract_yaml_field(text, "related_classics_extra")
    existing_paths = re.findall(r'"([^"]*)"', existing) if existing else []
    all_paths = list(dict.fromkeys(existing_paths + extra_paths))
    new_value = "[" + ", ".join(f'"{p}"' for p in all_paths) + "]" if all_paths else "[]"

    if re.search(r"^related_classics_extra:", text, re.M):
        new_text = re.sub(r"^related_classics_extra:.*$",
                          f"related_classics_extra: {new_value}", text, count=1, flags=re.M)
    else:
        new_text = re.sub(
            r"(\n---)\s*$",
            f"\nrelated_classics_extra: {new_value}\\1",
            text, count=1, flags=re.M
        )

    if new_text == text:
        return False, "no_change"
    if not dry_run:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_text)
    return True, f"注入 {len(all_paths)} 条"


def main() -> int:
    ap = argparse.ArgumentParser(description="关键词语义链接注入（映射表驱动）")
    ap.add_argument("--kb", required=True, help="知识库根目录")
    ap.add_argument("--papers", default=None, help="文献目录（默认 = --kb）")
    ap.add_argument("--map", required=True, help="关键词映射表 JSON 路径")
    ap.add_argument("--force", action="store_true", help="实际写入（默认 dry-run）")
    ap.add_argument("--report", default=None, help="dry-run 报告输出路径（默认 <kb>/all_matches.json）")
    args = ap.parse_args()

    kb = Path(args.kb).resolve()
    if not kb.is_dir():
        print(f"Error: 知识库目录不存在: {kb}")
        return 2
    map_path = Path(args.map).resolve()
    if not map_path.exists():
        print(f"Error: 映射表不存在: {map_path}")
        return 2
    kw_map = json.loads(map_path.read_text(encoding="utf-8"))
    papers_root = Path(args.papers).resolve() if args.papers else kb
    dry_run = not args.force

    all_results = []
    for dirpath, dirs, fns in os.walk(papers_root):
        dirs[:] = [d for d in dirs if d not in ("_assets", ".git", ".obsidian", "_build")]
        for fn in fns:
            if not fn.endswith(".md"):
                continue
            fp = os.path.join(dirpath, fn)
            result = process_paper(fp, str(kb), kw_map, dry_run)
            if result["matches"]:
                all_results.append(result)

    print("=" * 60)
    print(f"  链接注入 | {'DRY-RUN' if dry_run else 'EXECUTED'}")
    print("=" * 60)
    print(f"  命中文献数: {len(all_results)}")

    updated = 0
    for r in all_results:
        targets = [m["target"] for m in r["matches"]]
        if dry_run:
            print(f"  [MATCH] {r['file']} → {targets}")
        else:
            changed, msg = inject_extra_field(os.path.join(kb, r["file"]), targets, dry_run=False)
            if changed:
                updated += 1
                print(f"  [OK] {r['file']} {msg}")
            else:
                print(f"  [SKIP] {r['file']} no_change")

    if dry_run:
        report_path = args.report or os.path.join(kb, "all_matches.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print(f"\n  详细报告: {report_path}")
        print(f"  执行: python link_inject.py --kb <知识库根> --map <映射表.json> --force")
        return 0

    print(f"\n  文件更新: {updated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
