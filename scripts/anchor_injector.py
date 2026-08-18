#!/usr/bin/env python3
"""文枢段落标注工具 anchor_injector.py

按 R3《段落锚点规范》为文献生成段落级 Block ID，支撑段落级引用与溯源。
实现 workflows/段落标注.md 的完整流程：段落切分 → 分配 Block ID → 注入 → 校验。

用法：
    # 标准：按段落切分 + 注入锚点（输出到新文件，不改源）
    python anchor_injector.py --input file.md --prefix ws_glx --output file_anchored.md

    # 批量 dry-run（先预览，不落盘）
    python anchor_injector.py --input dir/ --prefix ws_glx --dry-run

    # 校验已有文件锚点（不注入，只检查）
    python anchor_injector.py --input file_anchored.md --check

参数：
    --input       输入 .md 文件或目录（目录时递归处理）
    --prefix      锚点前缀（如 ws_gxl），生成 ^<prefix>p0001
    --extra       可选：前缀后附加标识（如卷/篇），生成 ^<prefix><extra>p0001
    --output      输出路径（文件或目录）；不指定则打印到 stdout
    --dry-run     只预览切分结果，不写文件
    --check       校验已有锚点（唯一性/格式/前缀隔离），不注入
    --max-len     段落目标长度（默认 90 字，按句子合并）
    --width       段落位位数（默认 4）

规范要点（对齐 R3）：
  - 前缀隔离：每素材独立前缀，命名空间严格隔离
  - 格式统一：^<前缀>[标识]p<段落位>，段落位固定位数
  - 脚本生成：锚点由本脚本生成，AI 不手改
  - 只输出新文件，不修改源文件（锚点生成后冻结原则）
"""
import os
import re
import sys
import argparse
import pathlib


# ========== 段落切分 ==========

def split_paragraphs(text: str, max_len: int = 90) -> list[str]:
    """按语义句子切分，合并到接近 max_len 的段落。

    切分边界：。！？； 及换行；短句合并，长句保留完整。
    返回段落列表（去除首尾空白与空段）。
    """
    # 先按行处理，合并行内的句子
    sentences = re.split(r"(?<=[。！？；])", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    paras: list[str] = []
    buf = ""
    for s in sentences:
        if len(buf) + len(s) <= max_len:
            buf += s
        else:
            if buf:
                paras.append(buf)
            buf = s
    if buf:
        paras.append(buf)
    return paras


# ========== 锚点生成与注入 ==========

def build_anchor(prefix: str, seq: int, width: int = 4, extra: str = "") -> str:
    """生成 Block ID：^<prefix><extra>p<seq>（seq 按 width 补零）。"""
    return f"^{prefix}{extra}p{seq:0{width}d}"


def inject_anchors_to_text(
    text: str,
    prefix: str,
    max_len: int = 90,
    width: int = 4,
    extra: str = "",
) -> tuple[str, list[str]]:
    """把锚点注入文本：每段前插入锚点行。

    返回 (注入后的文本, 锚点列表)。
    """
    paras = split_paragraphs(text, max_len)
    anchors = [build_anchor(prefix, i, width, extra) for i in range(1, len(paras) + 1)]

    parts = []
    for anchor, para in zip(anchors, paras):
        parts.append(anchor)
        parts.append("")
        parts.append(para)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n", anchors


def process_md_file(
    path: pathlib.Path,
    prefix: str,
    output: pathlib.Path | None,
    max_len: int = 90,
    width: int = 4,
    extra: str = "",
    dry_run: bool = False,
) -> dict:
    """处理单个 .md 文件：提取正文区（跳过 YAML frontmatter），注入锚点。

    返回结果字典。
    """
    content = path.read_text(encoding="utf-8")

    # 分离 YAML frontmatter（--- 包裹）
    fm = ""
    body = content
    m = re.match(r"^---\n(.*?)\n---\n?", content, re.S)
    if m:
        fm = m.group(0)
        body = content[m.end() :]

    anchored_body, anchors = inject_anchors_to_text(body, prefix, max_len, width, extra)
    result = {
        "file": str(path),
        "paras": len(anchors),
        "anchors": anchors,
        "output": None,
    }

    if dry_run:
        # 预览切分结果（锚点 + 段落首 30 字）
        print(f"=== {path}（{len(anchors)} 段）===")
        for a, p in zip(anchors, split_paragraphs(body, max_len)):
            print(f"  {a} ({len(p)}字): {p[:30]}...")
        return result

    if output is None:
        # 打印到 stdout（预览）
        print(f"=== {path}（{len(anchors)} 段）===")
        print(anchored_body)
    else:
        output.parent.mkdir(parents=True, exist_ok=True) if output.parent != pathlib.Path(".") else None
        if output.is_dir() or str(output) == ".":
            output = output / (path.stem + "_anchored.md")
        output.write_text(fm + anchored_body, encoding="utf-8")
        result["output"] = str(output)
    return result


# ========== 锚点校验 ==========

def check_anchors(path: pathlib.Path) -> dict:
    """校验文件已有锚点：格式合法性 / 唯一性 / 顺序连续性。

    返回校验报告。
    """
    content = path.read_text(encoding="utf-8")
    anchors = re.findall(r"^(\^[\w-]+p\d+)$", content, re.M)

    issues = []
    if not anchors:
        return {"file": str(path), "anchors": 0, "ok": False, "issues": ["无锚点（未标注）"]}

    # 唯一性
    seen = {}
    for a in anchors:
        seen[a] = seen.get(a, 0) + 1
    dups = {k: v for k, v in seen.items() if v > 1}
    if dups:
        issues.append(f"重复锚点: {dups}")

    # 前缀隔离（同一文件应只有一种前缀）
    prefixes = set(re.match(r"^(\^[\w-]+)p\d+$", a).group(1) for a in anchors)
    if len(prefixes) > 1:
        issues.append(f"前缀混用: {prefixes}")

    # 段落位连续且位数一致
    widths = {len(re.search(r"p(\d+)$", a).group(1)) for a in anchors}
    if len(widths) > 1:
        issues.append(f"段落位位数不统一: {widths}")

    seqs = sorted({int(re.search(r"p(\d+)$", a).group(1)) for a in anchors})
    if seqs != list(range(1, len(seqs) + 1)):
        issues.append(f"段落位不连续: 实际 {seqs[0]}..{seqs[-1]}，期望 1..{len(seqs)}")

    return {
        "file": str(path),
        "anchors": len(anchors),
        "ok": not issues,
        "issues": issues,
    }


# ========== 主入口 ==========

def main():
    parser = argparse.ArgumentParser(
        description="文枢段落标注工具（R3 锚点规范）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--input", required=True, help="输入 .md 文件或目录")
    parser.add_argument("--prefix", default="ws", help="锚点前缀（如 ws_gxl），默认 ws")
    parser.add_argument("--extra", default="", help="前缀后附加标识（如卷/篇），默认空")
    parser.add_argument("--output", help="输出路径（文件或目录）；不指定则打印")
    parser.add_argument("--dry-run", action="store_true", help="只预览不写文件")
    parser.add_argument("--check", action="store_true", help="校验已有锚点，不注入")
    parser.add_argument("--max-len", type=int, default=90, help="段落目标长度（默认 90）")
    parser.add_argument("--width", type=int, default=4, help="段落位位数（默认 4）")
    args = parser.parse_args()

    in_path = pathlib.Path(args.input)

    # 校验模式
    if args.check:
        if in_path.is_dir():
            files = sorted(in_path.rglob("*.md"))
        else:
            files = [in_path]
        all_ok = True
        for f in files:
            rep = check_anchors(f)
            status = "OK" if rep["ok"] else "FAIL"
            if not rep["ok"]:
                all_ok = False
            print(f"[{status}] {rep['file']}（{rep['anchors']} 锚点）")
            for i in rep["issues"]:
                print(f"        - {i}")
        sys.exit(0 if all_ok else 1)

    # 注入模式
    out_path = pathlib.Path(args.output) if args.output else None

    if in_path.is_dir():
        files = sorted(in_path.rglob("*.md"))
    else:
        files = [in_path]

    if not files:
        print("未找到 .md 文件")
        sys.exit(1)

    total_paras = 0
    for f in files:
        rep = process_md_file(
            f,
            args.prefix,
            out_path,
            args.max_len,
            args.width,
            args.extra,
            args.dry_run,
        )
        total_paras += rep["paras"]
        if rep.get("output"):
            print(f"[写入] {rep['file']} → {rep['output']}（{rep['paras']} 段）")

    if args.dry_run:
        print(f"\n[dry-run] {len(files)} 文件，共 {total_paras} 段（未写盘）")
    else:
        print(f"\n完成：{len(files)} 文件，共 {total_paras} 段")


if __name__ == "__main__":
    main()
