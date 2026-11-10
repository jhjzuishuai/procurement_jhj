# -*- coding: utf-8 -*-
"""
Excel 批量处理（用 Pandas）。

1. 批量导入：读表格里的需求，一条一行
2. 批量导出：把生成记录导成 Excel

作者：贾皓杰 (JHJ)
"""
from io import BytesIO

import pandas as pd

# 导入模板要求的列名（支持几种常见写法）
COLUMN_ALIAS = {
    "title": ["标题", "项目名称", "需求标题"],
    "content": ["需求正文", "需求内容", "正文"],
    "budget": ["预算", "预算金额"],
    "delivery": ["交付周期", "交付期", "工期"],
    "supplier": ["供应商要求", "资质要求"],
    "category_code": ["品类编码", "品类"],
}


def pick_column(df: pd.DataFrame, names: list[str]) -> str:
    """在表格里找第一个存在的列名"""
    for name in names:
        if name in df.columns:
            return name
    return ""


def read_requirements(content: bytes) -> list[dict]:
    """
    读 Excel 里的需求列表。
    返回 [{"title":..., "content":..., "budget":..., ...}, ...]
    """
    df = pd.read_excel(BytesIO(content), dtype=str)
    df = df.fillna("")

    column_map = {}
    for key, names in COLUMN_ALIAS.items():
        column_map[key] = pick_column(df, names)

    if column_map["title"] == "" or column_map["content"] == "":
        raise ValueError("表格至少需要“标题”和“需求正文”两列")

    items = []
    for _, row in df.iterrows():
        title = str(row[column_map["title"]]).strip()
        text = str(row[column_map["content"]]).strip()
        if title == "" and text == "":
            continue

        budget_text = str(row[column_map["budget"]]).strip() if column_map["budget"] else ""
        budget = 0.0
        if budget_text:
            try:
                budget = float(budget_text.replace(",", "").replace("元", ""))
            except Exception:
                budget = 0.0

        items.append({
            "title": title or "未命名采购项目",
            "content": text,
            "budget": budget,
            "delivery": str(row[column_map["delivery"]]).strip() if column_map["delivery"] else "",
            "supplier": str(row[column_map["supplier"]]).strip() if column_map["supplier"] else "",
            "category_code": str(row[column_map["category_code"]]).strip() if column_map["category_code"] else "",
        })

    return items[:50]  # 一次最多处理 50 条，防止表格太大把服务拖死


def records_to_excel(records: list[dict]) -> bytes:
    """把记录列表导成 Excel 二进制"""
    rows = []
    for item in records:
        parameters = item.get("parameters_json", {}) or {}
        rows.append({
            "生成编号": item.get("generation_no", ""),
            "项目名称": item.get("title", ""),
            "采购品类": parameters.get("category_name", ""),
            "预算金额": parameters.get("budget", 0),
            "采购数量": parameters.get("quantity", ""),
            "交付周期": parameters.get("delivery", ""),
            "风险条数": len(item.get("risks_json", []) or []),
            "解析方式": item.get("parser", ""),
            "创建人": item.get("created_by", ""),
            "创建时间": str(item.get("create_time", "")),
        })

    if len(rows) == 0:
        rows.append({"生成编号": "", "项目名称": "暂无记录"})

    df = pd.DataFrame(rows)
    buffer = BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()
