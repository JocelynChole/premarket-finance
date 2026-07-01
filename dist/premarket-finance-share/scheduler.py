#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘前财经资讯研判智能体 - 定时任务调度器

两种使用方式：
1. 常驻进程（推荐用于持续运行）：
   python scheduler.py

2. 立即执行一次：
   python scheduler.py --now
"""
import sys
import os
import time
import json
import schedule
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    DATA_DIR, REPORTS_DIR, SUBSCRIBERS_FILE,
    SCHEDULED_TIME, PUSH_TIME, MARKET_OPEN_TIME,
    PROJECT_NAME, PROJECT_VERSION,
)
from modules.fetch_news import fetch_and_filter_news
from modules.analyze_news import analyze_news_list
from modules.generate_report import generate_and_save_report
from modules.send_wechat import send_to_subscribers


# ============== 工具函数 ==============

def load_subscribers():
    if SUBSCRIBERS_FILE.exists():
        try:
            with open(SUBSCRIBERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []


def save_today_report(payload: dict) -> Path:
    today = datetime.now().strftime('%Y%m%d')
    f = REPORTS_DIR / f"report_{today}.json"
    with open(f, 'w', encoding='utf-8') as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
    return f


# ============== 任务 ==============

def job_pipeline():
    """完整抓取-分析-生成-保存流程（不推送，推送由独立 job 负责）"""
    print("\n" + "=" * 60)
    print(f"📥 [{datetime.now():%Y-%m-%d %H:%M:%S}] 开始抓取-分析-生成")
    print("=" * 60)
    try:
        news = fetch_and_filter_news()
        if not news:
            print("⚠️ 未获取到任何资讯，可能是 china-finance-rss 未运行或时间窗口内无数据")
            return None

        print(f"✅ 抓取到 {len(news)} 条预测类资讯")
        analyzed = analyze_news_list(news)
        save_today_report(analyzed)
        report = generate_and_save_report(analyzed)
        print(f"✅ 简报已生成：{report['report_path']}")
        return analyzed
    except Exception as e:
        print(f"❌ 任务执行失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def job_push():
    """推送前先重新抓取一次，确保 8:30 ~ 9:25 之间的新闻也被纳入

    流程：重新抓取 → 重新分析 → 重新生成 → 推送
    如果重新抓取失败，则回退使用 8:30 已保存的旧报告
    """
    print("\n" + "=" * 60)
    print(f"📱 [{datetime.now():%Y-%m-%d %H:%M:%S}] 推送前最后刷新 + 推送微信")
    print("=" * 60)

    analyzed = None
    try:
        analyzed = job_pipeline()
    except Exception as e:
        print(f"⚠️ 推送前重新抓取失败: {e}")

    # 抓取失败 → 回退使用 8:30 的旧报告
    if not analyzed:
        today = datetime.now().strftime('%Y%m%d')
        report_file = REPORTS_DIR / f"report_{today}.json"
        if not report_file.exists():
            print(f"⚠️ 今日报告不存在：{report_file}，请确认 {SCHEDULED_TIME} 的抓取任务是否已执行")
            return
        with open(report_file, 'r', encoding='utf-8') as f:
            analyzed = json.load(f)
        print("ℹ️ 使用 8:30 的旧报告进行推送")

    subs = load_subscribers()
    active = [s for s in subs if s.get('active', True) and s.get('serverchan_key')]
    if not active:
        print("ℹ️ 没有配置了 SendKey 的活跃订阅者，跳过推送")
        return

    result = send_to_subscribers(active, analyzed.get('news_list', []))
    print(f"✅ 推送完成：成功 {result['success']} / 失败 {result['failed']} / 总计 {result['total']}")
    return result


def job_full():
    """抓取+分析+生成+推送 一气呵成（用于 --now 模式）"""
    analyzed = job_pipeline()
    if analyzed:
        job_push()


# ============== 入口 ==============

def print_banner():
    print(f"""
╔══════════════════════════════════════════════════════════╗
║   {PROJECT_NAME}    ║
║   v{PROJECT_VERSION} · 定时调度器                                  ║
╠══════════════════════════════════════════════════════════╣
║   ⏰ 抓取时间   每天 {SCHEDULED_TIME}                                ║
║   📱 推送时间   每天 {PUSH_TIME}                                ║
║   🌐 开盘时间   每天 {MARKET_OPEN_TIME}                                ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║   按 Ctrl+C 退出                                         ║
║   python scheduler.py --now  ←  立即执行一次              ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
""")


def main():
    print_banner()

    if len(sys.argv) > 1 and sys.argv[1] == '--now':
        print("🚀 立即执行模式（抓取 + 推送）\n")
        job_full()
        return

    # 注册定时任务
    schedule.every().day.at(SCHEDULED_TIME).do(job_pipeline)
    schedule.every().day.at(PUSH_TIME).do(job_push)

    print(f"✅ 已注册定时任务：")
    print(f"   · {SCHEDULED_TIME}  抓取 + 分析 + 生成简报")
    print(f"   · {PUSH_TIME}  推送微信")
    print()

    # 可选：开机后立即执行一次
    try:
        ans = input("是否立即执行一次抓取+推送？(y/N): ").strip().lower()
        if ans in ('y', 'yes'):
            job_full()
    except EOFError:
        pass

    print("\n🔄 调度器已启动，等待定时执行…\n")
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        print("\n👋 已退出")


if __name__ == '__main__':
    main()
