#!/usr/bin/env python3
"""split_works.py — 文枢通用入库流程 S4：分篇切分（卷感知）

从 toc_manifest.json + offset_config.json 切出每篇正文：
  页码换算（卷感知）：PDF页 = book页 + 该卷偏移
  无 book_end 的篇：用"下一篇起始页 - 1"推算
  每页清理：去页眉/孤立页码，保留自然段落

用法：
    python split_works.py --toc toc_manifest.json --offset offset_config.json \
        --extracted 提取目录 --output split_works.json

输出：
    split_works.json    [{title, volume, pdf_start, pdf_end, book_start, book_end,
                           pages: [{book_page, text}]}]
    <output>_report.json  统计报告
"""
import argparse
import json
import pathlib
import re
from collections import Counter


def detect_headers(pages: dict, min_ratio: float = 0.3, min_count: int = 2) -> set[str]:
    """跨页高频行检测（期刊页眉：刊名/期号/卷号逐页重复）。

    规范化：去空白、去表格管道符与边框；行长度 4-60 字且非纯数字。
    出现 ≥ max(min_count, 总页数×min_ratio) 次 → 判为页眉。
    min_count=2：小文件（3-5 页单篇论文）页眉在多数页出现即可识别；
    正文短句跨页逐字重复罕见，误判风险低。
    """
    counts = Counter()
    for text in pages.values():
        for line in text.splitlines():
            norm = re.sub(r"[\s|┃│—-]+", "", line).strip()
            if 4 <= len(norm) <= 60 and not re.fullmatch(r"\d{1,4}", norm):
                counts[norm] += 1
    threshold = max(min_count, int(len(pages) * min_ratio))
    return {line for line, c in counts.items() if c >= threshold}


HEADER_RE = re.compile(r"^\d+\s*毛泽东选[集栠粲桀]*\s*(?:第[一二三四五]\s*卷)?[^\n]*\n")


def clean_page(text: str, headers: set[str] | None = None) -> str:
    """清理单页：去页眉（毛选硬编码 + 跨页高频行）、去孤立页码行、保留自然段落。"""
    t = text.strip()
    t = HEADER_RE.sub("", t, count=1)
    if headers:
        kept = []
        for line in t.split("\n"):
            norm = re.sub(r"[\s|┃│—-]+", "", line).strip()
            if norm in headers:
                continue
            kept.append(line)
        t = "\n".join(kept)
    lines = t.split("\n")
    if lines and lines[0].strip().isdigit():
        lines = lines[1:]
    while lines and lines[-1].strip().isdigit():
        lines = lines[:-1]
    # 合并连续空行为单空行
    out, prev_blank = [], False
    for l in lines:
        if not l.strip():
            if not prev_blank:
                out.append("")
            prev_blank = True
        else:
            out.append(l)
            prev_blank = False
    return "\n".join(out).strip()


def compute_ranges(works: list[dict], vol_offset: dict, total_pages: int) -> list[dict]:
    """计算每篇 PDF 页范围 + 书内页码。无 book_end 用下一篇推算。
    优先以 pdf_start（通道 B 正文页号）为锚；book 页码仅作锚点参考。"""
    # 先按 pdf_start 排序（用于推算）
    sorted_works = sorted(works, key=lambda w: (w.get("pdf_start") or 0))

    result = []
    for i, w in enumerate(sorted_works):
        vol = w.get("volume") or ""
        offset = vol_offset.get(vol, 0)
        book_start = w.get("book_start")
        book_end = w.get("book_end")
        pdf_start = w.get("pdf_start")

        # PDF 起始页：优先用 S2 已提取的 pdf_start，否则换算
        if not pdf_start and book_start is not None:
            pdf_start = book_start + offset

        # 下一篇 pdf_start（用于推算本篇结束）
        nxt_pdf_start = None
        for j in range(i + 1, len(sorted_works)):
            w2 = sorted_works[j]
            if w2.get("pdf_start"):
                nxt_pdf_start = w2["pdf_start"]
                break
        boundary_end = (nxt_pdf_start - 1) if nxt_pdf_start else total_pages

        # PDF 结束页：换算值 与 下一篇边界 取更小者（避免重叠）
        if book_end is not None:
            pdf_end_calc = book_end + offset
        else:
            pdf_end_calc = None
        if pdf_end_calc is not None:
            pdf_end = min(pdf_end_calc, boundary_end)
        else:
            pdf_end = boundary_end

        # 校正书内页码（供锚点）
        if book_start is None and pdf_start:
            book_start = pdf_start - offset
        if book_end is None:
            book_end = pdf_end - offset

        result.append({
            "title": w["title"],
            "volume": vol,
            "pdf_start": pdf_start,
            "pdf_end": pdf_end,
            "book_start": book_start,
            "book_end": book_end,
        })
    return result


def load_pages(extracted: pathlib.Path) -> dict:
    """加载全部提取页 → {pdf_page: text}。"""
    pages = {}
    for f in sorted(extracted.glob("page_*.txt")):
        m = re.search(r"page_(\d+)\.txt", f.name)
        if m:
            pages[int(m.group(1))] = f.read_text(encoding="utf-8")
    return pages


def split_work(w: dict, pages: dict, total_pages: int, headers: set[str] | None = None) -> dict:
    """切出单篇：逐页清理 + 页码锚点信息。"""
    out_pages = []
    empty_blocks = 0
    for pg in range(w["pdf_start"], w["pdf_end"] + 1):
        if pg > total_pages:
            break
        text = pages.get(pg, "")
        body = clean_page(text, headers)
        if not body:
            empty_blocks += 1
            continue
        out_pages.append({"book_page": pg - w["pdf_start"] + w["book_start"],
                          "text": body})
    return {**w, "pages": out_pages, "empty_blocks": empty_blocks}


def validate(works: list[dict], total_pages: int) -> list[str]:
    """校验：范围重叠/越界/空篇。"""
    errors = []
    prev_end = 0
    for w in sorted(works, key=lambda x: x["pdf_start"]):
        if w["pdf_start"] is None or w["pdf_end"] is None:
            errors.append(f"[{w['title']}] 页范围缺失")
            continue
        if w["pdf_start"] < 1 or w["pdf_end"] > total_pages:
            errors.append(f"[{w['title']}] 页范围越界 {w['pdf_start']}-{w['pdf_end']}")
        if w["pdf_start"] <= prev_end:
            errors.append(f"[{w['title']}] 与上一篇重叠（start {w['pdf_start']} ≤ prev_end {prev_end}）")
        prev_end = w["pdf_end"]
        if not w["pages"]:
            errors.append(f"[{w['title']}] 空篇")
    return errors


def main():
    parser = argparse.ArgumentParser(description="文枢 S4：分篇切分（卷感知）")
    parser.add_argument("--toc", required=True, help="toc_manifest.json")
    parser.add_argument("--offset", required=True, help="offset_config.json")
    parser.add_argument("--extracted", required=True, help="提取目录")
    parser.add_argument("--output", required=True, help="输出 split_works.json")
    args = parser.parse_args()

    works = json.loads(pathlib.Path(args.toc).read_text(encoding="utf-8"))
    vol_offset = json.loads(pathlib.Path(args.offset).read_text(encoding="utf-8"))
    pages = load_pages(pathlib.Path(args.extracted))
    total_pages = len(pages)
    print(f"[加载] {len(works)} 篇，{total_pages} 页")

    # 跨页高频行检测（期刊页眉剥离）
    headers = detect_headers(pages)
    if headers:
        print(f"[页眉] 检测到 {len(headers)} 条高频行（跨页重复，将剥离）：")
        for h in sorted(headers)[:5]:
            print(f"    {h[:40]}")
    else:
        print("[页眉] 未检测到跨页高频行")

    ranged = compute_ranges(works, vol_offset, total_pages)
    split = [split_work(w, pages, total_pages, headers) for w in ranged]

    errors = validate(split, total_pages)
    if errors:
        for e in errors[:20]:
            print(f"[FAIL] {e}")
        raise SystemExit(f"S4 校验未通过：{len(errors)} 个问题（前 20 已列出）")

    # 统计
    total_chars = sum(len("".join(p["text"] for p in w["pages"])) for w in split)
    total_empty = sum(w["empty_blocks"] for w in split)
    print(f"[OK] {len(split)} 篇切分完成，总字数 {total_chars}，空块 {total_empty}")

    out = pathlib.Path(args.output)
    out.write_text(json.dumps(split, ensure_ascii=False, indent=1), encoding="utf-8")
    report = {
        "works": len(split),
        "total_chars": total_chars,
        "empty_blocks": total_empty,
        "per_volume": {},
    }
    for w in split:
        v = w["volume"] or "(无卷)"
        report["per_volume"].setdefault(v, 0)
        report["per_volume"][v] += 1
    report_path = out.with_name(out.stem + "_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"切分结果: {out}")
    print(f"统计: {report_path}")


if __name__ == "__main__":
    main()
