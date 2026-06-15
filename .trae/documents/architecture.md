# 盘前财经资讯研判智能体 — 技术架构文档

> 版本：v1.0 · 更新日期：2026-06-10

---

## 1. 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                       Windows 主机                            │
│                                                               │
│  ┌──────────────────────┐    ┌──────────────────────────┐    │
│  │ china-finance-rss    │    │  盘前资讯智能体 (本项目)   │    │
│  │  (port 8053)         │◀───│                          │    │
│  │  RSS 网关             │    │  app.py (Flask :5000)    │    │
│  │  - 财联社(新浪备份)   │    │  ├─ templates/ (HTML)    │    │
│  │  - 东方财富           │    │  ├─ static/ (CSS/JS)     │    │
│  │  - 同花顺             │    │  └─ modules/             │    │
│  └──────────────────────┘    │     ├─ fetch_news.py     │    │
│                              │     ├─ analyze_news.py   │    │
│                              │     ├─ filter_news_v2.py │    │
│                              │     ├─ generate_report.py│    │
│                              │     └─ send_wechat.py    │    │
│                              │  scheduler.py            │    │
│                              │  data/                   │    │
│                              │  ├─ reports/*.json       │    │
│                              │  ├─ markdown_reports/*.md│    │
│                              │  └─ subscribers.json     │    │
│                              └────────────┬─────────────┘    │
│                                           │                   │
│                              ┌────────────▼─────────────┐    │
│                              │  Server酱 (sct.ftqq.com)  │    │
│                              │  → 用户个人微信            │    │
│                              └──────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 技术选型

| 层 | 技术 | 理由 |
|----|------|------|
| 后端 | **Python 3.8+** | skill.md 强制要求 |
| Web 框架 | **Flask 2.x** | 轻量、零学习成本、适合单人项目 |
| 前端 | **原生 HTML/CSS/JS**（无框架） | 单页 + 服务端渲染，无需 React/Vue |
| CSS 设计 | **自写 CSS 变量 + 网格布局** | 编辑型杂志感 + 完全可控 |
| 字体 | **Noto Serif SC + Noto Sans SC + JetBrains Mono**（CDN 加载） | 衬线标题 + 无衬线正文 + 等宽数据 |
| 抓取 | **requests + xml.etree** | china-finance-rss 返回 RSS XML |
| 调度 | **schedule + Windows 任务计划** | 进程级 + 系统级双保险 |
| 推送 | **Server酱 开放 API** | 个人微信推送最简方案 |

---

## 3. 目录结构

```
premarket-finance/
├── .trae/
│   └── documents/                # 设计文档
│       ├── PRD.md
│       └── architecture.md
├── app.py                        # Web 入口 (Flask)
├── scheduler.py                  # 定时任务调度器
├── config.py                     # 全局配置
├── requirements.txt              # Python 依赖
├── setup_tasks.py                # Windows 任务计划安装
├── 启动助手.bat                  # Windows 一键启动菜单
├── .env.example                  # 环境变量模板
├── .gitignore
│
├── modules/                      # 核心业务模块
│   ├── __init__.py
│   ├── fetch_news.py            # 抓取 + 时间窗口过滤
│   ├── analyze_news.py          # 板块/情绪/重要性评分
│   ├── filter_news_v2.py        # 自变量/因变量判断
│   ├── generate_report.py       # Markdown 简报生成
│   └── send_wechat.py           # Server酱 推送
│
├── templates/                    # Flask 模板
│   ├── index.html               # 首页
│   ├── report.html              # 简报页
│   ├── sectors.html             # 板块推演
│   ├── subscribe.html           # 订阅中心
│   └── history.html             # 历史档案
│
├── static/                       # 前端静态资源
│   ├── css/
│   │   └── main.css             # 主样式
│   ├── js/
│   │   ├── app.js               # 首页交互
│   │   ├── report.js            # 简报页
│   │   └── subscribe.js         # 订阅页
│   └── img/
│
├── data/                         # 运行时数据
│   ├── reports/                 # JSON 报告
│   ├── markdown_reports/        # Markdown 简报
│   └── subscribers.json         # 订阅用户
│
├── china-finance-rss/            # 数据源服务（git clone）
└── README.md
```

---

## 4. 数据流

### 4.1 单次抓取-分析-生成流程

```
[启动] scheduler.py --now  或  app.py 收到 /api/refresh
        │
        ▼
[Step 1] fetch_news.fetch_and_filter_news()
        ├─ fetch_all_news()  ──→  GET http://localhost:8053/{cls,eastmoney,ths}/...
        ├─ is_within_trading_window()  时间窗口过滤（15:00 → 09:30）
        ├─ filter_news_v2.analyze_news_v2()  自变量判断
        ├─ filter_news_v2.filter_by_quality()  去重 + 质量排序
        └─ fix_news_links()  链接修复
        │
        ▼  List[Dict] (过滤后资讯)
[Step 2] analyze_news.analyze_news_list()
        ├─ detect_sectors()  板块识别
        ├─ classify_fact_or_opinion()  自变量/因变量
        ├─ calculate_importance()  重要性评分
        ├─ determine_sentiment()  情绪判断
        └─ generate_summary_and_advice()  总结生成
        │
        ▼  {news_list, stats}
[Step 3] generate_report.generate_and_save_report()
        ├─ generate_markdown_report()  5 段式简报
        └─ save_report()  → data/markdown_reports/report_YYYYMMDD.md
        │
        ▼
[Step 4] app.save_report()  → data/reports/report_YYYYMMDD.json
        │
        ▼
[Step 5] send_wechat.send_to_subscribers()  → 微信推送（如有活跃订阅者）
```

### 4.2 订阅推送流程

```
[用户] 在 Web 端填写 SendKey
        │
        ▼ POST /api/subscribe
[后端] 保存到 data/subscribers.json
        │
        ▼ 立即调用 test_serverchan() 发测试消息
[Server酱 API] sctapi.ftqq.com/{key}.send
        │
        ▼
[用户微信] 收到测试消息
        │
        ▼
[每日 9:25] scheduler 触发推送
        │
        ├─ 读取 subscribers.json 中 active=true 且有 sendkey 的用户
        ├─ 根据每个用户关注的板块二次过滤资讯
        └─ 逐个调用 send_serverchan() 推送简报摘要
```

---

## 5. 关键 API

| Method | Path | 说明 |
|--------|------|------|
| GET | `/` | 首页（今日速览） |
| GET | `/report` | 简报页（Markdown 渲染） |
| GET | `/sectors` | 板块推演页 |
| GET | `/subscribe` | 订阅中心页 |
| GET | `/history` | 历史档案页 |
| GET | `/api/news` | 获取今日分析结果 |
| POST | `/api/refresh` | 手动触发抓取-分析-生成 |
| GET | `/api/report/today` | 获取今日 Markdown 简报 |
| GET | `/api/report/date/<date>` | 获取指定日期的 JSON 报告 |
| GET | `/api/report/date/<date>/markdown` | 获取指定日期的 Markdown |
| GET | `/api/history` | 历史报告列表 |
| GET | `/api/sectors` | 板块统计 |
| POST | `/api/subscribe` | 新增/更新订阅 |
| GET | `/api/subscribers` | 活跃订阅者列表 |
| POST | `/api/send/test` | 测试 Server酱 |
| POST | `/api/send/all` | 推送给所有订阅者 |

---

## 6. 时间窗口算法

```python
# fetch_news.py
def is_within_trading_window(pub_time_str):
    now = datetime.now()
    last_trading_day = prev_trading_day(now)        # 跳过周末
    next_trading_day = next_trading_day(now)
    
    window_start = last_trading_day + 15:00:00      # 上一交易日收盘
    window_end   = next_trading_day + 09:30:00      # 今日开盘
    if now > window_end:
        window_end = now                            # 已过开盘则扩展到当前
    
    return window_start <= pub_time <= window_end
```

**为什么这样设计？**
- 锁定 15:00→09:30 完美符合 A 股交易时间规律
- 开盘后窗口自动扩展到当前时间，方便用户随时回看
- 周末自动跳过，不会在周六/周日跑出空报告

---

## 7. 自变量判断逻辑

`filter_news_v2.is_independent_variable()` 的判定顺序：

```
1. 排除非 A 股标的（港股、美团/快手等个股）
2. 排除纯行情描述（涨/跌/涨停/跌停）但无机构无预测 → 因变量
3. 强投资词 OR (弱投资词 + 机构来源) → 机构观点（自变量）
4. 命中 independent_patterns（机构研判/行情预测/板块推演/政策前瞻...） → 自变量
5. 命中 dependent_patterns（收盘/复盘/昨日/已获批...） → 因变量
6. 默认 → 中性（过滤）
```

---

## 8. 部署与运行

### 8.1 首次安装（用户视角）

```cmd
:: 1. 双击 启动助手.bat
:: 2. 选择 [3] 立即执行一次（会自动 pip install）
:: 3. 浏览器打开 http://localhost:5000
```

### 8.2 每日自动

```cmd
:: 方式 A: Windows 任务计划（推荐）
python setup_tasks.py     :: 创建每天 8:30 + 9:25 的任务

:: 方式 B: 后台常驻
python scheduler.py       :: schedule 进程级调度
```

### 8.3 环境变量（.env）

```env
# 微信推送（订阅者各自的 SendKey 存在 subscribers.json，不放这里）
WECHAT_WEBHOOK=

# RSS 服务
RSS_HOST=localhost
RSS_PORT=8053

# 调度
SCHEDULED_TIME=08:30
PUSH_TIME=09:25
```

---

## 9. 错误处理策略

| 场景 | 处理 |
|------|------|
| china-finance-rss 未启动 | `/api/news` 自动触发一次提示，控制台不抛错 |
| 单个源抓取失败 | 跳过该源，不影响其他源 |
| 单条资讯分析失败 | 跳过该条，不影响整体 |
| Server酱 推送失败 | 标记该订阅者失败，继续推下一个 |
| 时间窗口内无资讯 | 简报显示"今日无明确热点"，不报错 |

---

## 10. 安全与合规

- **不存储个人敏感信息**：仅存邮箱、SendKey（用户自填自管）
- **免责声明**：所有页面底部明确"不构成投资建议"
- **API 限速**：所有外部调用都有 timeout，无限速
- **数据本地化**：所有数据存本地 JSON，不上传第三方
