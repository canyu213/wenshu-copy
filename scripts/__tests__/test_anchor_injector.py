# -*- coding: utf-8 -*-
"""anchor_injector.py 回归测试
运行：python scripts/__tests__/test_anchor_injector.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import anchor_injector as ai  # noqa: E402

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


print("测试 1: 段落切分")
text = "第一段。" + "长" * 100 + "第二段内容。"
paras = ai.split_paragraphs(text, max_len=90)
check("长文按 max_len 切分", len(paras) >= 2, str(len(paras)))
check("短段不切", ai.split_paragraphs("短段落。", 90) == ["短段落。"])

print("测试 2: 锚点构建")
check("格式 ^wsp0001", ai.build_anchor("ws", 1) == "^wsp0001", ai.build_anchor("ws", 1))
check("宽度 3", ai.build_anchor("ws", 1, width=3) == "^wsp001", ai.build_anchor("ws", 1, width=3))

print("测试 3: 注入")
out, anchors = ai.inject_anchors_to_text("甲" * 50 + "。" + "乙" * 50 + "。", "ws")
check("锚点数=2", len(anchors) == 2, str(anchors))
check("锚点格式正确", anchors == ["^wsp0001", "^wsp0002"], str(anchors))
check("文本含锚点行", "^wsp0001" in out and "^wsp0002" in out)

print("测试 4: 校验通过")
with tempfile.TemporaryDirectory(prefix="hermes-verify-anch-") as td:
    p = Path(td) / "测试.md"
    p.write_text(out, encoding="utf-8")
    report = ai.check_anchors(p)
    check("校验报告 ok 且锚点数=2", report.get("ok") is True and report.get("anchors") == 2,
          str(report)[:120])

print("测试 5: CLI 冒烟")
script = str(Path(__file__).parent.parent / "anchor_injector.py")
r = subprocess.run([sys.executable, script, "--help"], capture_output=True, text=True, encoding="utf-8")
check("--help exit 0", r.returncode == 0, r.stderr[:100])

print(f"\n结果: {PASS} 通过 / {len(FAIL)} 失败")
sys.exit(1 if FAIL else 0)
