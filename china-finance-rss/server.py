#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""China Finance RSS Bridge

Lightweight RSS bridge server that converts Chinese financial news sources
into standard RSS 2.0 feeds.

Sources: CLS (财联社), Eastmoney (东方财富), THS (同花顺), Xueqiu (雪球)

Usage:
    python server.py
    PORT=9000 python server.py

Dependencies:
    - websocket-client (optional, only for Xueqiu CDP mode)
"""

import os
import json
import re
import signal
import sys
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from datetime import datetime, timezone
from time import time
from email.utils import formatdate

# Configuration via environment variables
PORT = int(os.getenv('PORT', '8053'))
CDP_URL = os.getenv('CDP_URL', 'http://localhost:9222')  # Chrome DevTools Protocol URL
CACHE_TTL = int(os.getenv('CACHE_TTL', '300'))  # Cache TTL in seconds (default: 5 min)

# In-memory cache
cache = {}


def fetch_json(url, headers=None):
    """Fetch URL with in-memory cache."""
    now = time()
    if url in cache and now - cache[url]['time'] < CACHE_TTL:
        return cache[url]['data']

    req = Request(url, headers=headers or {})
    with urlopen(req, timeout=10) as resp:
        data = resp.read().decode('utf-8')

    cache[url] = {'data': data, 'time': now}
    return data


def escape_xml(text):
    """Escape special XML characters."""
    return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;'))


def timestamp_to_rfc822(ts):
    """Convert Unix timestamp to RFC 822 date string."""
    return formatdate(timeval=ts, localtime=False, usegmt=True)


def generate_rss(title, link, description, items):
    """Generate standard RSS 2.0 XML."""
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>{escape_xml(title)}</title>
<link>{escape_xml(link)}</link>
<description>{escape_xml(description)}</description>
<lastBuildDate>{formatdate(timeval=None, localtime=False, usegmt=True)}</lastBuildDate>
'''
    for item in items:
        xml += '<item>\n'
        xml += f'<title>{escape_xml(item["title"])}</title>\n'
        xml += f'<link>{escape_xml(item["link"])}</link>\n'
        xml += f'<description>{escape_xml(item["description"])}</description>\n'
        xml += f'<pubDate>{item["pubDate"]}</pubDate>\n'
        xml += f'<guid isPermaLink="false">{escape_xml(item["guid"])}</guid>\n'
        xml += '</item>\n'

    xml += '</channel>\n</rss>'
    return xml


# ── Source handlers ──────────────────────────────────────────────────────────

def handle_cls_telegraph():
    """CLS Telegraph (财联社电报) - Real-time financial news flashes."""
    url = 'https://www.cls.cn/nodeapi/updateTelegraph?app=CailianpressWeb&os=web&sv=8.4.6&sign=8bc6630fbf8b4a195cd99b4da66ed07b&rn=50'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.cls.cn/telegraph'
    }

    data = json.loads(fetch_json(url, headers))
    items = []

    for item in data.get('data', {}).get('roll_data', []):
        items.append({
            'title': item.get('brief', item.get('content', ''))[:100],
            'link': f"https://www.cls.cn/telegraph/{item['id']}",
            'description': item.get('content', ''),
            'pubDate': timestamp_to_rfc822(item.get('ctime', 0)),
            'guid': f"cls_{item['id']}"
        })

    return generate_rss('财联社电报', 'https://www.cls.cn/telegraph', '财联社实时快讯', items)


def handle_eastmoney_kuaixun():
    """Eastmoney 7x24 News (东方财富快讯)."""
    url = 'https://newsapi.eastmoney.com/kuaixun/v1/getlist_102_ajaxResult_50_1_.html'
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://kuaixun.eastmoney.com/'}

    data = fetch_json(url, headers)
    match = re.search(r'var ajaxResult=(\{.*\});?', data, re.DOTALL)
    if not match:
        return generate_rss('东方财富快讯', 'https://kuaixun.eastmoney.com/', '东方财富7x24快讯', [])

    result = json.loads(match.group(1))
    items = []

    for item in result.get('LivesList', []):
        showtime = item.get('showtime', '')
        try:
            # 东方财富的 showtime 是北京时间（naive 字符串）
            # 显式标注为 +08:00 时区，避免 dt.timestamp() 在不同时区环境下产生不同结果
            dt = datetime.strptime(showtime, '%Y-%m-%d %H:%M:%S').replace(
                tzinfo=timezone(timedelta(hours=8))
            )
            pubdate = format_datetime(dt)
        except Exception:
            pubdate = formatdate()

        items.append({
            'title': item.get('title', ''),
            'link': f"https://kuaixun.eastmoney.com/a/{item.get('newsid', '')}.html",
            'description': item.get('digest', ''),
            'pubDate': pubdate,
            'guid': f"eastmoney_{item.get('newsid', '')}"
        })

    return generate_rss('东方财富快讯', 'https://kuaixun.eastmoney.com/', '东方财富7x24快讯', items)


def handle_ths_kuaixun():
    """THS 7x24 News (同花顺快讯)."""
    url = 'https://news.10jqka.com.cn/tapp/news/push/stock/?page=1&tag=&track=website&pagesize=50'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://news.10jqka.com.cn/'
    }

    data = json.loads(fetch_json(url, headers))
    items = []

    for item in data.get('data', {}).get('list', []):
        items.append({
            'title': item.get('title', ''),
            'link': f"https://news.10jqka.com.cn/{item.get('seq', '')}",
            'description': item.get('digest', item.get('remark', '')),
            'pubDate': timestamp_to_rfc822(int(item.get('ctime', 0))),
            'guid': f"ths_{item.get('seq', '')}"
        })

    return generate_rss('同花顺快讯', 'https://news.10jqka.com.cn/', '同花顺7x24快讯', items)


def handle_sina_kuaixun():
    """Sina Finance 7x24 News (新浪财经7x24快讯)."""
    url = 'https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=50&page=1&r=0.5'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://finance.sina.com.cn/'
    }

    try:
        data = json.loads(fetch_json(url, headers))
    except Exception:
        return generate_rss('新浪财经快讯', 'https://finance.sina.com.cn/', '新浪财经7x24快讯', [])

    items = []

    for item in data.get('result', {}).get('data', []):
        items.append({
            'title': item.get('title', ''),
            'link': item.get('url', ''),
            'description': item.get('intro', ''),
            'pubDate': timestamp_to_rfc822(int(item.get('ctime', 0))),
            'guid': f"sina_{item.get('id', '')}"
        })

    return generate_rss('新浪财经快讯', 'https://finance.sina.com.cn/', '新浪财经7x24快讯', items)


def xueqiu_fetch_via_cdp(api_path):
    """Fetch Xueqiu API via Chrome CDP to bypass WAF.

    Requires:
    - Chrome running with --remote-debugging-port
    - A Xueqiu tab open and logged in
    - pip install websocket-client
    """
    try:
        import websocket as ws_mod  # noqa: lazy import
    except ImportError:
        return None

    try:
        tabs = json.loads(urllib.request.urlopen(f"{CDP_URL}/json", timeout=5).read())
        xq_tab = next((t for t in tabs if 'xueqiu' in t.get('url', '')), None)
        if not xq_tab:
            return None

        ws_url = xq_tab['webSocketDebuggerUrl']
        # Replace localhost with CDP_URL host if connecting remotely
        cdp_host = urlparse(CDP_URL).hostname
        ws_url = ws_url.replace('127.0.0.1', cdp_host).replace('localhost', cdp_host)

        ws = ws_mod.create_connection(ws_url, timeout=15)
        js = f'fetch("{api_path}").then(r=>r.json()).then(d=>JSON.stringify(d))'
        ws.send(json.dumps({
            'id': 1,
            'method': 'Runtime.evaluate',
            'params': {'expression': js, 'awaitPromise': True, 'returnByValue': True}
        }))
        result = json.loads(ws.recv())
        ws.close()
        return json.loads(result.get('result', {}).get('result', {}).get('value', '{}'))
    except Exception:
        return None


def handle_xueqiu_user(uid):
    """Xueqiu user timeline (雪球用户动态).

    Uses Chrome CDP to bypass Alibaba Cloud WAF.
    """
    data = xueqiu_fetch_via_cdp(f'/v4/statuses/user_timeline.json?user_id={uid}&page=1&type=0')

    if not data:
        return generate_rss(
            '雪球用户动态', f'https://xueqiu.com/u/{uid}',
            'Error: Chrome CDP not available or Xueqiu tab not found. '
            'See README for setup instructions.', []
        )

    items = []
    for item in data.get('statuses', []):
        created_at = item.get('created_at', 0) // 1000
        items.append({
            'title': item.get('title', item.get('text', ''))[:100],
            'link': f"https://xueqiu.com/{item.get('id', '')}",
            'description': item.get('description', item.get('text', '')),
            'pubDate': timestamp_to_rfc822(created_at),
            'guid': f"xueqiu_{item.get('id', '')}"
        })

    username = data.get('statuses', [{}])[0].get('user', {}).get('screen_name', uid)
    return generate_rss(f'雪球-{username}', f'https://xueqiu.com/u/{uid}', f'{username}的雪球动态', items)


# ── HTTP Server ──────────────────────────────────────────────────────────────

ROUTES = {
    '/cls/telegraph': ('Sina Finance (新浪财经7x24)', handle_sina_kuaixun),  # 财联社API已失效，改用新浪财经
    '/eastmoney/kuaixun': ('Eastmoney News (东方财富快讯)', handle_eastmoney_kuaixun),
    '/ths/kuaixun': ('THS News (同花顺快讯)', handle_ths_kuaixun),
}


class RSSHandler(BaseHTTPRequestHandler):
    """HTTP request handler for RSS feeds."""

    def log_message(self, format, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")

    def do_GET(self):
        path = urlparse(self.path).path

        try:
            if path in ROUTES:
                _, handler = ROUTES[path]
                xml = handler()
            elif path.startswith('/xueqiu/user/'):
                uid = path.split('/')[-1]
                xml = handle_xueqiu_user(uid)
            elif path == '/':
                self._serve_index()
                return
            else:
                self.send_error(404, 'Not Found. Visit / for available feeds.')
                return

            self.send_response(200)
            self.send_header('Content-Type', 'application/rss+xml; charset=utf-8')
            self.end_headers()
            self.wfile.write(xml.encode('utf-8'))

        except Exception as e:
            self.send_error(500, f'Internal Server Error: {str(e)}')

    def _serve_index(self):
        """Serve a simple index page listing available feeds."""
        lines = ['<html><head><title>China Finance RSS Bridge</title></head>',
                 '<body><h1>🇨🇳 China Finance RSS Bridge</h1><ul>']
        for path, (name, _) in ROUTES.items():
            lines.append(f'<li><a href="{path}">{name}</a></li>')
        lines.append(f'<li><a href="/xueqiu/user/1247347556">Xueqiu User Example (雪球)</a></li>')
        lines.append('</ul><p>Add any URL above to your RSS reader.</p></body></html>')
        html = '\n'.join(lines)
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))


def main():
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    print(f'China Finance RSS Bridge running on http://localhost:{PORT}')
    print(f'Cache TTL: {CACHE_TTL}s | CDP: {CDP_URL}\n')
    print('Available feeds:')
    for path, (name, _) in ROUTES.items():
        print(f'  http://localhost:{PORT}{path}  — {name}')
    print(f'  http://localhost:{PORT}/xueqiu/user/{{uid}}  — Xueqiu User (雪球)')
    print(f'\nNote: Xueqiu requires Chrome with CDP enabled + a logged-in Xueqiu tab.')
    print(f'Visit http://localhost:{PORT}/ for the web index.\n')

    server = HTTPServer(('0.0.0.0', PORT), RSSHandler)
    server.serve_forever()


if __name__ == '__main__':
    main()
