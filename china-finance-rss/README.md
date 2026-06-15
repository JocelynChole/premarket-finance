# 🇨🇳 China Finance RSS Bridge

A lightweight RSS bridge that converts Chinese financial news sources into standard RSS 2.0 feeds. Single-file Python server, minimal dependencies.

[中文说明](#中文说明)

## Features

- **4 major Chinese financial news sources** in one server
- **Standard RSS 2.0** output — works with any RSS reader
- **Single file** — just `server.py`, no framework needed
- **In-memory cache** — configurable TTL, won't hammer upstream APIs
- **Xueqiu WAF bypass** — uses Chrome CDP to fetch behind Alibaba Cloud WAF

## Supported Sources

| Source | Endpoint | Description |
|--------|----------|-------------|
| CLS (财联社) | `/cls/telegraph` | Real-time financial news flashes |
| Eastmoney (东方财富) | `/eastmoney/kuaixun` | 7×24 financial news |
| THS (同花顺) | `/ths/kuaixun` | 7×24 financial news |
| Xueqiu (雪球) | `/xueqiu/user/{uid}` | User timeline (requires Chrome CDP) |

## Quick Start

```bash
# Clone
git clone https://github.com/yuxuan-made/china-finance-rss.git
cd china-finance-rss

# Run (no install needed for CLS/Eastmoney/THS)
python server.py

# Or with custom port
PORT=9000 python server.py
```

Open `http://localhost:8053/` in your browser to see available feeds.

Add any feed URL to your RSS reader:
```
http://localhost:8053/cls/telegraph
http://localhost:8053/eastmoney/kuaixun
http://localhost:8053/ths/kuaixun
http://localhost:8053/xueqiu/user/1247347556
```

## Configuration

All configuration via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8053` | Server port |
| `CDP_URL` | `http://localhost:9222` | Chrome DevTools Protocol URL |
| `CACHE_TTL` | `300` | Cache TTL in seconds |

## Xueqiu Setup (Optional)

Xueqiu (雪球) uses Alibaba Cloud WAF that blocks direct API requests. This bridge bypasses it by executing `fetch()` inside a real Chrome browser via CDP.

### Requirements

1. Install the optional dependency:
   ```bash
   pip install websocket-client
   ```

2. Start Chrome with remote debugging:
   ```bash
   # macOS
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --remote-allow-origins=*

   # Windows
   chrome.exe --remote-debugging-port=9222 --remote-allow-origins=*

   # Linux
   google-chrome --remote-debugging-port=9222 --remote-allow-origins=*
   ```

3. Open any Xueqiu page in Chrome and log in.

4. Start the RSS bridge:
   ```bash
   CDP_URL=http://localhost:9222 python server.py
   ```

5. Access `http://localhost:8053/xueqiu/user/{uid}` — replace `{uid}` with the Xueqiu user ID.

### Finding a Xueqiu User ID

Visit a user's profile page: `https://xueqiu.com/u/1247347556` — the number is the user ID.

## Docker (Optional)

```bash
docker run -d -p 8053:8053 --name cn-rss python:3.12-slim \
  sh -c "pip install websocket-client && python /app/server.py"
```

Or build your own:
```dockerfile
FROM python:3.12-slim
COPY server.py /app/server.py
RUN pip install --no-cache-dir websocket-client
WORKDIR /app
CMD ["python", "server.py"]
```

## How It Works

```
RSS Reader  →  china-finance-rss  →  CLS API / Eastmoney API / THS API
                    ↓
              Chrome CDP (WebSocket)
                    ↓
              Xueqiu (inside browser, bypasses WAF)
```

- **CLS, Eastmoney, THS**: Direct HTTP requests to public APIs, parsed and converted to RSS XML.
- **Xueqiu**: Connects to Chrome via CDP WebSocket, executes `fetch()` inside an open Xueqiu tab, returns the JSON response. This inherits the browser's cookies and session, bypassing WAF checks.

## License

MIT

---

# 中文说明

## 🇨🇳 中国财经 RSS 桥接服务

轻量级 RSS 桥接服务器，将中国财经新闻源转换为标准 RSS 2.0 feed。单文件 Python，最小依赖。

### 支持的数据源

| 数据源 | 路径 | 说明 |
|--------|------|------|
| 财联社 | `/cls/telegraph` | 实时电报快讯 |
| 东方财富 | `/eastmoney/kuaixun` | 7×24 快讯 |
| 同花顺 | `/ths/kuaixun` | 7×24 快讯 |
| 雪球 | `/xueqiu/user/{uid}` | 用户动态（需 Chrome CDP）|

### 快速开始

```bash
git clone https://github.com/yuxuan-made/china-finance-rss.git
cd china-finance-rss
python server.py
```

打开 `http://localhost:8053/` 查看可用 feed，将 URL 添加到任意 RSS 阅读器即可。

### 雪球设置

雪球使用阿里云 WAF，直接请求 API 会被拦截。本工具通过 Chrome CDP 在浏览器内执行 `fetch()` 绕过 WAF。

1. 安装可选依赖：`pip install websocket-client`
2. 启动 Chrome：`chrome.exe --remote-debugging-port=9222 --remote-allow-origins=*`
3. 在 Chrome 中打开雪球并登录
4. 启动服务：`CDP_URL=http://localhost:9222 python server.py`

### 为什么不用 RSSHub？

RSSHub 很好，但：
- 6000+ 文件，构建慢，配置复杂
- 雪球源需要额外配置且不稳定
- 本工具：单文件，零配置（除雪球外），直接跑

如果你只需要中国财经数据的 RSS，这个更轻量。
