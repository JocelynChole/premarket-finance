#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘前财经资讯研判智能体 - Web 应用入口

启动：python app.py
浏览器：http://localhost:5000
"""
import os
import sys
import json
import time
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, abort,
)
import requests

# 让模块导入使用项目根
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    PROJECT_NAME, PROJECT_VERSION, PROJECT_TAGLINE,
    DATA_DIR, REPORTS_DIR, MARKDOWN_REPORTS_DIR, SUBSCRIBERS_FILE,
    FLASK_HOST, FLASK_PORT, FLASK_DEBUG,
    SCHEDULED_TIME, PUSH_TIME, MARKET_OPEN_TIME,
)
from modules.fetch_news import fetch_and_filter_news
from modules.analyze_news import analyze_news_list
from modules.generate_report import generate_and_save_report
from modules.send_wechat import send_news_report, test_serverchan, send_to_subscribers

# ============== Flask 初始化 ==============
app = Flask(
    __name__,
    static_folder='static',
    template_folder='templates',
)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['JSON_AS_ASCII'] = False
app.jinja_env.add_extension('jinja2.ext.do')


# ============== RSS 子进程管理（Render/容器/本地一键启动都用） ==============

_rss_proc = None  # 全局句柄，关闭时回收


def _ensure_rss_running():
    """如果 :8053 没有 china-finance-rss 在跑，自动拉起子进程。

    - 本地开发时双击 一键启动.bat：bat 拉起一个独立窗口跑 RSS，所以这里检测到 :8053 已有服务就跳过
    - Render / 容器部署：单容器只能暴露一个端口，所以让 Flask 自带 RSS 子进程
    - 重复 import 不会重复启动：用端口探活判定
    """
    global _rss_proc
    rss_port = int(os.getenv("RSS_PORT", "8053"))
    # 探活：端口已经被占用说明已经有一个 RSS 在跑
    try:
        r = requests.get(f"http://localhost:{rss_port}/", timeout=1)
        if r.status_code == 200:
            print(f"[RSS] china-finance-rss 已在 :{rss_port} 运行，跳过自启")
            return None
    except Exception:
        pass

    rss_dir = Path(__file__).parent / "china-finance-rss"
    server_py = rss_dir / "server.py"
    if not server_py.exists():
        print(f"[RSS] 警告: 找不到 {server_py}，数据抓取将无法工作")
        return None

    print(f"[RSS] 正在启动 china-finance-rss 子进程（端口 {rss_port}）...")
    env = os.environ.copy()
    env["PORT"] = str(rss_port)
    _rss_proc = subprocess.Popen(
        [sys.executable, str(server_py)],
        cwd=str(rss_dir),
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    # 等待服务就绪（最多 10 秒）
    for _ in range(20):
        time.sleep(0.5)
        try:
            r = requests.get(f"http://localhost:{rss_port}/", timeout=1)
            if r.status_code == 200:
                print(f"[RSS] china-finance-rss 启动成功 (PID {_rss_proc.pid})")
                return _rss_proc
        except Exception:
            continue
    print(f"[RSS] 启动可能失败，请检查日志")
    return _rss_proc


# 模块加载时立即尝试启动 RSS（gunicorn / python app.py 都会触发）
_ensure_rss_running()


# ============== 辅助函数 ==============

def _load_subscribers():
    if SUBSCRIBERS_FILE.exists():
        try:
            with open(SUBSCRIBERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []


def _save_subscribers(subs):
    with open(SUBSCRIBERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(subs, f, ensure_ascii=False, indent=2)


def _get_today_report():
    today_str = datetime.now().strftime('%Y%m%d')
    f = REPORTS_DIR / f"report_{today_str}.json"
    if f.exists():
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                return json.load(fp)
        except Exception:
            return None
    return None


def _save_report(payload):
    today_str = datetime.now().strftime('%Y%m%d')
    f = REPORTS_DIR / f"report_{today_str}.json"
    with open(f, 'w', encoding='utf-8') as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
    return f


def _run_full_pipeline(silent: bool = False):
    """执行完整抓取-分析-生成流程，返回 dict 结果（不直接返回 jsonify）"""
    if not silent:
        print("=" * 60)
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 开始执行完整流程")
        print("=" * 60)

    news_list = fetch_and_filter_news()
    if not news_list:
        return {
            "success": False,
            "error": "未能获取到任何资讯，请检查 china-finance-rss 服务是否运行",
            "news_list": [], "stats": {}, "news_count": 0,
        }

    if not silent:
        print(f"✅ 抓取完成：{len(news_list)} 条")

    analyzed = analyze_news_list(news_list)
    _save_report(analyzed)
    report_info = generate_and_save_report(analyzed)

    if not silent:
        print(f"✅ 简报已生成：{report_info['report_path']}")

    # 推送
    subscribers = _load_subscribers()
    active = [s for s in subscribers if s.get("active", True)]
    push_summary = {"total": 0, "success": 0, "failed": 0}
    if active and active[0].get("serverchan_key"):
        push_summary = send_to_subscribers(active, analyzed["news_list"])
        if not silent:
            print(f"✅ 推送完成：{push_summary['success']}/{push_summary['total']}")

    return {
        "success": True,
        "news_count": len(news_list),
        "news_list": analyzed["news_list"],
        "stats": analyzed["stats"],
        "report_file": str(report_info["report_path"]),
        "push_summary": push_summary,
        "analyzed_at": analyzed["analyzed_at"],
    }


# ============== 页面路由 ==============

@app.route('/')
def page_index():
    return render_template(
        'index.html',
        project_name=PROJECT_NAME,
        project_version=PROJECT_VERSION,
        project_tagline=PROJECT_TAGLINE,
        scheduled_time=SCHEDULED_TIME,
        push_time=PUSH_TIME,
        market_open=MARKET_OPEN_TIME,
    )


@app.route('/report')
def page_report():
    return render_template(
        'report.html',
        project_name=PROJECT_NAME,
        project_version=PROJECT_VERSION,
    )


@app.route('/sectors')
def page_sectors():
    return render_template(
        'sectors.html',
        project_name=PROJECT_NAME,
        project_version=PROJECT_VERSION,
    )


@app.route('/subscribe')
def page_subscribe():
    return render_template(
        'subscribe.html',
        project_name=PROJECT_NAME,
        project_version=PROJECT_VERSION,
    )


@app.route('/history')
def page_history():
    return render_template(
        'history.html',
        project_name=PROJECT_NAME,
        project_version=PROJECT_VERSION,
    )


# ============== API: 资讯 ==============

@app.route('/api/news')
def api_news():
    report = _get_today_report()
    if report:
        return jsonify(report)
    return jsonify({"success": False, "error": "暂无今日数据，请点击刷新"})


@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    result = _run_full_pipeline(silent=True)
    return jsonify(result)


@app.route('/api/report/today')
def api_report_today():
    today_str = datetime.now().strftime('%Y%m%d')
    md = MARKDOWN_REPORTS_DIR / f"report_{today_str}.md"
    if not md.exists():
        return jsonify({"success": False, "error": "今日简报尚未生成，请先刷新"})
    with open(md, 'r', encoding='utf-8') as f:
        content = f.read()
    return jsonify({
        "success": True,
        "content": content,
        "generated_at": datetime.fromtimestamp(md.stat().st_mtime).isoformat(),
    })


@app.route('/api/report/date/<date_str>')
def api_report_date(date_str):
    f = REPORTS_DIR / f"report_{date_str}.json"
    if not f.exists():
        return jsonify({"error": "报告不存在"}), 404
    with open(f, 'r', encoding='utf-8') as fp:
        return jsonify(json.load(fp))


@app.route('/api/report/date/<date_str>/markdown')
def api_report_date_md(date_str):
    f = MARKDOWN_REPORTS_DIR / f"report_{date_str}.md"
    if not f.exists():
        return jsonify({"error": "简报不存在"}), 404
    with open(f, 'r', encoding='utf-8') as fp:
        return jsonify({"success": True, "content": fp.read()})


@app.route('/api/history')
def api_history():
    items = []
    if REPORTS_DIR.exists():
        for f in sorted(REPORTS_DIR.iterdir(), reverse=True):
            if f.name.startswith('report_') and f.name.endswith('.json'):
                date_str = f.name.replace('report_', '').replace('.json', '')
                items.append({
                    "date": date_str,
                    "formatted_date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}",
                    "size": f.stat().st_size,
                    "timestamp": f.stat().st_mtime,
                })
    return jsonify(items)


# ============== API: 订阅 ==============

@app.route('/api/subscribe', methods=['POST'])
def api_subscribe():
    data = request.json or {}
    email = (data.get('email') or '').strip()
    sendkey = (data.get('serverchan_key') or '').strip()
    sectors = data.get('sectors', []) or []
    phone = (data.get('phone') or '').strip()

    if not email:
        return jsonify({"success": False, "error": "请填写邮箱"}), 400

    subscribers = _load_subscribers()
    now_iso = datetime.now().isoformat()

    # 查重
    for sub in subscribers:
        if sub.get('email', '').lower() == email.lower():
            sub.update({
                'phone': phone,
                'sectors': sectors,
                'serverchan_key': sendkey,
                'updated_at': now_iso,
                'active': True,
            })
            _save_subscribers(subscribers)

            push_result = None
            if sendkey:
                push_result = test_serverchan(sendkey)

            return jsonify({
                "success": True,
                "message": "订阅已更新" + ("，测试消息已发送" if push_result and push_result.get("success") else ""),
                "subscriber": sub,
                "push_result": push_result,
            })

    # 新增
    sub = {
        "id": len([s for s in subscribers if s.get('active', True)]) + 1,
        "email": email,
        "phone": phone,
        "sectors": sectors,
        "serverchan_key": sendkey,
        "subscribed_at": now_iso,
        "updated_at": now_iso,
        "active": True,
    }
    subscribers.append(sub)
    _save_subscribers(subscribers)

    push_result = None
    if sendkey:
        push_result = test_serverchan(sendkey)

    return jsonify({
        "success": True,
        "message": "订阅成功！" + ("微信收到测试消息了吗？" if push_result and push_result.get("success") else "（如需微信推送请填写 Server酱 SendKey）"),
        "subscriber": sub,
        "push_result": push_result,
    })


@app.route('/api/subscribers')
def api_subscribers():
    return jsonify([s for s in _load_subscribers() if s.get('active', True)])


@app.route('/api/subscribe/<int:sub_id>', methods=['DELETE'])
def api_unsubscribe(sub_id):
    subs = _load_subscribers()
    for s in subs:
        if s.get('id') == sub_id:
            s['active'] = False
            s['unsubscribed_at'] = datetime.now().isoformat()
            _save_subscribers(subs)
            return jsonify({"success": True})
    return jsonify({"success": False, "error": "订阅不存在"}), 404


# ============== API: 推送测试 ==============

@app.route('/api/send/test', methods=['POST'])
def api_send_test():
    data = request.json or {}
    key = (data.get('serverchan_key') or '').strip()
    if not key:
        return jsonify({"success": False, "error": "请提供 SendKey"}), 400
    return jsonify(test_serverchan(key))


@app.route('/api/send/all', methods=['POST'])
def api_send_all():
    report = _get_today_report()
    if not report:
        return jsonify({"success": False, "error": "今日报告未生成，请先刷新"})
    subs = _load_subscribers()
    active = [s for s in subs if s.get('active', True) and s.get('serverchan_key')]
    if not active:
        return jsonify({"success": False, "error": "没有配置了 SendKey 的活跃订阅者"})

    # 每个用户根据自己关注的板块二次过滤
    results = []
    for sub in active:
        sectors_filter = sub.get('sectors') or None
        result = send_news_report(sub['serverchan_key'], report['news_list'], sectors_filter)
        results.append({"email": sub['email'], "result": result})

    success = sum(1 for r in results if r['result'].get('success'))
    return jsonify({
        "success": True,
        "total": len(results),
        "success_count": success,
        "failed_count": len(results) - success,
        "details": results,
    })


# ============== 错误处理 ==============

@app.errorhandler(404)
def err_404(e):
    if request.path.startswith('/api/'):
        return jsonify({"error": "API not found"}), 404
    return render_template('index.html',
                           project_name=PROJECT_NAME,
                           project_version=PROJECT_VERSION,
                           project_tagline=PROJECT_TAGLINE,
                           scheduled_time=SCHEDULED_TIME,
                           push_time=PUSH_TIME,
                           market_open=MARKET_OPEN_TIME), 200


# ============== 启动 ==============

def _print_banner():
    banner = f"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   {PROJECT_NAME:^40}   ║
║   {f'v{PROJECT_VERSION}  ·  {PROJECT_TAGLINE}':^52}   ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║   🌐 浏览器访问    http://localhost:{FLASK_PORT:<5}                  ║
║   ⏰ 每日抓取时间  {SCHEDULED_TIME}                                    ║
║   📱 每日推送时间  {PUSH_TIME}                                    ║
║   📂 数据目录      {str(DATA_DIR):<30}   ║
║                                                              ║
║   ⚠️  首次使用请先启动 china-finance-rss：                    ║
║      cd china-finance-rss && python server.py                ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)


if __name__ == '__main__':
    _print_banner()
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG, use_reloader=False)
