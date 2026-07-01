#!/usr/bin/env python3
"""
盘前财经资讯助手 - 简报生成模块
按照 output_spec.md 的格式生成结构化 Markdown 简报
"""
import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict
from collections import Counter
import sys
import json

# 北京时区
CST = timezone(timedelta(hours=8))

# 添加项目根目录到路径
sys.path.insert(0, str(__file__).rsplit('/', 2)[0] if '/' in __file__ else str(__file__).rsplit('\\', 2)[0])
from config import MARKDOWN_REPORTS_DIR


def generate_report_title(date_str: str = None) -> str:
    """生成报告标题"""
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')
    return f"## 📊 盘前速览（{date_str}）"


def generate_time_range() -> str:
    """生成时间范围说明（生成时间按北京时区显示）"""
    today = datetime.now(CST).strftime('%Y-%m-%d')
    return f"""### 📅 时间范围

- **起始**：前一交易日 15:00:00
- **截止**：本交易日 09:30:00
- **生成时间**：{datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')}"""


def generate_core_prediction(analyzed_news: List[Dict]) -> str:
    """生成核心预判部分"""
    # 统计各板块出现次数
    sector_counter = Counter()
    for news in analyzed_news:
        for sector in news.get("sectors", []):
            sector_counter[sector] += 1

    # 统计情绪
    sentiments = [n.get("sentiment", "中性") for n in analyzed_news]
    bullish = sentiments.count("利好")
    bearish = sentiments.count("利空")

    # 找出最热门的板块
    top_sectors = sector_counter.most_common(3)

    # 生成机构共识
    if top_sectors:
        sectors_str = "、".join([s[0] for s in top_sectors[:2]])
        consensus = f"{sectors_str}是今日主要关注方向"
    else:
        consensus = "今日无明确热点方向"

    # 生成整体情绪
    if bullish > bearish * 1.5:
        overall_sentiment = "偏乐观"
    elif bearish > bullish * 1.5:
        overall_sentiment = "偏谨慎"
    else:
        overall_sentiment = "中性"

    # 主要分歧：同时存在利好和利空才有分歧
    if bullish and bearish:
        divergence = f"市场情绪存在分歧（利好 {bullish} / 利空 {bearish}）"
    else:
        divergence = "无显著分歧"

    return f"""### 一、核心预判

- **机构共识**：{consensus}
- **主要分歧**：{divergence}
- **整体情绪**：{overall_sentiment}"""


def generate_sector_table(analyzed_news: List[Dict]) -> str:
    """生成热点板块推演表格"""
    # 按板块聚合资讯
    sector_news = {}
    for news in analyzed_news:
        for sector in news.get("sectors", []):
            if sector not in sector_news:
                sector_news[sector] = []
            sector_news[sector].append(news)

    # 统计并排序
    sector_data = []
    for sector, news_list in sector_news.items():
        sentiments = [n.get("sentiment", "中性") for n in news_list]
        bullish = sentiments.count("利好")
        bearish = sentiments.count("利空")

        direction = "利好" if bullish > bearish else ("利空" if bearish > bullish else "中性")

        # 找出代表性观点（修复时间截取：pub_time 格式 "2024-05-29 09:15" → 取 [11:16]）
        top_news = max(news_list, key=lambda x: x.get("importance_score", 0))
        pub_time = top_news.get('pub_time', '')
        time_str = pub_time[11:16] if len(pub_time) >= 16 else pub_time[:5]
        title_full = top_news.get('title', '')
        title_short = title_full[:20]
        representative = f"{top_news.get('source', '')}({time_str})：{title_short}{'...' if len(title_full) > 20 else ''}"

        sector_data.append({
            "sector": sector,
            "direction": direction,
            "count": len(news_list),
            "representative": representative,
            "logic": generate_sector_logic(top_news.get("content", ""))
        })

    # 按提及次数排序
    sector_data.sort(key=lambda x: x["count"], reverse=True)

    if not sector_data:
        return """### 二、热点板块推演

| 排名 | 板块 | 影响方向 | 核心逻辑 | 提及次数 | 代表性观点 |
|:----:|------|----------|----------|:--------:|------------|
| - | 无明确热点 | - | 今日无自变量（预测类）资讯 | 0 | - |"""

    table_header = """| 排名 | 板块 | 影响方向 | 核心逻辑 | 提及次数 | 代表性观点 |
|:----:|------|----------|----------|:--------:|------------|
"""
    table_rows = ""
    for i, data in enumerate(sector_data[:5], 1):  # 只显示前5个板块
        table_rows += f"| {i} | {data['sector']} | {data['direction']} | {data['logic']} | {data['count']} | {data['representative']} |\n"

    return f"### 二、热点板块推演\n\n{table_header}{table_rows}"


def generate_sector_logic(content: str) -> str:
    """从内容中提取核心逻辑（增强版：优先找因果/预测句式，而非截前30字）"""
    if not content:
        return "详见资讯内容"

    text = content.replace("\n", " ").strip()
    # 按句号/分号拆成句子
    sentences = re.split(r'[。；！？\n]', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return text[:40] + ("..." if len(text) > 40 else "")

    # 优先级 1：因果句式（由于/因为...导致/所以）
    for s in sentences:
        if re.search(r'(由于|因为|因).{2,}(导致|使得|促使|带动|推动|所以|因此)', s):
            return s[:50] + ("..." if len(s) > 50 else "")

    # 优先级 2：预测性表述（预计/有望/建议关注/看好/目标价/维持评级）
    for s in sentences:
        if re.search(r'(预计|有望|建议关注|看好|目标价|维持.*评级|上调|下调|渗透率|景气|拐点|需求.*增长|供给.*收缩)', s):
            return s[:50] + ("..." if len(s) > 50 else "")

    # 优先级 3：含数字+趋势词的句子（增长X%/突破X亿/达到X）
    for s in sentences:
        if re.search(r'\d+[%亿万]?', s) and re.search(r'(增长|下降|突破|达到|超过|提升|降低|扩张|收缩)', s):
            return s[:50] + ("..." if len(s) > 50 else "")

    # 优先级 4：最长的句子（信息量最大）
    longest = max(sentences, key=len)
    return longest[:50] + ("..." if len(longest) > 50 else "")


def generate_key_news_table(analyzed_news: List[Dict]) -> str:
    """生成关键自变量资讯精选表格"""
    # 过滤出自变量资讯并按重要性排序
    opinion_news = [n for n in analyzed_news if "预测" in n.get("fact_type", "") or "混合" in n.get("fact_type", "")]
    opinion_news.sort(key=lambda x: x.get("importance_score", 0), reverse=True)

    if not opinion_news:
        return """### 三、关键自变量资讯精选

今日无自变量（预测类）资讯。"""

    table_header = """| 时间 | 来源 | 资讯摘要 | 涉及板块 | 观点类型 |
|------|------|----------|----------|----------|
"""
    table_rows = ""
    for news in opinion_news[:10]:  # 只显示前10条
        pub_time = news.get("pub_time", "")
        time_str = pub_time[11:16] if len(pub_time) >= 16 else pub_time[:5]
        source = news.get("source", "")
        title = news.get("title", "")[:25]
        sectors = "、".join(news.get("sectors", [])[:2])
        fact_type = news.get("fact_type", "")

        table_rows += f"| {time_str} | {source} | {title} | {sectors} | {fact_type} |\n"

    return f"### 三、关键自变量资讯精选\n\n{table_header}{table_rows}"


def generate_fact_reference(analyzed_news: List[Dict]) -> str:
    """因变量参考（已发生事件）- 已禁用，只显示预测类资讯"""
    # 由于用户只需要预测/观点类资讯，此部分不再显示
    return ""


def generate_risk_warning(analyzed_news: List[Dict]) -> str:
    """生成风险提示（增强版：列出高重要性资讯 + 板块风险 + 情绪风险）"""
    lines = ["### 四、风险提示", ""]

    # ====== 1. 高重要性资讯逐条提醒 ======
    high_imp_news = [n for n in analyzed_news if n.get("importance_score", 0) >= 8]
    high_imp_news.sort(key=lambda x: x.get("importance_score", 0), reverse=True)

    if high_imp_news:
        lines.append(f"**⚠️ 高重要性资讯（{len(high_imp_news)} 条）需重点关注：**")
        lines.append("")
        for i, news in enumerate(high_imp_news[:5], 1):  # 最多列 5 条
            title = news.get("title", "")[:40]
            sectors = "、".join(news.get("sectors", [])[:2]) or "未分类"
            sentiment = news.get("sentiment", "中性")
            score = news.get("importance_score", 0)
            source = news.get("source", "")
            advice = news.get("advice", "")

            # 根据情绪生成具体风险提示
            if sentiment == "利空":
                risk_hint = f"注意规避{sectors}板块回调风险"
            elif sentiment == "利好":
                risk_hint = f"关注{sectors}板块追涨风险，谨防冲高回落"
            else:
                risk_hint = f"关注{sectors}板块后续方向选择"

            lines.append(f"{i}. **[{sentiment} · {score}分]** {title}")
            lines.append(f"   - 涉及板块：{sectors} · 来源：{source}")
            lines.append(f"   - 风险提示：{risk_hint}")
            if advice:
                lines.append(f"   - 操作建议：{advice}")
            lines.append("")

    # ====== 2. 板块集中度风险 ======
    sector_counter = Counter()
    sector_bearish = Counter()
    for news in analyzed_news:
        for s in news.get("sectors", []):
            sector_counter[s] += 1
            if news.get("sentiment") == "利空":
                sector_bearish[s] += 1

    # 找利空占比高的板块
    risky_sectors = []
    for sector, total in sector_counter.most_common(5):
        bear_count = sector_bearish.get(sector, 0)
        if bear_count >= 2 and bear_count / total >= 0.5:
            risky_sectors.append((sector, bear_count, total))

    if risky_sectors:
        lines.append("**📉 板块风险预警：**")
        lines.append("")
        for sector, bear, total in risky_sectors:
            lines.append(f"- **{sector}**：{bear}/{total} 条利空，利空占比 {bear/total*100:.0f}%，短期承压")
        lines.append("")

    # ====== 3. 情绪极端风险 ======
    sentiments = [n.get("sentiment", "中性") for n in analyzed_news]
    bullish = sentiments.count("利好")
    bearish = sentiments.count("利空")
    total = len(analyzed_news)

    if total > 0:
        bear_ratio = bearish / total
        if bear_ratio > 0.5:
            lines.append(f"**⚠️ 整体情绪偏空**：利空占比 {bear_ratio*100:.0f}%（{bearish}/{total}），建议谨慎操作、控制仓位")
            lines.append("")
        elif bullish > 0 and bearish > 0 and abs(bullish - bearish) <= 2:
            lines.append(f"**⚠️ 多空分歧明显**：利好 {bullish} vs 利空 {bearish}，市场方向不明确，建议观望")
            lines.append("")

    # ====== 4. 数据局限性提示 ======
    if not high_imp_news:
        lines.append("**ℹ️ 今日无高重要性（≥8分）资讯**，市场整体平稳，按常规策略操作。")
        lines.append("")

    lines.append("---")
    lines.append("*⚠️ 本分析仅基于公开资讯自动生成，不构成任何投资建议。市场有风险，投资需谨慎。*")

    return "\n".join(lines)


def generate_markdown_report(analyzed_news: List[Dict], date_str: str = None) -> str:
    """生成完整的Markdown简报（只包含预测/观点类资讯）"""
    today = date_str or datetime.now().strftime('%Y-%m-%d')

    # 只统计预测/观点类
    opinion_count = len([n for n in analyzed_news if "预测" in n.get("fact_type", "") or "混合" in n.get("fact_type", "")])

    report = f"""{generate_report_title(today)}

{generate_time_range()}

- 共检索预测/观点类资讯：{opinion_count} 条（已过滤既定事实）

{generate_core_prediction(analyzed_news)}

{generate_sector_table(analyzed_news)}

{generate_key_news_table(analyzed_news)}

{generate_risk_warning(analyzed_news)}

---

*本报告由盘前财经资讯助手自动生成，仅供参考*
"""


    return report


def save_report(markdown_content: str, date_str: str = None) -> str:
    """保存简报到文件"""
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')

    filename = f"report_{date_str}.md"
    filepath = MARKDOWN_REPORTS_DIR / filename

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(markdown_content)

    return str(filepath)


def generate_and_save_report(analyzed_result: Dict, date_str: str = None) -> Dict:
    """生成并保存报告"""
    analyzed_news = analyzed_result.get("news_list", [])
    markdown = generate_markdown_report(analyzed_news, date_str)
    filepath = save_report(markdown, date_str)

    return {
        "report_path": filepath,
        "report_content": markdown,
        "news_count": len(analyzed_news),
        "generated_at": datetime.now(timezone.utc).isoformat()
    }


if __name__ == "__main__":
    # 测试
    test_data = {
        "news_list": [
            {
                "title": "券商晨会：AI算力有望延续强势",
                "content": "多家券商发布盘前策略，认为AI算力板块在海外需求拉动下有望延续强势表现，建议关注光模块、服务器等细分领域。",
                "pub_time": "2024-05-29 09:15",
                "source": "新浪财经",
                "sectors": ["人工智能", "科技"],
                "fact_type": "预测/观点",
                "importance_score": 8,
                "sentiment": "利好"
            },
            {
                "title": "隔夜美股三大指数集体收跌",
                "content": "纳指跌1.2%，标普500跌0.7%，道指跌0.5%。",
                "pub_time": "2024-05-29 08:30",
                "source": "东方财富",
                "sectors": ["其他"],
                "fact_type": "既定事实",
                "importance_score": 6,
                "sentiment": "利空"
            }
        ]
    }

    report = generate_markdown_report(test_data["news_list"])
    print(report)
