# -*- coding: utf-8 -*-
"""toc_parse.py 回归测试（教材体例适配 + 毛选兼容）
运行：python -m pytest scripts/__tests__/test_toc_parse.py 或直接 python 运行
"""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import toc_parse

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

print("=== 通道 A：目录页解析 ===")
# 毛选式：范围页码（不回归）
entries = toc_parse.parse_toc_page("实践论……25—26\n矛盾论……32", "")
check("毛选范围页码 25—26", any(e["title"] == "实践论" and e["book_start"] == 25 and e["book_end"] == 26 for e in entries))
# 教材式：单页码（斜杠 / 空格）
entries = toc_parse.parse_toc_page("第一章世界的物质性及发展规律/ 25\n第二章 实践与认识及其发展规律/69", "")
check("教材单页码 /25", any(e["title"].startswith("第一章") and e["book_start"] == 25 and e["book_end"] is None for e in entries))
check("教材单页码 69", any(e["title"].startswith("第二章") and e["book_start"] == 69 for e in entries))
# 空格章标题（纲要体例：第 一章）
entries = toc_parse.parse_toc_page("第 一章 进入近代后中华民族的磨难与抗争/ 13", "")
check("空格章标题清理", any(e["title"] == "第一章进入近代后中华民族的磨难与抗争" and e["book_start"] == 13 for e in entries))
# 罗马数字
entries = toc_parse.parse_toc_page("导论/I\n目录\n一、什么是马克思主义/ 2", "")
check("罗马数字 导论/I → 1", any(e["title"] == "导论" and e["book_start"] == 1 for e in entries))
check("目录页眉行跳过", all(e["title"] != "目录" for e in entries))
# OCR 空格清理
check("OCR空格清理", any(e["title"] == "第一章世界的物质性及发展规律" for e in toc_parse.parse_toc_page("第一章世界的物质性及发展规律/ 25", "")))
# 残行过滤（汉字计数）
entries = toc_parse.parse_toc_page("一、/ 2\n导论/ I", "")
check("1汉字残行 一、 过滤", not any(e["title"] == "一、" for e in entries))
check("2汉字 导论 保留", any(e["title"] == "导论" for e in entries))

print("=== 通道 B：正文标题扫描 ===")
pages = {
    "page_0009.txt": "导论\n学习目标\n……",
    "page_0011.txt": "导论 3\n……",   # 页眉：章名+书内页码
    "page_0013.txt": "导论 S\n……",   # 页眉：OCR 噪声页码
    "page_0035.txt": "第一章世界的物质性及发展规律\n学习目标\n……",
    "page_0100.txt": "25\n实践论\n正文……",  # 毛选模式：孤立页码+标题
    "page_0014.txt": "导言\n中国近现代史，是指1840年……",  # 纲要：导言
    "page_0026.txt": "第 一章 进入近代后中华民族的磨难与抗争\n在西方国家工业革命发生前……",  # 纲要：空格章标题
    "page_0019.txt": "6\n争、解放战争，以武装的革命反对武装的反革命，推翻帝国主义……",  # 正文句误扫场景
}
hits = toc_parse.scan_body_titles(pages, [{"start": 5, "end": 8, "volume": ""}])
by_pdf = {h["pdf_page"]: h for h in hits}
check("第一章扫描", by_pdf.get(35, {}).get("title", "").startswith("第一章"))
check("孤词 导论 扫描", by_pdf.get(9, {}).get("title") == "导论")
check("页眉 导论 3 过滤", 11 not in by_pdf)
check("页眉 导论 S 过滤", 13 not in by_pdf)
check("毛选孤立页码不回归", by_pdf.get(100, {}).get("title") == "实践论")
check("纲要 导言 扫描", by_pdf.get(14, {}).get("title") == "导言")
check("纲要 空格章标题 扫描", re.sub(r"\s", "", by_pdf.get(26, {}).get("title", "")).startswith("第一章"))
check("正文句含逗号 过滤", 19 not in by_pdf)

print("=== 合并 merge ===")
# 教材：B 无书内页码 → 标题匹配 A
res = toc_parse.merge(
    [{"title": "导论", "book_start": 1, "book_end": None, "volume": ""},
     {"title": "第一章世界的物质性及发展规律", "book_start": 25, "book_end": None, "volume": ""}],
    [{"title": "导论", "pdf_page": 9, "book_page": None},
     {"title": "第一章世界的物质性及发展规律", "pdf_page": 35, "book_page": None}])
works = {w["title"]: w for w in res["works"]}
check("教材 导论 标题匹配", works.get("导论", {}).get("book_start") == 1 and works["导论"]["pdf_start"] == 9)
check("教材 第一章 标题匹配", works.get("第一章世界的物质性及发展规律", {}).get("book_start") == 25)
# 截断标题前缀补全（纲要：跨行截断）
res = toc_parse.merge(
    [{"title": "第九章改革开放与中国特色社会主义的开创和发展", "book_start": 242, "book_end": None, "volume": ""}],
    [{"title": "第 九章 改革开放与中国特色社会主义的", "pdf_page": 255, "book_page": None}])
w = res["works"][0]
check("截断标题前缀补全", w["title"] == "第九章改革开放与中国特色社会主义的开创和发展" and w["book_start"] == 242)
# 毛选：按页码匹配
res = toc_parse.merge([{"title": "实践论", "book_start": 25, "book_end": 26, "volume": ""}],
                      [{"title": "实践论", "pdf_page": 100, "book_page": 25}])
w = res["works"][0]
check("毛选 页码匹配", w["book_start"] == 25 and w["book_end"] == 26)

print(f"\n=== 结果: {PASS} 通过, {len(FAIL)} 失败 ===")
if FAIL:
    print("失败项:", FAIL)
    sys.exit(1)
print("全部通过")
