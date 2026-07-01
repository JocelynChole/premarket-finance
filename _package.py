#!/usr/bin/env python3
"""Build the shareable skill package - exclude sensitive/redundant files."""
import os
import shutil
import zipfile
from pathlib import Path

ROOT = Path(r"C:\Users\HP\Desktop\premarket-finance")
DST = ROOT / "dist" / "premarket-finance-share"
ZIP_PATH = ROOT / "dist" / "premarket-finance-share.zip"

# 白名单：要复制的条目
KEEP = [
    "assets", "china-finance-rss",
    "modules", "references", "static", "templates",
    ".env.example", ".gitignore", "README.md", "app.py", "config.py",
    "requirements.txt", "scheduler.py", "setup_tasks.py",
    "skill.md", "STUDENT_GUIDE.md",
    "\u4e00\u952e\u542f\u52a8.bat", "\u542f\u52a8Web\u670d\u52a1.bat", "\u542f\u52a8\u52a9\u624b.bat",
]
# 排除：复制时跳过的子项
SKIP_IN_SUBDIR = {"dist", "data", "__pycache__", ".trae", ".git",
                  "verify_persistence.txt", ".python-version", "python",
                  "node_modules", "venv", ".venv"}
# 删除：复制后额外清理的路径（相对 DST）
EXTRA_DELETE = []


def safe_rmtree(p: Path):
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)


def main():
    # 清理 dist
    safe_rmtree(ROOT / "dist")
    DST.mkdir(parents=True, exist_ok=True)

    # 复制
    for name in KEEP:
        src = ROOT / name
        if not src.exists():
            continue
        dst = DST / name
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
            for child in src.iterdir():
                if child.name in SKIP_IN_SUBDIR:
                    continue
                if child.is_dir():
                    shutil.copytree(child, dst / child.name, dirs_exist_ok=True,
                                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "python"))
                else:
                    shutil.copy2(child, dst / child.name)
        else:
            shutil.copy2(src, dst)

    # 额外清理
    for rel in EXTRA_DELETE:
        p = DST / rel
        if p.exists():
            if p.is_dir():
                safe_rmtree(p)
            else:
                p.unlink()
    # 兜底清理所有 __pycache__ / .pyc / .git
    for sub in ("__pycache__", ".git"):
        for p in DST.rglob(sub):
            safe_rmtree(p) if p.is_dir() else p.unlink()
    for p in DST.rglob("*.pyc"):
        if p.is_file():
            p.unlink()

    # ============ 脱敏 ============
    # 1) README.md: 残留的 Server酱 / sct.ftqq.com 提示
    rm = DST / "README.md"
    if rm.exists():
        text = rm.read_text(encoding="utf-8")
        text = text.replace("sct.ftqq.com", "pushplus.plus")
        text = text.replace("Server酱", "pushplus")
        text = text.replace("SCTxxxxx", "32位字母数字")
        text = text.replace("免费版每天 5 条", "免费版每天 200 条")
        rm.write_text(text, encoding="utf-8")

    # 写文件清单
    print("=" * 60)
    print("=== Share package contents ===")
    print("=" * 60)
    files = sorted(p for p in DST.rglob("*") if p.is_file())
    total_bytes = 0
    for f in files:
        rel = str(f.relative_to(DST)).replace("\\", "/")
        size = f.stat().st_size
        total_bytes += size
        print(f"  {rel:<60} {size:>8} B")
    print("=" * 60)
    print(f"Total files: {len(files)}")
    print(f"Total size:  {total_bytes/1024:.1f} KB")
    print(f"Path:        {DST}")

    # 打包 ZIP
    print("\nBuilding ZIP ...")
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in files:
            arcname = f.relative_to(DST.parent)  # 保留 premarket-finance-share/...
            zf.write(f, arcname)
    print(f"ZIP:         {ZIP_PATH} ({ZIP_PATH.stat().st_size/1024:.1f} KB)")


if __name__ == "__main__":
    main()
