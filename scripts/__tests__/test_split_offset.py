# -*- coding: utf-8 -*-
"""split_works.py + offset_detect.py 回归测试
运行：python scripts/__tests__/test_split_offset.py
"""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import split_works as sw  # noqa: E402
import offset_detect as od  # noqa: E402

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


print("测试 1: detect_headers（split_works）")
pages = {
    "1": "目 录\n第一篇 导言\n第二篇 正文",
    "2": "第一篇 导言\n第一段正文内容",
    "3": "第二篇 正文\n更多正文",
}
headers = sw.detect_headers(pages, min_ratio=0.2, min_count=2)
check("检出重复标题（去空格）", "第一篇导言" in headers and "第二篇正文" in headers, str(headers))

print("测试 2: clean_page（去页眉）")
cleaned = sw.clean_page("第一篇 导言\n正文段落", headers)
check("去页眉保留正文", "正文段落" in cleaned and "第一篇" not in cleaned, cleaned[:50])

print("测试 3: compute_ranges")
works = [{"title": "甲", "volume": 1, "pdf_start": 1, "pdf_end": 10},
         {"title": "乙", "volume": 1, "pdf_start": 11, "pdf_end": 20}]
ranges = sw.compute_ranges(works, {1: 0}, total_pages=20)
check("范围计算", len(ranges) == 2, str(ranges))
check("乙起点=11", ranges[1].get("pdf_start") == 11, str(ranges[1]))

print("测试 4: detect_offsets（offset_detect）")
offset_works = [{"title": "甲", "vol": 1, "start": 3, "end": 5},
                {"title": "乙", "vol": 1, "start": 6, "end": 8}]
offsets = od.detect_offsets(offset_works)
check("返回 (config, report) 元组", isinstance(offsets, tuple) and len(offsets) == 2, str(offsets)[:80])

print("测试 5: CLI 冒烟")
for mod in ("split_works", "offset_detect"):
    r = subprocess.run([sys.executable, str(Path(__file__).parent.parent / f"{mod}.py"), "--help"],
                       capture_output=True, text=True, encoding="utf-8")
    check(f"{mod} --help exit 0", r.returncode == 0, r.stderr[:100])

print(f"\n结果: {PASS} 通过 / {len(FAIL)} 失败")
sys.exit(1 if FAIL else 0)
