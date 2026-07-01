\---

name: premarket-finance-analyzer

description: 盘前财经资讯预判助手。分析前一日15:00收盘后至当日9:30开盘前发布的财经快讯、机构研判、行情预测，自动判断影响板块，生成结构化简报。

version: 1.0.0

author:Jocelyn

\---



\# 盘前财经资讯预判助手



\## 1. 目的



本 Skill 的核心目标是：\*\*在每日 9:30 开盘前，自动检索并分析前一日 15:00 收盘后至当日 9:30 之间发布的所有财经资讯\*\*，从中提取机构研判、行情预测、热点推演、后市分析等\*\*自变量（预测类）观点\*\*，自动判断每条资讯影响的板块，并生成结构化的盘前预判简报，为投资决策提供辅助参考。



\*\*重要约束\*\*：

\- 时间范围锁定：前一日 15:00:00 → 当日 9:30:00

\- 优先筛选自变量（预测未来），因变量（已发生事实）仅作为背景

\- 不构成投资建议，仅作为分析辅助工具



\## 2. 工具



本 Skill 依赖以下工具和数据源：



| 工具/数据源 | 用途 | 获取方式 |

|------------|------|----------|

| \*\*china-finance-rss\*\* | 抓取新浪财经、东方财富、同花顺的快讯 | 需提前启动 `python server.py` |

| \*\*Python 3.8+\*\* | 运行抓取和分析脚本 | 官网下载安装 |

| \*\*requests 库\*\* | 发送 HTTP 请求获取 RSS 数据 | `pip install requests` |

| \*\*大模型 API（可选）\*\* | 深度分析资讯语义，判断板块和情绪 | 腾讯元器内置或 DeepSeek API |

| \*\*JSON / Markdown\*\* | 数据存储和报告输出格式 | 标准格式 |



\*\*数据源端点\*\*：

\- 新浪财经 7×24 快讯：`http://localhost:8053/cls/telegraph`（路由保留 cls 前缀，内部已切到新浪财经）

\- 东方财富 7×24 快讯：`http://localhost:8053/eastmoney/kuaixun`

\- 同花顺 7×24 快讯：`http://localhost:8053/ths/kuaixun`



\*\*前置条件\*\*：

```bash

\# 1. 克隆并启动 china-finance-rss 服务

git clone https://github.com/yuxuan-made/china-finance-rss.git

cd china-finance-rss

python server.py



\# 2. 安装 Python 依赖

pip install requests

## 3. 输出

> 详见 [`references/output_spec.md`](./references/output_spec.md)

## 4. 步骤

> 详见 [`references/steps.md`](./references/steps.md)

## 5. 示例

> 详见 [`references/examples.md`](./references/examples.md)