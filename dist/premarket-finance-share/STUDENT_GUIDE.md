# 盘前财经资讯智能体 · 学生开箱指南

> 🎓 欢迎！这是给你的**完整上手手册**，跟着走就能跑起来。

---

## 📋 目录

1. [你拿到了什么](#1-你拿到了什么)
2. [5 分钟本地预览](#2-5-分钟本地预览)
3. [部署到腾讯云轻量服务器（推荐·学生免费）](#3-部署到腾讯云轻量服务器推荐学生免费)
4. [9:25 自动推送（可选）](#4-925-自动推送可选)
5. [常见问题](#5-常见问题)

---

## 1. 你拿到了什么

**这是一个完整的 Flask Web 应用**——每天早上 9:25 自动推送盘前财经资讯到你的微信。

```
premarket-finance-share/
├── app.py                  # Flask 主入口
├── config.py               # 板块/抓取时间配置
├── modules/                # 抓取/分析/推送模块
├── templates/              # 网页模板（首页、订阅页、报告页…）
├── static/                 # CSS / JS
├── china-finance-rss/      # RSS 数据桥接服务
├── scheduler.py            # 定时推送
├── STUDENT_GUIDE.md        # 本文档
├── 一键启动.bat             # ⭐ Windows 一键启动
└── 启动Web服务.bat          # Windows 启动脚本
```

⚠️ **不包含**（你不需要管）：
- 任何真实的 token / 密钥（你自己申请）
- 你的私人数据（`data/` 已删除）

---

## 2. 5 分钟本地预览

> **最简单的方式**，不部署、不联网。

### 2.1 准备环境

需要装两个东西（一次就好）：

1. **Python 3.10 或以上**
   - 下载：https://www.python.org/downloads/
   - 安装时**勾选 "Add Python to PATH"**

2. **TRAE IDE**（你已经有的话跳过）
   - 下载：https://www.trae.ai/

### 2.2 上传到 TRAE

**步骤 A**：
- 双击解压 `premarket-finance-share.zip`，得到 `premarket-finance-share` 文件夹

**步骤 B**：
- 打开 TRAE → 点击左上角「文件」→「打开文件夹」
- 选择刚才解压的 `premarket-finance-share` 文件夹
- 左侧能看到所有文件，就 OK 了

### 2.3 安装依赖

在 TRAE 底部**终端**（Terminal）输入：

```bash
pip install -r requirements.txt
```

看到 `Successfully installed ...` 就完成了。

### 2.4 启动

**方式 A（最简单·Windows）**：双击文件夹里的 **`一键启动.bat`**

**方式 B（手动）**：在 TRAE 终端执行：

```bash
python app.py
```

启动成功后终端会显示：
```
* Running on http://127.0.0.1:5000
* Running on http://0.0.0.0:5000
```

### 2.5 打开网页

浏览器访问：**http://127.0.0.1:5000**

能看到首页 → 点击「立即刷新」→ 等待 10-30 秒 → 看到资讯列表 → 成功！🎉

---

## 3. 部署到腾讯云轻量服务器（推荐·学生免费）

> 💰 **0 元/月**：学生认证后腾讯云成都节点免费
> 🎯 国内访问快、不用绑信用卡

### 3.1 购买服务器

- 访问 https://console.cloud.tencent.com/lighthouse
- 选**轻量应用服务器** → 地域选**成都** → 镜像选 **Ubuntu 22.04**
- 规格选最便宜的 2 核 2G
- 付款 0 元（学生认证后）

### 3.2 登录服务器

腾讯云控制台 → 你的服务器 → 顶部 **登录** → 选 **免密登录**（Web VNC）

进入黑窗口后执行：

```bash
sudo -i
# 输入 ubuntu 密码
```

### 3.3 部署（一次性脚本）

复制粘贴整段到终端：

```bash
# 1. 装基础
apt update && apt install -y python3 python3-pip git nginx supervisor

# 2. 装项目
cd /opt && git clone https://github.com/你的用户名/premarket-finance.git
cd premarket-finance && pip3 install -r requirements.txt
cd china-finance-rss && pip3 install -r requirements.txt && cd ..

# 3. 写 supervisor 配置（主项目）
cat > /etc/supervisor/conf.d/premarket.conf << 'EOF'
[program:premarket]
command=/usr/bin/python3 -m gunicorn app:app --bind 127.0.0.1:8080 --workers 2 --timeout 180
directory=/opt/premarket-finance
user=root
autostart=true
autorestart=true
EOF

# 4. 写 supervisor 配置（RSS）
cat > /etc/supervisor/conf.d/rss.conf << 'EOF'
[program:rss]
command=/usr/bin/python3 server.py
directory=/opt/premarket-finance/china-finance-rss
user=root
autostart=true
autorestart=true
EOF

# 5. nginx 反向代理
cat > /etc/nginx/sites-available/premarket << 'EOF'
server {
    listen 80 default_server;
    server_name _;
    location /rss/ { proxy_pass http://127.0.0.1:8053/; }
    location / { proxy_pass http://127.0.0.1:8080/; }
}
EOF
ln -sf /etc/nginx/sites-available/premarket /etc/nginx/sites-enabled/premarket
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# 6. 启动
systemctl restart supervisor
sleep 3
supervisorctl status
```

看到 `premarket RUNNING` 和 `rss RUNNING` 就成功。

### 3.4 打开网页

浏览器访问：`http://你的服务器IP/`（IP 在腾讯云控制台看）

---

## 4. 9:25 自动推送（可选）

### 4.1 申请 pushplus token（免费）

1. 打开 https://www.pushplus.plus/
2. 微信扫码登录
3. 复制首页的"您的 token"（32 位字母数字）

### 4.2 在订阅页配置

1. 访问你部署好的网址 → 顶部菜单「订阅」
2. 填邮箱、粘贴 pushplus token
3. 点击「📱 发送测试消息」→ 微信收到测试消息 = 成功

### 4.3 配置定时任务

> 登录服务器执行：

```bash
crontab -e
```

在文件末尾加：

```
25 9 * * 1-5 curl -s -X POST "http://127.0.0.1:8080/api/refresh" -H "Content-Type: application/json" -d '{}' > /var/log/premarket-refresh.log 2>&1
26 9 * * 1-5 curl -s -X POST "http://127.0.0.1:8080/api/send/all" -H "Content-Type: application/json" -d '{}' > /var/log/premarket-send.log 2>&1
```

- `1-5` = 周一到周五（A 股交易日）
- `25 9` = 每天 9:25 触发刷新
- `26 9` = 9:26 触发推送（给抓取留 1 分钟时间）

---

## 5. 常见问题

### Q1: pip install 报错 "Microsoft Visual C++ 14.0 required"（Windows）
A: 装 Microsoft C++ 生成工具：https://visualstudio.microsoft.com/visual-cpp-build-tools/
   安装时勾选 "C++ build tools" 工作负载

### Q2: 启动报 "Address already in use"
A: 5000 端口被占。改 `config.py` 里 `FLASK_PORT=8080`，重启

### Q3: 推送收不到
- 检查 pushplus token 填对没
- 微信关注 "pushplus 推送加" 公众号（首次必须）
- 看服务器日志：`/var/log/premarket-send.log`

### Q4: 腾讯云一定要学生认证吗？
A: 是的。访问 https://cloud.tencent.com/act/campus 完成学生认证（需学信网）

### Q5: 学生能免费用吗？
A: 可以！pushplus 免费版每天 200 条推送额度（你 1 条）。腾讯云成都节点 0 元/月

### Q6: 还有什么问题？
A: 把错误信息截图发给老师

---

## 🆘 遇到问题怎么办？

1. **看错误信息**——90% 的问题都在终端里
2. **把错误截图发给老师**——带上操作步骤
3. **README.md** — 项目根目录有更详细说明

祝部署顺利！🚀
