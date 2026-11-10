# -*- coding: utf-8 -*-
"""
登录相关接口：注册、登录、查自己、退出。

作者：贾皓杰 (JHJ)
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common import success, write_audit
from ..database import get_db
from ..deps import bearer_scheme, current_user
from ..models import User, UserSession
from ..schemas import LoginIn, RegisterIn
from ..security import check_password, hash_password, new_token, token_expire_time

router = APIRouter(prefix="/api/auth", tags=["登录"])


def user_to_dict(user: User) -> dict:
    """把用户对象转成能返回的字典（不返回密码）"""
    return {
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
    }


@router.post("/register", summary="注册（默认是采购员角色）")
async def register(data: RegisterIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(
        username=data.username,
        display_name=data.display_name or data.username,
        role="buyer",
        password_hash=hash_password(data.password),
    )
    db.add(user)
    await db.commit()
    return success(user_to_dict(user), "注册成功")


@router.post("/login", summary="登录，成功返回 token")
async def login(data: LoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 账号是否还在锁定期
    if user.locked_until is not None and user.locked_until > datetime.now():
        raise HTTPException(status_code=403, detail="密码错误次数过多，请稍后再试：" + str(user.locked_until))

    if not check_password(data.password, user.password_hash):
        user.failed_times = (user.failed_times or 0) + 1
        if user.failed_times >= 5:
            user.locked_until = datetime.now() + timedelta(minutes=10)
            user.failed_times = 0
        await db.commit()
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 登录成功：清空错误次数，发一个 token
    user.failed_times = 0
    user.locked_until = None

    token = new_token()
    db.add(UserSession(token=token, username=user.username, expire_at=token_expire_time()))

    ip = request.client.host if request.client else ""
    await write_audit(db, user.username, "login", "用户登录", ip)
    await db.commit()

    return success({"token": token, "user": user_to_dict(user)}, "登录成功")


@router.get("/me", summary="查当前登录用户")
async def me(user: User = Depends(current_user)):
    return success(user_to_dict(user))


@router.post("/logout", summary="退出登录")
async def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    token = credentials.credentials if credentials else ""
    await db.execute(delete(UserSession).where(UserSession.token == token))
    await db.commit()
    return success(None, "已退出")
