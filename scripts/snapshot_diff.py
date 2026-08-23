#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识库快照 + 日差异（通用化版，源：个人知识库实战脚本 snapshot_diff.py + log_utils.py）

用法：
  python snapshot_diff.py --kb <知识库根>                  # 生成今日快照 → 对比昨日 → 输出差异
  python snapshot_diff.py --kb <知识库根> --snapshot-only   # 仅生成快照
  python snapshot_diff.py --kb <知识库根> --log <变更日志.md>  # 差异同时写入变更日志

依赖：仅 Python stdlib。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

EXCLUDE_DIRS = {"_assets", ".git", ".obsidian", "_build", "snapshots", "__pycache__", ".workbuddy"}
CST = timezone(timedelta(hours=8))


def _extract_yaml_field(text: str, field: str) -> str:
    m = re.search(rf'^{field}:\s*["\']?(.+?)["\']?\s*$', text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def take_snapshot(kb_root: Path, exclude: set[str]) -> dict:
    snap = {"date": date.today().strftime("%Y-%m-%d"), "total_files": 0, "files": {}}
    for root, dirs, files in os.walk(kb_root):
        dirs[:] = [d for d in dirs if d not in exclude]
        for f in files:
            if not f.endswith(".md"):
                continue
            full = Path(root) / f
            rel = str(full.relative_to(kb_root)).replace("\\", "/")
            try:
                stat = full.stat()
                size, mtime = stat.st_size, int(stat.st_mtime)
            except OSError:
                size, mtime = 0, 0
            try:
                status = _extract_yaml_field(full.read_text(encoding="utf-8")[:2048], "status")
            except Exception:
                status = ""
            snap["files"][rel] = {"mtime": mtime, "size": size, "status": status}
    snap["total_files"] = len(snap["files"])
    return snap


def save_snapshot(snap: dict, snap_dir: Path, pattern: str) -> Path:
    snap_dir.mkdir(parents=True, exist_ok=True)
    path = snap_dir / pattern.format(date=snap["date"])
    path.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_snapshot(date_str: str, snap_dir: Path, pattern: str) -> dict | None:
    path = snap_dir / pattern.format(date=date_str)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def diff_snapshots(old: dict, new: dict) -> dict:
    old_files = set(old.get("files", {}).keys())
    new_files = set(new.get("files", {}).keys())
    added = new_files - old_files
    removed = old_files - new_files
    changed = set()
    for f in old_files & new_files:
        o, n = old["files"][f], new["files"][f]
        if o.get("mtime") != n.get("mtime") or o.get("size") != n.get("size") or o.get("status") != n.get("status"):
            changed.add(f)
    return {
        "date_old": old["date"], "date_new": new["date"],
        "total_old": old["total_files"], "total_new": new["total_files"],
        "added": sorted(added), "removed": sorted(removed), "changed": sorted(changed),
        "added_count": len(added), "removed_count": len(removed), "changed_count": len(changed),
    }


def log_change(log_file: Path, source: str, action: str, affected: int, summary: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if not log_file.exists():
        log_file.write_text(
            "# 知识库变更日志\n\n| 时间 | 来源 | 操作 | 影响 | 摘要 |\n|:-----|:-----|:-----|:----:|:-----|\n",
            encoding="utf-8")
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"| {now} | {source} | {action} | {affected} | {summary} |\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="知识库快照 + 日差异")
    ap.add_argument("--kb", required=True, help="知识库根目录")
    ap.add_argument("--snapshot-only", action="store_true", help="仅生成今日快照，不做对比")
    ap.add_argument("--snapshot-dir", default=None, help="快照目录（默认 <kb>/_build/snapshots）")
    ap.add_argument("--log", default=None, help="变更日志路径（默认不写日志）")
    args = ap.parse_args()

    kb = Path(args.kb).resolve()
    if not kb.is_dir():
        print(f"Error: 知识库目录不存在: {kb}")
        return 2
    snap_dir = Path(args.snapshot_dir).resolve() if args.snapshot_dir else kb / "_build" / "snapshots"
    pattern = "snapshot_{date}.json"

    today = date.today()
    print(f"生成快照: {today}")
    snap = take_snapshot(kb, EXCLUDE_DIRS)
    path = save_snapshot(snap, snap_dir, pattern)
    print(f"  保存: {path} ({snap['total_files']} 文件)")

    if args.snapshot_only:
        return 0

    yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    old = load_snapshot(yesterday, snap_dir, pattern)
    if not old:
        print(f"  无昨日快照 {yesterday}，跳过对比")
        return 0

    d = diff_snapshots(old, snap)
    print(f"差异（{d['date_old']} → {d['date_new']}）:")
    print(f"  新增 {d['added_count']} / 删除 {d['removed_count']} / 变更 {d['changed_count']}")
    for f in d["added"][:10]:
        print(f"    + {f}")
    for f in d["removed"][:10]:
        print(f"    - {f}")
    for f in d["changed"][:10]:
        print(f"    ~ {f}")

    if args.log and (d["added_count"] or d["removed_count"] or d["changed_count"]):
        log_change(Path(args.log).resolve(), "snapshot_diff", "快照差异",
                   d["added_count"] + d["removed_count"] + d["changed_count"],
                   f"{d['date_old']}→{d['date_new']} +{d['added_count']}/-{d['removed_count']}/~{d['changed_count']}")
        print(f"  变更已写入日志: {args.log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
