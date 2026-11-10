# -*- coding: utf-8 -*-
"""
程序入口。启动时自动建表 + 写入演示数据。
    uvicorn app.main:app --reload

作者：贾皓杰 (JHJ)
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .database import create_all, engine, init_demo_data
from .routers import admin, auth, categories, records

# 日志格式
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("procurement")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """服务启动时执行建表和初始化，关闭时释放连接池"""
    logger.info("正在初始化数据库：%s", config.DATABASE_URL)
    await create_all()
    await init_demo_data()
    logger.info("初始化完成，接口文档 http://127.0.0.1:%s/docs", config.PORT)
    yield
    await engine.dispose()
    logger.info("数据库连接已释放")


app = FastAPI(
    title=config.APP_NAME,
    description="登录 -> 录入需求 -> 解析参数 -> 匹配品类 -> 生成文档 -> 风险预审 -> 导出 Word",
    version="2.0",
    lifespan=lifespan,
)

# 允许跨域，方便前端联调
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(categories.router)
app.include_router(records.router)
app.include_router(admin.router)

# 前端静态页：和接口挂在同一个端口，就不存在跨域问题
STATIC_DIR = config.BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def index_page():
    """打开根路径直接返回前端页面"""
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/health", tags=["系统"], summary="健康检查")
async def health():
    return {
        "code": 0,
        "msg": "ok",
        "data": {
            "app": config.APP_NAME,
            "database": config.DATABASE_URL.split("://")[0],
            "ai_enabled": config.AI_API_KEY != "",
        },
    }


@app.exception_handler(Exception)
async def handle_all_error(request: Request, exc: Exception):
    """兜底异常处理：任何没被捕获的错误都返回统一格式，不把堆栈丢给前端"""
    logger.exception("接口异常：%s", exc)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "msg": "服务器内部错误：" + str(exc), "data": None},
    )
