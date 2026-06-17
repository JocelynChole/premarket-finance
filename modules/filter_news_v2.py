"""
新版资讯筛选模块 - 基于自变量/因变量理论

自变量（决策有效）：指向未来、可指导开盘后交易决策
因变量（无效）：仅总结过去、无法预判未来

筛选逻辑（6 层）：
1. 非 A 股标的（港股/美股个股）
2. 上下文类别（自然灾害/疫情/国际政治等）→ 必须含 A 股影响关键词
3. 纯行情描述（已发生价格回顾）
4. 机构观点识别
5. 自变量模式匹配
6. 因变量模式兜底
"""

import re
from typing import Dict, List, Tuple
from difflib import SequenceMatcher


# ============================================================
# 条件性过滤：可能影响 A 股的"非传统"类别
# 这些类别不是直接过滤，而是必须含 A 股影响关键词才放行
# ============================================================
CONTEXTUAL_CATEGORIES = {
    "自然灾害/气象": {
        "patterns": ["气象", "天气", "地震", "台风", "洪涝", "暴雨", "暴雪", "寒潮",
                     "高温", "干旱", "沙尘暴", "雷电", "泥石流", "山洪", "海啸", "龙卷风"],
        "include_if_any": ["A股", "股市", "板块", "概念股", "影响", "保险", "灾后重建", "种业", "农业",
                          "煤炭", "电力", "光伏", "锂电", "风电", "化工", "钢铁", "水泥", "建材",
                          "应急", "新能源", "供给", "需求", "价格", "通胀", "运输", "港口", "航运"],
    },
    "疫情/防控": {
        "patterns": ["疫情", "防控", "新冠", "核酸", "抗原", "封城", "封控", "静态管理", "隔离", "确诊"],
        "include_if_any": ["A股", "股市", "板块", "消费", "旅游", "航空", "酒店", "餐饮", "零售",
                          "医药", "疫苗", "口罩", "防护服", "经济", "GDP", "外贸", "出口", "复苏",
                          "反弹", "影响"],
    },
    "环保/督察/限产": {
        "patterns": ["环保督察", "环保整改", "环保检查", "限产", "关停", "环保限产", "去产能"],
        "include_if_any": ["A股", "概念股", "板块", "钢铁", "化工", "水泥", "电解铝", "光伏", "玻璃",
                          "环保股", "高耗能", "供给侧", "涨价", "成本", "利润", "业绩"],
    },
    "国际政治/中东/俄乌": {
        "patterns": ["伊朗", "以色列", "哈马斯", "俄乌", "巴以", "中东", "叙利亚", "沙特", "也门",
                     "黎巴嫩", "真主党", "胡塞武装", "加沙", "克里姆林宫", "泽连斯基", "内塔尼亚胡"],
        "include_if_any": ["A股", "概念股", "油价", "金价", "避险", "原油", "黄金", "军工",
                          "国防", "外贸", "出口", "航运", "海运", "有色", "天然气", "能源",
                          "板块", "避险情绪", "军工股"],
    },
    "美联储/欧央行/外盘": {
        "patterns": ["美联储", "鲍威尔", "美国CPI", "美国通胀", "美债", "美股", "纳斯达克", "标普500",
                     "道琼斯", "欧央行", "欧洲央行", "ECB", "欧债", "欧洲议会", "欧盟"],
        "include_if_any": ["A股", "概念股", "股市", "外贸", "出口", "汇率", "美元", "人民币",
                          "外资", "北向资金", "美元指数", "中美", "出口管制", "芯片", "半导体",
                          "板块", "开盘", "影响", "开盘价"],
    },
    "外国新闻/日韩印": {
        "patterns": ["日本央行", "韩国央行", "日经", "韩国KOSPI", "印度SENSEX", "越南", "印尼",
                     "菲律宾", "泰国", "新加坡", "东盟"],
        "include_if_any": ["A股", "概念股", "板块", "外贸", "出口", "替代", "产业链", "竞争",
                          "汇率", "外资", "供应链"],
    },
    "活动/会议/峰会": {
        "patterns": ["发布会", "峰会", "展览", "论坛", "大会", "开幕", "举办", "启动仪式"],
        "include_if_any": ["A股", "概念股", "板块", "行业", "产业", "AI", "新能源", "芯片",
                          "签约", "落地", "合作", "新政策", "订单", "采购", "投资", "项目"],
    },
    "体育赛事": {
        "patterns": ["世界杯", "欧洲杯", "奥运会", "亚运会", "NBA", "中超", "CBA", "足球",
                     "篮球", "网球", "F1", "欧冠", "世界杯预选赛"],
        "include_if_any": ["A股", "概念股", "板块", "啤酒", "体育概念", "体育用品", "赛事经济",
                          "消费", "赞助", "转播", "版权", "彩票", "门票", "赛事营销", "赞助商",
                          "李宁", "安踏", "特步", "青岛啤酒", "燕京啤酒", "重庆啤酒", "视觉中国",
                          "当代明诚", "新华网", "中体产业"],
    },
    "安全/网安/数据": {
        "patterns": ["国家安全", "网络安全", "保密", "数据安全", "信创", "国产替代", "等保"],
        "include_if_any": ["A股", "概念股", "板块", "启明星辰", "深信服", "奇安信", "安恒信息",
                          "天融信", "绿盟科技", "卫士通", "金融科技", "网安", "信息安全", "数字货币"],
    },
    "反腐/司法": {
        "patterns": ["反腐", "落马", "双开", "立案审查", "严重违纪", "司法判决"],
        "include_if_any": ["A股", "概念股", "板块", "公司", "上市", "实控人", "股权", "ST"],
    },
    "社会民生/就业": {
        "patterns": ["社会民生", "就业", "失业率", "就业率", "人口", "出生率", "老龄化", "结婚率"],
        "include_if_any": ["A股", "概念股", "板块", "消费", "养老", "医疗", "婴童", "辅助生殖",
                          "房地产", "教育", "人力资源"],
    },
}

# ============================================================
# 始终排除（即使有 A 股词也不留）
# ============================================================
ALWAYS_EXCLUDE_PATTERNS = [
    # 港股/美股标的
    "港股", "恒指", "科指", "港股通",
    "美团", "快手", "腾讯控股", "腾讯音乐", "拼多多", "金山云", "百度", "阿里", "京东",
    "永利澳门", "银河娱乐", "金沙中国", "澳博", "美高梅", "耐世特", "汇丰", "友邦",
    # 重复性价格预测
    "长江有色", "2日锡价", "2日锌价", "2日镍价", "2日铝价", "2日铜价",
    "锡价或", "锌价或", "镍价或", "铝价或", "铜价或",
    # 与投资决策完全无关
    "员工薪酬", "员工工资", "员工福利", "员工持股", "人事变动",
    "招聘启事", "校招", "社招", "薪酬体系",
]


def is_independent_variable(text: str) -> Tuple[bool, str, str]:
    """
    判断是否为自变量（决策有效资讯）
    返回: (是否有效, 类型标签, 说明)
    """
    text = text.lower()

    # ========== 第 1 层：始终排除（港股/美股标的/完全无关）==========
    if any(p in text for p in ALWAYS_EXCLUDE_PATTERNS):
        return (False, "非A股", "港股/美股个股或完全无关内容")

    # ========== 第 2 层：条件性过滤（必须含 A 股影响才放行）==========
    # 注意：可能一条资讯同时命中多个类别（如"世界杯开幕"同时命中"体育赛事"和"活动/会议/峰会"）
    # 逻辑：找到第一个有 A 股影响的就放行；遍历完都无影响才拒绝
    contextual_hits = []
    for category, config in CONTEXTUAL_CATEGORIES.items():
        matched = [p for p in config["patterns"] if p in text]
        if matched:
            has_impact = any(m in text for m in config["include_if_any"])
            if has_impact:
                # 找到 A 股影响 → 立即放行
                return (True, f"事件驱动:{category}", f"自变量：{category}（含A股影响：{matched[0]}）")
            # 记录"命中但无影响"，继续找下一个类别
            contextual_hits.append((category, matched[0]))

    # 所有命中的类别都没有 A 股影响 → 拒绝
    if contextual_hits:
        first_cat, first_word = contextual_hits[0]
        return (False, "与A股无关", f"「{first_cat}」但未提及A股影响（{first_word}）")

    # ========== 第 3 层：纯行情描述（已发生价格回顾）==========
    pure_price_patterns = [
        "涨近", "涨超", "跌近", "跌超", "涨停", "跌停",
        "盘中涨", "盘中跌", "早盘涨", "早盘跌", "午后涨", "午后跌",
        "概念回暖", "概念走强", "概念反弹", "概念下挫",
        "板块回暖", "板块走强", "板块反弹", "板块下挫",
        "持续反弹", "持续走强", "震荡反弹", "异动拉升",
        "领涨", "走强", "活跃",
    ]

    # 机构观点关键词
    institution_patterns = [
        "高盛", "摩根", "大摩", "小摩", "花旗", "瑞银", "瑞信",
        "中金", "中信证券", "中信建投", "国泰君安", "海通证券", "华泰证券",
        "招商证券", "申万宏源", "广发证券", "兴业证券",
        "黄仁勋", "马斯克", "巴菲特", "达里奥",
    ]

    # 预测性表达关键词
    prediction_patterns = ["预计", "有望", "目标价", "看好", "建议", "评级", "料", "认为", "称"]

    has_pure_price = any(p in text for p in pure_price_patterns)
    has_institution = any(p in text for p in institution_patterns)
    has_prediction = any(p in text for p in prediction_patterns)

    # 纯行情描述（无机构+无预测）→ 过滤
    if has_pure_price and not has_institution and not has_prediction:
        return (False, "因变量", "纯行情回顾，无机构观点")

    # ========== 第 4 层：机构观点识别 ==========
    strong_investment_keywords = [
        "上涨", "下跌", "上行", "下行", "飙升", "回落", "反弹", "回调",
        "目标价", "看好", "推荐", "买入", "增持", "减持", "卖出", "评级",
        "估值", "市值", "股价", "业绩", "景气", "拐点", "周期", "赛道", "风口", "主线",
        "供应", "产能", "订单", "需求", "增长", "下滑", "涨价", "跌价", "提价",
    ]
    weak_investment_keywords = ["万亿", "亿美元", "亿元", "%", "倍"]

    has_strong_investment = any(k in text for k in strong_investment_keywords)
    has_weak_investment = any(k in text for k in weak_investment_keywords)

    has_investment_context = has_strong_investment or (has_weak_investment and "称" in text)

    if has_institution and has_prediction and has_investment_context:
        return (True, "机构观点", "自变量：机构观点")

    # ========== 第 5 层：自变量模式匹配 ==========
    independent_patterns = {
        "机构研判": ["后市研判", "后市展望", "机构看市", "券商看市", "策略周报", "策略月报"],
        "行情预测": ["行情预测", "走势预测", "有望上涨", "有望突破", "目标价", "看高至",
                     "上看", "下看", "料持续", "料上涨", "料下跌", "料将", "走势偏强", "走势偏弱"],
        "板块推演": ["板块轮动", "主线", "风口", "赛道", "高景气"],
        "政策前瞻": ["政策预期", "政策前瞻", "政策红利", "政策催化", "政策窗口"],
        "行业预判": ["行业拐点", "周期见底", "景气回升", "旺季来临", "淡季不淡"],
        "事件催化": ["引爆", "驱动", "主题投资"],
        "业绩指引": ["业绩预增", "业绩超预期", "业绩预告"],
        "资金流向": ["资金流入", "资金抢筹", "北向资金", "主力资金", "机构调研", "机构加仓"],
        "题材推演": ["新基建", "国产替代", "自主可控"],
        "评级调整": ["买入评级", "增持评级", "上调评级", "首次覆盖", "强推"],
    }

    for category, patterns in independent_patterns.items():
        if any(p in text for p in patterns):
            return (True, category, f"自变量：{category}")

    # ========== 第 6 层：因变量模式兜底 ==========
    dependent_patterns = [
        "收盘", "复盘", "今日总结", "今日行情", "今日盘面", "今日回顾",
        "沪指涨", "沪指跌", "深成指", "创业板指",
        "昨日", "上周", "上月", "今年以来", "年初至今",
        "累计上涨", "累计下跌", "涨幅达", "跌幅达",
        "数据显示", "据统计", "历史数据", "过往表现",
        "结果出炉", "尘埃落定", "靴子落地", "正式落地",
        "已获批", "已通过", "已完成", "已签署",
        "历史走势", "历史回顾", "历年表现", "同期对比",
        "政策落地后", "政策实施后", "政策效果", "政策回顾",
        "公告", "披露", "发布", "正式", "已经", "已完成",
    ]

    if not has_institution and any(p in text for p in dependent_patterns):
        return (False, "因变量", "仅总结过去，无机构观点")

    # 默认：无法明确判断预测价值
    return (False, "中性", "无法明确判断预测价值")


def classify_sector_precise(text: str) -> List[str]:
    """
    精准匹配板块（禁止模糊归类）
    """
    text = text.lower()
    sectors = []

    # 科技类（细分）
    if any(w in text for w in ["人工智能", "ai", "大模型", "算力", "chatgpt"]):
        sectors.append("人工智能")
    if any(w in text for w in ["半导体", "芯片", "光刻机", "晶圆", "封测", "国产替代"]):
        sectors.append("半导体/芯片")
    if any(w in text for w in ["机器人", "人形机器人", "减速器", "伺服电机"]):
        sectors.append("机器人")
    if any(w in text for w in ["消费电子", "智能手机", "苹果链", "华为链"]):
        sectors.append("消费电子")

    # 新能源类（细分）
    if any(w in text for w in ["锂电池", "宁德时代", "磷酸铁锂", "固态电池"]):
        sectors.append("锂电池")
    if any(w in text for w in ["光伏", "硅料", "组件", "逆变器", "储能"]):
        sectors.append("光伏/储能")
    if any(w in text for w in ["风电", "海上风电", "风机"]):
        sectors.append("风电")
    if any(w in text for w in ["新能源汽车", "比亚迪", "特斯拉", "造车新势力"]):
        sectors.append("新能源汽车")

    # 周期类（细分）
    if any(w in text for w in ["铜", "铝", "锌", "镍", "锡", "有色金属"]):
        sectors.append("有色金属")
    if any(w in text for w in ["钢铁", "铁矿石", "螺纹钢"]):
        sectors.append("钢铁")
    if any(w in text for w in ["煤炭", "焦煤", "焦炭", "动力煤"]):
        sectors.append("煤炭")
    if any(w in text for w in ["化工", "石化", "mdi", "钛白粉"]):
        sectors.append("化工")

    # 金融类（细分）
    if any(w in text for w in ["银行", "券商", "保险", "信托"]):
        sectors.append("金融")
    if any(w in text for w in ["地产", "房地产", "建材", "水泥"]):
        sectors.append("地产链")

    # 消费类（细分）
    if any(w in text for w in ["白酒", "茅台", "五粮液", "啤酒"]):
        sectors.append("白酒/啤酒")
    if any(w in text for w in ["医药", "创新药", "cxo", "医疗器械"]):
        sectors.append("医药")
    if any(w in text for w in ["食品", "调味品", "乳业"]):
        sectors.append("食品饮料")

    # 其他题材
    if any(w in text for w in ["军工", "航天", "航空", "船舶"]):
        sectors.append("军工")
    if any(w in text for w in ["基建", "建筑", "工程机械", "挖掘机"]):
        sectors.append("基建")

    return sectors if sectors else ["其他"]


def filter_by_quality(news_list: List[Dict]) -> List[Dict]:
    """
    价值优先级筛选
    优先保留：券商头部机构、权威财经媒体、产业一线观点
    """
    high_quality_sources = [
        "中信证券", "中信建投", "国泰君安", "海通证券", "华泰证券",
        "招商证券", "中金公司", "申万宏源", "广发证券", "兴业证券",
        "高盛", "摩根士丹利", "摩根大通", "花旗", "瑞银", "瑞信",
        "证券时报", "上海证券报", "中国证券报", "经济观察报",
        "工信部", "发改委", "统计局", "能源局", "央行", "证监会", "国务院",
    ]

    scored_news = []
    for news in news_list:
        title = news.get('title', '')
        source = news.get('source', '')

        score = 0
        if any(s in source or s in title for s in high_quality_sources):
            score += 3

        if any(w in title for w in ['看好', '推荐', '买入', '增持', '目标价']):
            score += 2

        if re.search(r'\d+%', title) or re.search(r'\d+亿', title):
            score += 1

        scored_news.append((score, news))

    scored_news.sort(key=lambda x: x[0], reverse=True)

    filtered = []
    seen_titles = []
    for score, news in scored_news:
        title = news.get('title', '')
        is_duplicate = False
        for seen in seen_titles:
            similarity = calculate_similarity(title, seen)
            if similarity > 0.9:
                is_duplicate = True
                break

        if not is_duplicate:
            filtered.append(news)
            seen_titles.append(title)

    return filtered


def calculate_similarity(str1: str, str2: str) -> float:
    """计算两个字符串的相似度（0-1）

    使用 difflib.SequenceMatcher 算法（最长公共子序列）
    - 比"位置完全相同字符数"更鲁棒
    - 能识别漏字、增字的同事件标题（如"筹建" vs "加紧筹建"）

    测试案例：
        "中国正在加紧筹建世界人工智能合作组织" (20字)
        "中国正在筹建世界人工智能合作组织" (18字)
        → 0.95（超过 0.75 阈值）
    """
    if not str1 or not str2:
        return 0.0

    # 清洗：只保留中文/字母/数字
    s1 = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', str1)
    s2 = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', str2)

    if not s1 or not s2:
        return 0.0

    # SequenceMatcher.ratio() = 2.0 * LCS / (len(s1) + len(s2))
    return SequenceMatcher(None, s1, s2).ratio()


def analyze_news_v2(news: Dict) -> Dict:
    """
    新版资讯分析（基于自变量理论 + 条件性过滤）
    """
    text = f"{news.get('title', '')} {news.get('content', '')}"

    # 1. 判断是否为自变量
    is_valid, var_type, reason = is_independent_variable(text)

    # 2. 精准匹配板块
    sectors = classify_sector_precise(text)

    # 3. 情绪判断
    sentiment = "中性"
    if any(w in text for w in ['看好', '上涨', '突破', '机会', '利好', '超预期']):
        sentiment = "利好"
    elif any(w in text for w in ['看空', '下跌', '风险', '利空', '不及预期']):
        sentiment = "利空"

    # 4. 生成决策建议
    advice = ""
    if is_valid:
        advice_parts = []
        if sentiment == "利好":
            advice_parts.append("📈 偏利好")
        elif sentiment == "利空":
            advice_parts.append("📉 偏利空")

        if sectors and sectors[0] != "其他":
            advice_parts.append(f"关注{sectors[0]}")

        advice = " | ".join(advice_parts) if advice_parts else "关注相关板块"
    else:
        advice = f"➡️ {reason}"

    return {
        **news,
        "is_valid": is_valid,
        "var_type": var_type,
        "sectors": sectors,
        "sentiment": sentiment,
        "advice": advice,
    }
