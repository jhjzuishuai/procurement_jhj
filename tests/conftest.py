# -*- coding: utf-8 -*-
"""
pytest 公共夹具（fixture）。

作者：贾皓杰 (JHJ)

三个关键点：
1. os.environ["DATABASE_URL"] 必须写在 import app 之前。
   app/config.py 里的 load_dotenv() 是在"模块被导入的那一刻"执行的，
   导入之后再设环境变量就晚了。load_dotenv(override=False) 不覆盖已有变量，所以先设先赢。
2. os.environ["AI_API_KEY"] 置空：测试绝不真的去调大模型。
   否则每生成一条记录都要等网络（几秒到超时 30 秒），测试又慢又不稳定，
   还会真的花钱。置空后走本地规则，结果完全可复现。
3. 建表和演示数据一轮测试只做一次（prepared_db），每个测试之间只清业务数据。
   如果每个测试都 drop + create + 重新哈希 3 个账号密码，纯属浪费。
"""
import os
import sys
from pathlib import Path

import httpx
import pytest
from sqlalchemy import delete

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TEST_DB = ROOT / "data" / "test.db"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + TEST_DB.as_posix()
os.environ["AI_API_KEY"] = ""

from app.database import SessionLocal, engine, init_demo_data  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditLog, Base, Record, UserSession  # noqa: E402

# 老的 print 版冒烟脚本（tests/test_api.py）不参与 pytest 收集：
# 它没有 test_ 开头的函数，留着给人手工快速跑一遍用。
collect_ignore = ["test_api.py"]


@pytest.fixture(scope="session", autouse=True)
async def prepared_db():
    """整个测试会话只建一次表、只写一次演示数据"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await init_demo_data()
    yield


@pytest.fixture(autouse=True)
async def clean_business_data(prepared_db):
    """每个测试开始前清掉业务数据，保留 user / category（演示账号和品类要复用）"""
    async with SessionLocal() as session:
        await session.execute(delete(AuditLog))
        await session.execute(delete(UserSession))
        await session.execute(delete(Record))
        await session.commit()
    yield


@pytest.fixture
async def client(clean_business_data):
    """进程内客户端：直接走 ASGI，不占端口、不用真起服务"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as c:
        yield c


@pytest.fixture
async def token(client):
    """管理员 token"""
    response = await client.post("/api/auth/login", json={"username": "admin", "password": "Jhj@123456"})
    assert response.status_code == 200, response.text
    return response.json()["data"]["token"]


@pytest.fixture
def headers(token):
    return {"Authorization": "Bearer " + token}


@pytest.fixture
def requirement():
    """一条完整的大白话需求，后面好几个测试共用"""
    return {
        "title": "2026年机房服务器采购项目",
        "content": ("采购机架式服务器100台。预算为800万元。合同签订后45天内完成供货和安装调试。"
                    "CPU要求不低于32核64线程，内存不低于512GB DDR5，硬盘不低于2块960GB SSD，"
                    "网络配置双万兆网卡。质保3年，需提供培训服务和远程运维支持。"),
        "budget": 0,
        "delivery": "",
        "supplier": "具备营业执照、具备同类项目经验、具备原厂授权",
        "category_code": "",
    }


@pytest.fixture
async def record(client, headers, requirement):
    """先生成一条记录，需要"已有记录"的测试都依赖它"""
    response = await client.post("/api/records/generate", json=requirement, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]
