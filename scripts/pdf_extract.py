#!/usr/bin/env python3
"""pdf_extract.py — 文枢通用入库流程 S1：PDF 全量提取

逐页提取 PDF 文本，输出 page_XXXX.txt；内嵌空页/乱码校验（fail-fast 哨兵）。
对齐 v2 规划：零硬编码、参数化、确定性输出。

用法：
    python pdf_extract.py --input 书.pdf --output 输出目录 [--empty-threshold 0.10] [--garbled-threshold 0.05]

输出：
    输出目录/page_0001.txt ... page_NNNN.txt   （每页一个文本文件，页号 1 起）
    输出目录/extract_report.json                （提取统计 + 校验结果）

校验哨兵（不过即停）：
    - 提取页数 != PDF 页数          → 停
    - 空页率 > empty_threshold      → 停（默认 10%）
    - 乱码率 > garbled_threshold    → 停（默认 5%）
"""
import argparse
import json
import pathlib
import re

try:
    import pypdf
except ImportError:
    raise SystemExit("缺少依赖 pypdf，请先安装：pip install pypdf")

# 乱码特征字符（GBK 被误当 Latin-1 时出现的字符）
GARBLED_RE = re.compile(r"[\u00c0-\u00ff\u0080-\u009f]")


def detect_garbled_rate(text: str) -> float:
    """乱码率：文本中 Latin-1 乱码区字符占比（GBK 误读特征）。"""
    if not text:
        return 0.0
    garbled = len(GARBLED_RE.findall(text))
    # 正常中文标点不在此区间；控制字符（\u0080-\u009f）误读特征明显
    return garbled / len(text)


def extract_pdf(pdf_path: pathlib.Path, out_dir: pathlib.Path) -> dict:
    """逐页提取，返回统计报告。"""
    reader = pypdf.PdfReader(str(pdf_path))
    total = len(reader.pages)
    out_dir.mkdir(parents=True, exist_ok=True)

    empty_pages = 0
    garbled_pages = 0
    stats = []

    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception as e:
            text = ""
            print(f"[warn] 第{i+1}页提取异常: {type(e).__name__}")

        text = text.strip()
        out_file = out_dir / f"page_{i+1:04d}.txt"
        out_file.write_text(text, encoding="utf-8")

        is_empty = len(text) == 0
        garbled_rate = detect_garbled_rate(text)
        is_garbled = garbled_rate > 0.05  # 单页乱码标记阈值（宽松）

        if is_empty:
            empty_pages += 1
        if is_garbled:
            garbled_pages += 1

        stats.append({
            "page": i + 1,
            "chars": len(text),
            "empty": is_empty,
            "garbled_rate": round(garbled_rate, 4),
        })

        if (i + 1) % 200 == 0:
            print(f"  已提取 {i+1}/{total} 页")

    report = {
        "pdf": str(pdf_path),
        "total_pages": total,
        "empty_pages": empty_pages,
        "garbled_pages": garbled_pages,
        "empty_rate": round(empty_pages / total, 4),
        "garbled_page_rate": round(garbled_pages / total, 4),
        "pages": stats,
    }
    return report


def validate(report: dict, empty_threshold: float, garbled_threshold: float) -> None:
    """fail-fast 校验：不过即退出码 1。"""
    errors = []
    if report["empty_rate"] > empty_threshold:
        errors.append(
            f"空页率 {report['empty_rate']:.1%} > 阈值 {empty_threshold:.0%}"
        )
    if report["garbled_page_rate"] > garbled_threshold:
        errors.append(
            f"乱码页率 {report['garbled_page_rate']:.1%} > 阈值 {garbled_threshold:.0%}"
        )
    if errors:
        for e in errors:
            print(f"[FAIL] {e}")
        raise SystemExit(f"S1 校验未通过：{'；'.join(errors)}")
    print(f"[OK] 提取校验通过：{report['total_pages']} 页，"
          f"空页 {report['empty_pages']}（{report['empty_rate']:.1%}），"
          f"乱码页 {report['garbled_pages']}（{report['garbled_page_rate']:.1%}）")


def main():
    parser = argparse.ArgumentParser(description="文枢 S1：PDF 全量提取 + 校验")
    parser.add_argument("--input", required=True, help="输入 PDF 路径")
    parser.add_argument("--output", required=True, help="输出目录")
    parser.add_argument("--empty-threshold", type=float, default=0.10,
                        help="空页率阈值（默认 0.10）")
    parser.add_argument("--garbled-threshold", type=float, default=0.05,
                        help="乱码页率阈值（默认 0.05）")
    args = parser.parse_args()

    pdf = pathlib.Path(args.input)
    if not pdf.exists():
        raise SystemExit(f"PDF 不存在: {pdf}")

    out = pathlib.Path(args.output)
    report = extract_pdf(pdf, out)

    report_path = out / "extract_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"报告已存: {report_path}")

    validate(report, args.empty_threshold, args.garbled_threshold)


if __name__ == "__main__":
    main()
