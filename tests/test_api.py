# -*- coding: utf-8 -*-
"""
接口自测脚本（不依赖 pytest，直接跑就行）。

运行方式（在项目根目录）：
    .venv\\Scripts\\python.exe tests\\test_api.py

它会按真实使用顺序把主要接口走一遍：
健康检查 -> 登录 -> 生成文件 -> 列表 -> 详情 -> 下载 Word -> 调整章节 -> 查看版本
-> 导出 Excel -> 批量导入 Excel -> 品类列表 -> 审计日志

作者：贾皓杰 (JHJ)
"""
import asyncio
import re
import sys
from io import BytesIO
from pathlib import Path

# 把项目根目录加进搜索路径，这样在 tests 目录里也能 import app
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx
import pandas as pd

from app.database import create_all, init_demo_data
from app.main import app

BASE_URL = "http://test"
passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    """打印一条检查结果"""
    global passed, failed
    if condition:
        passed = passed + 1
        print("[通过] " + name)
    else:
        failed = failed + 1
        print("[失败] " + name + "  " + detail)


async def main() -> None:
    # 先把表建好、演示数据写进去（正常启动时这一步在 lifespan 里自动做）
    await create_all()
    await init_demo_data()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL, timeout=30) as client:

        # 1. 健康检查
        response = await client.get("/api/health")
        check("健康检查", response.status_code == 200, str(response.text))

        # 1a. 前端首页（验证静态文件挂载成功）
        response = await client.get("/")
        page_text = response.text
        check("前端首页可打开", response.status_code == 200 and "采购技术规格书" in page_text,
              str(response.status_code))

        # 1b. 首页里写的 css / js 地址必须真能取到
        #     （曾经写成 ./styles.css，从 / 访问就变成 /styles.css，全部 404，页面白屏没样式）
        refs = re.findall(r'(?:href|src)="(/static[^"]+)"', page_text)
        bad = []
        for ref in refs:
            r = await client.get(ref)
            if r.status_code != 200:
                bad.append(ref + " -> " + str(r.status_code))
        check("首页引用的静态资源可访问", len(refs) >= 3 and len(bad) == 0,
              "引用 " + str(len(refs)) + " 个；" + "、".join(bad))

        # 2. 登录
        response = await client.post("/api/auth/login", json={"username": "admin", "password": "Jhj@123456"})
        check("管理员登录", response.status_code == 200, str(response.text))
        token = ""
        if response.status_code == 200:
            token = response.json()["data"]["token"]
        headers = {"Authorization": "Bearer " + token}

        # 3. 查当前用户
        response = await client.get("/api/auth/me", headers=headers)
        check("查询当前用户", response.status_code == 200, str(response.text))

        # 4. 生成采购文件
        requirement = {
            "title": "2026年机房服务器采购项目",
            "content": ("采购机架式服务器100台。预算为800万元。合同签订后45天内完成供货和安装调试。"
                        "CPU要求不低于32核64线程，内存不低于512GB DDR5，硬盘不低于2块960GB SSD，"
                        "网络配置双万兆网卡。质保3年，需提供培训服务和远程运维支持。"),
            "budget": 0,
            "delivery": "",
            "supplier": "具备营业执照、具备同类项目经验、具备原厂授权",
            "category_code": "",
        }
        response = await client.post("/api/records/generate", json=requirement, headers=headers)
        check("生成采购文件", response.status_code == 200, str(response.text))
        record_id = 0
        record = {}
        if response.status_code == 200:
            record = response.json()["data"]
            record_id = record["id"]
            parameters = record["parameters"]
            check("  自动识别预算", parameters["budget"] == 8000000, str(parameters["budget"]))
            check("  自动识别数量", parameters["quantity"] == "100台", str(parameters["quantity"]))
            check("  自动识别交付期", "45" in parameters["delivery"], str(parameters["delivery"]))
            check("  自动匹配品类", parameters["category_name"] == "服务器采购", str(parameters["category_name"]))
            check("  生成 5 个章节", len(record["sections"]) == 5, str(len(record["sections"])))
            check("  风险预审有结果", len(record["risks"]) >= 1, str(len(record["risks"])))

        # 5. 记录列表
        response = await client.get("/api/records", params={"page": 1, "size": 5}, headers=headers)
        check("记录列表", response.status_code == 200 and response.json()["data"]["total"] >= 1, str(response.text)[:200])

        # 6. 记录详情
        response = await client.get("/api/records/" + str(record_id), headers=headers)
        check("记录详情", response.status_code == 200, str(response.text)[:200])

        # 7. 下载 Word
        response = await client.get("/api/records/" + str(record_id) + "/download", headers=headers)
        check("下载 Word", response.status_code == 200 and len(response.content) > 10000,
              str(response.status_code) + " 长度=" + str(len(response.content)))
        if response.status_code == 200:
            out_file = ROOT / "data" / "exports" / ("测试导出_" + str(record_id) + ".docx")
            out_file.write_bytes(response.content)
            print("      Word 已保存到：" + str(out_file))

        # 8. 调整章节
        payload = {"section": "bid", "content": "本项目的采购背景由业务部门提出，现按流程组织采购。"}
        response = await client.post("/api/records/" + str(record_id) + "/adjust", json=payload, headers=headers)
        check("调整章节", response.status_code == 200, str(response.text)[:200])

        # 9. 查看版本
        response = await client.get("/api/records/" + str(record_id) + "/versions", headers=headers)
        check("查看版本历史", response.status_code == 200 and len(response.json()["data"]) == 1,
              str(response.text)[:200])

        # 10. 回滚
        response = await client.post("/api/records/" + str(record_id) + "/versions/0/restore", headers=headers)
        check("回滚版本", response.status_code == 200, str(response.text)[:200])

        # 10a. 块级编辑：改第 0 块 -> 插一块 -> 删一块 -> 两个非法请求
        detail = (await client.get("/api/records/" + str(record_id), headers=headers)).json()["data"]
        blocks_before = len(detail["sections"]["techSpec"]["blocks"])

        payload = {"section": "techSpec", "index": 0, "action": "replace",
                   "block": {"type": "p", "text": "这段是块级编辑改出来的内容。"}}
        response = await client.patch("/api/records/" + str(record_id) + "/document",
                                      json=payload, headers=headers)
        first_text = ""
        if response.status_code == 200:
            first_text = response.json()["data"]["sections"]["techSpec"]["blocks"][0]["text"]
        check("块级编辑-替换某一块", response.status_code == 200 and first_text == "这段是块级编辑改出来的内容。",
              str(response.text)[:200])

        payload = {"section": "techSpec", "index": blocks_before, "action": "insert",
                   "block": {"type": "p", "text": "这是插进来的新段落。"}}
        response = await client.patch("/api/records/" + str(record_id) + "/document",
                                      json=payload, headers=headers)
        blocks_after_insert = 0
        if response.status_code == 200:
            blocks_after_insert = len(response.json()["data"]["sections"]["techSpec"]["blocks"])
        check("块级编辑-插入新块", response.status_code == 200 and blocks_after_insert == blocks_before + 1,
              str(response.status_code) + " 块数=" + str(blocks_after_insert))

        payload = {"section": "techSpec", "index": blocks_before, "action": "delete"}
        response = await client.patch("/api/records/" + str(record_id) + "/document",
                                      json=payload, headers=headers)
        blocks_after_delete = -1
        if response.status_code == 200:
            blocks_after_delete = len(response.json()["data"]["sections"]["techSpec"]["blocks"])
        check("块级编辑-删除某一块", response.status_code == 200 and blocks_after_delete == blocks_before,
              str(response.status_code) + " 块数=" + str(blocks_after_delete))

        payload = {"section": "techSpec", "index": 999, "action": "replace",
                   "block": {"type": "p", "text": "越界"}}
        response = await client.patch("/api/records/" + str(record_id) + "/document",
                                      json=payload, headers=headers)
        check("块级编辑-越界被拦", response.status_code == 400, str(response.status_code))

        payload = {"section": "techSpec", "index": 0, "action": "replace",
                   "block": {"type": "p", "text": "   "}}
        response = await client.patch("/api/records/" + str(record_id) + "/document",
                                      json=payload, headers=headers)
        check("块级编辑-空段落被拦", response.status_code == 400, str(response.status_code))

        # 11. 风险预审
        response = await client.post("/api/records/" + str(record_id) + "/review-risks", headers=headers)
        check("重新风险预审", response.status_code == 200, str(response.text)[:200])

        # 12. 导出 Excel
        response = await client.get("/api/records/export-excel", headers=headers)
        check("导出记录 Excel", response.status_code == 200 and len(response.content) > 3000,
              str(response.status_code) + " 长度=" + str(len(response.content)))

        # 13. 批量导入 Excel（内存里造一个表格）
        table = pd.DataFrame([
            {"标题": "办公笔记本采购", "需求正文": "采购笔记本电脑50台，预算为100万元，合同签订后20天内供货。",
             "预算": "", "交付周期": "", "品类编码": "office-device"},
            {"标题": "采购管理系统开发", "需求正文": "开发采购管理系统一套，预算为60万元，工期90天，需驻场实施。",
             "预算": "", "交付周期": "", "品类编码": "software-service"},
        ])
        buffer = BytesIO()
        table.to_excel(buffer, index=False, engine="openpyxl")
        files = {"file": ("需求清单.xlsx", buffer.getvalue(),
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        response = await client.post("/api/records/import-excel", files=files, headers=headers)
        check("批量导入 Excel", response.status_code == 200 and response.json()["data"]["count"] == 2,
              str(response.text)[:300])

        # 14. 品类列表
        response = await client.get("/api/categories", headers=headers)
        check("品类列表", response.status_code == 200 and len(response.json()["data"]) == 3,
              str(response.text)[:200])

        # 15. 审计日志
        response = await client.get("/api/admin/audit-logs", params={"page": 1, "size": 10}, headers=headers)
        check("审计日志", response.status_code == 200 and response.json()["data"]["total"] >= 1,
              str(response.text)[:200])

        # 16. 未登录访问应该被拦
        response = await client.get("/api/records")
        check("未登录拦截", response.status_code == 401, str(response.status_code))

        # 17. 采购员不能看后台日志
        response = await client.post("/api/auth/login", json={"username": "buyer", "password": "Buyer@123"})
        buyer_token = response.json()["data"]["token"] if response.status_code == 200 else ""
        response = await client.get("/api/admin/audit-logs", headers={"Authorization": "Bearer " + buyer_token})
        check("越权访问被拒", response.status_code == 403, str(response.status_code))

    print("")
    print("========== 结果：通过 " + str(passed) + " 项，失败 " + str(failed) + " 项 ==========")


if __name__ == "__main__":
    asyncio.run(main())
