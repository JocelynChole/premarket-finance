"""
盘前财经资讯智能体 - pushplus 微信推送模块

pushplus：https://www.pushplus.plus/
- 免费版每天 200 条推送额度（盘前简报每天 1 条完全够用）
- 微信扫码登录后即可获取 token
- 支持 Markdown / HTML 格式
"""

import requests
import json
import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

API_BASE = "https://www.pushplus.plus"
TIMEOUT = 10
CST = timezone(timedelta(hours=8))


def send_pushplus(token: str, title: str, content: str,
                  template: str = "markdown", topic: str = "") -> Dict:
    """
    通过 pushplus 发送微信消息

    Args:
        token:    pushplus token
        title:    消息标题
        content:  消息内容（markdown / html / json / txt）
        template: 内容模板，默认 markdown
        topic:    群组编码（可选，用于一对多推送）

    Returns:
        dict: {"success": bool, "message": str, "pushid": str}
    """
    if not token:
        return {"success": False, "message": "pushplus token 不能为空"}

    # pushplus token 通常是 32 位字母数字组合（无前缀）
    if not re.match(r'^[a-zA-Z0-9]{8,64}$', token):
        return {"success": False, "message": "pushplus token 格式无效"}

    url = f"{API_BASE}/send"
    payload = {
        "token": token,
        "title": title,
        "content": content,
        "template": template,
    }
    if topic:
        payload["topic"] = topic

    try:
        response = requests.post(url, json=payload, timeout=TIMEOUT)
        try:
            result = response.json()
        except (json.JSONDecodeError, ValueError):
            return {"success": False, "message": f"pushplus返回非JSON响应 (HTTP {response.status_code})"}
        if result.get("code") == 200:
            return {
                "success": True,
                "message": "推送成功",
                "pushid": str(result.get("data", "")),
            }
        return {
            "success": False,
            "message": f"推送失败: {result.get('msg', '未知错误')}",
        }
    except requests.exceptions.Timeout:
        return {"success": False, "message": "推送超时，请检查网络"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "message": "无法连接 pushplus 服务"}
    except Exception as e:
        return {"success": False, "message": f"推送异常: {e}"}


def test_pushplus(token: str) -> Dict:
    """测试 pushplus 推送通道"""
    now = datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')
    content = f"""**✅ 盘前资讯 · pushplus 测试成功**

这是一条来自「盘前财经资讯研判智能体」的测试消息。
您的微信能收到此消息，说明推送通道配置正确。

---

📅 {now}
💡 每天 9:25 自动为您推送盘前简报
"""
    return send_pushplus(token, "✅ 盘前资讯推送测试", content)


def send_news_report(token: str, news_list: List[Dict],
                     subscriber_sectors: Optional[List[str]] = None) -> Dict:
    """
    发送盘前资讯简报到个人微信

    Args:
        token:              pushplus token
        news_list:          资讯列表（已经过板块/类型/重要性分析）
        subscriber_sectors: 订阅者关注的板块（None = 不限）
    """
    if not news_list:
        return {"success": False, "message": "没有资讯可推送"}

    # 个性化筛选：只推用户关注的板块
    if subscriber_sectors:
        news_list = [
            n for n in news_list
            if n.get("sectors") and any(s in subscriber_sectors for s in n["sectors"])
        ]
        if not news_list:
            return {"success": False, "message": "您关注的板块暂无预测类资讯"}

    # 板块统计
    sector_counter: Dict[str, int] = {}
    for n in news_list:
        for s in n.get("sectors", []):
            sector_counter[s] = sector_counter.get(s, 0) + 1
    top_sectors = sorted(sector_counter.items(), key=lambda x: x[1], reverse=True)[:5]

    # 情绪统计
    sentiments = [n.get("sentiment", "中性") for n in news_list]
    bullish = sentiments.count("利好")
    bearish = sentiments.count("利空")
    overall = "📈 偏乐观" if bullish > bearish * 1.5 else (
        "📉 偏谨慎" if bearish > bullish * 1.5 else "➡️ 中性"
    )

    # 按重要性排序，取 TOP 8
    top_news = sorted(
        news_list,
        key=lambda x: x.get("importance_score", 0),
        reverse=True,
    )[:8]

    # 组装 Markdown 内容
    now_str = datetime.now(CST).strftime('%Y-%m-%d %H:%M')
    lines = []
    lines.append(f"# 📊 盘前速览 · {now_str}")
    lines.append("")
    lines.append(f"**窗口**：T-1 15:00 → T 09:30 · **资讯**：{len(news_list)} 条")
    lines.append(f"**整体情绪**：{overall}")
    lines.append("")

    if top_sectors:
        sector_str = " · ".join([f"`{s}` {c}" for s, c in top_sectors])
        lines.append(f"**🔥 热点板块**：{sector_str}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 📰 重点预测")
    lines.append("")

    for i, news in enumerate(top_news, 1):
        title = news.get("title", "无标题")
        sectors = " · ".join(news.get("sectors", [])[:3]) or "其他"
        sentiment = news.get("sentiment", "中性")
        emoji = "📈" if sentiment == "利好" else ("📉" if sentiment == "利空" else "➡️")
        importance = news.get("importance_score", 0)
        advice = news.get("advice", "")
        source = news.get("source", "")
        pub_time_raw = news.get("pub_time", "") or ""
        pub_time = pub_time_raw[:16] if len(pub_time_raw) >= 16 else pub_time_raw

        lines.append(f"### {i}. {title}")
        lines.append(f"> {emoji} **{sentiment}** · ⭐ {importance}分 · {sectors}")
        if pub_time or source:
            lines.append(f"> 🕐 {pub_time} · 📡 {source}")
        if advice:
            lines.append(f"> 💡 {advice}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("⚠️ **免责声明**：本简报由智能算法自动整理，仅供研究参考，不构成任何投资建议。")
    lines.append("")
    lines.append(f"📈 盘前财经资讯研判智能体 · {now_str}")

    content = "\n".join(lines)
    # pushplus 单条内容上限 ~50KB，做个保险截断
    if len(content) > 40000:
        content = content[:40000] + "\n\n...(内容过长已截断)"
    title = f"📊 盘前速览 {datetime.now(CST).strftime('%m月%d日')} · {len(news_list)}条"
    return send_pushplus(token, title, content, template="markdown")


def send_to_subscribers(subscribers: List[Dict], news_list: List[Dict]) -> Dict:
    """
    向多个订阅者发送简报

    Returns:
        dict: {"total": int, "success": int, "failed": int, "details": list}
    """
    def _push_one(sub):
        if not sub.get("active", True):
            return None
        token = (sub.get("pushplus_token") or sub.get("serverchan_key") or "").strip()
        if not token:
            return None
        user_sectors = sub.get("sectors") or None
        result = send_news_report(token, news_list, user_sectors)
        return {"email": sub.get("email", ""), "result": result}

    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(_push_one, sub) for sub in subscribers]
        for f in as_completed(futures):
            r = f.result()
            if r:
                results.append(r)

    success = sum(1 for r in results if r["result"].get("success"))
    failed = len(results) - success
    return {
        "total": len(results),
        "success": success,
        "failed": failed,
        "details": results,
    }


if __name__ == "__main__":
    print("pushplus 推送模块 - 自测")
    print("请先在订阅页填入 pushplus token 再测试")
