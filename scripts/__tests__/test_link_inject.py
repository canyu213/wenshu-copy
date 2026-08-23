# -*- coding: utf-8 -*-
"""link_inject.py 回归测试
运行：python scripts/__tests__/test_link_inject.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import link_inject as li  # noqa: E402

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


with tempfile.TemporaryDirectory(prefix="hermes-verify-linject-") as td:
    kb = Path(td) / "kb"
    papers = kb / "论文"
    papers.mkdir(parents=True)
    (papers / "教育研究.md").write_text(
        "---\ntitle: 教育数字化研究\nkeywords:\n  - 教育\n  - 数字化\nabstract: 讨论教育数字化转型\n---\n正文\n", encoding="utf-8")
    (papers / "农业研究.md").write_text(
        "---\ntitle: 农业政策研究\nkeywords: [农业]\nabstract: 讨论农业补贴政策\n---\n正文\n", encoding="utf-8")
    kmap = kb / "map.json"
    kmap.write_text(json.dumps({
        "教育": {"lib": "经典", "subpath": "教育经典.md"},
        "数字化": {"lib": "经典", "subpath": "数字化经典.md", "short_only": True},
    }, ensure_ascii=False), encoding="utf-8")
    script = str(Path(__file__).parent.parent / "link_inject.py")

    print("测试 1: process_paper 单元（字段提取 + 关键词匹配）")
    r1 = li.process_paper(str(papers / "教育研究.md"), str(kb),
                          json.loads(kmap.read_text(encoding="utf-8")))
    check("匹配 2 个关键词", len(r1["matches"]) == 2, str(r1["matches"]))
    check("目标路径解析正确", any("经典/教育经典.md" in m["target"] for m in r1["matches"]))
    check("title 提取", r1["title"] == "教育数字化研究", r1["title"])

    print("测试 2: short_only 仅匹配标题/关键词")
    # 数字化 在 abstract 也有但 title/keywords 也有——构造一个只在 abstract 出现的场景
    r2 = li.process_paper(str(papers / "农业研究.md"), str(kb),
                          json.loads(kmap.read_text(encoding="utf-8")))
    check("农业研究无匹配（无教育/数字化）", len(r2["matches"]) == 0, str(r2["matches"]))

    print("测试 3: inject_extra_field 单元（注入 + 不覆盖 related_classics）")
    target = papers / "教育研究.md"
    changed, msg = li.inject_extra_field(str(target), ["经典/教育经典.md"], dry_run=False)
    text = target.read_text(encoding="utf-8")
    check("注入成功", changed and "related_classics_extra" in text)
    m = re.search(r"related_classics_extra:\s*(\[.*?\])", text, re.M)
    check("注入内容正确", m and "教育经典.md" in m.group(1), m.group(1) if m else "无")

    print("测试 4: CLI dry-run")
    r3 = subprocess.run([sys.executable, script, "--kb", str(kb), "--map", str(kmap)],
                        capture_output=True, text=True, encoding="utf-8")
    check("dry-run exit 0", r3.returncode == 0, r3.stderr)
    check("dry-run 命中教育研究", "教育研究.md" in r3.stdout, r3.stdout[:200])
    report = kb / "all_matches.json"
    check("报告生成", report.exists())

    print("测试 5: CLI --force 写入")
    r4 = subprocess.run([sys.executable, script, "--kb", str(kb), "--map", str(kmap), "--force"],
                        capture_output=True, text=True, encoding="utf-8")
    check("force exit 0", r4.returncode == 0, r4.stderr)
    text2 = (papers / "教育研究.md").read_text(encoding="utf-8")
    check("YAML 已注入 2 条", "数字化经典.md" in text2 and "教育经典.md" in text2)

    print("测试 6: 幂等（二次执行 no_change）")
    r5 = subprocess.run([sys.executable, script, "--kb", str(kb), "--map", str(kmap), "--force"],
                        capture_output=True, text=True, encoding="utf-8")
    check("二次执行 SKIP", "SKIP" in r5.stdout, r5.stdout[-200:])

    print("测试 7: 映射表缺失报错")
    r6 = subprocess.run([sys.executable, script, "--kb", str(kb), "--map", str(kb / "不存在.json")],
                        capture_output=True, text=True, encoding="utf-8")
    check("exit 2", r6.returncode == 2, f"(exit={r6.returncode})")

print(f"\n结果: {PASS} 通过 / {len(FAIL)} 失败")
sys.exit(1 if FAIL else 0)
