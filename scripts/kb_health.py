#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识库健康巡检（通用化版，源：个人知识库实战脚本 check_yaml_health/check_tags/check_dead_links）

三个子命令：
  python kb_health.py --kb <知识库根> yaml [--dir <子目录>]     # YAML 闭合 + tags 数组格式
  python kb_health.py --kb <知识库根> tags [--dir <子目录>] [--forbidden "缩写=全称,..."]
  python kb_health.py --kb <知识库根> links [--dir <子目录>]   # wikilink 死链

依赖：仅 Python stdlib（yaml 检查用正则实现，无需 PyYAML）。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

EXCLUDE_DIRS = {"_assets", ".git", ".obsidian", "_build", "snapshots", ".workbuddy", "__pycache__"}

# 示例/占位符死链白名单（文档示例、模板占位符，非真实死链）
SAMPLE_WHITELIST = {
    "文件名", "文件", "wikilink", "source_url", "概念名", "x",
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15",
    "来源文件", "目标文件", "论文名", "链接", "占位", "示例",
}


# ───────────────────── yaml ─────────────────────
def check_yaml_closure(text: str) -> list[str]:
    """YAML --- 成对闭合检查。"""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return []
    for i in range(1, min(len(lines), 120)):
        if lines[i].strip() == "---":
            return []
    return ["YAML 未闭合（第一行 --- 无对应闭合）"]


def check_tags_format(text: str) -> list[str]:
    """tags 字段数组格式检查。"""
    m = re.search(r"^tags:\s*(.+)$", text, re.MULTILINE)
    if not m:
        return []
    val = m.group(1).strip()
    if val.startswith("[") or val.startswith("-") or val == "[]":
        return []
    return [f"tags 非数组格式: '{val}'（应为 [tag1, tag2] 或多行 - tag）"]


def scan_yaml(kb: Path, subdir: str | None) -> list[tuple[str, list[str]]]:
    results = []
    target = kb / subdir if subdir else kb
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if not f.endswith(".md"):
                continue
            fp = Path(root) / f
            try:
                text = fp.read_text(encoding="utf-8")
            except Exception:
                continue
            issues = check_yaml_closure(text) + check_tags_format(text)
            if issues:
                results.append((str(fp.relative_to(kb)).replace("\\", "/"), issues))
    return results


# ───────────────────── tags ─────────────────────
def scan_tags(kb: Path, subdir: str | None, forbidden: dict[str, str]) -> list[tuple[str, list[str]]]:
    results = []
    target = kb / subdir if subdir else kb
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if not f.endswith(".md"):
                continue
            fp = Path(root) / f
            try:
                text = fp.read_text(encoding="utf-8")
            except Exception:
                continue
            issues = []
            for abbr, full in forbidden.items():
                if re.search(rf"#\s*{re.escape(abbr)}\b", text) or abbr in text:
                    issues.append(f"禁用缩写标签「{abbr}」→ 应写「{full}」")
            if issues:
                results.append((str(fp.relative_to(kb)).replace("\\", "/"), issues))
    return results


# ───────────────────── links ─────────────────────
def build_file_index(directory: Path) -> dict:
    idx: dict[str, list] = defaultdict(list)
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if not f.endswith(".md"):
                continue
            name = f[:-3]
            rel = str(Path(root).relative_to(directory) / f).replace("\\", "/")
            idx[name].append(rel)
    return idx


def extract_wikilinks(text: str) -> list[str]:
    text = re.sub(r"\[\[[^\]]*\]\]\([^)]*\)", "", text)
    text = re.sub(r"\[\[[^\]]*\]\]\[[^\]]*\]", "", text)
    pattern = r"\[\[([^\]|#]+?)(?:#[^\]]+?)?(?:\|[^\]]+?)?\]\]"
    return [m.group(1).strip() for m in re.finditer(pattern, text)]


def scan_links(kb: Path, subdir: str | None) -> tuple[int, list[tuple[str, list[str]]]]:
    target = kb / subdir if subdir else kb
    file_idx = build_file_index(target)
    dead: dict[str, list] = defaultdict(list)
    total_links = 0

    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if not f.endswith(".md"):
                continue
            fp = Path(root) / f
            try:
                text = fp.read_text(encoding="utf-8")
            except Exception:
                continue
            if text.startswith("---"):
                m = re.match(r"^---\n.*?\n---\n", text, re.S)
                if m:
                    text = text[m.end():]
            for link_target in extract_wikilinks(text):
                total_links += 1
                if link_target in SAMPLE_WHITELIST:
                    continue
                if re.fullmatch(r"\d+", link_target) or not link_target:
                    continue
                if link_target not in file_idx:
                    rel_src = str(fp.relative_to(kb)).replace("\\", "/")
                    dead[link_target].append(rel_src)

    return total_links, sorted(dead.items())


def main() -> int:
    ap = argparse.ArgumentParser(description="知识库健康巡检（yaml / tags / links）")
    ap.add_argument("--kb", required=True, help="知识库根目录")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_yaml = sub.add_parser("yaml", help="YAML 闭合 + tags 数组格式检查")
    p_yaml.add_argument("--dir", default=None, help="仅扫描指定子目录")
    p_tags = sub.add_parser("tags", help="禁用缩写标签扫描")
    p_tags.add_argument("--dir", default=None, help="仅扫描指定子目录")
    p_tags.add_argument("--forbidden", default=None,
                        help="禁用缩写表，格式 '缩写=全称,缩写=全称'")
    p_links = sub.add_parser("links", help="wikilink 死链检测")
    p_links.add_argument("--dir", default=None, help="仅扫描指定子目录")
    args = ap.parse_args()

    kb = Path(args.kb).resolve()
    if not kb.is_dir():
        print(f"Error: 知识库目录不存在: {kb}")
        return 2

    if args.cmd == "yaml":
        results = scan_yaml(kb, args.dir)
        print(f"YAML 健康巡检 | {len(results)} 个文件有问题")
        for path, issues in results[:20]:
            print(f"  [X] {path}")
            for i in issues:
                print(f"      - {i}")
        if not results:
            print("  ✅ 全部通过")
        return 1 if results else 0

    if args.cmd == "tags":
        forbidden = {}
        if args.forbidden:
            for pair in args.forbidden.split(","):
                if "=" in pair:
                    abbr, full = pair.split("=", 1)
                    forbidden[abbr.strip()] = full.strip()
        results = scan_tags(kb, args.dir, forbidden)
        print(f"标签合规扫描 | {len(results)} 个文件命中禁用缩写")
        for path, issues in results[:20]:
            print(f"  [X] {path}")
            for i in issues:
                print(f"      - {i}")
        if not results:
            print("  ✅ 全部通过")
        return 1 if results else 0

    if args.cmd == "links":
        total, dead = scan_links(kb, args.dir)
        print(f"死链检测 | 扫描链接 {total} 条 | {len(dead)} 个死链目标")
        for target, sources in dead[:20]:
            print(f"  [X] [[{target}]] 被 {len(sources)} 个文件引用: {sources[0]}")
        if not dead:
            print("  ✅ 无死链")
        return 1 if dead else 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
