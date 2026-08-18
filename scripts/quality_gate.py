#!/usr/bin/env python3
"""S6 汇总质量门（v2 通用入库流程）。

对 S5 产出的 md 知识库做全库校验 + 输出抽样验收清单。

功能：
  1. 全库统计：文件数 / 锚点数 / 字数 / 卷分布 / 空篇检测
  2. 一致性校验：YAML title 必填 / 锚点格式合法 / 卷目录与 volume 一致 / pages 字段与锚点首尾一致
  3. 抽样清单：按卷分层抽样（默认每卷约 10%），输出结构化清单供人工验收

用法：
    quality_gate.py --kb 知识库目录 [--sample-ratio 0.1] [--json out.json]
"""
import argparse
import json
import pathlib
import re
import sys
from collections import Counter

VOL_CODE = {
    "第一卷": "01", "第二卷": "02", "第三卷": "03", "第四卷": "04",
    "第五卷": "05", "第六卷": "06", "第七卷": "07", "第八卷": "08",
}
ANCHOR_RE = re.compile(r"^\^v(\d{2})p(\d{4})$", re.M)


def analyze(kb_dir: pathlib.Path, sample_ratio: float) -> dict:
    """遍历知识库做全库校验，返回报告 dict。"""
    files = sorted(kb_dir.rglob("*.md"))
    report = {
        "total_files": len(files),
        "total_anchors": 0,
        "total_chars": 0,
        "by_volume": Counter(),
        "issues": [],
        "warnings": [],
        "sample": [],
    }

    # 卷目录 → 卷号 映射校验
    for f in files:
        vol_dir = f.parent.name
        text = f.read_text(encoding="utf-8")
        report["total_chars"] += len(text)

        # YAML title 必填
        m_title = re.search(r"^title:.*$", text, re.M)
        if not m_title:
            report["issues"].append(f"缺 title: {f}")
            continue
        title = m_title.group(0).split(":", 1)[1].strip()

        # 锚点统计 + 格式 + 空篇
        anchors = ANCHOR_RE.findall(text)
        report["total_anchors"] += len(anchors)
        if not anchors:
            report["issues"].append(f"无锚点: {f.name}")

        # 卷目录与锚点卷号一致
        code = VOL_CODE.get(vol_dir)
        if code:
            wrong = [a for a in anchors if a[0] != code]
            if wrong:
                report["warnings"].append(
                    f"卷号与目录不一致: {f.name}（{len(wrong)} 个锚点）")
            # 校验 pages 字段与锚点首尾
            m_pages = re.search(r"^pages:\s*([\d-]+)", text, re.M)
            if m_pages:
                try:
                    p_start, p_end = m_pages.group(1).split("-")
                    nums = sorted(int(a[1]) for a in anchors)
                    if nums and (nums[0] != int(p_start) or nums[-1] != int(p_end)):
                        report["warnings"].append(
                            f"pages 与锚点首尾不一致: {f.name} "
                            f"(pages {p_start}-{p_end} vs 锚点 {nums[0]}-{nums[-1]})")
                except ValueError:
                    pass

        report["by_volume"][vol_dir] += 1

        # 收集抽样候选（每篇记一条，按卷分组后抽样）
        report.setdefault("_sample_pool", []).append({
            "title": title,
            "file": str(f.relative_to(kb_dir)),
            "volume": vol_dir,
            "anchors": len(anchors),
            "chars": len(text),
        })

    # 按卷分层抽样
    pool = report.pop("_sample_pool", [])
    by_vol = {}
    for item in pool:
        by_vol.setdefault(item["volume"], []).append(item)
    for vol in sorted(by_vol):
        items = sorted(by_vol[vol], key=lambda x: x["file"])
        n = max(1, round(len(items) * sample_ratio))
        # 均匀取：等间隔抽样（确定性，非随机，可复现）
        step = len(items) / n
        picked = [items[int(i * step)] for i in range(n)]
        report["sample"].extend(picked)

    report["by_volume"] = dict(sorted(report["by_volume"].items()))
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="S6 汇总质量门")
    ap.add_argument("--kb", required=True, help="md 知识库目录")
    ap.add_argument("--sample-ratio", type=float, default=0.1, help="抽样比例（默认 0.1）")
    ap.add_argument("--json", help="输出报告到 JSON 文件")
    args = ap.parse_args()

    kb_dir = pathlib.Path(args.kb)
    if not kb_dir.is_dir():
        print(f"[ERROR] 知识库目录不存在: {kb_dir}")
        return 1

    report = analyze(kb_dir, args.sample_ratio)

    # 控制台汇总
    print(f"[S6] 全库统计")
    print(f"  文件数: {report['total_files']} | 锚点: {report['total_anchors']} | 字数: {report['total_chars']}")
    print(f"  卷分布: {dict(report['by_volume'])}")
    print(f"  问题(issues): {len(report['issues'])} | 警告(warnings): {len(report['warnings'])}")
    for i in report["issues"][:10]:
        print(f"    [ISSUE] {i}")
    for w in report["warnings"][:10]:
        print(f"    [WARN] {w}")

    print(f"\n[S6] 抽样验收清单（每卷 {round(args.sample_ratio*100)}%，共 {len(report['sample'])} 篇，请逐篇核对标题/首尾页/锚点）")
    for s in report["sample"]:
        print(f"  [{s['volume']}] {s['title']}  (锚点 {s['anchors']} | {s['chars']} 字)")

    if args.json:
        out = pathlib.Path(args.json)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[S6] 报告已存: {out}")

    return 0 if not report["issues"] else 2


if __name__ == "__main__":
    sys.exit(main())
