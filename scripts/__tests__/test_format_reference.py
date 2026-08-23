# -*- coding: utf-8 -*-
"""format_reference.py 回归测试（期刊/专著格式 + 作者处理）
运行：python scripts/__tests__/test_format_reference.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import format_reference as fr  # noqa: E402

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


print("测试 1: 作者格式化")
check("单作者", fr.format_authors(["张三"]) == "张三", fr.format_authors(["张三"]))
check("多作者逗号（GB/T）", fr.format_authors(["张三", "李四"]) == "张三，李四",
      fr.format_authors(["张三", "李四"]))
check("西方作者", fr.western_author_name("Marx, Karl") == "Marx K", fr.western_author_name("Marx, Karl"))

print("测试 2: 期刊引文渲染")
item = {
    "title": "思想政治教育数字化转型研究",
    "authors": ["张三"],
    "journal": "思想理论教育",
    "year": "2025",
    "issue": "3",
    "pages": "12-18",
    "type": "journal",
}
out = fr.render_item(item, 1)
check("含题名", "思想政治教育数字化转型研究" in out, out)
check("含期刊名", "思想理论教育" in out)
check("含年(期)", "2025(3)" in out, out)
check("含页码", "12-18" in out)

print("测试 3: 专著引文渲染")
book = {"title": "实践论", "authors": ["毛泽东"], "publisher": "人民出版社",
        "year": "1991", "type": "book"}
out2 = fr.render_item(book, 2)
check("含出版社", "人民出版社" in out2, out2)
check("含编号 [2]", "[2]" in out2.split("\n")[0], out2.split("\n")[0])

print("测试 4: 清理函数")
check("去尾句号", fr.strip_trailing_period("引文。") == "引文", fr.strip_trailing_period("引文。"))
check("标题清理", fr.title_for_reference(" 题名 ") == "题名", fr.title_for_reference(" 题名 "))

print("测试 5: CLI 冒烟")
script = str(Path(__file__).parent.parent / "format_reference.py")
r = subprocess.run([sys.executable, script, "--help"], capture_output=True, text=True, encoding="utf-8")
check("--help exit 0", r.returncode == 0, r.stderr[:100])

print(f"\n结果: {PASS} 通过 / {len(FAIL)} 失败")
sys.exit(1 if FAIL else 0)
