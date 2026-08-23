# -*- coding: utf-8 -*-
"""snapshot_diff.py 回归测试
运行：python scripts/__tests__/test_snapshot_diff.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import snapshot_diff as sd  # noqa: E402

PASS = 0
FAIL = []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL.append(name)
        print(f"  [FAIL] {name} {detail}")


with tempfile.TemporaryDirectory(prefix="hermes-verify-snap-") as td:
    kb = Path(td) / "kb"
    (kb / "文献").mkdir(parents=True)
    (kb / "文献" / "a.md").write_text("---\ntitle: a\n---\n正文\n", encoding="utf-8")
    (kb / "文献" / "b.md").write_text("---\ntitle: b\n---\n正文\n", encoding="utf-8")
    script = str(Path(__file__).parent.parent / "snapshot_diff.py")

    print("测试 1: take_snapshot 单元")
    snap = sd.take_snapshot(kb, sd.EXCLUDE_DIRS)
    check("total_files=2", snap["total_files"] == 2, str(snap["total_files"]))
    check("字段含 mtime/size/status", "文献/a.md" in snap["files"] and "mtime" in snap["files"]["文献/a.md"])

    print("测试 2: diff_snapshots 单元")
    old = {"date": "2026-01-01", "total_files": 2,
           "files": {"文献/a.md": {"mtime": 1, "size": 10, "status": ""},
                     "文献/b.md": {"mtime": 1, "size": 10, "status": ""}}}
    new = {"date": "2026-01-02", "total_files": 3,
           "files": {"文献/a.md": {"mtime": 2, "size": 10, "status": ""},
                     "文献/b.md": {"mtime": 1, "size": 10, "status": ""},
                     "文献/c.md": {"mtime": 1, "size": 5, "status": ""}}}
    d = sd.diff_snapshots(old, new)
    check("added=1（c.md）", d["added_count"] == 1 and "文献/c.md" in d["added"], str(d))
    check("changed=1（a.md）", d["changed_count"] == 1 and "文献/a.md" in d["changed"], str(d))
    check("removed=0", d["removed_count"] == 0)

    print("测试 3: CLI --snapshot-only 生成快照")
    snap_dir = Path(td) / "snaps"
    r = subprocess.run([sys.executable, script, "--kb", str(kb),
                        "--snapshot-only", "--snapshot-dir", str(snap_dir)],
                       capture_output=True, text=True, encoding="utf-8")
    check("exit 0", r.returncode == 0, r.stderr)
    files = list(snap_dir.glob("snapshot_*.json"))
    check("快照文件生成", len(files) == 1, str(files))
    data = json.loads(files[0].read_text(encoding="utf-8"))
    check("快照内容 total=2", data["total_files"] == 2, str(data.get("total_files")))

    print("测试 4: CLI 完整流程（今日快照 → 无昨日 → 跳过对比）")
    r2 = subprocess.run([sys.executable, script, "--kb", str(kb), "--snapshot-dir", str(snap_dir)],
                        capture_output=True, text=True, encoding="utf-8")
    check("exit 0（无昨日快照跳过对比）", r2.returncode == 0, r2.stderr)
    check("提示无昨日快照", "无昨日快照" in r2.stdout or "跳过对比" in r2.stdout, r2.stdout[-150:])

    print("测试 5: 变更日志写入（--log）")
    log_file = Path(td) / "变更日志.md"
    # 模拟昨日快照存在
    (snap_dir / f"snapshot_{sd.date.today().strftime('%Y-%m-%d')}.json").unlink()
    yesterday = (sd.date.today() - sd.timedelta(days=1)).strftime("%Y-%m-%d")
    old_snap = {"date": yesterday, "total_files": 1,
                "files": {"文献/a.md": {"mtime": 1, "size": 10, "status": ""}}}
    (snap_dir / f"snapshot_{yesterday}.json").write_text(json.dumps(old_snap), encoding="utf-8")
    r3 = subprocess.run([sys.executable, script, "--kb", str(kb),
                         "--snapshot-dir", str(snap_dir), "--log", str(log_file)],
                        capture_output=True, text=True, encoding="utf-8")
    check("exit 0", r3.returncode == 0, r3.stderr)
    check("差异输出含新增", "新增 1" in r3.stdout, r3.stdout[-200:])
    check("日志文件生成且含记录", log_file.exists() and "snapshot_diff" in log_file.read_text(encoding="utf-8"))

print(f"\n结果: {PASS} 通过 / {len(FAIL)} 失败")
sys.exit(1 if FAIL else 0)
