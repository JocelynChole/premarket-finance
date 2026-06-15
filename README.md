# 📊 盘前财经资讯研判智能体

> **每天 9:30 开盘前 5 分钟，看懂今日主战场。**
> 自动抓取财联社、东方财富、同花顺的预测类快讯 → 智能识别影响板块 → 结构化 Markdown 简报 → 一键推送个人微信。

---

## ✨ 它能做什么

每天前一日 **15:00 收盘后** → 当日 **9:30 开盘前**，自动完成：

1. **抓取** 财联社、东方财富、同花顺三大平台的全部快讯
2. **过滤** 已发生事实（公告、涨跌、复盘等），**只保留预测/观点类资讯**
3. **分析** 每条资讯影响的板块、情绪倾向、重要性评分
4. **生成** 5 段式结构化 Markdown 简报
5. **推送** 9:25 推送到所有订阅者的个人微信
6. **归档** 每日报告自动保存，永久可回溯

---

## 🚀 零基础启动指南（3 分钟）

### 第一步：确认已安装 Python 3.8+

打开「命令提示符」或「PowerShell」，输入：
```
python --version
```
看到 `Python 3.8` 或更高即可。如果没装，访问 https://www.python.org/downloads/ 下载安装。

### 第二步：双击 `启动助手.bat`

在文件资源管理器中双击 `启动助手.bat`，会弹出中文菜单：

```
============================================================
   盘前财经资讯研判智能体  v1.0
============================================================

   [1] 启动 Web 服务（推荐）
   [2] 启动定时任务调度器（后台常驻）
   [3] 立即执行一次（抓取+分析+生成+推送）
   [4] 设置 Windows 任务计划（开机自启）
   [5] 仅启动数据服务 china-finance-rss
   [6] 查看 README
   [0] 退出
```

#### 首次使用

1. **选项 5** → 启动 `china-finance-rss` 数据服务（会自动克隆或提示克隆）
2. **选项 1** → 启动 Web 服务
3. 浏览器自动打开 http://localhost:5000

#### 日常使用

- 想看今天的简报 → **选项 1**
- 想要 8:30 自动抓取 + 9:25 自动推送 → **选项 4**（设置 Windows 任务计划，一次配置永久生效）
- 手动触发一次 → **选项 3**

### 第三步：订阅微信推送

1. 浏览器打开 http://localhost:5000/subscribe
2. 访问 [sct.ftqq.com](https://sct.ftqq.com/) 微信扫码登录，复制你的 `SendKey`
3. 在订阅页填邮箱 + SendKey + 关注的板块
4. 点击「发送测试消息」→ 微信立刻收到测试
5. 点击「立即订阅」→ 完成

之后每天 9:25 微信自动收到盘前简报。

---

## 📂 项目结构

```
premarket-finance/
├── 启动助手.bat              ← ⭐ 双击它开始
├── app.py                    ← Web 服务入口
├── scheduler.py              ← 定时任务调度器
├── config.py                 ← 全局配置
├── setup_tasks.py            ← Windows 任务计划安装
├── requirements.txt          ← Python 依赖
├── .env.example              ← 环境变量模板
├── README.md                 ← 本文件
│
├── modules/                  ← 核心业务模块
│   ├── fetch_news.py         ←   抓取 + 时间窗口过滤
│   ├── filter_news_v2.py     ←   自变量/因变量判断
│   ├── analyze_news.py       ←   板块/情绪/重要性分析
│   ├── generate_report.py    ←   Markdown 简报生成
│   └── send_wechat.py        ←   Server酱 微信推送
│
├── templates/                ← Flask 模板
│   ├── index.html            ←   今日速览
│   ├── report.html           ←   完整简报
│   ├── sectors.html          ←   板块推演
│   ├── subscribe.html        ←   订阅中心
│   └── history.html          ←   历史档案
│
├── static/                   ← 前端静态资源
│   ├── css/main.css          ←   主样式
│   └── js/                   ←   交互逻辑
│
├── data/                     ← 运行时数据
│   ├── reports/              ←   JSON 报告
│   ├── markdown_reports/     ←   Markdown 简报
│   └── subscribers.json      ←   订阅者列表
│
├── .trae/                    ← 设计文档
│   └── documents/
│       ├── PRD.md
│       └── architecture.md
│
└── china-finance-rss/        ← 数据源服务（首次启动时自动克隆）
```

---

## ⏰ 每日运行时间表

| 时间 | 动作 | 配置项 |
|------|------|--------|
| 08:30 | 自动抓取 → 分析 → 生成简报 | `SCHEDULED_TIME` |
| 09:25 | 推送微信 | `PUSH_TIME` |
| 09:30 | A 股开盘 | — |
| 全天 | Web 服务可随时访问 | — |

> 想调整时间？编辑 `config.py` 中的 `SCHEDULED_TIME` 和 `PUSH_TIME`。

---

## 🎨 Web 界面预览

打开 http://localhost:5000 后的 5 个页面：

| 页面 | 路径 | 功能 |
|------|------|------|
| 速览 | `/` | 今日资讯卡片流 + 板块热度图 + 倒计时 |
| 简报 | `/report` | 5 段式 Markdown 完整简报 |
| 板块 | `/sectors` | 按板块归类 + 情绪统计 |
| 订阅 | `/subscribe` | Server酱 订阅表单 + 测试推送 |
| 档案 | `/history` | 历史简报时间线 |

设计风格：编辑型杂志感 × 金融终端，深色高级感。

---

## 🧠 核心逻辑（与 skill.md 对齐）

### 时间窗口
```
前一日 15:00（收盘）  ──────────────►  当日 09:30（开盘）
        ↓                                       ↓
   [窗口起点]                              [窗口终点]
        └─ 只抓取这段时间内发布的资讯 ─┘
```

### 自变量过滤（只保留预测类）
`modules/filter_news_v2.py` 用以下规则过滤：

1. 排除港股、美股等非 A 股标的
2. 排除纯涨跌描述（无机构、无预测）
3. 命中"机构研判 / 行情预测 / 热点推演 / 后市分析"等关键词 → 保留
4. 命中"收盘 / 复盘 / 已获批 / 公告"等关键词 → 丢弃
5. 既不是预测也不是事实 → 丢弃

### 板块识别
`modules/analyze_news.py` 用 13 大板块 + 关键词匹配，识别每条资讯影响的板块。

---

## 🛠 常见问题

### Q1: 启动后看不到任何资讯？
A: 三种可能：
- `china-finance-rss` 未启动 → 运行「启动助手」→「选项 5」
- 时间窗口内确实无新资讯 → 周末/节假日正常
- RSS 服务端口冲突 → 检查 :8053 端口

### Q2: 微信没收到推送？
A: 三个排查点：
- 浏览器先点「发送测试消息」→ 验证 SendKey 是否正确
- 登录 [sct.ftqq.com](https://sct.ftqq.com/) → 检查微信是否绑定
- 订阅时是否填了 SendKey 且保存成功

### Q3: 推送内容很短 / 不完整？
A: Server酱 免费版每天 5 条 + 单条 2000 字以内。盘前简报设计在 1-2 条额度内，超出会截断。可付费升级到 VIP。

### Q4: 抓取失败 / 报错？
A: 财联社官方 API 已失效，本项目用新浪财经备份源。仍可能受反爬影响，可：
- 重试（点「立即刷新」）
- 调整 `fetch_news.py` 中的 timeout
- 等 5-10 分钟再试

### Q5: 想调整哪些资讯被保留？
A: 编辑 `config.py` 中的：
- `SECTOR_KEYWORDS` — 板块识别
- `OPINION_WORDS` / `FACT_WORDS` — 关键判断词
- `IMPORTANT_WORDS` — 重要性评分

### Q6: 想添加新的数据源？
A: 复制 `modules/fetch_news.py` 中的 `fetch_all_news()` 函数，添加新的 RSS endpoint 到 `config.RSS_ENDPOINTS`。

---

## ☁️ 部署到 Render（公网分享给朋友）

想把项目**部署到公网、生成可分享的链接**？推荐用 **Render.com**（免费）。

- 完整教程：[DEPLOY_RENDER.md](DEPLOY_RENDER.md)
- 一键部署时间：约 10 分钟
- 拿到的链接形如 `https://premarket-finance.onrender.com`，可分享给任何人直接点击
- 支持绑定自己的域名（如 `premarket.xxx.top`）

**简要流程**：
1. 注册 GitHub + Render（都用邮箱即可）
2. 把本项目推送到 GitHub（公开仓库）
3. Render → New Blueprint → 选你的仓库 → Apply
4. 等待 3-5 分钟部署完成，拿到 `xxx.onrender.com` 链接
5. 发给朋友 🎉

**注意事项**：
- 免费 tier 15 分钟无活动会休眠，访问需等冷启动
- 免费 tier 无持久化磁盘，`data/reports/` 每次重启会丢
- 升级到付费计划 $7/月可解休眠 + 加持久化磁盘

---

## 📡 数据源

本项目依赖 [china-finance-rss](https://github.com/yuxuan-made/china-finance-rss) 提供 RSS 服务。

`启动助手.bat` 会在首次启动时自动克隆这个仓库到 `china-finance-rss/` 目录。

---

## ⚠️ 免责声明

本项目仅作为**信息聚合 + 辅助研判工具**，**不构成任何投资建议**。
所有资讯来源于第三方公开平台，准确性、及时性、完整性由原作者负责。
任何投资决策需结合自身风险承受能力独立判断。

---

## 📜 License

MIT
