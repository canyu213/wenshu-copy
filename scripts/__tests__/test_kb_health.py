# -*- coding: utf-8 -*-
"""kb_health.py 回归测试
运行：python scripts/__tests__/test_kb_health.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import kb_health  # noqa: E402

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
    lib = root / "文献"
    lib.mkdir(parents=True)
    (lib / "正常.md").write_text("---\ntitle: 正常\ntags: [a, b]\n---\n正文\n", encoding="utf-8")
    (lib / "坏YAML.md").write_text("---\ntitle: 坏YAML\ntags: [a]\n正文无闭合\n", encoding="utf-8")
    (lib / "坏tags.md").write_text("---\ntitle: 坏tags\ntags: 逗号字符串\n---\n正文\n", encoding="utf-8")
    (lib / "死链.md").write_text("---\ntitle: 死链\ntags: [a]\n---\n引用 [[不存在的文件]]\n", encoding="utf-8")
    (lib / "好链.md").write_text("---\ntitle: 好链\ntags: [a]\n---\n引用 [[正常]]\n", encoding="utf-8")
    return root


with tempfile.TemporaryDirectory(prefix="hermes-verify-kbh-") as td:
    kb = make_fake_kb(Path(td))
    script = str(Path(__file__).parent.parent / "kb_health.py")

    print("测试 1: 单元级（scan_yaml）")
    yaml_results = kb_health.scan_yaml(kb, None)
    paths = [p for p, _ in yaml_results]
    check("yaml 检出坏YAML（未闭合）", "坏YAML.md" in str(paths), str(paths))
    check("yaml 检出坏tags（非数组）", "坏tags.md" in str(paths))
    check("yaml 不误报正常文件", "正常.md" not in str(paths))

    print("测试 2: 单元级（scan_links）")
    total, dead = kb_health.scan_links(kb, None)
    check("links 检出死链目标", any(t == "不存在的文件" for t, _ in dead), str(dead))
    check("links 正常链接不报", not any(t == "正常" for t, _ in dead))
    check("links 总链接数 ≥ 2", total >= 2, str(total))

    print("测试 3: CLI yaml 子命令")
    r = subprocess.run([sys.executable, script, "--kb", str(kb), "yaml"],
                       capture_output=True, text=True, encoding="utf-8")
    check("exit 1（有问题）", r.returncode == 1, f"(exit={r.returncode})")
    check("报告含 2 个问题文件", "2 个文件有问题" in r.stdout, r.stdout[:200])

    print("测试 4: CLI tags 子命令（--forbidden）")
    (kb / "文献" / "带缩写.md").write_text(
        "---\ntitle: 带缩写\ntags: [#思政]\n---\n正文\n", encoding="utf-8")
    r2 = subprocess.run([sys.executable, script, "--kb", str(kb), "tags",
                         "--forbidden", "思政=思想政治教育"],
                        capture_output=True, text=True, encoding="utf-8")
    check("exit 1（命中禁用）", r2.returncode == 1, f"(exit={r2.returncode})")
    check("报告含思政命中", "思政" in r2.stdout and "思想政治教育" in r2.stdout, r2.stdout[:200])

    print("测试 5: CLI links 子命令")
    r3 = subprocess.run([sys.executable, script, "--kb", str(kb), "links"],
                        capture_output=True, text=True, encoding="utf-8")
    check("exit 1（有死链）", r3.returncode == 1, f"(exit={r3.returncode})")
    check("报告含死链目标", "不存在的文件" in r3.stdout, r3.stdout[:200])

    print("测试 6: 干净库全过")
    clean = Path(td) / "clean"
    (clean / "好").mkdir(parents=True)
    (clean / "好" / "a.md").write_text("---\ntitle: a\ntags: [x]\n---\n正文 [[a]]\n", encoding="utf-8")
    r4 = subprocess.run([sys.executable, script, "--kb", str(clean), "links"],
                        capture_output=True, text=True, encoding="utf-8")
    check("干净库 links exit 0", r4.returncode == 0, f"(exit={r4.returncode}) {r4.stdout[-100:]}")

print(f"\n结果: {PASS} 通过 / {len(FAIL)} 失败")
sys.exit(1 if FAIL else 0)
