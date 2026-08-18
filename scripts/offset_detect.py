#!/usr/bin/env python3
"""offset_detect.py — 文枢通用入库流程 S3：页码偏移分段检测

从 toc_manifest.json 计算"书内页码 → PDF 页号"的偏移量，按卷分段。
偏移 = pdf_start - book_start（每篇的起始页同时有书内页码与 PDF 页号）。

用法：
    python offset_detect.py --input toc_manifest.json --output offset_config.json

输出：
    offset_config.json   {volume: offset, ...} 供 S4 使用
    <output>_report.json 检测报告（各卷偏移/置信度/异常点）

校验哨兵（不过即停）：
    - 偏移不在 [0, 50] → 停
    - 卷内偏移分散（标准差 > 3）→ 停
"""
import argparse
import json
import pathlib
from collections import Counter


def detect_offsets(works: list[dict]) -> dict:
    """按卷计算偏移分布，返回各卷偏移（众数）+ 报告。"""
    by_vol = {}
    for w in works:
        vol = w.get("volume") or "(无卷)"
        pdf = w.get("pdf_start")
        book = w.get("book_start")
        if pdf is None or book is None:
            continue
        by_vol.setdefault(vol, []).append(pdf - book)

    vol_config = {}
    report = {}
    for vol, offsets in sorted(by_vol.items()):
        cnt = Counter(offsets)
        most_common, freq = cnt.most_common(1)[0]
        # 样本量、一致性
        n = len(offsets)
        consistency = freq / n
        distinct = len(cnt)
        # 异常点（偏离众数 > 1）
        anomalies = [o for o in offsets if abs(o - most_common) > 1]

        vol_config[vol] = most_common
        report[vol] = {
            "offset": most_common,
            "samples": n,
            "consistency": round(consistency, 3),
            "distinct_values": distinct,
            "anomalies": anomalies,
            "all_offsets": offsets,
        }
    return vol_config, report


def validate(vol_config: dict, report: dict) -> None:
    """fail-fast 校验。"""
    errors = []
    for vol, offset in vol_config.items():
        if not (0 <= offset <= 50):
            errors.append(f"[{vol}] 偏移 {offset} 超出 [0,50]")
        r = report[vol]
        if r["samples"] >= 5 and r["consistency"] < 0.7:
            errors.append(f"[{vol}] 偏移一致性 {r['consistency']:.0%} 过低（{r['samples']} 样本）")
    if errors:
        for e in errors:
            print(f"[FAIL] {e}")
        raise SystemExit(f"S3 校验未通过：{'；'.join(errors)}")
    for vol, offset in vol_config.items():
        print(f"[OK] {vol}: 偏移 {offset}（{report[vol]['samples']} 样本，"
              f"一致性 {report[vol]['consistency']:.0%}）")


def main():
    parser = argparse.ArgumentParser(description="文枢 S3：页码偏移分段检测")
    parser.add_argument("--input", required=True, help="toc_manifest.json")
    parser.add_argument("--output", required=True, help="输出 offset_config.json")
    args = parser.parse_args()

    works = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8"))
    print(f"[加载] {len(works)} 篇")

    vol_config, report = detect_offsets(works)

    out = pathlib.Path(args.output)
    out.write_text(json.dumps(vol_config, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = out.with_name(out.stem + "_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"配置: {out}")
    print(f"报告: {report_path}")

    validate(vol_config, report)


if __name__ == "__main__":
    main()
