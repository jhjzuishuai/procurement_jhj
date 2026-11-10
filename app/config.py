# -*- coding: utf-8 -*-
"""
全局配置：从 .env 文件读参数，读不到就用默认值。

作者：贾皓杰 (JHJ)
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录：app/config.py -> 上一级就是项目根
BASE_DIR = Path(__file__).resolve().parent.parent

# 读取 .env（没有这个文件也不会报错，会直接用默认值）
load_dotenv(BASE_DIR / ".env", encoding="utf-8")

APP_NAME = os.getenv("APP_NAME", "采购文档智能生成系统 v2")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# 数据目录
DATA_DIR = BASE_DIR / "data"
TEMPLATE_DIR = DATA_DIR / "templates"
EXPORT_DIR = DATA_DIR / "exports"
DB_FILE = DATA_DIR / "app.db"


def get_database_url() -> str:
    """
    拼数据库连接串。
    - .env 里 DATABASE_URL 写 sqlite  -> 用本地 SQLite 文件（零配置）
    - .env 里写完整连接串            -> 用 MySQL
    """
    value = os.getenv("DATABASE_URL", "sqlite").strip()
    if value == "" or value == "sqlite":
        # 注意：Windows 路径要用 /，所以用 as_posix()
        return "sqlite+aiosqlite:///" + DB_FILE.as_posix()
    return value


DATABASE_URL = get_database_url()
SQL_ECHO = os.getenv("SQL_ECHO", "false").strip().lower() == "true"

# 登录 token 有效期
TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", "720"))

# 大模型配置
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.siliconflow.cn/v1").strip().rstrip("/")
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_MODEL = os.getenv("AI_MODEL", "deepseek-ai/DeepSeek-V3")
AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "30"))

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))


def ensure_dirs() -> None:
    """保证数据目录都存在（第一次运行会自动创建）"""
    for folder in (DATA_DIR, TEMPLATE_DIR, EXPORT_DIR):
        folder.mkdir(parents=True, exist_ok=True)
