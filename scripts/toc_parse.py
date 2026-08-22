#!/usr/bin/env python3
"""toc_parse.py — 文枢通用入库流程 S2：目录解析（双通道）

从 pdf_extract.py 输出的 page_*.txt 解析篇目清单：
  通道 A：目录页解析（定位每卷目录区间 → 篇目 + 页码范围 + 卷归属）
  通道 B：正文标题扫描（孤立页码 + 标题行 → 篇目起始页）
  合并：A 骨架 + B 校正/补漏，冲突标"需人工确认"

用法：
    python toc_parse.py --input 提取目录 --output 清单.json [--verbose]

输出：
    <output>.json                篇目清单 [{title, volume, book_start, book_end}]
    <output>_report.json         双通道对比报告
"""
import argparse
import json
import pathlib
import re

# ========== 目录页识别 ==========

# 目录行：纯"目录" 或 "目 录 N"（带页码）
DIRECTORY_RE = re.compile(r"^(目\s*录|目录)(?:\s*\d{1,3})?\s*$")
PERIOD_RE = re.compile(r"([一-龥]{2,12}(?:战争|革命|建设)时期)")
VOL_RE = re.compile(r"第[一二三四五]卷")

# 篇目行：篇名（年份）…… 页码范围；容忍 OCR 空格
PAGE_RANGE_RE = re.compile(r"(\d[\d ]*)\s*(?:—|–|-)\s*(\d{1,4})\s*$")
# 教材/单页码目录：标题/ 25 或 标题 25（尾部单阿拉伯或罗马数字）
SINGLE_PAGE_RE = re.compile(r"(?:/|・|\s)\s*([0-9IVXLivxl]{1,4})\s*$")
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6,
         "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12}
# 教材章标题：导言/导论/绪论/结语/第X章（容忍"第 一章"OCR/排版空格；章名后可有标题或孤词"导言"）
CHAPTER_RE = re.compile(r"^(导言|导论|绪论|结语|前言|第\s*[一二三四五六七八九十百]+\s*章)(?:\s*\S.*)?$")
TOC_HEADER_RE = re.compile(r"^(目录|目\s*录)(\s*[ivxlIVXL\d]*)?$")

# 页眉：页码 + 书名选集 + 时期/卷
HEADER_RE = re.compile(r"^\d+\s*[^\s\n]{1,12}选[集栠粲桀]*\s*(?:第[一二三四五]\s*卷)?[^\n]*$")


def norm_num(s: str) -> int:
    return int(re.sub(r"\s", "", s))


def is_toc_page(text: str) -> bool:
    """判断是否目录页：首行是'目录'(可带页码) 或 页内含'目录'+篇目行特征。"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return False
    if DIRECTORY_RE.match(lines[0]):
        return True
    # 页首含"书名选集X第X卷"（目录页眉）+ 页内有页码范围行
    if len(lines) > 2 and re.search(r"目录", lines[0]):
        return True
    return False


def _page_num(pname: str) -> int:
    """从 'page_0001.txt' 提取页码。"""
    m = re.search(r"page_(\d+)\.txt", pname)
    return int(m.group(1)) if m else 0


def find_toc_ranges(pages: dict) -> list[dict]:
    """扫描全部页，定位目录区间（可能多卷各自有目录）。
    返回 [{start, end, volume}]，按 start 排序。"""
    # 候选目录页
    cands = []
    for pname, text in sorted(pages.items()):
        pg = _page_num(pname)
        if is_toc_page(text):
            cands.append(pg)

    # 合并连续候选页为区间（间隔 ≤ 3 视为同一目录）
    ranges = []
    for pg in cands:
        if ranges and pg - ranges[-1]["end"] <= 3:
            ranges[-1]["end"] = pg
        else:
            ranges.append({"start": pg, "end": pg})

    # 识别卷：目录区间前最近的"第X卷"扉页/页眉
    for rng in ranges:
        rng["volume"] = detect_volume(pages, rng["start"])
    return ranges


def detect_volume(pages: dict, toc_start: int) -> str:
    """从目录区间前几页找卷号（扉页'第X卷'或目录页眉）。"""
    for pg in range(toc_start - 1, max(1, toc_start - 8), -1):
        pname = f"page_{pg:04d}.txt"
        text = pages.get(pname, "")
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        for l in lines[:5]:
            m = VOL_RE.search(l)
            if m:
                return m.group(0)
    return ""


# ========== 通道 A：目录页解析 ==========

def parse_toc_page(text: str, volume: str) -> list[dict]:
    """解析单个目录页 → 篇目条目 [{title, book_start, book_end}]。
    支持两种格式：毛选式范围页码（标题…25—26）与教材式单页码（标题/ 25 或 导论/I）。"""
    entries = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines:
        # 跳过目录页页眉（"目录"/"iii 目录"/"目录 iv"）
        if TOC_HEADER_RE.match(line):
            continue
        # 目录行尾错位章号（OCR："邓小平理论/ 150第六章"）→ 前移为"第六章邓小平理论/ 150"
        m_ch = re.search(r"(第[一二三四五六七八九十百]+章)\s*$", line)
        if m_ch and not re.match(r"^(导言|导论|绪论|结语|前言|第\s*[一二三四五六七八九十百]+\s*章)", line):
            line = m_ch.group(1) + line[:m_ch.start()].rstrip()
        m = PAGE_RANGE_RE.search(line)
        if m:
            start, end = norm_num(m.group(1)), int(m.group(2))
            if end < start or end - start > 400:
                continue
            title = clean_toc_title(line)
            if len(title) < 3:
                continue
            entries.append({"title": title, "book_start": start, "book_end": end,
                            "volume": volume})
            continue
        # 教材式单页码（数字或罗马数字）
        m2 = SINGLE_PAGE_RE.search(line)
        if m2:
            pg = m2.group(1)
            if pg.isdigit():
                start = int(pg)
            elif pg.lower() in ROMAN:
                start = ROMAN[pg.lower()]
            else:
                continue
            title = clean_toc_title_single(line, pg)
            # 残行过滤：按汉字计数（"导论"2 汉字通过，"一、"1 汉字过滤）
            if len(re.findall(r"[\u4e00-\u9fff]", title)) < 2:
                continue
            entries.append({"title": title, "book_start": start, "book_end": None,
                            "volume": volume})
    return entries


def clean_toc_title_single(line: str, pg: str) -> str:
    """教材目录行清理：去尾部' / 页码'、去省略号、压缩 OCR 空格。"""
    t = re.sub(r"(?:/|・|\s)+\s*" + re.escape(pg) + r"\s*$", "", line)
    t = re.sub(r"[…．．．·…]+.*$", "", t)
    t = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", t)
    return t.strip()


def clean_toc_title(line: str) -> str:
    """清理目录行篇名：去省略号、去尾部页码、压缩 OCR 空格。"""
    t = re.sub(r"[…．．．·…]+.*$", "", line)
    t = re.sub(r"[\d ]+\s*(?:—|–|-)\s*[\d ]+\s*$", "", t)
    # 压缩中文间空格（OCR 产生）
    t = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", t)
    return t.strip()


# ========== 通道 B：正文标题扫描（独立精确扫描） ==========

def scan_body_titles(pages: dict, toc_ranges: list[dict]) -> list[dict]:
    """扫描正文页：孤立页码行 + 下一行短中文标题（独立扫描，提取完整篇名）。
    规则：页首孤立数字（书内页码）+ 下一行中文标题（≤35字、不以句号结尾、
    不含页眉）。返回 [{title, pdf_page, book_page}]。"""
    toc_pages = set()
    for r in toc_ranges:
        toc_pages.update(range(r["start"], r["end"] + 1))

    hits = []
    for pname, text in sorted(pages.items()):
        pg = _page_num(pname)
        if pg in toc_pages:
            continue
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if len(lines) < 2:
            continue
        # 教材模式：页首为章标题（导言/第X章 等），无需孤立页码行。
        # 标题可带紧贴页码（页眉样式，如"第四章…成果96"）——清洗去页码，merge 去重保留最早页。
        first = lines[0]
        if CHAPTER_RE.match(first):
            title = re.sub(r"[\dSIVXLivxl]{1,4}$", "", first).strip()
            if (not (2 <= len(title) <= 35)
                    or re.search(r"[。！？；．，、]$", title)
                    or "选集" in title or "全集" in title):
                continue
            hits.append({"title": title, "pdf_page": pg, "book_page": None})
            continue
        # 原毛选模式：孤立页码行 + 下一行短中文标题
        if not re.fullmatch(r"\d{1,4}", lines[0]):
            continue
        title = lines[1]
        # 标题特征：中文开头、3-35字、不以句号/问号/点号结尾、非页眉、不含句中标点（防正文句误扫）
        if not title or "选集" in title or "全集" in title:
            continue
        if re.search(r"[。！？；．，、：]$", title):
            continue
        if not re.match(r"^[\u4e00-\u9fff《》]", title):
            continue
        if re.search(r"[，、；：]", title):  # 正文句含逗号/顿号 → 非标题
            continue
        if not (3 <= len(title) <= 35):
            continue
        hits.append({"title": title, "pdf_page": pg, "book_page": int(lines[0])})
    return hits


# ========== 合并 ==========

def merge(toc_entries: list[dict], body_hits: list[dict],
          toc_ranges: list[dict] = None) -> dict:
    """合并双通道结果。
    body_hits（通道 B）：完整篇名 + 起始页 → 权威骨架
    toc_entries（通道 A）：页码范围（book_start/book_end）+ 卷归属 → 补充
    合并：B 的篇名 + A 的页码范围/卷；B 无匹配范围的保留（范围 S4 推算）。
    返回 {works, conflicts, report}。"""
    # 通道 A 页码索引：book_start → 条目
    a_by_start = {}
    for e in toc_entries:
        a_by_start.setdefault(e["book_start"], []).append(e)
    # 通道 A 标题索引（教材场景：B 只给 pdf_page，靠标题匹配 A 的书内页码）
    a_by_title = {}
    for e in toc_entries:
        key = re.sub(r"[\s/]+", "", e["title"])
        a_by_title.setdefault(key, []).append(e)

    works = []
    used_a = set()
    for h in body_hits:
        title = re.sub(r"[．。，、＊*]+$", "", h["title"]).strip()
        book_start = h["book_page"]
        fuzzy_hit = False
        # 教材场景：B 无书内页码 → 标题匹配 A（精确→前缀→模糊）
        match = None
        if book_start is None:
            key = re.sub(r"[\s/]+", "", title)
            cands = a_by_title.get(key, [])
            if not cands:
                # 前缀匹配：B 为跨行截断标题，A 完整标题以 B 开头
                for a_key, a_cands in a_by_title.items():
                    if a_key.startswith(key):
                        cands = a_cands
                        break
            if not cands:
                # 模糊匹配：OCR 变体标题（如"毛泽东思血"→"毛泽东思想"），同前缀内相似度>0.6
                import difflib
                best, best_r = None, 0.6
                for a_key, a_cands in a_by_title.items():
                    r = difflib.SequenceMatcher(None, a_key, key).ratio()
                    if a_key[:2] == key[:2] and r > best_r:
                        best, best_r = a_cands, r
                if best:
                    cands = best
                    fuzzy_hit = True
            if cands:
                match = cands[0]
        else:
            # 原毛选场景：按起始页匹配（精确或 ±2 内）
            for delta in range(0, 3):
                for e in a_by_start.get(book_start + delta, []):
                    match = e
                    break
                if match:
                    break
        if match:
            used_a.add(id(match))
            # 标题补全：B 截断（B 是 A 前缀）或 OCR 变体（模糊命中）→ 用 A 完整标题
            a_t = re.sub(r"[\s/]+", "", match["title"])
            b_t = re.sub(r"[\s/]+", "", title)
            if (a_t.startswith(b_t) and len(a_t) > len(b_t)) or fuzzy_hit:
                title = match["title"]
            works.append({
                "title": title,
                "volume": match["volume"],
                "book_start": match["book_start"],
                "book_end": match["book_end"],
                "pdf_start": h["pdf_page"],
            })
        else:
            # 无范围匹配：保留，范围留空（S4 用下一篇推算）
            works.append({
                "title": title,
                "volume": "",
                "book_start": book_start,
                "book_end": None,
                "pdf_start": h["pdf_page"],
            })

    # 通道 A 中未被 B 匹配的条目：只贡献页码范围，不产生新篇名。
    # （A 的目录行篇名残缺，不是可靠来源；B 未扫到的篇目由 S4 用
    #  "下一篇起始页" 推算，或质量门人工补充。）

    # 卷推断：volume 为空的，按 pdf_start 落在哪个目录区间后归属
    toc_ranges_sorted = sorted(toc_ranges or [], key=lambda x: x["start"])
    for w in works:
        if w.get("volume"):
            continue
        anchor = w.get("pdf_start") or (w.get("book_start", 0) + 0)
        vol = ""
        for rng in toc_ranges_sorted:
            if anchor and anchor >= rng["start"]:
                vol = rng["volume"]
        w["volume"] = vol

    works.sort(key=lambda x: (x.get("book_start") or 0))
    # 去重：同标题（去空白）保留 pdf_start 最早（教材页眉重复场景：章标题每页出现）
    seen = {}
    for w in works:
        key = re.sub(r"[\s/]+", "", w["title"])
        if key not in seen or w.get("pdf_start", 99999) < seen[key].get("pdf_start", 99999):
            seen[key] = w
    works = list(seen.values())
    works.sort(key=lambda x: (x.get("book_start") or 0))

    report = {
        "toc_entries": len(toc_entries),
        "body_hits": len(body_hits),
        "merged": len(works),
        "matched": len([w for w in works if w.get("book_end")]),
        "unmatched": len([w for w in works if not w.get("book_end")]),
        "conflicts": [],
    }
    return {"works": works, "report": report}


def main():
    parser = argparse.ArgumentParser(description="文枢 S2：目录解析（双通道 + 单篇模式）")
    parser.add_argument("--input", required=True, help="提取目录（含 page_*.txt）")
    parser.add_argument("--output", required=True, help="输出 JSON 路径")
    parser.add_argument("--single", metavar="标题", nargs="?", const="__auto__",
                        help="单篇/少量文献模式：整篇=1 篇（省略标题则自动取首页标题）")
    parser.add_argument("--min-works", type=int, default=5,
                        help="篇目数下限哨兵（默认 5；单篇/小批文献用 --single 或调低）")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    in_dir = pathlib.Path(args.input)
    pages = {}
    for f in sorted(in_dir.glob("page_*.txt")):
        pages[f.name] = f.read_text(encoding="utf-8")
    print(f"[加载] {len(pages)} 页")

    # 通道 C：单篇模式（整篇 = 1 篇，偏移 0）
    if args.single is not None:
        if args.single == "__auto__":
            # 自动取首页非空标题行（过滤期刊页眉：表格管道符/期卷号/纯数字）
            first = pages.get("page_0001.txt", "")
            title = ""
            for line in first.splitlines():
                line = line.strip()
                if not line or re.match(r"^[\d\s]+$", line):
                    continue
                if "|" in line or re.search(r"(总第\d+期|年第\d+期|第\d+卷|第\d+期)", line):
                    continue
                if 3 <= len(line) <= 40:
                    title = re.sub(r"[＊*．。]+$", "", line)
                    break
            if not title:
                raise SystemExit("[FAIL] --single 自动取标题失败，请显式传入标题")
        else:
            title = args.single
        works = [{
            "title": title,
            "volume": "未分卷",
            "book_start": 1,
            "book_end": len(pages),
            "pdf_start": 1,
        }]
        report = {"mode": "single", "toc_entries": 0, "body_hits": 1,
                  "merged": 1, "matched": 1, "unmatched": 0, "conflicts": []}
        print(f"[单篇] {title}（{len(pages)} 页，整篇 = 1 篇）")
    else:
        # 定位目录区间
        toc_ranges = find_toc_ranges(pages)
        print(f"[目录] 定位到 {len(toc_ranges)} 个目录区间")
        for r in toc_ranges:
            print(f"  {r['volume'] or '?'} 目录: 页 {r['start']}-{r['end']}")

        # 通道 A
        toc_entries = []
        for r in toc_ranges:
            for pg in range(r["start"], r["end"] + 1):
                toc_entries.extend(parse_toc_page(pages.get(f"page_{pg:04d}.txt", ""), r["volume"]))
        print(f"[通道A] 目录解析 {len(toc_entries)} 条")

        # 通道 B：正文标题扫描（独立精确扫描，提取完整篇名）
        body_hits = scan_body_titles(pages, toc_ranges)
        print(f"[通道B] 正文标题扫描 {len(body_hits)} 条")

        # 合并
        result = merge(toc_entries, body_hits, toc_ranges)
        works = result["works"]
        report = result["report"]

    # 输出
    out = pathlib.Path(args.output)
    out.write_text(json.dumps(works, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = out.with_name(out.stem + "_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"\n[合并] {len(works)} 篇（正文标题 {report.get('body_hits', 0)} + 目录补充，"
          f"有范围 {report.get('matched', 0)} / 无范围 {report.get('unmatched', 0)}）")
    print(f"清单: {out}")
    print(f"报告: {report_path}")

    # 质量门：篇目数阈值（--single 跳过；--min-works 可调）
    if args.single is None and len(works) < args.min_works:
        raise SystemExit(f"[FAIL] 篇目数 {len(works)} < {args.min_works}，目录解析失败"
                         f"（单篇/小批文献请用 --single，或调低 --min-works）")
    print(f"[OK] 篇目数 {len(works)} ≥ {args.min_works if args.single is None else 1}")


if __name__ == "__main__":
    main()
