# -*- coding: utf-8 -*-
"""
公共小工具：统一返回格式、写审计日志、生成编号。

作者：贾皓杰 (JHJ)
"""
import random
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLog


def success(data=None, msg: str = "ok") -> dict:
    """所有接口统一返回这个格式：{code, msg, data}"""
    return {"code": 0, "msg": msg, "data": data}


def now_text() -> str:
    """当前时间的文字形式，例如 2026-11-08 10:30:15"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def new_generation_no() -> str:
    """生成编号，例如 PG20261108103015001"""
    base = datetime.now().strftime("%Y%m%d%H%M%S")
    return "PG" + base + str(random.randint(100, 999))


async def write_audit(db: AsyncSession, username: str, action: str, detail: str, ip: str = "") -> None:
    """写一条审计日志（不单独提交，交给调用方统一 commit）"""
    db.add(AuditLog(username=username, action=action, detail=detail, ip=ip))
