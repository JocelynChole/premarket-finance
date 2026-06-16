#!/usr/bin/env python3
"""
盘前财经资讯助手 - 资讯分析模块
分析资讯：判断板块、区分事实/观点、评估重要性
"""
import re
from typing import List, Dict, Tuple
from datetime import datetime, timezone

# 添加项目根目录到路径
import sys
sys.path.insert(0, str(__file__).rsplit('/', 2)[0] if '/' in __file__ else str(__file__).rsplit('\\', 2)[0])
from config import SECTOR_KEYWORDS, FACT_WORDS, OPINION_WORDS, IMPORTANT_WORDS


def detect_sectors(text: str) -> List[str]:
    """检测资讯涉及的板块"""
    sectors = []

    for sector, keywords in SECTOR_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                if sector not in sectors:
                    sectors.append(sector)
                break

    if not sectors:
        sectors.append("其他")

    return sectors


def classify_news_type(text: str) -> str:
    """判断资讯类型（替代原来的事实/观点分类）"""
    text_lower = text.lower()
    
    # 研报类
    if any(word in text for word in ['研报', '证券', '中信证券', '中信建投', '国泰君安', '海通证券', '华泰证券', '招商证券', '中金公司', 'Goldman', '摩根', '大摩', '小摩']):
        return '研报'
    
    # 政策类
    if any(word in text for word in ['政策', '监管', '央行', '证监会', '银保监会', '国务院', '发改委', '工信部', '财政部', '税务总局']):
        return '政策'
    
    # 公司公告类
    if any(word in text for word in ['公告', '回购', '减持', '中标', '签约', '订单', '业绩', '财报', '盈利', '亏损', '预告']):
        return '公司'
    
    # 行业数据类
    if any(word in text for word in ['产量', '销量', '出货量', '价格', '指数', 'PMI', '同比', '环比', '增长', '下降']):
        return '数据'
    
    # 默认归类
    return '行业'


def classify_fact_or_opinion(text: str) -> Tuple[str, str]:
    """
    分类资讯为事实或观点（保留用于情绪判断）
    返回: (分类结果, 详细说明)
    
    核心原则：只有对"未来行情/板块走势"有预测价值的才算"预测/观点"
    以下不算预测：
    - 对已发生事件的回顾/评论（如"已有铺垫"、"此前已..."）
    - 人事变动、公告解读（如"卸任"、"增聘"）
    - 纯数据描述（如"收盘涨了X%"）
    """
    has_fact = any(word in text for word in FACT_WORDS)
    has_opinion = any(word in text for word in OPINION_WORDS)

    # ====== 第零层：排除与股市/投资完全无关的资讯 ======
    # 这些资讯即使包含预测词，也跟开盘决策无关
    non_market_words = [
        "国家安全部", "安全提示", "网络安全", "远程控制软件", "窃密",
        "国家安全", "保密隐患", "数据安全", "信息安全",
        "气象", "天气预报", "台风", "暴雨", "地震", "洪水", "高温", "降水",
        "疫情防控", "核酸检测", "疫苗接种点",
        "交通管制", "限行", "违章",
        "刑事案件", "治安", "交通事故",
        "环保督察", "污染治理", "碳排放",
        "反腐", "纪律审查", "监察调查", "被查", "被双开",
        "火灾", "安全事故", "安全生产",
        "社会民生", "民生保障", "就业率",
        # 国际政治/外交新闻
        "外交部发言人", "伊朗", "以色列", "巴勒斯坦", "加沙", "黎巴嫩",
        "俄罗斯", "乌克兰", "普京", "泽连斯基",
        "美国国会", "拜登", "特朗普", "白宫",
        "访华", "访美", "外交大臣", "外交部发言人",
        "联合国", "安理会", "北约", "欧盟峰会",
        # 外国新闻（对A股影响有限）
        "日本东京", "福岛", "核电站", "日本首相", "日本考虑", "日本政府",
        "德国总理", "法国总统", "英国首相",
        "韩国", "朝鲜",
        # 活动公告（不是行情预测）
        "开发者大会", "发布会", "峰会将于", "论坛将于", "年会将于",
        "展览将于", "博览会将于",
        # 欧洲经济数据（对中国A股影响有限）
        "欧元区", "德国制造业PMI", "法国制造业PMI", "意大利PMI", "西班牙PMI",
        "欧洲央行", "欧元区通胀", "英国制造业PMI", "英国PMI", "德国PMI",
        "英国5月制造业PMI", "德国5月制造业PMI",
        # 单个公司公告（除非重大）
        "补缴税款", "补缴企业所得税", "药品注册证书", "获得证书", "工商变更",
        "设立全资子公司", "投资设立", "辞职", "副总经理辞职", "人事变动",
        # 法国/德国/英国新闻
        "法国巴黎富通银行", "法国银行", "德国银行",
        # 一般政策文件（不是行情预测）
        "九部门", "各部门依托科技计划", "科研助理岗位",
        # 品牌合作/代言（无投资价值）
        "代言", "品牌大使", "形象大使", "库里", "李宁与",
        # 航天/军工非A股相关
        "NASA", "蓝色起源", "SpaceX", "火箭",
        # 天气/自然灾害
        "范围今日将达", "降水将上线",
        # 港股/美股个股（非A股，除非是行业标杆如英伟达）
        "美团-W", "美团绩后", "美团涨", "美团跌", "美团亏损",
        "永利澳门", "银河娱乐", "金沙中国",
        "港股", "恒生指数",
        # 海外市场非A股相关
        "印度", "日本鸡肉", "炸鸡", "烤串",
        "韩国", "朝鲜",
        # 非主流小公司（非A股主要标的）
        "元亨燃气", "哈根达斯", "柠季",
        "李氏大药厂",
        # 非交易性公告
        "短期融资券", "股份奖励计划", "激励计划",
        "股本重组",
        # 未成年保护等社会新闻
        "未成年人", "保护未成年人",
        # 欧洲政治新闻（对A股影响有限）
        "欧洲议会", "欧盟贸易", "欧美贸易", "英国脱欧",
        "德国议会", "法国议会",
        # 非财经类新闻
        "世界杯", "夺冠", "足球", "篮球", "体育",
        # 港股个股
        "顺丰同城", "美团", "快手", "腾讯控股",
        # 单个公司公告（非重大）
        "业绩已翻倍", "股价仍躺平", "年产", "投产",
        # 重复性价格预测（长江有色每天多条类似内容）
        "长江有色", "2日锡价", "2日锌价", "2日镍价", "2日铝价", "2日铜价",
        "锡价或", "锌价或", "镍价或", "铝价或", "铜价或",
    ]

    is_non_market = any(word in text for word in non_market_words)
    if is_non_market:
        return ("既定事实", "与A股投资无关的资讯，无行情预测价值")

    # ====== 第一层：检测明确的预测性表述 ======
    prediction_patterns = [
        r'\d+[年月天]?[以内后]?[将可能会有望]',
        r'预计增长\d+',
        r'预计下降\d+',
        r'预计达到\d+',
        r'有望突破\d+',
        r'可能达到\d+',
        r'将超过\d+',
        r'预期.*\d+',
        r'预计.*\d+%',
        r'有望.*延续',
        r'有望.*反弹',
        r'有望.*上涨',
        r'有望.*下跌',
        r'建议关注',
        r'建议配置',
        r'值得布局',
        r'行情可期',
        r'反弹可期',
        r'看好.*前景',
        r'看好.*后市',
        r'看好.*板块',
        r'看多',
        r'看空',
        r'布局.*时机',
        r'逢低.*布局',
        r'逢低.*买入',
        r'目标价.*\d+',
        r'维持.*评级',
        r'上调.*评级',
        r'下调.*评级',
        r'首次覆盖',
        r'给予.*评级',
        r'渗透率.*突破',
        r'渗透率.*达到',
        r'周期.*见底',
        r'周期.*回暖',
        r'拐点.*临近',
        r'拐点.*已至',
        r'景气.*上行',
        r'景气.*回升',
        r'景气.*延续',
        r'需求.*拉动',
        r'需求.*增长',
        r'供给.*收缩',
        r'产能.*扩张',
    ]

    has_prediction = any(re.search(pattern, text) for pattern in prediction_patterns)

    # ====== 第二层：排除"假预测"（对已发生事件的评论/回顾） ======
    # 这些词说明内容是对过去的回顾，不是对未来的预测
    review_words = [
        "已有铺垫", "此前已", "此前已经", "回顾", "总结",
        "卸任", "离任", "增聘", "聘任", "任命", "人事变动",
        "公告称", "公告显示", "据公告", "根据公告",
        "财报显示", "业绩报", "年报显示", "季报显示",
        "数据显示", "统计显示",
    ]

    is_review = any(word in text for word in review_words)

    # 如果是回顾/评论类内容，即使有预测词也不算预测
    if is_review and not has_prediction:
        return ("既定事实", "对已发生事件的回顾/评论，无行情预测价值")

    # ====== 第三层：分类 ======
    if has_prediction:
        return ("预测/观点", "包含明确的行情预测或板块研判")

    if has_fact and has_opinion and not is_review:
        return ("混合（事实+观点）", "既有事实陈述也有预测观点")
    elif has_fact and has_opinion and is_review:
        return ("既定事实", "对已发生事件的评论，无行情预测价值")
    elif has_fact:
        return ("既定事实", "主要是已发生事件的描述")
    elif has_opinion:
        return ("预测/观点", "主要是预测性观点和预期")
    else:
        return ("中性", "无明显事实或观点倾向")


def extract_keywords(text: str, max_count: int = 5) -> List[str]:
    """提取关键词"""
    keywords = []

    # 按优先级提取
    priority_keywords = ["重大", "突破", "首次", "万亿", "千亿", "百亿", "重磅", "龙头"]

    for kw in priority_keywords:
        if kw in text and kw not in keywords:
            keywords.append(kw)
            if len(keywords) >= max_count:
                return keywords

    # 从板块关键词中提取
    for sector, sector_kws in SECTOR_KEYWORDS.items():
        for kw in sector_kws:
            if kw in text and kw not in keywords:
                keywords.append(kw)
                if len(keywords) >= max_count:
                    return keywords

    return keywords[:max_count]


def calculate_importance(text: str, sectors: List[str], fact_type: str) -> int:
    """计算重要性得分 (1-10)"""
    score = 5  # 基础分

    # 重要关键词加分
    for word in IMPORTANT_WORDS:
        if word in text:
            score += 1

    # 多板块涉及
    if len(sectors) > 2:
        score += 2
    elif len(sectors) > 1:
        score += 1

    # 预测性内容加分（因为这是我们的核心关注点）
    if "预测" in fact_type or "观点" in fact_type or "混合" in fact_type:
        score += 2

    # 内容长度适中者分数更高
    if 100 < len(text) < 500:
        score += 1
    elif len(text) > 500:
        score -= 1

    # 数值数据加分
    if re.search(r'\d+%', text):
        score += 1
    if re.search(r'\d+亿', text) or re.search(r'\d+万', text):
        score += 1

    # 确保分数在1-10之间
    return max(1, min(10, score))


def determine_sentiment(text: str) -> str:
    """判断情绪倾向"""
    bullish_keywords = ["利好", "上涨", "突破", "看好", "推荐", "机会", "增长", "景气",
                        "强势", "超预期", "业绩", "盈利", "景气"]
    bearish_keywords = ["利空", "下跌", "风险", "看空", "减持", "亏损", "暴雷",
                        "承压", "不及预期", "业绩下滑", "危机"]

    bullish_count = sum(1 for kw in bullish_keywords if kw in text)
    bearish_count = sum(1 for kw in bearish_keywords if kw in text)

    if bullish_count > bearish_count:
        return "利好"
    elif bearish_count > bullish_count:
        return "利空"
    else:
        return "中性"


def generate_summary_and_advice(news: Dict, sectors: List[str], sentiment: str) -> tuple:
    """生成资讯总结和投资建议（精简版）"""
    title = news.get('title', '')
    content = news.get('content', '')
    full_text = title + " " + content

    # 智能生成概括性总结（提取核心观点，不是原文截取）
    summary = ""

    # ======== 研报类：提取核心观点 ========
    if "证券" in title or "研报" in title:
        # 尝试从标题提取核心观点
        if "：" in title:
            # 格式：券商名：观点
            parts = title.split("：", 1)
            if len(parts) > 1:
                summary = parts[1][:25]  # 取观点部分
        elif "看好" in title:
            # 提取看好什么
            idx = title.find("看好")
            summary = title[idx:idx+15] if idx >= 0 else "券商看好相关板块"
        elif "建议" in title:
            idx = title.find("建议")
            summary = title[idx:idx+15] if idx >= 0 else "券商建议关注"
        elif "预计" in title:
            idx = title.find("预计")
            summary = title[idx:idx+15] if idx >= 0 else "券商预计"
        else:
            summary = "券商研报观点，关注相关行业"

    # ======== 行业动态类 ========
    elif "黄仁勋" in title or "英伟达" in title:
        summary = "英伟达AI芯片动态，关注国产替代"
    elif "美光" in title:
        summary = "美光股价创新高，存储芯片景气"
    elif "机器人" in title or "人形机器人" in title:
        summary = "机器人产业进展，关注产业链"
    elif "AI" in title or "人工智能" in title:
        summary = "AI产业链动态，关注算力/芯片"
    elif "半导体" in title or "芯片" in title:
        summary = "半导体行业动态，关注国产替代"

    # ======== 宏观/政策类 ========
    elif "关税" in title or "进口" in title:
        summary = "贸易政策调整，关注相关行业影响"
    elif "人民币" in title or "汇率" in title:
        summary = "汇率波动，关注对出口影响"
    elif "流动性" in title:
        summary = "流动性充裕，市场资金面稳定"
    elif "美元" in title or "美联储" in title:
        summary = "美元/美联储动态影响外资流向"
    elif "黄金" in title:
        summary = "黄金价格波动，关注避险情绪"

    # ======== 公司公告类 ========
    elif "回购" in title:
        summary = "公司回购，传递信心"
    elif "减持" in title:
        summary = "股东减持，注意抛压"
    elif "中标" in title or "签约" in title:
        summary = "订单落地，业绩有望提升"
    elif "战略合作" in title:
        summary = "战略合作达成，关注后续进展"

    # ======== 默认 ========
    else:
        summary = "行业动态，关注对板块影响"

    # 生成精简投资建议（一句话）
    advice_parts = []

    # 基于情绪
    if sentiment == "利好":
        advice_parts.append("偏利好")
    elif sentiment == "利空":
        advice_parts.append("偏利空")

    # 基于板块
    if sectors:
        main_sector = sectors[0]
        if main_sector in ["新能源", "半导体/芯片", "人工智能"]:
            advice_parts.append(f"关注{main_sector}")
        elif main_sector in ["金融/银行"]:
            advice_parts.append("关注金融板块")
        else:
            advice_parts.append(f"关注{main_sector}")

    # 基于关键词
    if "回购" in title:
        advice_parts.append("回购利好")
    elif "减持" in title:
        advice_parts.append("减持承压")
    elif "中标" in title or "签约" in title:
        advice_parts.append("订单落地")
    elif "业绩" in title or "财报" in title:
        advice_parts.append("关注业绩")

    advice = " | ".join(advice_parts) if advice_parts else "观望"
    return summary, advice


def analyze_single_news(news: Dict) -> Dict:
    """分析单条资讯"""
    text = f"{news.get('title', '')} {news.get('content', '')}"

    # 检测板块
    sectors = detect_sectors(text)

    # 分类资讯类型（研报/政策/公司/数据/行业）
    news_type = classify_news_type(text)

    # 分类事实/观点（用于过滤）
    fact_type, fact_detail = classify_fact_or_opinion(text)

    # 提取关键词
    keywords = extract_keywords(text)

    # 计算重要性
    importance = calculate_importance(text, sectors, fact_type)

    # 判断情绪
    sentiment = determine_sentiment(text)

    # 生成总结和建议
    summary, advice = generate_summary_and_advice(news, sectors, sentiment)

    return {
        **news,
        "sectors": sectors,
        "news_type": news_type,  # 资讯类型：研报/政策/公司/数据/行业
        "fact_type": fact_type,
        "fact_or_opinion": news_type,  # 前端显示资讯类型替代事实/观点
        "fact_detail": fact_detail,
        "keywords": keywords,
        "importance_score": importance,
        "sentiment": sentiment,
        "summary": summary,
        "advice": advice,
        "analyzed_at": datetime.now(timezone.utc).isoformat()
    }


def analyze_news_list(news_list: List[Dict]) -> Dict:
    """分析资讯列表，返回分析结果和统计"""
    analyzed_news = []
    stats = {
        "total": len(news_list),
        "facts": 0,
        "opinions": 0,
        "mixed": 0,
        "neutral": 0,
        "sectors": {},
        "sentiments": {"利好": 0, "利空": 0, "中性": 0}
    }

    for news in news_list:
        analyzed = analyze_single_news(news)
        analyzed_news.append(analyzed)

        # 统计
        if analyzed["fact_type"] == "既定事实":
            stats["facts"] += 1
        elif analyzed["fact_type"] == "预测/观点":
            stats["opinions"] += 1
        elif analyzed["fact_type"] == "混合（事实+观点）":
            stats["mixed"] += 1
        else:
            stats["neutral"] += 1

        # 板块统计
        for sector in analyzed["sectors"]:
            stats["sectors"][sector] = stats["sectors"].get(sector, 0) + 1

        # 情绪统计
        stats["sentiments"][analyzed["sentiment"]] += 1

    # 按重要性排序
    analyzed_news.sort(key=lambda x: x["importance_score"], reverse=True)

    return {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "news_list": analyzed_news,
        "stats": stats
    }


def filter_opinion_news(news_list: List[Dict]) -> List[Dict]:
    """过滤出只含预测/观点的资讯"""
    return [n for n in news_list if "预测" in n.get("fact_type", "") or "混合" in n.get("fact_type", "")]


if __name__ == "__main__":
    # 测试
    test_news = [
        {
            "title": "券商晨会：AI算力有望延续强势",
            "content": "多家券商发布盘前策略，认为AI算力板块在海外需求拉动下有望延续强势表现，建议关注光模块、服务器等细分领域。",
            "pub_time": "2024-05-29 09:15",
            "source": "财联社"
        },
        {
            "title": "隔夜美股三大指数集体收跌",
            "content": "纳指跌1.2%，标普500跌0.7%，道指跌0.5%。特斯拉跌3.5%，中概股普遍下跌。",
            "pub_time": "2024-05-29 08:30",
            "source": "东方财富"
        }
    ]

    result = analyze_news_list(test_news)
    print(f"分析完成，共 {result['stats']['total']} 条资讯")
    print(f"事实类: {result['stats']['facts']}, 观点类: {result['stats']['opinions']}")
