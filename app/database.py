# -*- coding: utf-8 -*-
"""
数据库连接：异步引擎 + 会话工厂 + 建表 + 初始化演示数据。

作者：贾皓杰 (JHJ)
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from . import config
from .models import Base, User, Category
from .security import hash_password

logger = logging.getLogger("procurement")

config.ensure_dirs()

# SQLite 的连接池参数和 MySQL 不一样，分开写更稳
if config.DATABASE_URL.startswith("sqlite"):
    engine = create_async_engine(config.DATABASE_URL, echo=config.SQL_ECHO)
else:
    engine = create_async_engine(
        config.DATABASE_URL,
        echo=config.SQL_ECHO,
        pool_size=10,          # 常驻连接数
        max_overflow=20,       # 临时多开的连接数
        pool_pre_ping=True,    # 取连接前先探活，防止 MySQL 断连
    )

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """
    FastAPI 依赖：每个请求给一个独立会话，用完自动关闭。
    用法： db: AsyncSession = Depends(get_db)
    """
    async with SessionLocal() as session:
        yield session


async def create_all() -> None:
    """建表（已存在就跳过）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def init_demo_data() -> None:
    """
    第一次启动时写入演示账号和采购品类。
    已经有数据就不重复写。
    """
    async with SessionLocal() as session:
        # ---------- 演示账号 ----------
        result = await session.execute(select(func.count()).select_from(User))
        user_count = result.scalar()
        if user_count == 0:
            demo_users = [
                User(username="admin", display_name="管理员", role="admin",
                     password_hash=hash_password("Jhj@123456")),
                User(username="buyer", display_name="采购员", role="buyer",
                     password_hash=hash_password("Buyer@123")),
                User(username="expert", display_name="采购专家", role="expert",
                     password_hash=hash_password("Expert@123")),
            ]
            session.add_all(demo_users)
            logger.info("已创建 3 个演示账号")

        # ---------- 采购品类 ----------
        result = await session.execute(select(func.count()).select_from(Category))
        category_count = result.scalar()
        if category_count == 0:
            categories = [
                Category(
                    code="server",
                    name="服务器采购",
                    keywords_json=["服务器", "CPU", "内存", "硬盘", "机架", "虚拟化"],
                    contract_type="货物采购合同",
                    contract_terms_json={
                        "payment": "到货安装调试并验收合格、发票合规且资料齐备后30日内付款。",
                        "acceptance": "依据技术规格书、投标响应文件、合同条款及国家或行业标准组织验收。",
                        "dispute": "双方协商不成的，可依法向有管辖权的人民法院提起诉讼。",
                    },
                ),
                Category(
                    code="office-device",
                    name="办公电脑采购",
                    keywords_json=["电脑", "台式机", "笔记本", "显示器", "办公设备"],
                    contract_type="货物采购合同",
                    contract_terms_json={
                        "payment": "到货验收合格后30日内付款。",
                        "acceptance": "按装箱清单和技术参数逐项验收。",
                        "dispute": "双方协商不成的，可依法向有管辖权的人民法院提起诉讼。",
                    },
                ),
                Category(
                    code="software-service",
                    name="信息化软件服务",
                    keywords_json=["软件", "系统", "平台", "开发", "运维", "实施"],
                    contract_type="服务采购合同",
                    contract_terms_json={
                        "payment": "按里程碑分阶段付款，验收合格后支付尾款。",
                        "acceptance": "按需求文档、实施方案和验收标准组织验收。",
                        "dispute": "双方协商不成的，可依法向有管辖权的人民法院提起诉讼。",
                    },
                ),
            ]
            session.add_all(categories)
            logger.info("已创建 3 个采购品类")

        await session.commit()
