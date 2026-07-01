#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘前财经资讯研判智能体 - Web 应用入口

启动：python app.py
浏览器：http://localhost:7860
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
from modules.send_wechat import send_news_report, test_pushplus, send_to_subscribers

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
    if active and any(s.get("serverchan_key") or s.get("pushplus_token") for s in active):
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


@app.route('/api/report/fetch/<date_str>')
def api_report_fetch(date_str):
    """按需检索：从三大平台翻页抓取指定日期的预测类资讯"""
    if not date_str.isdigit() or len(date_str) != 8:
        return jsonify({"success": False, "error": "日期格式应为 YYYYMMDD"}), 400

    # 检查是否已有报告
    existing = REPORTS_DIR / f"report_{date_str}.json"
    if existing.exists():
        with open(existing, 'r', encoding='utf-8') as fp:
            return jsonify(json.load(fp))

    try:
        from modules.fetch_news import fetch_news_for_date
        result = fetch_news_for_date(date_str)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": f"按需检索失败: {str(e)}"}), 500


@app.route('/api/trading-day/<date_str>')
def api_trading_day(date_str):
    """检查指定日期是否为交易日"""
    if not date_str.isdigit() or len(date_str) != 8:
        return jsonify({"error": "日期格式应为 YYYYMMDD"}), 400
    try:
        y, m, d = int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8])
        from datetime import date
        target = date(y, m, d)
        from modules.fetch_news import is_trading_day
        trading = is_trading_day(target)
        return jsonify({
            "date": date_str,
            "is_trading_day": trading,
            "weekday": target.weekday(),
            "weekday_cn": ["周一","周二","周三","周四","周五","周六","周日"][target.weekday()],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/history')
def api_history():
    items = []
    if REPORTS_DIR.exists():
        for f in sorted(REPORTS_DIR.iterdir(), reverse=True):
            if f.name.startswith('report_') and f.name.endswith('.json'):
                date_str = f.name.replace('report_', '').replace('.json', '')
                try:
                    with open(f, 'r', encoding='utf-8') as fp:
                        data = json.load(fp)
                    items.append({
                        "date": date_str,
                        "formatted_date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}",
                        "size": f.stat().st_size,
                        "timestamp": f.stat().st_mtime,
                        "news_count": data.get("news_count", len(data.get("news_list", []))),
                        "analyzed_at": data.get("analyzed_at", ""),
                    })
                except Exception:
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
    sendkey = (data.get('serverchan_key') or data.get('pushplus_token') or '').strip()
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
                push_result = test_pushplus(sendkey)

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
        push_result = test_pushplus(sendkey)

    return jsonify({
        "success": True,
        "message": "订阅成功！" + ("微信收到测试消息了吗？" if push_result and push_result.get("success") else "（如需微信推送请填写 Server酱 SendKey）"),
        "subscriber": sub,
        "push_result": push_result,
    })


@app.route('/api/subscribers')
def api_subscribers():
    result = []
    for s in _load_subscribers():
        if s.get('active', True):
            item = {k: v for k, v in s.items() if k != 'serverchan_key'}
            item['has_pushplus_token'] = bool((s.get('serverchan_key') or s.get('pushplus_token') or '').strip())
            result.append(item)
    return jsonify(result)


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
    key = (data.get('serverchan_key') or data.get('pushplus_token') or '').strip()
    if not key:
        return jsonify({"success": False, "error": "请提供 pushplus token"}), 400
    return jsonify(test_pushplus(key))


@app.route('/api/send/all', methods=['POST'])
def api_send_all():
    report = _get_today_report()
    if not report:
        return jsonify({"success": False, "error": "今日报告未生成，请先刷新"})
    subs = _load_subscribers()
    active = [s for s in subs if s.get('active', True) and (s.get('serverchan_key') or s.get('pushplus_token'))]
    if not active:
        return jsonify({"success": False, "error": "没有配置了 SendKey 的活跃订阅者"})

    # 每个用户根据自己关注的板块二次过滤
    results = []
    for sub in active:
        sectors_filter = sub.get('sectors') or None
        token = sub.get('pushplus_token') or sub.get('serverchan_key') or ''
        result = send_news_report(token, report['news_list'], sectors_filter)
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


def _ensure_rss_running():
    """在容器/创空间部署时，自动拉起 china-finance-rss 子进程（避免双进程端口冲突）"""
    rss_port = int(os.getenv("RSS_PORT", "8053"))
    try:
        r = requests.get(f"http://localhost:{rss_port}", timeout=1)
        if r.status_code == 200:
            print(f"[RSS] china-finance-rss 已在运行 (端口 {rss_port})")
            return None
    except Exception:
        pass

    rss_dir = Path(__file__).parent / "china-finance-rss"
    server_py = rss_dir / "server.py"
    if not server_py.exists():
        print(f"[RSS] 警告: 找不到 {server_py}，数据抓取将无法工作")
        return None

    print(f"[RSS] 正在启动 china-finance-rss (端口 {rss_port}) ...")
    proc = subprocess.Popen(
        [sys.executable, str(server_py)],
        cwd=str(rss_dir),
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    for _ in range(30):
        time.sleep(0.5)
        try:
            r = requests.get(f"http://localhost:{rss_port}", timeout=1)
            if r.status_code == 200:
                print(f"[RSS] 启动成功 (PID {proc.pid})")
                return proc
        except Exception:
            continue
    print(f"[RSS] 启动可能失败，请检查日志")
    return proc


def _run_with_gradio():
    """用 Gradio 包装 Flask（魔搭创空间部署需要 Gradio 兼容协议）

    注意：不能使用 WSGIMiddleware 挂载 Flask，因为 Gradio 4.x 的
    mount_gradio_app 会向父应用注入中间件，拦截所有 /flask/* 请求。
    正确做法：把路由直接以 FastAPI 形式注册到 Gradio 的底层 ASGI 应用上。
    """
    import gradio as gr
    from fastapi import Request as FastAPIRequest
    from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.templating import Jinja2Templates

    # 1. 自启 RSS
    rss_proc = _ensure_rss_running()

    # 2. 读取所有模板 HTML，把 CSS/JS 内联（避免 Gradio 嵌套后静态资源 404）
    def _read_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return ""

    css_main = _read_text(Path(__file__).parent / "static" / "css" / "main.css")
    js_app_raw = _read_text(Path(__file__).parent / "static" / "js" / "app.js")
    js_report_raw = _read_text(Path(__file__).parent / "static" / "js" / "report.js")

    # 把 fetch 绝对路径改成相对路径（iframe 内 Gradio 应用能正常解析）
    js_app = js_app_raw.replace("fetch('/api/", "fetch('api/")
    js_report = js_report_raw.replace("fetch('/api/", "fetch('api/")

    # 客户端路由脚本：把 <a href="/xxx"> 改为 hash 路由，避免顶层跳走
    router_js = r"""
<script>
/* ============== 客户端 SPA 路由（iframe 内安全导航） ============== */
(function(){
  const ROUTES = ['index','report','sectors','subscribe','history'];

  function showPage(name) {
    name = (name || 'index').toLowerCase();
    if (ROUTES.indexOf(name) < 0) name = 'index';
    document.querySelectorAll('.page-section').forEach(function(s){
      s.hidden = (s.id !== 'page-' + name);
    });
    // 顶部导航高亮
    document.querySelectorAll('.nav a[data-route]').forEach(function(a){
      a.classList.toggle('is-active', a.getAttribute('data-route') === name);
    });
    // 更新地址栏 hash（不触发导航）
    if (location.hash.replace('#/','') !== name) {
      try { history.replaceState(null, '', '#/' + name); } catch(e){}
    }
    // 触发各页面的初始化逻辑（只初始化一次）
    var sec = document.getElementById('page-' + name);
    if (sec && !sec.dataset.inited) {
      sec.dataset.inited = '1';
      if (name === 'report' && typeof window.initReport === 'function') {
        window.initReport();
      }
    }
    window.scrollTo(0, 0);
  }

  // 全局拦截站内 <a> 链接
  document.addEventListener('click', function(e){
    var a = e.target.closest && e.target.closest('a[href^="#/"]');
    if (!a) return;
    e.preventDefault();
    var name = a.getAttribute('href').replace('#/','').split('/')[0];
    showPage(name);
  });

  // 拦截顶导 / footer / 站内全部 /xxx 链接（防止 Gradio iframe 跳到平台 404）
  document.addEventListener('click', function(e){
    var a = e.target.closest && e.target.closest('a');
    if (!a) return;
    var href = a.getAttribute('href') || '';
    // 已经是 hash 路由 / 外部链接 / 锚点 / API 下载链接，都放过
    if (!href || href[0] !== '/' || href[1] === '/') return;
    if (href === '/api/' || href.indexOf('/api/') === 0) return;  // API 链接允许下载
    var seg = href.replace(/^\//,'').split('/')[0];
    if (['index','','report','sectors','subscribe','history'].indexOf(seg) >= 0) {
      e.preventDefault();
      showPage(seg === '' ? 'index' : seg);
    }
  });

  window.addEventListener('hashchange', function(){
    showPage(location.hash.replace('#/',''));
  });

  document.addEventListener('DOMContentLoaded', function(){
    showPage(location.hash.replace('#/','') || 'index');
  });
  // 立即执行一次（gr.HTML 嵌入时 DOMContentLoaded 可能已触发）
  showPage(location.hash.replace('#/','') || 'index');
})();
</script>
"""

    def _inline_assets(html: str, page: str = "index") -> str:
        """把 link/script 外链替换为内联 style/script 块"""
        if css_main:
            inline_style = f"<style>/* === main.css (inlined) === */\n{css_main}\n</style>"
            html = html.replace(
                '<link rel="stylesheet" href="/static/css/main.css">',
                inline_style,
            )
            html = html.replace(
                '<link rel="stylesheet" href="">',
                inline_style,
            )
            html = html.replace(
                '<link rel="stylesheet" href="{{ url_for(\'static\', filename=\'css/main.css\') }}">',
                inline_style,
            )
        if js_app:
            inline_app = f"<script>/* === app.js (inlined) === */\n{js_app}\n</script>"
            html = html.replace('<script src="/static/js/app.js"></script>', inline_app)
            html = html.replace('<script src=""></script>', inline_app)
            html = html.replace(
                '<script src="{{ url_for(\'static\', filename=\'js/app.js\') }}"></script>',
                inline_app,
            )
        if js_report and page == "report":
            inline_rep = f"<script>/* === report.js (inlined) === */\n{js_report}\n</script>"
            html = html.replace('<script src="/static/js/report.js"></script>', inline_rep)
            html = html.replace('<script src=""></script>', inline_rep)
        return html

    def _render(name: str, **extra) -> str:
        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader(str(Path(__file__).parent / "templates")))
        # 注入 url_for 桩函数（防止 Gradio 嵌入后 /static/ 路径失效）
        def _url_for(endpoint: str, **values) -> str:
            if endpoint == "static":
                return f"/static/{values.get('filename', '')}"
            return "#"
        env.globals["url_for"] = _url_for
        template = env.get_template(name)
        vars_map = {
            "project_name": PROJECT_NAME,
            "project_version": PROJECT_VERSION,
            "project_tagline": PROJECT_TAGLINE,
            "scheduled_time": SCHEDULED_TIME,
            "push_time": PUSH_TIME,
            "market_open": MARKET_OPEN_TIME,
            **extra,
        }
        html = template.render(**vars_map)
        page = name.replace(".html", "")
        return _inline_assets(html, page)

    # 渲染所有 5 个页面（每个是完整 HTML，含 head + body + 自己的内联 CSS/JS）
    index_html_raw = _render("index.html")
    report_html_raw = _render("report.html")
    sectors_html_raw = _render("sectors.html")
    subscribe_html_raw = _render("subscribe.html")
    history_html_raw = _render("history.html")

    import re

    def _to_section(name: str, full_html: str) -> str:
        """提取 <body> 内部，包成 <section id="page-xxx">"""
        m = re.search(r"<body[^>]*>(.*?)</body>", full_html, re.DOTALL)
        body = m.group(1) if m else full_html
        # 移除 section 内联 <style>（已并入主 CSS）和内联 <script src>（已替换），
        # 但保留 <script>xxx</script> 内联 JS 块（用于该页面初始化）
        return f'<section id="page-{name}" class="page-section" data-page="{name}">{body}</section>'

    sections_html = "\n".join([
        _to_section("index", index_html_raw),
        _to_section("report", report_html_raw),
        _to_section("sectors", sectors_html_raw),
        _to_section("subscribe", subscribe_html_raw),
        _to_section("history", history_html_raw),
    ])

    # 用 index 的 head（含主 CSS），把 5 个 section 拼成一个完整 SPA
    head_match = re.search(r"<head[^>]*>(.*?)</head>", index_html_raw, re.DOTALL)
    head_inner = head_match.group(1) if head_match else ""
    # 移除 head 里的内联 <style>/* main.css */...</style>（已统一）
    head_inner_clean = re.sub(
        r"<style>\s*/\*\s*===\s*main\.css\s*\(inlined\)\s*===\s*\*/.*?</style>",
        "", head_inner, flags=re.DOTALL,
    )
    # 移除 head 里残留的 <link rel="stylesheet" href="/static/...">
    head_inner_clean = re.sub(
        r'<link rel="stylesheet" href="[^"]*">', "", head_inner_clean,
    )
    # 移除 head 里的 <script src>（已统一）
    head_inner_clean = re.sub(
        r'<script src="[^"]*"></script>', "", head_inner_clean,
    )

    # 提取主 CSS（只在 head 里加一次）
    css_match = re.search(
        r"<style>\s*/\*\s*===\s*main\.css\s*\(inlined\)\s*===\s*\*/(.*?)</style>",
        index_html_raw, re.DOTALL,
    )
    css_block = ""
    if css_match:
        css_block = "<style>\n/* === main.css (unified) === */\n" + css_match.group(1) + "\n</style>"

    # report 页面有独立的 initReport，需要在 SPA 中保留为函数
    # report.js 默认会在 DOMContentLoaded 时执行 loadReport()，这在 SPA 中不合适
    # 把 report.js 里的 IIFE 包成函数，仅在切到 report 页时调用
    # 这里用占位符替换：把 report.js 里的 loadReport() 调用和 btnRefresh 监听挪到 initReport()
    report_init_js = ""
    if js_report:
        # 提取 report.js 中需要绑定的事件，去掉直接执行的 loadReport() 和 addEventListener
        # 简单方案：把整个 report.js 包到 initReport 函数中
        # report.js 末尾有 document.getElementById('btnRefresh').addEventListener + loadReport()
        # 把它们包成 function initReport() { ... }
        wrapped = re.sub(
            r"^document\.getElementById\('btnRefresh'\)\.addEventListener\(.*?loadReport\(\);",
            "document.getElementById('btnRefresh').addEventListener('click', refreshReport);",
            js_report, flags=re.DOTALL,
        )
        # 去掉顶层 loadReport() 调用
        wrapped = re.sub(r"^\s*loadReport\(\);\s*$", "", wrapped, flags=re.MULTILINE)
        report_init_js = (
            "<script>\nwindow.initReport = function(){\n"
            + wrapped
            + "\n};\n</script>"
        )

    # 主页 app.js 中的事件绑定保持原样（loadNews() 自动调用、按钮监听等）

    index_html = (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head>"
        "<meta charset=\"UTF-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        f"<title>{PROJECT_NAME} · 今日速览</title>"
        "<link rel=\"icon\" href=\"data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📊</text></svg>\">"
        + css_block +
        "</head><body>"
        + sections_html
        + report_init_js
        + router_js +
        "</body></html>"
    )
    # 4 个其他页面不再单独使用（保留兼容）
    report_html = index_html
    sectors_html = index_html
    subscribe_html = index_html
    history_html = index_html

    # 3. 创建 Gradio Blocks — 用 gr.HTML 渲染完整的 index.html（关键！）
    with gr.Blocks(
        title=PROJECT_NAME,
        theme=gr.themes.Default(),
    ) as demo:
        gr.HTML(value=index_html)

    app_fastapi = demo.app

    # 4. 静态文件
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app_fastapi.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # 5. 页面路由
    @app_fastapi.get("/", response_class=HTMLResponse)
    async def page_index():
        return HTMLResponse(index_html)

    @app_fastapi.get("/report", response_class=HTMLResponse)
    async def page_report():
        return HTMLResponse(report_html)

    @app_fastapi.get("/sectors", response_class=HTMLResponse)
    async def page_sectors():
        return HTMLResponse(sectors_html)

    @app_fastapi.get("/subscribe", response_class=HTMLResponse)
    async def page_subscribe():
        return HTMLResponse(subscribe_html)

    @app_fastapi.get("/history", response_class=HTMLResponse)
    async def page_history():
        return HTMLResponse(history_html)

    # 6. API 路由
    @app_fastapi.get("/api/news")
    async def api_news():
        report = _get_today_report()
        if not report:
            return JSONResponse({"success": False, "error": "暂无今日数据，请先执行一次抓取", "news_list": [], "news_count": 0, "stats": {}})
        return JSONResponse(report)

    @app_fastapi.post("/api/refresh")
    async def api_refresh():
        result = _run_full_pipeline(silent=False)
        return JSONResponse(result)

    @app_fastapi.get("/api/report/today")
    async def api_report_today():
        report = _get_today_report()
        if not report:
            return JSONResponse({"success": False, "error": "暂无今日数据"}, status_code=404)
        return JSONResponse(report)

    @app_fastapi.get("/api/report/date/{date_str}")
    async def api_report_date(date_str: str):
        if not date_str.isdigit() or len(date_str) != 8:
            return JSONResponse({"success": False, "error": "日期格式应为 YYYYMMDD"}, status_code=400)
        f = REPORTS_DIR / f"report_{date_str}.json"
        if not f.exists():
            return JSONResponse({"success": False, "error": f"未找到 {date_str} 的报告"}, status_code=404)
        with open(f, 'r', encoding='utf-8') as fp:
            return JSONResponse(json.load(fp))

    @app_fastapi.get("/api/report/date/{date_str}/markdown")
    async def api_report_date_md(date_str: str):
        if not date_str.isdigit() or len(date_str) != 8:
            return JSONResponse({"success": False, "error": "日期格式应为 YYYYMMDD"}, status_code=400)
        f = MARKDOWN_REPORTS_DIR / f"report_{date_str}.md"
        if not f.exists():
            return JSONResponse({"success": False, "error": f"未找到 {date_str} 的报告"}, status_code=404)
        return FileResponse(str(f), media_type="text/markdown", filename=f"report_{date_str}.md")

    @app_fastapi.get("/api/report/fetch/{date_str}")
    async def api_report_fetch(date_str: str):
        """按需检索：从三大平台翻页抓取指定日期的预测类资讯"""
        if not date_str.isdigit() or len(date_str) != 8:
            return JSONResponse({"success": False, "error": "日期格式应为 YYYYMMDD"}, status_code=400)

        existing = REPORTS_DIR / f"report_{date_str}.json"
        if existing.exists():
            with open(existing, 'r', encoding='utf-8') as fp:
                return JSONResponse(json.load(fp))

        try:
            from modules.fetch_news import fetch_news_for_date
            result = fetch_news_for_date(date_str)
            return JSONResponse(result)
        except Exception as e:
            return JSONResponse({"success": False, "error": f"按需检索失败: {str(e)}"}, status_code=500)

    @app_fastapi.get("/api/trading-day/{date_str}")
    async def api_trading_day(date_str: str):
        """检查指定日期是否为交易日"""
        if not date_str.isdigit() or len(date_str) != 8:
            return JSONResponse({"error": "日期格式应为 YYYYMMDD"}, status_code=400)
        try:
            y, m, d = int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8])
            from datetime import date as dt_date
            target = dt_date(y, m, d)
            from modules.fetch_news import is_trading_day
            trading = is_trading_day(target)
            return JSONResponse({
                "date": date_str,
                "is_trading_day": trading,
                "weekday": target.weekday(),
                "weekday_cn": ["周一","周二","周三","周四","周五","周六","周日"][target.weekday()],
            })
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @app_fastapi.get("/api/history")
    async def api_history():
        history = []
        for f in sorted(REPORTS_DIR.glob("report_*.json"), reverse=True):
            date_str = f.stem.replace("report_", "")
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                history.append({
                    "date": date_str,
                    "news_count": data.get("news_count", len(data.get("news_list", []))),
                    "stats": data.get("stats", {}),
                    "analyzed_at": data.get("analyzed_at", ""),
                })
            except Exception as e:
                history.append({"date": date_str, "error": str(e)})
        return JSONResponse({"success": True, "history": history})

    @app_fastapi.post("/api/subscribe")
    async def api_subscribe(request: FastAPIRequest):
        body = await request.json()
        email = (body.get("email") or "").strip()
        sendkey = (body.get("serverchan_key") or body.get("pushplus_token") or "").strip()
        sectors = body.get("sectors", []) or []
        phone = (body.get("phone") or "").strip()

        if not email:
            return JSONResponse({"success": False, "error": "请填写邮箱"}, status_code=400)

        subs = _load_subscribers()
        now_iso = datetime.now().isoformat()

        for s in subs:
            if s.get("email", "").lower() == email.lower():
                s.update({
                    "phone": phone,
                    "sectors": sectors,
                    "serverchan_key": sendkey,
                    "updated_at": now_iso,
                    "active": True,
                })
                _save_subscribers(subs)
                push_result = None
                if sendkey:
                    from modules.send_wechat import test_pushplus
                    push_result = test_pushplus(sendkey)
                return JSONResponse({
                    "success": True,
                    "message": "订阅已更新" + ("，测试消息已发送" if push_result and push_result.get("success") else ""),
                    "subscriber": {k: v for k, v in s.items() if k != "serverchan_key"},
                })

        new_sub = {
            "id": int(datetime.now().timestamp() * 1000),
            "email": email,
            "phone": phone,
            "sectors": sectors,
            "serverchan_key": sendkey,
            "subscribed_at": now_iso,
            "updated_at": now_iso,
            "active": True,
        }
        subs.append(new_sub)
        _save_subscribers(subs)

        push_result = None
        if sendkey:
            from modules.send_wechat import test_pushplus
            push_result = test_pushplus(sendkey)

        return JSONResponse({
            "success": True,
            "message": "订阅成功！" + ("微信收到测试消息了吗？" if push_result and push_result.get("success") else "（如需微信推送请填写 pushplus token）"),
            "subscriber": {k: v for k, v in new_sub.items() if k != "serverchan_key"},
        })

    @app_fastapi.get("/api/subscribers")
    async def api_subscribers():
        subs = _load_subscribers()
        safe = []
        for s in subs:
            item = {k: v for k, v in s.items() if k != "serverchan_key"}
            item['has_pushplus_token'] = bool((s.get('serverchan_key') or s.get('pushplus_token') or '').strip())
            safe.append(item)
        return JSONResponse({"success": True, "subscribers": safe, "total": len(safe)})

    @app_fastapi.delete("/api/subscribe/{sub_id}")
    async def api_unsubscribe(sub_id: int):
        subs = _load_subscribers()
        new_subs = [s for s in subs if s.get("id") != sub_id]
        if len(new_subs) == len(subs):
            return JSONResponse({"success": False, "error": f"未找到 ID={sub_id} 的订阅"}, status_code=404)
        _save_subscribers(new_subs)
        return JSONResponse({"success": True, "remaining": len(new_subs)})

    @app_fastapi.post("/api/send/test")
    async def api_send_test(request: FastAPIRequest):
        body = await request.json()
        key = (body.get("serverchan_key") or body.get("pushplus_token") or "").strip()
        if not key:
            return JSONResponse({"success": False, "error": "缺少 pushplus token"}, status_code=400)
        from modules.send_wechat import test_pushplus
        ok, msg = test_pushplus(key)
        return JSONResponse({"success": ok, "message": msg})

    @app_fastapi.post("/api/send/all")
    async def api_send_all():
        from modules.send_wechat import send_to_subscribers
        report = _get_today_report()
        if not report:
            return JSONResponse({"success": False, "error": "暂无今日报告"}, status_code=400)
        subs = _load_subscribers()
        active = [s for s in subs if s.get("active", True) and (s.get("serverchan_key") or s.get("pushplus_token"))]
        if not active:
            return JSONResponse({"success": False, "error": "无活跃订阅者"}, status_code=400)
        result = send_to_subscribers(active, report.get("news_list", []))
        return JSONResponse({"success": True, **result})

    # 7. 错误处理
    @app_fastapi.exception_handler(404)
    async def not_found(request: FastAPIRequest, exc):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": "API not found", "path": request.url.path}, status_code=404)
        return HTMLResponse(index_html, status_code=200)

    print(f"\n[启动] Gradio 模式（魔搭创空间兼容 - FastAPI 路由已注册到 Gradio）")
    print(f"   · 浏览器访问    http://localhost:{FLASK_PORT}/")
    print(f"   · 5 个页面       /, /report, /sectors, /subscribe, /history")
    print(f"   · API 接口       /api/* (12 个)\n")

    try:
        demo.launch(
            server_name=FLASK_HOST,
            server_port=FLASK_PORT,
            show_error=True,
        )
    finally:
        if rss_proc:
            rss_proc.terminate()
            print("[RSS] 子进程已停止")


if __name__ == '__main__':
    _print_banner()
    # 优先用 Gradio 包装（兼容魔搭创空间）
    # 通过环境变量 DISABLE_GRADIO=1 可强制使用 Flask 原生模式
    if os.getenv("DISABLE_GRADIO", "0") == "1":
        print(f"[启动] Flask 原生模式（DISABLE_GRADIO=1）\n")
        app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG, use_reloader=False)
    else:
        try:
            _run_with_gradio()
        except ImportError as e:
            print(f"[警告] Gradio 未安装 ({e})，降级到 Flask 原生模式")
            print(f"   提示: pip install gradio fastapi uvicorn\n")
            app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG, use_reloader=False)
