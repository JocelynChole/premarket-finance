#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘前财经资讯研判智能体 - Windows 任务计划安装/管理

为不熟悉命令行的用户提供一个简单的图形化交互界面，
通过 schtasks 命令创建/查询/删除 Windows 任务计划。

使用：
  python setup_tasks.py
"""
import os
import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.absolute()
PYTHON_EXE = sys.executable
SCHEDULER_PATH = PROJECT_ROOT / "scheduler.py"
APP_PATH = PROJECT_ROOT / "app.py"
RSS_DIR = PROJECT_ROOT / "china-finance-rss"
RSS_SERVER = RSS_DIR / "server.py"

FETCH_TASK = "盘前财经智能体_抓取"
PUSH_TASK = "盘前财经智能体_推送"
WEB_TASK = "盘前财经智能体_Web服务"
RSS_TASK = "盘前财经智能体_数据服务"
ALL_TASKS = (FETCH_TASK, PUSH_TASK, WEB_TASK, RSS_TASK)


def run(cmd: str) -> tuple:
    """执行 shell 命令，返回 (returncode, stdout, stderr)"""
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='gbk', errors='ignore')
    return p.returncode, p.stdout, p.stderr


def create_all_tasks():
    """创建 4 个 Windows 任务：抓取 / 推送 / Web 服务 / 数据服务"""
    from config import SCHEDULED_TIME, PUSH_TIME, FLASK_PORT

    # 数据服务启动器（封装 cd + python）
    rss_runner = PROJECT_ROOT / "scripts" / "_rss_runner.py"
    rss_runner.parent.mkdir(exist_ok=True)
    rss_runner.write_text(f'''# -*- coding: utf-8 -*-
"""自动生成的数据服务启动器 - 由 setup_tasks.py 创建"""
import os, sys
from pathlib import Path
ROOT = Path(r"{PROJECT_ROOT}")
os.chdir(ROOT / "china-finance-rss")
sys.path.insert(0, str(ROOT / "china-finance-rss"))
# 简单的崩溃自愈：进程异常退出后立即重启
while True:
    try:
        import server
        server.main()
        break
    except SystemExit as e:
        if e.code == 0:
            break
        print(f"[WARN] china-finance-rss 异常退出 (code={{e.code}})，3 秒后自动重启...", flush=True)
        import time
        time.sleep(3)
    except Exception as e:
        print(f"[WARN] china-finance-rss 启动失败: {{e}}，3 秒后重试...", flush=True)
        import time
        time.sleep(3)
''', encoding='utf-8')

    push_runner = PROJECT_ROOT / "scripts" / "_push_runner.py"
    push_runner.parent.mkdir(exist_ok=True)
    push_runner.write_text(f'''# -*- coding: utf-8 -*-
"""自动生成的推送任务脚本 - 由 setup_tasks.py 创建"""
import sys, json
from pathlib import Path
sys.path.insert(0, r"{PROJECT_ROOT}")
from datetime import datetime
from config import REPORTS_DIR, SUBSCRIBERS_FILE
from modules.send_wechat import send_to_subscribers

today = datetime.now().strftime('%Y%m%d')
rf = REPORTS_DIR / f"report_{{today}}.json"
report = json.load(open(rf, encoding='utf-8')) if rf.exists() else None
subs = json.load(open(SUBSCRIBERS_FILE, encoding='utf-8')) if SUBSCRIBERS_FILE.exists() else []
active = [s for s in subs if s.get('active', True) and s.get('pushplus_token')]
news = report.get('news_list', []) if report else []
print(send_to_subscribers(active, news))
''', encoding='utf-8')

    # 删除旧任务
    print("正在清理旧任务…")
    for name in ALL_TASKS:
        run(f'schtasks /delete /tn "{name}" /f')

    # 1. 数据服务（开机自启 + 持续运行）
    rss_cmd = (
        f'schtasks /create /tn "{RSS_TASK}" '
        f'/tr "\\"{PYTHON_EXE}\\" \\"{rss_runner}\\" " '
        f'/sc onlogon /rl highest /f'
    )
    rc, out, err = run(rss_cmd)
    print(f"{'✅' if rc == 0 else '❌'} 数据服务（开机自启）：{RSS_TASK}  →  :8053")

    # 2. 抓取任务
    fetch_cmd = (
        f'schtasks /create /tn "{FETCH_TASK}" '
        f'/tr "\\"{PYTHON_EXE}\\" \\"{SCHEDULER_PATH}\\" --now" '
        f'/sc daily /st {SCHEDULED_TIME} /ru System /f'
    )
    rc, out, err = run(fetch_cmd)
    print(f"{'✅' if rc == 0 else '❌'} 抓取任务（{SCHEDULED_TIME}）：{FETCH_TASK}")

    # 3. 推送任务
    push_cmd = (
        f'schtasks /create /tn "{PUSH_TASK}" '
        f'/tr "\\"{PYTHON_EXE}\\" \\"{push_runner}\\" " '
        f'/sc daily /st {PUSH_TIME} /ru System /f'
    )
    rc, out, err = run(push_cmd)
    print(f"{'✅' if rc == 0 else '❌'} 推送任务（{PUSH_TIME}）：{PUSH_TASK}")

    # 4. Web 服务（开机自启）
    web_cmd = (
        f'schtasks /create /tn "{WEB_TASK}" '
        f'/tr "\\"{PYTHON_EXE}\\" \\"{APP_PATH}\\" " '
        f'/sc onlogon /rl highest /f'
    )
    rc, out, err = run(web_cmd)
    print(f"{'✅' if rc == 0 else '❌'} Web 服务（开机自启）：{WEB_TASK}  →  http://localhost:{FLASK_PORT}")

    print()
    print("=" * 50)
    print("✅ 全部 4 个任务已创建！")
    print("=" * 50)
    print()
    print("📋 任务清单：")
    print(f"  · {RSS_TASK}     开机自启（数据采集服务）")
    print(f"  · {WEB_TASK}    开机自启（Web 访问）")
    print(f"  · {FETCH_TASK}   每天 {SCHEDULED_TIME}（抓取+分析+生成）")
    print(f"  · {PUSH_TASK}    每天 {PUSH_TIME}（微信推送）")
    print()
    print("💡 查看所有任务：")
    print("  schtasks /query | findstr 盘前")
    print()
    print("🗑 删除所有任务：")
    for n in ALL_TASKS:
        print(f"  schtasks /delete /tn \"{n}\" /f")
    print()
    print("⚠️ 重要：电脑要保持开机状态（睡眠可以，关机不行）")


def delete_all_tasks():
    print("正在删除所有相关任务…")
    for name in ALL_TASKS:
        rc, out, err = run(f'schtasks /delete /tn "{name}" /f')
        if rc == 0:
            print(f"  ✅ 已删除：{name}")
        else:
            print(f"  ⏭️  不存在：{name}")


def show_tasks():
    rc, out, err = run('schtasks /query /fo CSV /nh')
    print("=" * 60)
    print("  当前 Windows 任务计划中与本系统相关的任务")
    print("=" * 60)
    if rc != 0:
        print(f"❌ 查询失败：{err}")
        return
    found = False
    for line in out.splitlines():
        for kw in ('盘前', 'premarket', 'scheduler'):
            if kw.lower() in line.lower():
                print(line)
                found = True
                break
    if not found:
        print("（暂无相关任务）")
    print("=" * 60)


def main():
    print("\n" + "=" * 50)
    print("  Windows 任务计划配置工具")
    print("=" * 50)
    print("\n选项：")
    print("  1. 创建/更新定时任务（推荐）")
    print("  2. 查看当前任务")
    print("  3. 删除所有相关任务")
    print("  4. 退出")
    print("=" * 50)

    try:
        choice = input("\n请选择 (1-4): ").strip()
    except EOFError:
        choice = "1"

    if choice == "1":
        print("\n即将创建以下任务：")
        from config import SCHEDULED_TIME, PUSH_TIME
        print(f"  · 数据服务   开机时             china-finance-rss (:8053)")
        print(f"  · Web 服务   开机时             http://localhost:{FLASK_PORT}")
        print(f"  · 抓取任务   每天 {SCHEDULED_TIME}    自动抓取+分析+生成")
        print(f"  · 推送任务   每天 {PUSH_TIME}    自动推送给所有订阅者")
        try:
            confirm = input("\n确认创建？(Y/n): ").strip().lower()
        except EOFError:
            confirm = "y"
        if confirm in ('', 'y', 'yes'):
            create_all_tasks()
        else:
            print("已取消")
    elif choice == "2":
        show_tasks()
    elif choice == "3":
        delete_all_tasks()
    else:
        print("\n再见！")

    try:
        input("\n按 Enter 键退出...")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
