# Render 部署指南 - 盘前财经资讯研判智能体

> 把本地 Flask 项目部署到 Render.com，**任何人打开链接即可访问**，完全免费。

---

## 📋 部署前清单

- [ ] GitHub 账号（https://github.com，免费注册）
- [ ] Render 账号（https://render.com，用 GitHub 登录）
- [ ] 项目已准备好（已完成本仓库的 6 处改动）

---

## 🚀 部署步骤（全程约 10 分钟）

### 第 1 步：把项目推到 GitHub（5 分钟）

#### 1.1 创建 GitHub 仓库

1. 打开 https://github.com/new
2. **Repository name**：`premarket-finance`（或你喜欢的名字）
3. **Public**（必须选 Public，Render 免费 tier 不支持私有仓库的 Web Service）
4. **不要**勾选 "Add a README file"
5. 点 **Create repository**

#### 1.2 在项目目录里初始化 git 并推送

在项目根目录（`c:\Users\HP\Desktop\premarket-finance`）打开终端：

```powershell
# 1. 初始化 git
cd "c:\Users\HP\Desktop\premarket-finance"
git init
git config user.name "你的名字"
git config user.email "你的邮箱@example.com"

# 2. 把 china-finance-rss 的本地 .git 删掉（避免嵌套仓库）
#    Render 不会处理嵌套 git 仓库
Remove-Item -Recurse -Force "china-finance-rss\.git" -ErrorAction SilentlyContinue

# 3. 添加所有文件并提交
git add .
git commit -m "Initial commit - ready for Render deploy"

# 4. 关联到 GitHub 仓库（替换下面的 URL 为你刚创建的）
git remote add origin https://github.com/你的用户名/premarket-finance.git

# 5. 推送到 GitHub
git branch -M main
git push -u origin main
```

> ⚠️ **如果推送时弹出 GitHub 登录窗口**：用 Personal Access Token（PAT）登录，不要用密码。
> 申请 PAT：https://github.com/settings/tokens/new → 勾选 `repo` 权限 → 生成 → 复制 token 当密码用

#### 1.3 验证

刷新 GitHub 仓库页面，应该能看到所有文件（包括 `china-finance-rss/` 目录）已经上传。

---

### 第 2 步：在 Render 创建服务（3 分钟）

#### 2.1 新建 Blueprint 服务

1. 登录 https://render.com
2. 右上角 **New +** → **Blueprint**
3. **Connect a repository** → 选你刚创建的 `premarket-finance` 仓库
4. 如果第一次用，授权 Render 访问你的 GitHub
5. 选好仓库后，Render 会自动检测到根目录的 `render.yaml`
6. **Name** 默认是 `premarket-finance`（可改）
7. 点 **Apply**

#### 2.2 等待首次部署（约 3-5 分钟）

- Render 会执行 `pip install -r requirements.txt && pip install -r china-finance-rss/requirements.txt`
- 然后启动 `gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120`
- 你会在 Logs 面板看到：
  ```
  [RSS] 正在启动 china-finance-rss 子进程（端口 8053）...
  [RSS] china-finance-rss 启动成功 (PID xxx)
  * Running on http://0.0.0.0:10000  （端口由 Render 分配）
  ```

#### 2.3 拿到公网 URL

部署成功后，Render 会显示一个 URL：

```
https://premarket-finance.onrender.com
```

**这就是你要分享的链接！** 复制发给任何人，他们打开就能用。

---

### 第 3 步：验证部署（1 分钟）

打开 https://premarket-finance.onrender.com，应该看到：

- ✅ 顶部黑色顶导 + 5 个页面链接
- ✅ 4 个数字卡（预测类资讯 0 / 涉及板块 0 / 整体情绪 -- / 更新于 --）
- ✅ 点 **立即刷新** 按钮 → 等待 30-60 秒 → 数字卡更新成真实数据
- ✅ 5 个页面之间点击切换正常
- ✅ 订阅页可以加 SendKey

如果点刷新一直转圈，**大概率是 RSS 子进程没起来**：
- 打开 Render 控制台 → 你的服务 → **Logs** 标签
- 搜索 `[RSS]`，看是否成功启动
- 失败的话通常是因为 `china-finance-rss/requirements.txt` 不存在（需要保留这个目录的全部源码）

---

## 🌍 绑定自定义域名（可选，约 10 分钟）

### 1. 买域名

便宜方案（任选）：

| 注册商 | 推荐后缀 | 首年价格 |
|---|---|---|
| 腾讯云 | `.top` / `.xyz` | ¥1-9 |
| 阿里云 | `.top` / `.xyz` | ¥1-9 |
| Namecheap | `.xyz` | $0.99（首年） |
| Cloudflare | `.com` | ¥60 |

### 2. 在 Render 加域名

1. Render 控制台 → 你的服务 → **Settings** → **Custom Domains**
2. 输入你的域名，例如 `premarket.xxx.top`
3. Render 会显示一条 CNAME 记录，类似：
   ```
   premarket.xxx.top  →  premarket-finance.onrender.com
   ```

### 3. 去域名注册商加 DNS 记录

1. 登录域名注册商控制台
2. 找 DNS 设置
3. 添加 CNAME：
   - 主机记录：`premarket`
   - 记录类型：`CNAME`
   - 记录值：`premarket-finance.onrender.com`（Render 给你的值）
   - TTL：600（或默认）

### 4. 等待生效

- 通常 5-30 分钟
- Render 自动签发 HTTPS 证书（Let's Encrypt）
- 验证：访问 `https://premarket.xxx.top` 看到绿色锁

---

## ⚙️ 常用 Render 操作

### 查看日志

Render 控制台 → 你的服务 → **Logs** 标签 → 实时滚动

### 手动重新部署

Render 控制台 → 你的服务 → 右上 **Manual Deploy** → **Deploy latest commit**

### 设置环境变量

Render 控制台 → 你的服务 → **Environment** → 添加 Key-Value
- 例如 `SCHEDULED_TIME=08:00` 改抓取时间
- 例如 `PUSH_TIME=09:00` 改推送时间

### 改完代码自动部署

```powershell
git add .
git commit -m "更新说明"
git push
```

Render 检测到 push 后会自动重新部署（约 2-3 分钟）。

---

## 💡 免费 tier 注意事项

| 项目 | 限制 | 影响 |
|---|---|---|
| **休眠** | 15 分钟无活动会休眠 | 下次访问需等 30-50 秒冷启动 |
| **CPU** | 0.1 CPU 共享 | 抓取慢一点但不卡 |
| **内存** | 512 MB | 够用，但 RSS 抓大量数据时可能 OOM |
| **磁盘** | 临时，每次重启清空 | `data/reports/*.json` 不会持久化 |
| **构建时间** | 每月 500 分钟 | 足够 |
| **流量** | 每月 100 GB | 几万次访问足够 |

**磁盘不持久化的解决方案**：
- 短期：用 Render Disk（$1/月/1GB，挂到 `/var/data`）
- 中期：改用云数据库（Supabase / Neon PostgreSQL 免费）
- 长期：换 Railway / Fly.io

---

## 🆘 常见问题

### Q1: 部署成功但首页"暂无今日资讯"
- 原因：RSS 子进程没起来 / RSS 抓取失败
- 排查：Render → Logs → 搜 `[RSS]` 和 `/api/refresh`
- 临时：手动访问 `https://xxx.onrender.com/api/refresh` 触发一次

### Q2: 推送微信 (Server酱) 失败
- 原因：Render 出口 IP 被 Server酱限流
- 排查：Logs 找 `推送` 相关错误

### Q3: 部署报错 "ModuleNotFoundError"
- 原因：`china-finance-rss/requirements.txt` 没装上
- 解决：检查 `render.yaml` 的 `buildCommand` 是否包含 `pip install -r china-finance-rss/requirements.txt`

### Q4: 冷启动太慢
- 解决：升级到 Render Standard 计划 $7/月（无休眠）

### Q5: 想用自己域名但不会配 DNS
- 解决：腾讯云/阿里云有"新手引导"，跟着点 5 步搞定

---

## 📚 进阶：升级到 PostgreSQL 持久化

免费版每次重启会丢失 `data/reports/` 和 `data/subscribers.json`。要解决：

1. Render → New + → **PostgreSQL**（免费 90 天）
2. 拿到 `DATABASE_URL`
3. 改 `modules/` 下的存储代码用 SQLAlchemy
4. 改 `.env` 注入 `DATABASE_URL`

（这部分需要写代码，超出本文范围。需要时再开新文档。）

---

**祝你部署顺利！** 拿到链接后欢迎分享给朋友测试。
