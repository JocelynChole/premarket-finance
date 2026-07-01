#!/usr/bin/env python3
"""
本地持久化模块 - 腾讯云轻量服务器自带持久化磁盘，无需 GitHub 同步
"""
import os, json
from pathlib import Path

PERSISTENCE_ENABLED = False  # 不再需要 GitHub 持久化

def save_json_to_github(path: str, data) -> bool:
    """腾讯云部署：本地磁盘即可，无需 GitHub"""
    return False

def load_json_from_github(path: str):
    """腾讯云部署：本地磁盘即可，无需 GitHub"""
    return None

def sync_github_to_local(repo_path: str, local_path: Path) -> bool:
    """腾讯云部署：本地磁盘即可，无需 GitHub"""
    return False

def save_to_github(path: str, content: str) -> bool:
    return False

def load_from_github(path: str) -> str | None:
    return None

def sync_local_to_github(local_path: Path, repo_path: str):
    pass

def status() -> str:
    return "本地存储（腾讯云持久化磁盘）"
