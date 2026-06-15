markdown

\# 执行步骤详细说明



\## 步骤概览

启动数据服务 → 安装依赖 → 抓取资讯 → 分析资讯 → 生成简报 → （可选）推送到微信 → （可选）设置定时任务



text



\---



\## 步骤 1：启动数据采集服务（china-finance-rss）



\### 1.1 下载并启动服务



```bash

\# 克隆项目

git clone https://github.com/yuxuan-made/china-finance-rss.git

cd china-finance-rss



\# 启动服务（默认端口 8053）

python server.py

1.2 验证服务是否正常

打开浏览器，访问 http://localhost:8053/cls/telegraph，如果能正常显示 XML 内容，说明服务启动成功。



注意：此服务需要保持运行，不能关闭终端窗口。



步骤 2：安装 Python 依赖

打开新的终端，执行：



bash

pip install requests

步骤 3：抓取财经资讯

3.1 进入脚本目录

bash

cd /path/to/premarket-finance-analyzer/scripts

（把 /path/to/ 换成你电脑上实际的文件夹路径）



3.2 执行抓取脚本

bash

python fetch\_news.py

3.3 抓取结果

脚本会在当前目录生成 news\_raw.json 文件，包含从以下来源抓取的资讯：



财联社（cls）



东方财富（eastmoney）



同花顺（ths）



时间过滤：脚本会自动只保留前一交易日 15:00 至当日 9:30 之间的资讯。



步骤 4：分析资讯

4.1 执行分析脚本

bash

python analyze.py

4.2 分析内容

脚本会自动对每条资讯进行：



板块判断：根据关键词匹配（AI/人工智能、半导体、新能源等）



情绪判断：利好/利空/中性



变量类型判断：自变量（预测类）/ 因变量（事实类）



4.3 分析结果

脚本会生成 analysis\_result.json 文件，包含分析后的数据。



步骤 5：生成简报

5.1 使用 AI 生成简报

将 analysis\_result.json 的内容提供给 AI，并让 AI 按照 output\_spec.md 的模板格式生成最终简报。



提示词示例：



text

请根据以下分析结果，按照 output\_spec.md 的模板格式，生成一份完整的盘前预判简报。



分析结果：

\[粘贴 analysis\_result.json 的内容]

5.2 保存简报

将 AI 生成的简报保存为 report.md 文件。



步骤 6：（可选）推送到微信

6.1 获取企业微信机器人 Webhook

打开企业微信群



点击右上角「···」→「添加群机器人」



复制 Webhook 地址（格式：https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx）



6.2 使用脚本推送

创建 scripts/send\_to\_wechat.py：



python

import requests

import sys



def send\_markdown(content, webhook\_url):

&#x20;   data = {

&#x20;       "msgtype": "markdown",

&#x20;       "markdown": {"content": content}

&#x20;   }

&#x20;   response = requests.post(webhook\_url, json=data)

&#x20;   return response.json()



if \_\_name\_\_ == "\_\_main\_\_":

&#x20;   webhook = sys.argv\[1]  # 第一个参数：Webhook地址

&#x20;   report\_file = sys.argv\[2]  # 第二个参数：简报文件路径

&#x20;   

&#x20;   with open(report\_file, "r", encoding="utf-8") as f:

&#x20;       content = f.read()

&#x20;   

&#x20;   result = send\_markdown(content, webhook)

&#x20;   print(result)

6.3 执行推送

bash

python send\_to\_wechat.py "你的Webhook地址" "report.md"

步骤 7：（可选）设置定时任务

7.1 Windows 任务计划程序

打开「任务计划程序」



点击「创建基本任务」



名称：盘前财经预判



触发器：每天 9:15



操作：启动程序



程序：python



参数：run\_pipeline.py



起始于：C:\\path\\to\\premarket-finance-analyzer\\scripts



7.2 Mac/Linux Crontab

bash

\# 编辑 crontab

crontab -e



\# 添加以下行（每天 9:15 执行）

15 9 \* \* \* cd /path/to/premarket-finance-analyzer/scripts \&\& python run\_pipeline.py

步骤 8：一键执行（整合脚本）

运行 run\_pipeline.py 可以自动执行 步骤3 + 步骤4 + 步骤5：



bash

cd /path/to/premarket-finance-analyzer/scripts

python run\_pipeline.py

常见问题

问题	可能原因	解决方法

ModuleNotFoundError: No module named 'requests'	未安装 requests 库	执行 pip install requests

Connection refused	china-finance-rss 服务未启动	先启动服务：python server.py

抓取到的资讯为空	时间范围内无资讯	检查系统时间是否正确

板块判断不准确	关键词匹配不够全面	在 analyze.py 的 detect\_blocks() 函数中添加更多关键词

文件清单

执行完成后，会生成以下文件：



文件	说明

news\_raw.json	抓取的原始资讯

analysis\_result.json	分析后的数据（含板块、情绪、变量类型）

report.md	最终简报

