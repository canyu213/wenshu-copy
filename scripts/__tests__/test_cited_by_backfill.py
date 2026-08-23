# -*- coding: utf-8 -*-
"""cited_by_backfill.py 回归测试
运行：python scripts/__tests__/test_cited_by_backfill.py
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import cited_by_backfill as cbf  # noqa: E402

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


def make_fake_kb(root: Path) -> Path:
    """构造假知识库：2 篇论文引用 1 篇经典"""
    papers = root / "学术论文"
    classics = root / "经典"
    papers.mkdir(parents=True)
    classics.mkdir()
    (papers / "论文A.md").write_text(
        "---\ntitle: 论文A\nrelated_classics: [\"../经典/经典B\"]\n---\n正文A\n", encoding="utf-8")
    (papers / "论文C.md").write_text(
        "---\ntitle: 论文C\nrelated_classics: [\"../经典/经典B\"]\nrelated_classics_extra: [\"../经典/经典B\"]\n---\n正文C\n", encoding="utf-8")
    (classics / "经典B.md").write_text(
        "---\ntitle: 经典B\n---\n经典正文\n", encoding="utf-8")
    return root


with tempfile.TemporaryDirectory(prefix="hermes-verify-citedby-") as td:
    kb = make_fake_kb(Path(td))

    print("测试 1: 反向索引构建（直接调函数）")
    reverse = {}
    for dirpath, _, fns in os.walk(kb / "学术论文"):
        for fn in fns:
            if not fn.endswith(".md"):
                continue
            pp = os.path.join(dirpath, fn)
            text = (kb / "学术论文" / fn).read_text(encoding="utf-8")
            for field in ["related_classics", "related_classics_extra"]:
                for rel in cbf.parse_path_list(cbf.extract_yaml_field(text, field)):
                    for tf in cbf.resolve_target_file(pp, rel):
                        reverse.setdefault(tf, []).append(pp)
    target = os.path.join(kb, "经典", "经典B.md")
    check("解析目标文件（目录→经典B.md）", target in reverse, str(reverse.keys()))
    check("去重后 2 篇引用（含 extra）", len(set(reverse[target])) == 2, str(reverse[target]))

    print("测试 2: dry-run 报告")
    r = subprocess.run([sys.executable, str(Path(__file__).parent.parent / "cited_by_backfill.py"),
                        "--kb", str(kb)], capture_output=True, text=True, encoding="utf-8")
    check("dry-run exit 0", r.returncode == 0, r.stderr)
    check("报告含经典B 2篇引用", "经典B" in r.stdout and "2篇引用" in r.stdout)
    report = kb / "l3_backfill_report.json"
    check("报告文件生成", report.exists())
    import json
    data = json.loads(report.read_text(encoding="utf-8"))
    check("报告 JSON 含 citing_count=2", data and data[0]["citing_count"] == 2, str(data))

    print("测试 3: --force 写入")
    r2 = subprocess.run([sys.executable, str(Path(__file__).parent.parent / "cited_by_backfill.py"),
                         "--kb", str(kb), "--force"], capture_output=True, text=True, encoding="utf-8")
    check("force exit 0", r2.returncode == 0, r2.stderr)
    text = (kb / "经典" / "经典B.md").read_text(encoding="utf-8")
    check("经典B 含 cited_by", "cited_by:" in text, text)
    m = re.search(r"cited_by:\s*(\[.*?\])", text, re.M)
    check("cited_by 含 2 篇论文", m and "论文A" in m.group(1) and "论文C" in m.group(1), m.group(1) if m else "无")

    print("测试 4: 幂等（二次执行无变化）")
    r3 = subprocess.run([sys.executable, str(Path(__file__).parent.parent / "cited_by_backfill.py"),
                         "--kb", str(kb), "--force"], capture_output=True, text=True, encoding="utf-8")
    check("二次执行 exit 0", r3.returncode == 0, r3.stderr)
    check("二次执行无文件更新", "文件更新: 0" in r3.stdout, r3.stdout[-200:])

    print("测试 5: --targets 限定写入范围")
    # 构造目标库外引用：论文A 引用 经典B + 其他/外文X
    (papers := kb / "学术论文").mkdir(exist_ok=True)
    (papers / "论文D.md").write_text(
        "---\ntitle: 论文D\nrelated_classics: [\"../经典/经典B\", \"../其他/外文X\"]\n---\n正文D\n", encoding="utf-8")
    (kb / "其他").mkdir(exist_ok=True)
    (kb / "其他" / "外文X.md").write_text("---\ntitle: 外文X\n---\n外文\n", encoding="utf-8")
    r4 = subprocess.run([sys.executable, str(Path(__file__).parent.parent / "cited_by_backfill.py"),
                         "--kb", str(kb), "--targets", "经典", "--force"],
                        capture_output=True, text=True, encoding="utf-8")
    text_x = (kb / "其他" / "外文X.md").read_text(encoding="utf-8")
    check("--targets 限定后外部文件未被写", "cited_by" not in text_x, text_x)
    text_b = (kb / "经典" / "经典B.md").read_text(encoding="utf-8")
    check("限定后经典B 增加论文D 引用", "论文D" in text_b, text_b)

print(f"\n结果: {PASS} 通过 / {len(FAIL)} 失败")
sys.exit(1 if FAIL else 0)
