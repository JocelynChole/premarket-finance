# -*- coding: utf-8 -*-
"""
阿里云函数计算 FC - 每日 9:25 盘前简报自动推送

部署：阿里云函数计算 FC（Python 3.10 runtime）
触发：定时触发器 Cron `0 25 9 ? * MON-FRI`（时区 Asia/Shanghai）
流程：① /api/refresh 生成简报 → ② 等待 5s 落盘 → ③ /api/send/all 推送

环境变量：
- RENDER_URL:    Render Web Service URL（如 https://premarket-finance.onrender.com）
- ADMIN_TOKEN:   管理员 token（与 Render 端 ADMIN_TOKEN 保持一致）
"""
import os
import time
import requests


def handler(event, context):
    """FC 入口函数：被定时触发器调用时执行"""
    render_url = os.getenv('RENDER_URL', 'https://premarket-finance.onrender.com').rstrip('/')
    admin_token = os.getenv('ADMIN_TOKEN', '').strip()

    headers = {'Content-Type': 'application/json'}
    if admin_token:
        headers['X-Admin-Token'] = admin_token

    result = {'success': False, 'stages': {}}

    # ---- 第 1 步：refresh 生成今日简报 ----
    try:
        print("[1/3] /api/refresh (Render 冷启动可能 30-50s)")
        r1 = requests.post(
            f"{render_url}/api/refresh",
            headers=headers,
            json={},
            timeout=180,
        )
        result['stages']['refresh'] = {
            'status': r1.status_code,
            'success': r1.status_code == 200,
            'body': r1.text[:500],
        }
        print(f"      HTTP {r1.status_code}: {r1.text[:200]}")
        if r1.status_code != 200:
            print("refresh 失败，中止")
            return result
    except Exception as e:
        print(f"refresh 异常: {e}")
        result['stages']['refresh'] = {'error': str(e)}
        return result

    # ---- 第 2 步：等待报告落盘 ----
    print("[2/3] 等待 5 秒")
    time.sleep(5)

    # ---- 第 3 步：send/all 推送给所有订阅者 ----
    try:
        print("[3/3] /api/send/all")
        r2 = requests.post(
            f"{render_url}/api/send/all",
            headers=headers,
            json={},
            timeout=180,
        )
        result['stages']['send'] = {
            'status': r2.status_code,
            'success': r2.status_code == 200,
            'body': r2.text[:500],
        }
        print(f"      HTTP {r2.status_code}: {r2.text[:500]}")
        result['success'] = r2.status_code == 200
    except Exception as e:
        print(f"send 异常: {e}")
        result['stages']['send'] = {'error': str(e)}

    print(f"=== 完成 success={result['success']} ===")
    return result
