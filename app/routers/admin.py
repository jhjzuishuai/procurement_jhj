# -*- coding: utf-8 -*-
"""
管理接口：审计日志、用户列表、简单统计。

作者：贾皓杰 (JHJ)
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common import success
from ..database import get_db
from ..deps import check_permission, current_user
from ..models import AuditLog, Record, User

router = APIRouter(prefix="/api/admin", tags=["管理"])


@router.get("/audit-logs", summary="审计日志（分页）")
async def audit_logs(
    page: int = 1,
    size: int = 20,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    check_permission(user, "admin")

    if page < 1:
        page = 1
    if size < 1 or size > 100:
        size = 20

    statement = select(AuditLog)
    total_result = await db.execute(select(func.count()).select_from(statement.subquery()))
    total = total_result.scalar()

    statement = statement.order_by(AuditLog.id.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(statement)
    items = result.scalars().all()

    return success({
        "total": total,
        "items": [
            {
                "id": item.id,
                "username": item.username,
                "action": item.action,
                "detail": item.detail,
                "ip": item.ip,
                "create_time": str(item.create_time),
            }
            for item in items
        ],
    })


@router.get("/users", summary="用户列表")
async def list_users(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    check_permission(user, "admin")

    result = await db.execute(select(User).order_by(User.id))
    items = result.scalars().all()

    return success([
        {
            "username": item.username,
            "display_name": item.display_name,
            "role": item.role,
            "create_time": str(item.create_time),
        }
        for item in items
    ])


@router.get("/stats", summary="简单统计")
async def stats(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    check_permission(user, "admin")

    record_count = (await db.execute(select(func.count()).select_from(Record))).scalar()
    user_count = (await db.execute(select(func.count()).select_from(User))).scalar()

    # 按品类统计
    result = await db.execute(select(Record.parameters_json))
    rows = result.scalars().all()

    by_category = {}
    for item in rows:
        name = (item or {}).get("category_name", "未知")
        by_category[name] = by_category.get(name, 0) + 1

    return success({
        "record_count": record_count,
        "user_count": user_count,
        "by_category": by_category,
    })
