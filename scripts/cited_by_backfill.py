#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cited_by 反向回填（通用化版，源：个人知识库实战脚本 backfill_cited_by.py）

遍历文献目录中所有 md 的 related_classics / related_classics_extra，
构建 {目标文件: [引用文献列表]} 反向索引，写入目标文件 YAML 的 cited_by 字段。

用法：
  python cited_by_backfill.py --kb <知识库根> [--papers <文献目录>] [--targets <允许写入子目录>] [--force] [--report <路径>]

默认 dry-run（只预览 + 出报告）；--force 才实际写入。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict


def is_allowed_target(abs_path: str, kb: str, targets: list[str]) -> bool:
    abs_path = abs_path.replace("\\", "/")
    kb = kb.replace("\\", "/")
    for t in targets:
        lib_path = os.path.join(kb, t).replace("\\", "/")
        if abs_path.startswith(lib_path):
            return True
    return False


def resolve_target_file(paper_path: str, rel_target: str) -> list[str]:
    """将文献中的相对目标路径解析为知识库中的绝对 .md 文件路径。"""
    paper_dir = os.path.dirname(paper_path)
    abs_path = os.path.normpath(os.path.join(paper_dir, rel_target))

    if os.path.isfile(abs_path):
        return [abs_path]
    if os.path.isfile(abs_path + ".md"):
        return [abs_path + ".md"]
    if os.path.isdir(abs_path):
        # 优先级: MOC > 索引 > 导航 > README > 第一个文件
        for pattern in ["*MOC*.md", "*索引*.md", "*导航*.md", "README*.md", "*.md"]:
            files = glob.glob(os.path.join(abs_path, pattern))
            if files:
                files.sort()
                return [files[0]]
        return []
    return []


def extract_yaml_field(text: str, field_name: str) -> str:
    m = re.search(rf"^{field_name}:\s*(.*?)(\n\s*\n|\n---|$)", text, re.M | re.I)
    if not m:
        return ""
    return m.group(1).strip()


def parse_path_list(field_value: str) -> list[str]:
    if not field_value or field_value == "[]":
        return []
    return re.findall(r'"([^"]*)"', field_value)


def read_cited_by(text: str) -> list[str]:
    m = re.search(r"^cited_by:\s*(\[.*?\])", text, re.M | re.DOTALL)
    if m:
        return parse_path_list(m.group(1))
    return []


def make_yaml_list(paths: list[str]) -> str:
    if not paths:
        return "[]"
    return "[" + ", ".join(f'"{p}"' for p in sorted(set(paths))) + "]"


def inject_cited_by(filepath: str, citing_paths: list[str], dry_run: bool = True) -> tuple[bool, str]:
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    existing = read_cited_by(text)
    all_paths = list(set(existing + citing_paths))
    new_value = make_yaml_list(all_paths)

    if re.search(r"^cited_by:", text, re.M):
        new_text = re.sub(r"^cited_by:.*$", f"cited_by: {new_value}", text, count=1, flags=re.M)
    else:
        new_text = re.sub(
            r"(\n---)\s*$",
            f"\ncited_by: {new_value}\\1",
            text, count=1, flags=re.M
        )

    if new_text == text:
        return False, "no_change"

    if not dry_run:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_text)

    added = len(all_paths) - len(existing)
    return True, f"{'+' + str(added) if added > 0 else 'merged'} (total: {len(all_paths)})"


def main() -> int:
    ap = argparse.ArgumentParser(description="cited_by 反向回填（遍历 related_* 生成反向索引）")
    ap.add_argument("--kb", required=True, help="知识库根目录")
    ap.add_argument("--papers", default=None, help="文献目录（默认 = --kb 全库扫描）")
    ap.add_argument("--targets", default=None,
                    help="允许写入 cited_by 的子目录，逗号分隔（默认全部）")
    ap.add_argument("--force", action="store_true", help="实际写入（默认 dry-run）")
    ap.add_argument("--report", default=None, help="dry-run 报告输出路径（默认 <kb>/l3_backfill_report.json）")
    args = ap.parse_args()

    kb = os.path.abspath(args.kb)
    papers_root = os.path.abspath(args.papers) if args.papers else kb
    targets = [t.strip() for t in args.targets.split(",") if t.strip()] if args.targets else None
    dry_run = not args.force

    # ===== Phase 1: 构建反向索引 =====
    reverse_index: dict[str, list] = defaultdict(list)

    for dirpath, _, fns in os.walk(papers_root):
        rd = dirpath.replace("\\", "/")
        if "/_assets" in rd or "/00_索引" in rd or "/_build" in rd or "/.obsidian" in rd:
            continue
        for fn in fns:
            if not fn.endswith(".md"):
                continue
            paper_path = os.path.join(dirpath, fn)
            with open(paper_path, "r", encoding="utf-8") as f:
                text = f.read()

            for field in ["related_classics", "related_classics_extra"]:
                val = extract_yaml_field(text, field)
                for rel_target in parse_path_list(val):
                    for tf in resolve_target_file(paper_path, rel_target):
                        if targets and not is_allowed_target(tf, kb, targets):
                            continue
                        target_dir = os.path.dirname(tf)
                        rel_from_target = os.path.relpath(paper_path, target_dir).replace("\\", "/")
                        if rel_from_target.endswith(".md"):
                            rel_from_target = rel_from_target[:-3]
                        # 同一文献对同一目标只记一次（related_* 多字段/重复路径去重）
                        if not any(p[0] == paper_path for p in reverse_index[tf]):
                            reverse_index[tf].append((paper_path, rel_from_target))

    # ===== Phase 2: 预览/写入 =====
    sorted_targets = sorted(reverse_index.items(), key=lambda x: -len(x[1]))
    print("=" * 60)
    print(f"  cited_by 反向回填 | {'DRY-RUN' if dry_run else 'EXECUTED'}")
    print("=" * 60)
    print(f"  唯一目标文件数: {len(reverse_index)}")
    print(f"  总引用关系: {sum(len(v) for v in reverse_index.values())}")
    print()
    print("  === 被引用最多的目标文件 (TOP 15) ===")
    for target, papers in sorted_targets[:15]:
        rel = os.path.relpath(target, kb).replace("\\", "/")
        print(f"    {rel:55s} {len(papers):4d}篇引用")

    files_updated = 0
    files_no_change = 0

    if dry_run:
        print(f"\n  以上为 dry-run 预览。执行将修改 {len(reverse_index)} 个文件。")
        report_path = args.report or os.path.join(kb, "l3_backfill_report.json")
        report = []
        for target, papers in sorted_targets:
            report.append({
                "target": os.path.relpath(target, kb).replace("\\", "/"),
                "citing_count": len(papers),
                "citing_papers": [os.path.relpath(p[0], kb).replace("\\", "/") for p in papers],
            })
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  详细报告: {report_path}")
        print(f"  执行: python cited_by_backfill.py --kb <知识库根> --force")
        return 0

    for target, citing_papers in sorted_targets:
        citing_paths = [p[1] for p in citing_papers]
        changed, msg = inject_cited_by(target, citing_paths, dry_run=False)
        if changed:
            files_updated += 1
            print(f"  [OK] {os.path.relpath(target, kb).replace(chr(92), '/')} {msg}")
        else:
            files_no_change += 1

    print()
    print(f"  文件更新: {files_updated}")
    print(f"  无变化:   {files_no_change}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
