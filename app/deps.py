# -*- coding: utf-8 -*-
"""
登录校验与权限判断。

用 HTTPBearer 而不是手工读 Header 的原因：
    这样 Swagger 文档右上角会出现 "Authorize" 按钮，
    登录拿到 token 后点一下填进去，后面所有接口就自动带上，不用一个个粘。

用法（在接口函数里）：
    user: User = Depends(current_user)
    check_permission(user, "generate")

作者：贾皓杰 (JHJ)
"""
from datetime import datetime

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .models import User, UserSession

# auto_error=False：没带 token 时不自动报错，交给我们自己返回统一的中文提示
bearer_scheme = HTTPBearer(auto_error=False)

# 角色能干什么
ROLE_PERMISSIONS = {
    "admin": ["generate", "review", "records", "templates", "admin"],
    "buyer": ["generate", "records"],
    "expert": ["generate", "review", "records"],
}


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    从请求头 Authorization: Bearer xxx 里解析出当前用户。
    解析不出来就报 401。
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="未登录：请求头里没有 Authorization")

    token = credentials.credentials

    result = await db.execute(select(UserSession).where(UserSession.token == token))
    session_row = result.scalar_one_or_none()
    if session_row is None:
        raise HTTPException(status_code=401, detail="登录凭证无效，请重新登录")
    if session_row.expire_at < datetime.now():
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")

    result = await db.execute(select(User).where(User.username == session_row.username))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def check_permission(user: User, permission: str) -> None:
    """没有权限就报 403"""
    allowed = ROLE_PERMISSIONS.get(user.role, [])
    if permission not in allowed:
        raise HTTPException(status_code=403, detail="当前角色 " + user.role + " 无权执行 " + permission)
