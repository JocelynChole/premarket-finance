#!/usr/bin/env python3
"""
盘前财经资讯助手 - 数据抓取模块
通过 china-finance-rss 服务获取新浪财经、东方财富、同花顺资讯
"""
import re
import requests
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
import sys
import json
from difflib import SequenceMatcher

# XML 解析：优先使用 defusedxml 防御 XXE，不可用则回退到标准库
try:
    from defusedxml import ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

# 模块顶部
sys.path.insert(0, str(__file__).rsplit('/', 2)[0] if '/' in __file__ else str(__file__).rsplit('\\', 2)[0])
from config import REPORTS_DIR

# china-finance-rss 服务地址（优先从 config 读取，失败则 fallback）
try:
    from config import RSS_BASE_URL
except ImportError:
    RSS_BASE_URL = "http://localhost:8053"

# RSS 端点配置
RSS_ENDPOINTS = {
    "新浪财经": f"{RSS_BASE_URL}/cls/telegraph",  # /cls/telegraph 路由内部已指向新浪财经 handler
    "东方财富": f"{RSS_BASE_URL}/eastmoney/kuaixun",
    "同花顺": f"{RSS_BASE_URL}/ths/kuaixun",
}

# 中文星期映射
WEEKDAY_CN = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}

# 北京时区（+8）
CST = timezone(timedelta(hours=8))

# 支持的时间格式（按优先级匹配）
# 备注：%z 可以同时识别 +0800 和 +08:00 两种格式
TIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%a, %d %b %Y %H:%M:%S %z",   # 带时区偏移（如 +0800 / +08:00 / +0000）
    "%a, %d %b %Y %H:%M:%S GMT",  # RFC 822 格式（带 GMT 字面量 = UTC）
    "%a, %d %b %Y %H:%M:%S",      # RFC 822 格式（无时区）
    "%d %b %Y %H:%M:%S",
]


def parse_pub_time(pub_time_str: str) -> Optional[datetime]:
    """
    解析 RSS 时间字符串为带时区的 datetime 对象（aware datetime，UTC 时区）
    - 自动识别 RFC 822、ISO 8601 等常见格式
    - 无时区标记的，假定为北京时间（+08:00）
    - 带其他时区标记的（GMT / +0000 / +08:00 等），自动转换
    - 解析失败返回 None
    """
    if not pub_time_str or not isinstance(pub_time_str, str):
        return None

    text = pub_time_str.strip()
    # 清洗时区字串
    text = text.replace("GMT+0800", "+0800").replace("CST", "+0800").strip()
    # "GMT" 字面量 = UTC：把字面 GMT 替换成 +0000，让 %z 识别
    # 例: "Tue, 16 Jun 2026 10:36:00 GMT" → "Tue, 16 Jun 2026 10:36:00 +0000"
    import re as _re
    text = _re.sub(r'\s+GMT\s*$', ' +0000', text)

    for fmt in TIME_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                # 无时区标记 → 假定为北京时间（中国财经资讯源基本都用北京时间）
                dt = dt.replace(tzinfo=CST)
            # 统一返回 UTC（aware datetime）
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue

    return None


def extract_time_fields(pub_time_str: str) -> Dict:
    """
    从原始时间字符串提取 4 个独立字段，统一按北京时间显示

    返回字段：
      - pub_time        原始字符串（保留）
      - pub_datetime    ISO 格式（带 +08:00 后缀，便于前端识别时区）
      - pub_date        北京时间日期 "2026-06-16"
      - pub_time_of_day 北京时间时分 "18:36"
      - pub_weekday     中文星期 "周三"
      - pub_display     友好显示 "2026-06-16 18:36 周三"
      - pub_timestamp   Unix 时间戳（用于排序）
    """
    dt_utc = parse_pub_time(pub_time_str)
    if dt_utc is None:
        return {
            "pub_time": pub_time_str or "",
            "pub_datetime": "",
            "pub_date": "",
            "pub_time_of_day": "",
            "pub_weekday": "",
            "pub_display": pub_time_str or "",
            "pub_timestamp": 0,
        }

    # 转北京时间生成显示字段
    dt_cst = dt_utc.astimezone(CST)
    return {
        "pub_time": pub_time_str or "",
        "pub_datetime": dt_cst.isoformat(),
        "pub_date": dt_cst.strftime("%Y-%m-%d"),
        "pub_time_of_day": dt_cst.strftime("%H:%M"),
        "pub_weekday": WEEKDAY_CN.get(dt_cst.weekday(), ""),
        "pub_display": f"{dt_cst.strftime('%Y-%m-%d %H:%M')} {WEEKDAY_CN.get(dt_cst.weekday(), '')}",
        "pub_timestamp": int(dt_utc.timestamp()),
    }


def parse_rss_xml(xml_content: str, source: str) -> List[Dict]:
    """解析RSS XML内容"""
    news_list = []

    try:
        root = ET.fromstring(xml_content)
        for item in root.findall('.//item'):
            title_el = item.find('title')
            desc_el = item.find('description')
            pub_date_el = item.find('pubDate')
            link_el = item.find('link')

            title = title_el.text if title_el is not None and title_el.text else ""
            content = desc_el.text if desc_el is not None and desc_el.text else ""
            pub_time = pub_date_el.text if pub_date_el is not None and pub_date_el.text else ""
            link = link_el.text if link_el is not None and link_el.text else ""

            # 构造 news 字典
            news_item = {
                "title": title,
                "content": content,
                "source": source,
                "link": link,
            }
            # 添加解析后的 4 个时间字段
            news_item.update(extract_time_fields(pub_time))
            news_list.append(news_item)

    except ET.ParseError as e:
        print(f"  解析 {source} XML 失败: {e}")
    except Exception as e:
        print(f"  处理 {source} 数据时出错: {e}")

    return news_list


def fetch_from_rss(source_name: str, url: str, timeout: int = 15) -> List[Dict]:
    """从 china-finance-rss 服务获取指定来源的资讯"""
    try:
        print(f"正在抓取 {source_name}...")
        response = requests.get(
            url,
            timeout=timeout,
            headers={'User-Agent': 'PremarketFinance/1.0 (RSS Reader)'},
        )
        response.encoding = 'utf-8'

        if response.status_code != 200:
            print(f"  {source_name}：服务返回错误 {response.status_code}，跳过")
            return []

        content = response.text.strip()

        if not content or content.startswith('<!DOCTYPE') or 'Error' in content[:100]:
            print(f"  {source_name}：服务返回无效数据，跳过")
            return []

        # 解析 RSS XML
        news_list = parse_rss_xml(content, source_name)

        print(f"  {source_name}：获取到 {len(news_list)} 条")
        return news_list

    except requests.exceptions.ConnectionError:
        print(f"  {source_name}：连接 RSS 服务失败（请确保 china-finance-rss 已启动）")
        return []
    except requests.exceptions.Timeout:
        print(f"  {source_name}：请求超时，跳过")
        return []
    except Exception as e:
        print(f"  {source_name}：抓取失败 ({e})，跳过")
        return []


def check_rss_service() -> bool:
    """检查 RSS 服务是否可用"""
    try:
        response = requests.get(RSS_BASE_URL, timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def fetch_all_news() -> List[Dict]:
    """从所有来源抓取资讯（单个源失败不影响其他源）

    直接调用 china-finance-rss/server.py 里的 handler 函数，
    不通过 HTTP 桥接层，省掉子进程 + 端口 + HTTP 解析。

    旧逻辑：requests.get("http://localhost:8053/...") 依赖 RSS 子进程
    新逻辑：直接 import 抓取函数，零外部依赖
    """
    all_news = []

    # 直接调用 china-finance-rss 桥接服务的抓取函数
    # 这些函数返回标准 RSS 2.0 XML 字符串，与 HTTP 模式完全等价
    handlers = []
    try:
        import sys
        import importlib
        from pathlib import Path
        rss_dir = Path(__file__).parent.parent / "china-finance-rss"
        if str(rss_dir) not in sys.path:
            sys.path.insert(0, str(rss_dir))
        # 强制重载 server 模块，确保使用最新代码
        if 'server' in sys.modules:
            importlib.reload(sys.modules['server'])
        from server import handle_sina_kuaixun, handle_eastmoney_kuaixun, handle_ths_kuaixun
        handlers = [
            ("新浪财经", handle_sina_kuaixun),
            ("东方财富", handle_eastmoney_kuaixun),
            ("同花顺", handle_ths_kuaixun),
        ]
    except Exception as e:
        print(f"[FETCH] 加载 china-finance-rss handler 失败: {e}")
        return all_news

    for source_name, handler in handlers:
        try:
            xml_content = handler()
            if not xml_content:
                print(f"  {source_name}：返回空内容，跳过")
                continue
            news_list = parse_rss_xml(xml_content, source_name)
            print(f"  {source_name}：获取到 {len(news_list)} 条")
            all_news.extend(news_list)
        except Exception as e:
            print(f"  {source_name}：抓取失败 ({e})，跳过")
            continue

    # 按时间戳排序（最新的在前）
    all_news.sort(key=lambda x: x.get("pub_timestamp", 0), reverse=True)

    return all_news


# 节假日支持：优先使用 chinese_calendar，不可用则回退到只跳周末
try:
    import chinese_calendar

    def is_trading_day(date):
        try:
            return chinese_calendar.is_workday(date)
        except NotImplementedError:
            # chinese_calendar 库未覆盖该日期
            return date.weekday() < 5

    def get_last_trading_day(date: datetime.date) -> datetime.date:
        """获取上一个交易日（跳过周末和法定节假日）"""
        prev = date - timedelta(days=1)
        while not is_trading_day(prev):
            prev -= timedelta(days=1)
        return prev

    def get_next_trading_day(date: datetime.date) -> datetime.date:
        """获取下一个交易日（跳过周末和法定节假日）"""
        nxt = date + timedelta(days=1)
        while not is_trading_day(nxt):
            nxt += timedelta(days=1)
        return nxt
except ImportError:
    # chinese_calendar 未安装，回退到只跳周末
    def get_last_trading_day(date: datetime.date) -> datetime.date:
        """获取上一个交易日（跳过周末）"""
        prev = date - timedelta(days=1)
        while prev.weekday() >= 5:
            prev -= timedelta(days=1)
        return prev

    def get_next_trading_day(date: datetime.date) -> datetime.date:
        """获取下一个交易日（跳过周末）"""
        nxt = date + timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += timedelta(days=1)
        return nxt


def is_within_trading_window(pub_time_str: str) -> bool:
    """判断发布时间是否在交易时间窗口内

    核心逻辑：上一个交易日收盘(15:00 北京时间) → 下一个交易日开盘(09:30 北京时间)
    如果当前已过开盘时间，延长到当前时间方便查看

    所有时间统一用北京时区（aware datetime）做比较，避免时区混用报错
    """
    pub_time_utc = parse_pub_time(pub_time_str)
    if pub_time_utc is None:
        print(f"  ⚠️ 时间解析失败，不放行: {pub_time_str!r}")
        return False  # 解析失败不放行

    # 统一转北京时区
    pub_time_cst = pub_time_utc.astimezone(CST)
    now_cst = datetime.now(CST)
    today_cst = now_cst.date()
    last_trading_day = get_last_trading_day(today_cst)
    next_trading_day = get_next_trading_day(today_cst)

    # 起始：上一个交易日 15:00（北京时间，aware）
    window_start = datetime.combine(
        last_trading_day,
        datetime.strptime("15:00:00", "%H:%M:%S").time()
    ).replace(tzinfo=CST)

    # 结束：下一个交易日 09:30（北京时间，aware）
    # 固定为 09:30，不延长——所有存档只含盘前窗口资讯
    window_end = datetime.combine(
        next_trading_day,
        datetime.strptime("09:30:00", "%H:%M:%S").time()
    ).replace(tzinfo=CST)

    return window_start <= pub_time_cst <= window_end


def fetch_and_filter_news() -> List[Dict]:
    """抓取并过滤资讯，只保留交易时间窗口内的预测/观点类资讯"""
    print("=" * 60)
    print(f"[{datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')}] 开始抓取财经资讯")
    print("=" * 60)

    all_news = fetch_all_news()
    print(f"\n总计获取 {len(all_news)} 条原始资讯")

    if not all_news:
        print("⚠️ 未获取到任何资讯")
        return []

    # 过滤时间窗口
    time_filtered = [news for news in all_news if is_within_trading_window(news.get("pub_time", ""))]
    print(f"时间窗口过滤后: {len(time_filtered)} 条")

    # 使用新版筛选（基于自变量/因变量理论）
    from modules.filter_news_v2 import analyze_news_v2, filter_by_quality
    filtered_news = []
    for news in time_filtered:
        analyzed = analyze_news_v2(news)
        # 只保留自变量（决策有效资讯）
        if analyzed.get('is_valid', False):
            filtered_news.append(analyzed)

    print(f"自变量（决策有效）: {len(filtered_news)} 条 (已过滤因变量)")

    # 价值优先级筛选（动态数量，不强制固定）
    filtered_news = filter_by_quality(filtered_news)
    print(f"质量筛选后: {len(filtered_news)} 条")

    # 去重：根据标题相似度去除重复资讯
    filtered_news = remove_duplicates(filtered_news)
    print(f"去重后: {len(filtered_news)} 条")

    # 修复无效链接（东方财富/同花顺快讯页会被删除）
    filtered_news = fix_news_links(filtered_news)

    # 保存原始数据
    raw_data_file = REPORTS_DIR / f"raw_news_{datetime.now(CST).strftime('%Y%m%d_%H%M%S')}.json"
    with open(raw_data_file, 'w', encoding='utf-8') as f:
        json.dump({
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "total_count": len(all_news),
            "filtered_count": len(filtered_news),
            "news_list": filtered_news
        }, f, ensure_ascii=False, indent=2)

    print(f"原始数据已保存至: {raw_data_file}")

    # 清理 7 天前的 raw_news 文件
    cutoff = datetime.now(CST) - timedelta(days=7)
    for old_file in REPORTS_DIR.glob("raw_news_*.json"):
        try:
            file_time = datetime.fromtimestamp(old_file.stat().st_mtime, tz=CST)
            if file_time < cutoff:
                old_file.unlink()
        except Exception:
            pass

    return filtered_news


def remove_duplicates(news_list: List[Dict]) -> List[Dict]:
    """去除重复资讯

    根据标题相似度判断是否为重复资讯，保留第一条，去除后续相似的。
    使用 difflib.SequenceMatcher 计算相似度（与 filter_news_v2.py 的 calculate_similarity 一致），
    阈值 0.75。
    """
    if not news_list:
        return []

    unique_news = []
    seen_titles = []

    for news in news_list:
        title = news.get('title', '').strip()
        if not title:
            continue

        # 清洗：移除标点符号，保留中文、英文、数字
        clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', title)
        is_dup = False
        for seen in seen_titles:
            seen_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', seen)
            if clean and seen_clean:
                ratio = SequenceMatcher(None, clean, seen_clean).ratio()
                if ratio > 0.75:
                    is_dup = True
                    break

        if not is_dup:
            unique_news.append(news)
            seen_titles.append(title)

    return unique_news


def fix_news_links(news_list: List[Dict]) -> List[Dict]:
    """保留 RSS 源返回的原文链接

    东方财富、同花顺、新浪财经的原文链接均由 china-finance-rss 直接提供，
    均为对应平台的原文地址，保持不变，确保用户点击直接跳转到原文。
    """
    converted = []
    for news in news_list:
        news = dict(news)  # 复制，避免修改原数据
        source = news.get('source', '')
        link = news.get('link', '')

        # 所有三个源（新浪财经、东方财富、同花顺）的原文链接均保持不变
        # china-finance-rss 已提供正确的原文链接：
        #   新浪财经 → finance.sina.com.cn 原文
        #   东方财富 → kuaixun.eastmoney.com 原文
        #   同花顺   → news.10jqka.com.cn 原文
        if not link:
            # 极端情况：link 为空，记录日志但不改动
            print(f"  ⚠️ [{source}] 缺少原文链接: {news.get('title', '')[:40]}")

        converted.append(news)

    return converted


# ============== 按日期按需抓取 ==============
import urllib.request as _urllib

def _calc_date_window(date_str: str):
    """计算指定日期的交易时间窗口

    窗口：T-1 交易日 15:00 → T 交易日 09:30（均为北京时间）
    返回 (window_start_dt, window_end_dt)，均为 aware datetime (CST)
    """
    y, m, d = int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8])
    target_date = datetime(y, m, d, tzinfo=CST).date()

    # T-1 交易日
    prev = target_date - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    try:
        prev = get_last_trading_day(target_date)
    except Exception:
        pass  # fallback to weekday check

    window_start = datetime.combine(prev, datetime.strptime("15:00:00", "%H:%M:%S").time()).replace(tzinfo=CST)
    window_end = datetime.combine(target_date, datetime.strptime("09:30:00", "%H:%M:%S").time()).replace(tzinfo=CST)

    return window_start, window_end


def _fetch_ths_raw_for_window(window_start: datetime, window_end: datetime) -> List[Dict]:
    """直接调用同花顺 API，翻页收集时间窗口内的资讯"""
    import json as _json
    items = []
    for page in range(1, 501):
        url = f'https://news.10jqka.com.cn/tapp/news/push/stock/?page={page}&tag=&track=website&pagesize=50'
        req = _urllib.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Referer': 'https://news.10jqka.com.cn/'
        })
        try:
            data = _json.loads(_urllib.urlopen(req, timeout=10).read().decode())
            page_items = data.get('data', {}).get('list', [])
            if not page_items:
                break
            oldest_ts = int(page_items[-1].get('ctime', 0))
            newest_ts = int(page_items[0].get('ctime', 0))
            dt_oldest = datetime.fromtimestamp(oldest_ts, tz=CST)
            dt_newest = datetime.fromtimestamp(newest_ts, tz=CST)
            for it in page_items:
                ts = int(it.get('ctime', 0))
                dt = datetime.fromtimestamp(ts, tz=CST)
                if window_start <= dt <= window_end:
                    api_url = it.get('url', '')
                    if api_url and 'baidu.com' not in api_url and 'zs/search' not in api_url:
                        link = api_url
                    else:
                        seq = it.get('seq', '')
                        d_str = dt.strftime('%Y%m%d')
                        link = f'https://news.10jqka.com.cn/{d_str}/c{seq}.shtml' if seq else ''
                    items.append({
                        'title': it.get('title', ''),
                        'content': it.get('digest', it.get('remark', '')),
                        'source': '同花顺',
                        'link': link,
                        'pub_time': dt.strftime('%a, %d %b %Y %H:%M:%S +0800'),
                        'pub_timestamp': ts,
                    })
            # 如果本页最早的时间已经早于窗口开始，可以停止翻页
            if dt_oldest < window_start:
                break
            # 如果本页最新时间也早于窗口开始，停止
            if dt_newest < window_start:
                break
        except Exception:
            break
    return items


def _fetch_sina_raw_for_window(window_start: datetime, window_end: datetime) -> List[Dict]:
    """直接调用新浪财经 API，翻页收集时间窗口内的资讯"""
    import json as _json
    items = []
    for page in range(1, 201):
        url = f'https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=50&page={page}'
        req = _urllib.Request(url, headers={
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://finance.sina.com.cn/'
        })
        try:
            data = _json.loads(_urllib.urlopen(req, timeout=10).read().decode())
            page_items = data.get('result', {}).get('data', [])
            if not page_items:
                break
            for it in page_items:
                ts = int(it.get('ctime', 0))
                dt = datetime.fromtimestamp(ts, tz=CST)
                if window_start <= dt <= window_end:
                    items.append({
                        'title': it.get('title', ''),
                        'content': it.get('intro', ''),
                        'source': '新浪财经',
                        'link': it.get('url', ''),
                        'pub_time': dt.strftime('%a, %d %b %Y %H:%M:%S +0800'),
                        'pub_timestamp': ts,
                    })
            oldest_ts = int(page_items[-1].get('ctime', 0))
            if datetime.fromtimestamp(oldest_ts, tz=CST) < window_start:
                break
        except Exception:
            break
    return items


def _fetch_eastmoney_raw_for_window(window_start: datetime, window_end: datetime) -> List[Dict]:
    """直接调用东方财富 API 收集时间窗口内的资讯（翻页抓取，最多 20 页）"""
    import json as _json
    items = []
    for page in range(1, 21):
        url = f'https://newsapi.eastmoney.com/kuaixun/v1/getlist_102_ajaxResult_50_{page}_.html'
        req = _urllib.Request(url, headers={
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://kuaixun.eastmoney.com/'
        })
        try:
            data = _urllib.urlopen(req, timeout=10).read().decode()
            match = re.search(r'var ajaxResult=(\{.*\});?', data, re.DOTALL)
            if not match:
                break
            result = _json.loads(match.group(1))
            page_items = result.get('LivesList', [])
            if not page_items:
                break
            oldest_in_page = None
            for it in page_items:
                showtime = it.get('showtime', '')
                try:
                    dt = datetime.strptime(showtime, '%Y-%m-%d %H:%M:%S').replace(tzinfo=CST)
                except Exception:
                    continue
                if oldest_in_page is None or dt < oldest_in_page:
                    oldest_in_page = dt
                if window_start <= dt <= window_end:
                    newsid = it.get('newsid', '')
                    link = f'https://finance.eastmoney.com/a/{newsid}.html' if newsid else ''
                    items.append({
                        'title': it.get('title', ''),
                        'content': it.get('digest', ''),
                        'source': '东方财富',
                        'link': link,
                        'pub_time': dt.strftime('%a, %d %b %Y %H:%M:%S +0800'),
                        'pub_timestamp': int(dt.timestamp()),
                    })
            if oldest_in_page and oldest_in_page < window_start:
                break
        except Exception:
            break
    return items


def fetch_news_for_date(date_str: str) -> Dict:
    """按需检索指定日期的预测类资讯

    检索 T-1 15:00 → T 09:30 窗口内的资讯，从三大平台翻页抓取，
    应用自变量/因变量筛选，进行分析，保存报告，返回结果。

    Args:
        date_str: 日期字符串 "20260625"
    Returns:
        dict: {"success": bool, "news_list": [...], "stats": {...}, ...}
    """
    from modules.filter_news_v2 import analyze_news_v2, filter_by_quality
    from modules.analyze_news import analyze_news_list
    from modules.generate_report import generate_and_save_report

    window_start, window_end = _calc_date_window(date_str)
    print(f"[FETCH] {date_str} 窗口: {window_start.strftime('%m-%d %H:%M')} → {window_end.strftime('%m-%d %H:%M')}")

    all_raw = []

    # 同花顺（回溯最深，约60天）
    print("[FETCH] 正在检索同花顺...")
    ths_news = _fetch_ths_raw_for_window(window_start, window_end)
    ths_count = len(ths_news)
    print(f"[FETCH]   同花顺: {ths_count} 条")
    all_raw.extend(ths_news)

    # 新浪财经（约16天）
    print("[FETCH] 正在检索新浪财经...")
    sina_news = _fetch_sina_raw_for_window(window_start, window_end)
    sina_count = len(sina_news)
    print(f"[FETCH]   新浪财经: {sina_count} 条")
    all_raw.extend(sina_news)

    # 东方财富（翻页抓取，约20天）
    print("[FETCH] 正在检索东方财富...")
    em_news = _fetch_eastmoney_raw_for_window(window_start, window_end)
    em_count = len(em_news)
    print(f"[FETCH]   东方财富: {em_count} 条")
    all_raw.extend(em_news)

    if not all_raw:
        # 给出具体的诊断信息
        parts = []
        if ths_count == 0:
            parts.append("同花顺 API 无数据（可能超出回溯范围）")
        if sina_count == 0:
            parts.append("新浪财经 API 无数据（可能超出回溯范围）")
        if em_count == 0:
            parts.append("东方财富 API 无数据（可能超出回溯范围）")
        detail = "；".join(parts) if parts else "三大平台均无返回数据"
        return {"success": False, "error": f"{date_str} 无可用资讯 — {detail}",
                "news_list": [], "stats": {}, "news_count": 0,
                "source_counts": {"同花顺": ths_count, "新浪财经": sina_count, "东方财富": em_count}}

    # 补充时间字段
    for n in all_raw:
        n.update(extract_time_fields(n.get('pub_time', '')))

    # 按时间排序
    all_raw.sort(key=lambda x: x.get('pub_timestamp', 0), reverse=True)

    print(f"[FETCH] 原始资讯合计: {len(all_raw)} 条")

    # 应用自变量筛选
    filtered = []
    for n in all_raw:
        analyzed = analyze_news_v2(n)
        if analyzed.get('is_valid', False):
            filtered.append(analyzed)
    print(f"[FETCH] 自变量（决策有效）: {len(filtered)} 条")

    # 质量筛选
    filtered = filter_by_quality(filtered)

    # 去重
    filtered = remove_duplicates(filtered)
    print(f"[FETCH] 去重后: {len(filtered)} 条")

    # 如果筛选后为空，返回明确信息
    if not filtered:
        return {"success": False,
                "error": f"{date_str} 抓取到 {len(all_raw)} 条原始资讯，但经自变量/因变量筛选后无有效预测类资讯（可能该日以事实报道为主）",
                "news_list": [], "stats": {}, "news_count": 0,
                "source_counts": {"同花顺": ths_count, "新浪财经": sina_count, "东方财富": em_count}}

    # 运行分析
    analyzed = analyze_news_list(filtered)

    # 保存报告
    report_path = REPORTS_DIR / f"report_{date_str}.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(analyzed, f, ensure_ascii=False, indent=2)

    # 生成 Markdown 简报
    try:
        generate_and_save_report(analyzed, date_str=date_str)
    except Exception:
        pass

    print(f"[FETCH] 报告已保存: {report_path}")

    return {
        "success": True,
        "news_count": len(filtered),
        "news_list": analyzed["news_list"],
        "stats": analyzed["stats"],
        "analyzed_at": analyzed["analyzed_at"],
        "source_counts": {"同花顺": ths_count, "新浪财经": sina_count, "东方财富": em_count},
    }


if __name__ == "__main__":
    news = fetch_and_filter_news()
    print(f"\n最终获取 {len(news)} 条资讯")
    for i, n in enumerate(news[:5], 1):
        print(f"\n{i}. [{n['source']}] {n['title']}")
