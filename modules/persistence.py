#!/usr/bin/env python3
"""
持久化模块 - 通过 GitHub API 将关键数据写回仓库
解决 Render 免费 tier ephemeral filesystem 重启丢失数据的问题

环境变量（在 Render Dashboard 配置）：
  GITHUB_TOKEN  - GitHub Personal Access Token（需 repo 权限）
  GITHUB_REPO   - 仓库全名，如 "user/premarket-finance"
  GITHUB_BRANCH - 分支名，默认 "main"

用法：
  from modules.persistence import save_to_github, load_from_github
  save_to_github("data/subscribers.json", json_content)
  content = load_from_github("data/subscribers.json")
"""
import os
import base64
import json
from pathlib import Path

import requests

# ============== 配置 ==============
_GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
_GITHUB_REPO = os.getenv("GITHUB_REPO", "").strip()
_GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main").strip()

# 是否启用 GitHub 持久化（三个环境变量都配了才启用）
PERSISTENCE_ENABLED = bool(_GITHUB_TOKEN and _GITHUB_REPO)

_API_BASE = "https://api.github.com/repos"


def _headers():
    return {
        "Authorization": f"token {_GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }


def _get_file_sha(path: str) -> str | None:
    """获取文件当前 sha（更新文件时必须提供）"""
    url = f"{_API_BASE}/{_GITHUB_REPO}/contents/{path}"
    try:
        r = requests.get(url, headers=_headers(), params={"ref": _GITHUB_BRANCH}, timeout=10)
        if r.status_code == 200:
            return r.json().get("sha")
    except Exception:
        pass
    return None


def save_to_github(path: str, content: str) -> bool:
    """将文本内容写入 GitHub 仓库指定路径

    Args:
        path: 仓库内相对路径，如 "data/subscribers.json"
        content: 文件内容（字符串）

    Returns:
        True 成功 / False 失败（或未启用）
    """
    if not PERSISTENCE_ENABLED:
        return False

    # base64 编码
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    sha = _get_file_sha(path)

    url = f"{_API_BASE}/{_GITHUB_REPO}/contents/{path}"
    payload = {
        "message": f"chore(data): update {path}",
        "content": b64,
        "branch": _GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    try:
        r = requests.put(url, headers=_headers(), json=payload, timeout=15)
        if r.status_code in (200, 201):
            print(f"[PERSIST] ✅ {path} 已写回 GitHub")
            return True
        else:
            print(f"[PERSIST] ❌ {path} 写回失败: HTTP {r.status_code} {r.text[:200]}")
            return False
    except Exception as e:
        print(f"[PERSIST] ❌ {path} 写回异常: {e}")
        return False


def save_json_to_github(path: str, data) -> bool:
    """将 Python 对象序列化为 JSON 后写入 GitHub"""
    return save_to_github(path, json.dumps(data, ensure_ascii=False, indent=2))


def load_from_github(path: str) -> str | None:
    """从 GitHub 仓库读取文件内容

    Returns:
        文件内容字符串，失败返回 None
    """
    if not PERSISTENCE_ENABLED:
        return None

    url = f"{_API_BASE}/{_GITHUB_REPO}/contents/{path}"
    try:
        r = requests.get(url, headers=_headers(), params={"ref": _GITHUB_BRANCH}, timeout=10)
        if r.status_code == 200:
            b64 = r.json().get("content", "")
            return base64.b64decode(b64).decode("utf-8")
        else:
            print(f"[PERSIST] 读取 {path} 失败: HTTP {r.status_code}")
            return None
    except Exception as e:
        print(f"[PERSIST] 读取 {path} 异常: {e}")
        return None


def load_json_from_github(path: str):
    """从 GitHub 读取 JSON 文件并反序列化

    Returns:
        Python 对象，失败返回 None
    """
    content = load_from_github(path)
    if content is None:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def sync_local_to_github(local_path: Path, repo_path: str):
    """本地文件存在时同步到 GitHub（用于启动时检查）"""
    if not PERSISTENCE_ENABLED:
        return
    if not local_path.exists():
        return
    content = local_path.read_text(encoding="utf-8")
    save_to_github(repo_path, content)


def sync_github_to_local(repo_path: str, local_path: Path) -> bool:
    """从 GitHub 拉取文件到本地（本地不存在或为空时）

    Returns:
        True 如果从 GitHub 恢复了数据
    """
    if not PERSISTENCE_ENABLED:
        return False

    # 本地已有有效数据就不覆盖（Render 重启后文件可能存在但 size=0）
    if local_path.exists() and local_path.stat().st_size > 0:
        try:
            with open(local_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    return False  # 已有真实数据，不覆盖
        except OSError:
            pass

    content = load_from_github(repo_path)
    if content is None:
        return False

    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(content, encoding="utf-8")
    print(f"[PERSIST] ✅ 从 GitHub 恢复 {repo_path} → {local_path}")
    return True


def status() -> str:
    """返回持久化状态描述（用于启动日志）"""
    if PERSISTENCE_ENABLED:
        return f"已启用（repo={_GITHUB_REPO}, branch={_GITHUB_BRANCH}）"
    return "未启用（需配置 GITHUB_TOKEN + GITHUB_REPO 环境变量）"
