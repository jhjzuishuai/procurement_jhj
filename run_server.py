# -*- coding: utf-8 -*-
"""
PyCharm 里直接点绿三角运行就用这个文件。

用法：
    右键本文件 -> Run 'run_server'
    或者顶部运行配置选 run_server.py

它干的事情和命令行里
    uvicorn app.main:app --reload
完全一样。

作者：贾皓杰 (JHJ)
"""
import uvicorn

from app import config

if __name__ == "__main__":
    # 这里要传字符串 "app.main:app"，不能传 app 对象，
    # 因为 reload=True 时 uvicorn 要自己重新导入模块。
    uvicorn.run(
        "app.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=True,
    )
