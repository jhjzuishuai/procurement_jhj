# -*- coding: utf-8 -*-
"""
记录接口测试：生成、解析、列表、详情、下载、Excel 导入导出、品类、审计日志。
作者：贾皓杰 (JHJ)
"""
from io import BytesIO

import pandas as pd


async def test_generate_and_parse(client, headers, requirement):
    """核心链路：一句话需求 -> 自动识别参数 -> 出 5 个章节 + 风险"""
    response = await client.post("/api/records/generate", json=requirement, headers=headers)
    assert response.status_code == 200, response.text

    data = response.json()["data"]
    parameters = data["parameters"]

    assert parameters["budget"] == 8000000, parameters["budget"]
    assert parameters["quantity"] == "100台", parameters["quantity"]
    assert "45" in parameters["delivery"], parameters["delivery"]
    assert parameters["category_name"] == "服务器采购", parameters["category_name"]

    assert len(data["sections"]) == 5, list(data["sections"].keys())
    assert len(data["risks"]) >= 1, data["risks"]


async def test_list_records(client, headers, record):
    response = await client.get("/api/records", params={"page": 1, "size": 5}, headers=headers)
    assert response.status_code == 200, response.text

    data = response.json()["data"]
    assert data["total"] >= 1
    assert len(data["items"]) >= 1
    assert data["items"][0]["id"] == record["id"]


async def test_record_detail(client, headers, record):
    response = await client.get("/api/records/" + str(record["id"]), headers=headers)
    assert response.status_code == 200, response.text

    data = response.json()["data"]
    assert set(data["sections"].keys()) == {"techSpec", "announcement", "bid", "contract", "evaluation"}
    for key, part in data["sections"].items():
        assert len(part["blocks"]) >= 1, key


async def test_download_word(client, headers, record, tmp_path):
    """下载必须返回真 docx：首字节是 PK（zip 头），体积不能是几 KB 的空壳"""
    response = await client.get("/api/records/" + str(record["id"]) + "/download", headers=headers)
    assert response.status_code == 200, response.text
    assert len(response.content) > 10000, len(response.content)
    assert response.content[:2] == b"PK", response.content[:2]

    # 用 pytest 的 tmp_path 落盘，不往 data/exports 里扔垃圾
    out_file = tmp_path / "download.docx"
    out_file.write_bytes(response.content)
    assert out_file.stat().st_size == len(response.content)


async def test_export_excel(client, headers, record):
    response = await client.get("/api/records/export-excel", headers=headers)
    assert response.status_code == 200, response.text
    assert len(response.content) > 3000, len(response.content)


async def test_import_excel(client, headers):
    """内存里造一个表，走真实的 multipart 上传"""
    table = pd.DataFrame([
        {"标题": "办公笔记本采购",
         "需求正文": "采购笔记本电脑50台，预算为100万元，合同签订后20天内供货。",
         "预算": "", "交付周期": "", "品类编码": "office-device"},
        {"标题": "采购管理系统开发",
         "需求正文": "开发采购管理系统一套，预算为60万元，工期90天，需驻场实施。",
         "预算": "", "交付周期": "", "品类编码": "software-service"},
    ])
    buffer = BytesIO()
    table.to_excel(buffer, index=False, engine="openpyxl")
    files = {"file": ("需求清单.xlsx", buffer.getvalue(),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}

    response = await client.post("/api/records/import-excel", files=files, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["count"] == 2


async def test_categories(client, headers):
    response = await client.get("/api/categories", headers=headers)
    assert response.status_code == 200, response.text
    assert len(response.json()["data"]) == 3


async def test_audit_logs(client, headers, record):
    """生成过一次记录，审计日志里就该有痕迹"""
    response = await client.get("/api/admin/audit-logs", params={"page": 1, "size": 10}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["total"] >= 1
