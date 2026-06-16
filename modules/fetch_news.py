#!/usr/bin/env python3
"""
盘前财经资讯助手 - 数据抓取模块
通过 china-finance-rss 服务获取财联社、东方财富、同花顺资讯
"""
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
import sys
import json

# 添加项目根目录到路径
sys.path.insert(0, str(__file__).rsplit('/', 2)[0] if '/' in __file__ else str(__file__).rsplit('\\', 2)[0])
from config import REPORTS_DIR

# china-finance-rss 服务地址
RSS_BASE_URL = "http://localhost:8053"

# RSS 端点配置
RSS_ENDPOINTS = {
    "新浪财经": f"{RSS_BASE_URL}/cls/telegraph",  # 财联社API已失效，改用新浪财经
    "东方财富": f"{RSS_BASE_URL}/eastmoney/kuaixun",
    "同花顺": f"{RSS_BASE_URL}/ths/kuaixun",
}

# 中文星期映射
WEEKDAY_CN = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}

# 支持的时间格式（按优先级匹配）
TIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%a, %d %b %Y %H:%M:%S GMT",   # RFC 822 格式（带 GMT）
    "%a, %d %b %Y %H:%M:%S",        # RFC 822 格式（无时区）
    "%d %b %Y %H:%M:%S",
    "%a, %d %b %Y %H:%M:%S %z",     # 带时区偏移
]


def parse_pub_time(pub_time_str: str) -> Optional[datetime]:
    """
    解析 RSS 时间字符串为 datetime 对象
    - 自动识别 RFC 822、ISO 8601 等常见格式
    - GMT 时间自动转换为北京时间（+8 小时）
    - 解析失败返回 None
    """
    if not pub_time_str or not isinstance(pub_time_str, str):
        return None

    text = pub_time_str.strip()
    # 处理中文时区字串
    text = text.replace("GMT+0800", "+0800").replace("CST", "").strip()

    for fmt in TIME_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            # GMT 时间 → 北京时间（+8 小时）
            if 'GMT' in pub_time_str or 'gmt' in pub_time_str.lower():
                dt = dt + timedelta(hours=8)
            # 含 +0800 时区 → 视为北京时间
            elif '+0800' in pub_time_str or '+0800' in pub_time_str:
                pass  # 已经是 +8 时区，不转换
            return dt
        except ValueError:
            continue

    return None


def extract_time_fields(pub_time_str: str) -> Dict:
    """
    从原始时间字符串提取 4 个独立字段，统一存到 news dict 里

    返回字段：
      - pub_time       原始字符串（保留）
      - pub_datetime   ISO 格式 "2026-06-10T15:30:00"
      - pub_date       日期 "2026-06-10"
      - pub_time_of_day 时分 "15:30"
      - pub_weekday    中文星期 "周三"
      - pub_display    友好显示 "2026-06-10 15:30 周三"
      - pub_timestamp  Unix 时间戳（用于排序）
    """
    dt = parse_pub_time(pub_time_str)
    if dt is None:
        return {
            "pub_time": pub_time_str or "",
            "pub_datetime": "",
            "pub_date": "",
            "pub_time_of_day": "",
            "pub_weekday": "",
            "pub_display": pub_time_str or "",
            "pub_timestamp": 0,
        }

    return {
        "pub_time": pub_time_str or "",
        "pub_datetime": dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "pub_date": dt.strftime("%Y-%m-%d"),
        "pub_time_of_day": dt.strftime("%H:%M"),
        "pub_weekday": WEEKDAY_CN.get(dt.weekday(), ""),
        "pub_display": f"{dt.strftime('%Y-%m-%d %H:%M')} {WEEKDAY_CN.get(dt.weekday(), '')}",
        "pub_timestamp": int(dt.timestamp()),
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
        response = requests.get(url, timeout=timeout)
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
    """从所有来源抓取资讯（单个源失败不影响其他源）"""
    all_news = []

    # 先检查服务是否可用
    if not check_rss_service():
        print("⚠️ china-finance-rss 服务未启动！")
        print("   请先在另一个终端运行：")
        print("   cd china-finance-rss && python server.py")
        print("")
        return all_news

    for source_name, url in RSS_ENDPOINTS.items():
        news_list = fetch_from_rss(source_name, url)
        all_news.extend(news_list)

    # 按时间戳排序（最新的在前）
    all_news.sort(key=lambda x: x.get("pub_timestamp", 0), reverse=True)

    return all_news


def get_last_trading_day(date: datetime.date) -> datetime.date:
    """获取上一个交易日（跳过周末）"""
    prev_day = date - timedelta(days=1)
    while prev_day.weekday() >= 5:  # 5=周六, 6=周日
        prev_day -= timedelta(days=1)
    return prev_day


def get_next_trading_day(date: datetime.date) -> datetime.date:
    """获取下一个交易日（跳过周末）"""
    next_day = date + timedelta(days=1)
    while next_day.weekday() >= 5:  # 5=周六, 6=周日
        next_day += timedelta(days=1)
    return next_day


def is_within_trading_window(pub_time_str: str) -> bool:
    """判断发布时间是否在交易时间窗口内

    核心逻辑：上一个交易日收盘(15:00) → 下一个交易日开盘(09:30)
    如果当前已过开盘时间，延长到当前时间方便查看
    """
    pub_time = parse_pub_time(pub_time_str)
    if pub_time is None:
        return True  # 解析失败默认放行（避免误杀）

    now = datetime.now()
    today = now.date()
    last_trading_day = get_last_trading_day(today)
    next_trading_day = get_next_trading_day(today)

    # 起始：上一个交易日 15:00
    window_start = datetime.combine(last_trading_day, datetime.strptime("15:00:00", "%H:%M:%S").time())

    # 结束：下一个交易日 09:30
    # 但如果已过这个时间，延长到当前时间（方便随时查看）
    window_end = datetime.combine(next_trading_day, datetime.strptime("09:30:00", "%H:%M:%S").time())
    if now > window_end:
        window_end = now

    return window_start <= pub_time <= window_end


def fetch_and_filter_news() -> List[Dict]:
    """抓取并过滤资讯，只保留交易时间窗口内的预测/观点类资讯"""
    print("=" * 60)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始抓取财经资讯")
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
    raw_data_file = REPORTS_DIR / f"raw_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(raw_data_file, 'w', encoding='utf-8') as f:
        json.dump({
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "total_count": len(all_news),
            "filtered_count": len(filtered_news),
            "news_list": filtered_news
        }, f, ensure_ascii=False, indent=2)

    print(f"原始数据已保存至: {raw_data_file}")

    return filtered_news


def remove_duplicates(news_list: List[Dict]) -> List[Dict]:
    """去除重复资讯

    根据标题相似度判断是否为重复资讯，保留第一条，去除后续相似的。
    """
    import re
    
    def extract_keywords_set(title):
        """提取标题中的关键词集合（用于比较相似度）"""
        # 移除标点符号，保留中文、英文、数字
        clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', title)
        # 过滤常见词
        stop_words = {'商务部', '将在', '在', '对', '的', '含当日', '基础上', '现行适用'}
        for w in stop_words:
            clean = clean.replace(w, '')
        # 返回清理后的字符串
        return clean
    
    if not news_list:
        return []

    unique_news = []
    seen_keys = []

    for news in news_list:
        title = news.get('title', '').strip()
        if not title:
            continue

        # 提取核心关键词
        key = extract_keywords_set(title)
        
        # 检查是否与已保留的关键词相似
        is_duplicate = False
        for seen in seen_keys:
            # 计算编辑距离相似度
            if len(key) > 0 and len(seen) > 0:
                # 简单比较：前30个字符相同度
                min_len = min(len(key), len(seen), 30)
                if key[:min_len] == seen[:min_len]:
                    is_duplicate = True
                    break
                # 或者80%以上字符相同
                common = sum(1 for a, b in zip(key, seen) if a == b)
                if min(len(key), len(seen)) > 0 and common / min(len(key), len(seen)) > 0.8:
                    is_duplicate = True
                    break

        if not is_duplicate:
            unique_news.append(news)
            seen_keys.append(key)

    return unique_news


def fix_news_links(news_list: List[Dict]) -> List[Dict]:
    """修复无效链接

    东方财富和同花顺的快讯详情页会在一段时间后被删除（返回404），
    改为指向各自站内的搜索页面，用标题搜索即可找到原文。
    新浪财经的链接长期有效，保持不变。
    """
    from urllib.parse import quote

    converted = []
    for news in news_list:
        news = dict(news)  # 复制，避免修改原数据
        source = news.get('source', '')
        title = news.get('title', '')
        link = news.get('link', '')

        if source == '东方财富':
            # 用标题在东方财富站内搜索
            news['link'] = f"https://so.eastmoney.com/news/s?keyword={quote(title)}"
        elif source == '同花顺':
            # 同花顺搜索页不可用，用百度搜索（加site限定）
            news['link'] = f"https://www.baidu.com/s?wd={quote(title + ' site:10jqka.com.cn')}"
        # 新浪财经链接保持不变

        converted.append(news)

    return converted


if __name__ == "__main__":
    news = fetch_and_filter_news()
    print(f"\n最终获取 {len(news)} 条资讯")
    for i, n in enumerate(news[:5], 1):
        print(f"\n{i}. [{n['source']}] {n['title']}")
