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
import re
import time
import threading
import subprocess
from datetime import datetime, timedelta, timezone
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
from modules.persistence import (
    PERSISTENCE_ENABLED, save_json_to_github, load_json_from_github,
    sync_github_to_local, status as persistence_status,
)
from scheduler import job_pipeline, job_push
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# ============== 常量 ==============
CST = timezone(timedelta(hours=8))  # 北京时区
_subscribers_lock = threading.Lock()  # subscribers.json 写入锁
_push_log_lock = threading.Lock()    # push_log.json 写入锁
_last_refresh_ts = 0                 # /api/refresh 限流时间戳
_REFRESH_MIN_INTERVAL = 60           # 刷新最小间隔（秒）
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()  # 管理操作鉴权 token

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


# RSS 自启已取消：Render 上不需要（也没法用）RSS 子进程
# 推送功能通过 send_wechat.py 直接调用 Server 酱 API，不需要本地 RSS
# 如需抓取资讯，请用户主动点击刷新或使用订阅推送功能


# ============== APScheduler 定时任务（Render 单进程跑用） ==============

_scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def _self_ping():
    """自 ping 保活，防止 Render 免费层 15 分钟休眠"""
    try:
        url = os.getenv("RENDER_EXTERNAL_URL", f"http://localhost:{FLASK_PORT}")
        r = requests.get(url, timeout=10)
        status = '成功' if r.status_code == 200 else f'HTTP {r.status_code}'
        print(f"[PING] {datetime.now(CST):%H:%M:%S} 自 ping {status}")
    except Exception as e:
        print(f"[PING] 自 ping 失败: {e}")


def _start_scheduler():
    """启动 APScheduler（gunicorn 主进程 + 本地 Flask 都会触发）

    - 用途：线上 Render 没有 Windows 任务计划，靠 gunicorn 进程内挂后台线程调度
    - 时区：强制 Asia/Shanghai（不受 Render 服务器 UTC 影响）
    - 防重入：gunicorn 多个 worker 会重复 import，但 BackgroundScheduler 默认是单例

    设计原则：只保留 9:25 自动推送，8:30 任务已去掉
    - 9:25 之前没数据是正常的（用户需要主动刷新或订阅推送触发）
    - 避免 8:30 任务在 Render 休眠时失效导致"假阴性"

    关键：整个函数用 try/except 包裹，绝不让 APScheduler 启动失败导致 gunicorn 崩溃
    """
    try:
        if _scheduler.running:
            return

        from config import PUSH_TIME
        ph, pm = PUSH_TIME.split(":")

        _scheduler.add_job(
            job_push,
            CronTrigger(hour=int(ph), minute=int(pm), timezone="Asia/Shanghai"),
            id="push_wechat",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        # 自 ping 保活：每 10 分钟请求自身，防止 Render 免费层休眠
        _scheduler.add_job(
            _self_ping,
            'interval',
            minutes=10,
            id="self_ping",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        _scheduler.start()
        print(f"[SCHEDULER] APScheduler 已启动（时区 Asia/Shanghai）")
        print(f"  · {PUSH_TIME}  推送微信（提前重抓一次确保资讯最新）")
        print(f"  · 每 10 分钟  自 ping 保活（防 Render 休眠）")
        print(f"  · 其他时段：用户点击刷新 + 已订阅时，推送至该用户")
    except Exception as e:
        # 调度器启动失败不影响 Web 服务
        print(f"[SCHEDULER] 启动失败（Web 服务继续运行）: {e}")


# Scheduler 启动已取消：Render 免费层 15 分钟休眠，APScheduler 经常失效
# 改为：用户主动点击刷新 / 订阅推送时执行，不依赖后台调度
# 取消模块加载时的副作用，确保 gunicorn 启动零阻塞


# ============== 持久化：启动时从 GitHub 恢复数据 ==============
# 关键：GitHub API 调用必须用 try/except 保护，绝不能让网络问题阻塞 gunicorn 启动
print(f"[PERSIST] GitHub 持久化：{persistence_status()}")
if PERSISTENCE_ENABLED:
    def _async_sync_from_github():
        """启动时从 GitHub 恢复数据，失败不影响 Web 服务"""
        try:
            sync_github_to_local("data/subscribers.json", SUBSCRIBERS_FILE)
            sync_github_to_local("data/push_log.json", DATA_DIR / "push_log.json")
        except Exception as e:
            print(f"[PERSIST] 启动时从 GitHub 恢复数据失败（不影响服务）: {e}")

    # 异步执行，不阻塞 gunicorn 启动
    _persist_thread = threading.Thread(target=_async_sync_from_github, daemon=True, name="persist-bootstrap")
    _persist_thread.start()


# ============== 辅助函数 ==============

def _load_subscribers():
    # 先尝试本地文件
    if SUBSCRIBERS_FILE.exists():
        try:
            with open(SUBSCRIBERS_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:  # 文件非空
                    return json.loads(content)
        except (json.JSONDecodeError, OSError):
            pass
    # 本地为空/不存在/解析失败 → 尝试从 GitHub 拉取
    if PERSISTENCE_ENABLED:
        data = load_json_from_github("data/subscribers.json")
        if data is not None:
            # 立即写回本地，避免下次再走网络
            try:
                SUBSCRIBERS_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(SUBSCRIBERS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except OSError:
                pass
            return data
    return []


def _save_subscribers(subs):
    with _subscribers_lock:
        with open(SUBSCRIBERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(subs, f, ensure_ascii=False, indent=2)
    if PERSISTENCE_ENABLED:
        save_json_to_github("data/subscribers.json", subs)


def _get_today_report():
    today_str = datetime.now(CST).strftime('%Y%m%d')
    f = REPORTS_DIR / f"report_{today_str}.json"
    if f.exists():
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                return json.load(fp)
        except Exception:
            return None
    return None


def _save_report(payload):
    today_str = datetime.now(CST).strftime('%Y%m%d')
    f = REPORTS_DIR / f"report_{today_str}.json"
    with open(f, 'w', encoding='utf-8') as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
    return f


# ============== 隐私 & 令牌辅助 ==============

PUSH_LOG_FILE = DATA_DIR / "push_log.json"


def _mask_email(email: str) -> str:
    """邮箱脱敏：z***@example.com"""
    if not email or '@' not in email:
        return email
    name, domain = email.split('@', 1)
    if len(name) <= 2:
        masked = name[0] + '*'
    else:
        masked = name[0] + '*' * (len(name) - 2) + name[-1]
    return f"{masked}@{domain}"


def _find_subscriber_by_sendkey(sendkey: str):
    """通过 sendkey 查找订阅者（令牌方案）"""
    if not sendkey:
        return None
    for s in _load_subscribers():
        if s.get('serverchan_key', '').strip() == sendkey:
            return s
    return None


def _log_push(email: str, sendkey: str, sectors: list, news_count: int, success: bool):
    """记录推送历史到 push_log.json（令牌方案：历史页展示用户推送记录）"""
    with _push_log_lock:
        log = []
        if PUSH_LOG_FILE.exists():
            try:
                with open(PUSH_LOG_FILE, 'r', encoding='utf-8') as f:
                    log = json.load(f)
            except Exception:
                log = []
        now_cst = datetime.now(CST)
        log.append({
            "date": now_cst.strftime('%Y%m%d'),
            "timestamp": now_cst.isoformat(),
            "email": email,
            "sendkey": sendkey,
            "sectors": sectors or [],
            "news_count": news_count,
            "success": success,
        })
        # 保留最近 500 条
        log = log[-500:]
        with open(PUSH_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    # 同步到 GitHub（防 Render 重启丢失）
    if PERSISTENCE_ENABLED:
        save_json_to_github("data/push_log.json", log)


def _run_full_pipeline(silent: bool = False, push_to_all: bool = False):
    """执行完整抓取-分析-生成流程，返回 dict 结果（不直接返回 jsonify）

    Args:
        silent:       是否静默（不打印日志）
        push_to_all:  是否推送给所有订阅者（默认 False，由调用方按需推）
    """
    if not silent:
        print("=" * 60)
        print(f"[{datetime.now(CST):%Y-%m-%d %H:%M:%S}] 开始执行完整流程")
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

    # 默认不推送；只有显式 push_to_all=True 才推给所有订阅者
    push_summary = None
    if push_to_all:
        subscribers = _load_subscribers()
        active = [s for s in subscribers if s.get("active", True)]
        push_summary = {"total": 0, "success": 0, "failed": 0}
        if active and active[0].get("serverchan_key"):
            push_summary = send_to_subscribers(active, analyzed["news_list"])
            if not silent:
                print(f"✅ 全量推送完成：{push_summary['success']}/{push_summary['total']}")

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
    """手动刷新：跑完整抓取流程（不自动推送给所有订阅者）

    可选行为：如果请求 body 带了 sendkey，则额外推送给该用户
    - 设计目的：用户订阅后点击刷新 → 微信收到当日资讯
    - 普通用户（未带 sendkey）刷新：只更新页面，不推送
    """
    global _last_refresh_ts
    now_ts = time.time()
    if now_ts - _last_refresh_ts < _REFRESH_MIN_INTERVAL:
        wait = int(_REFRESH_MIN_INTERVAL - (now_ts - _last_refresh_ts))
        return jsonify({
            "success": False,
            "error": f"刷新太频繁，请 {wait} 秒后再试",
            "retry_after": wait,
        }), 429
    _last_refresh_ts = now_ts

    data = request.json or {}
    user_sendkey = (data.get("sendkey") or "").strip()

    result = _run_full_pipeline(silent=True, push_to_all=False)

    # 如果该用户已订阅（带 sendkey），额外推给他一次
    if user_sendkey and result.get("success"):
        try:
            from modules.send_wechat import send_news_report
            sub = _find_subscriber_by_sendkey(user_sendkey)
            sub_sectors = sub.get('sectors') if sub else None
            personal_push = send_news_report(user_sendkey, result.get("news_list", []), sub_sectors)
            result["personal_push"] = personal_push
            # 记录推送日志（令牌方案：历史页展示）
            _log_push(
                email=sub.get('email', '') if sub else '',
                sendkey=user_sendkey,
                sectors=sub_sectors or [],
                news_count=len(result.get("news_list", [])),
                success=personal_push.get('success', False),
            )
        except Exception as e:
            result["personal_push"] = {"success": False, "message": f"推送异常: {e}"}

    return jsonify(result)


@app.route('/api/report/today')
def api_report_today():
    today_str = datetime.now().strftime('%Y%m%d')
    md = MARKDOWN_REPORTS_DIR / f"report_{today_str}.md"
    if not md.exists():
        return jsonify({"success": False, "error": "今日简报尚未生成，请先刷新"})
    with open(md, 'r', encoding='utf-8') as f:
        content = f.read()

    # 令牌方案：如果带 sendkey，返回该用户关注板块的过滤资讯
    personalized = None
    sendkey = (request.args.get('sendkey') or '').strip()
    if sendkey:
        sub = _find_subscriber_by_sendkey(sendkey)
        if sub and sub.get('sectors'):
            report_json = _get_today_report()
            if report_json:
                sectors = sub['sectors']
                filtered = [
                    n for n in report_json.get('news_list', [])
                    if n.get('sectors') and any(s in n['sectors'] for s in sectors)
                ]
                personalized = {
                    'sectors': sectors,
                    'news_list': filtered,
                    'count': len(filtered),
                }

    return jsonify({
        "success": True,
        "content": content,
        "generated_at": datetime.fromtimestamp(md.stat().st_mtime, tz=CST).isoformat(),
        "personalized": personalized,
    })


@app.route('/api/report/date/<date_str>')
def api_report_date(date_str):
    # 路径遍历防护：只允许 8 位数字
    if not re.match(r'^\d{8}$', date_str):
        return jsonify({"error": "日期格式无效"}), 400
    f = REPORTS_DIR / f"report_{date_str}.json"
    if not f.exists():
        return jsonify({"error": "报告不存在"}), 404
    with open(f, 'r', encoding='utf-8') as fp:
        return jsonify(json.load(fp))


@app.route('/api/report/date/<date_str>/markdown')
def api_report_date_md(date_str):
    if not re.match(r'^\d{8}$', date_str):
        return jsonify({"error": "日期格式无效"}), 400
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


@app.route('/api/my-pushes')
def api_my_pushes():
    """令牌方案：返回当前 sendkey 对应的推送历史记录"""
    sendkey = (request.args.get('sendkey') or '').strip()
    if not sendkey:
        return jsonify([])
    log = []
    if PUSH_LOG_FILE.exists():
        try:
            with open(PUSH_LOG_FILE, 'r', encoding='utf-8') as f:
                log = json.load(f)
        except Exception:
            log = []
    return jsonify([l for l in log if l.get('sendkey') == sendkey])


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

    # 邮箱格式校验
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({"success": False, "error": "邮箱格式无效"}), 400

    # SendKey 格式校验（如果填了）
    if sendkey and not re.match(r'^SCT[a-zA-Z0-9]+$', sendkey):
        return jsonify({"success": False, "error": "SendKey 格式无效（应以 SCT 开头）"}), 400

    subscribers = _load_subscribers()
    now_iso = datetime.now(CST).isoformat()

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

    # 新增（使用 max(id)+1 避免取消订阅后 id 重复）
    all_ids = [s.get('id', 0) for s in subscribers]
    new_id = max(all_ids) + 1 if all_ids else 1
    sub = {
        "id": new_id,
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
    """返回订阅者列表（脱敏：邮箱打码，不返回 sendkey/phone）"""
    safe = []
    for s in _load_subscribers():
        if not s.get('active', True):
            continue
        safe.append({
            'id': s.get('id'),
            'email': _mask_email(s.get('email', '')),
            'sectors': s.get('sectors', []),
            'subscribed_at': s.get('subscribed_at', ''),
            'has_sendkey': bool(s.get('serverchan_key')),
        })
    return jsonify(safe)


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
    # 鉴权：需要 ADMIN_TOKEN（如未配置则允许，方便本地开发）
    if ADMIN_TOKEN:
        token = (request.headers.get('X-Admin-Token') or '').strip()
        if token != ADMIN_TOKEN:
            return jsonify({"success": False, "error": "未授权：需要管理员 token"}), 403
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
        # 记录推送日志（令牌方案：历史页展示）
        _log_push(
            email=sub.get('email', ''),
            sendkey=sub['serverchan_key'],
            sectors=sectors_filter or [],
            news_count=len(report.get('news_list', [])),
            success=result.get('success', False),
        )

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
                           market_open=MARKET_OPEN_TIME), 404


# ============== 健康检查 ==============

@app.route('/healthz')
def healthz():
    """轻量健康检查端点（供 Render healthCheck 使用）"""
    return jsonify({"status": "ok"}), 200


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
