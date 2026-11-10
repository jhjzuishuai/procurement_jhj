# -*- coding: utf-8 -*-
"""
采购品类接口：列表、新建、上传模板。

作者：贾皓杰 (JHJ)
"""
import re
from io import BytesIO

from docx import Document
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import config
from ..common import success
from ..database import get_db
from ..deps import check_permission, current_user
from ..models import Category, User

router = APIRouter(prefix="/api/categories", tags=["采购品类"])


class CategoryIn(BaseModel):
    code: str
    name: str
    keywords: list[str] = []
    contract_type: str = "货物采购合同"


def category_to_dict(item: Category) -> dict:
    return {
        "id": item.id,
        "code": item.code,
        "name": item.name,
        "keywords": item.keywords_json,
        "contract_type": item.contract_type,
        "contract_terms": item.contract_terms_json,
        "template_file": item.template_file,
        "template_placeholders": item.template_placeholders_json,
    }


@router.get("", summary="品类列表")
async def list_categories(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Category).order_by(Category.id))
    items = result.scalars().all()
    return success([category_to_dict(item) for item in items])


@router.post("", summary="新建品类（管理员）")
async def create_category(
    data: CategoryIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    check_permission(user, "templates")

    result = await db.execute(select(Category).where(Category.code == data.code))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="品类编码已存在")

    category = Category(
        code=data.code,
        name=data.name,
        keywords_json=data.keywords,
        contract_type=data.contract_type,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return success(category_to_dict(category), "新建成功")


def read_placeholders(content: bytes) -> list[str]:
    """
    从模板 Word 里找出 {{字段}} 或 {字段} 这类占位符。
    只做展示用，方便用户知道模板要填哪些字段。
    """
    document = Document(BytesIO(content))
    texts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                texts.append(cell.text)

    joined = "\n".join(texts)
    found = re.findall(r"\{\{([^}]+)\}\}|\{([^{}]+)\}", joined)

    names = []
    for first, second in found:
        name = (first or second).strip()
        if name and name not in names:
            names.append(name)
    return names


@router.post("/{code}/template", summary="上传该品类的 Word 模板（管理员）")
async def upload_template(
    code: str,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    check_permission(user, "templates")

    if not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="只支持 .docx 文件")

    content = await file.read()
    if len(content) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件超过 " + str(config.MAX_UPLOAD_MB) + "MB")

    result = await db.execute(select(Category).where(Category.code == code))
    category = result.scalar_one_or_none()
    if category is None:
        raise HTTPException(status_code=404, detail="品类不存在")

    # 保存文件：品类编码 + 原文件名
    save_name = code + "_" + file.filename.replace(" ", "_")
    save_path = config.TEMPLATE_DIR / save_name
    with open(save_path, "wb") as f:
        f.write(content)

    placeholders = read_placeholders(content)

    category.template_file = save_name
    category.template_placeholders_json = placeholders
    await db.commit()

    return success({
        "template_file": save_name,
        "placeholders": placeholders,
    }, "模板上传成功")


@router.delete("/{code}/template", summary="删除模板（管理员）")
async def delete_template(
    code: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    check_permission(user, "templates")

    result = await db.execute(select(Category).where(Category.code == code))
    category = result.scalar_one_or_none()
    if category is None:
        raise HTTPException(status_code=404, detail="品类不存在")

    category.template_file = ""
    category.template_placeholders_json = []
    await db.commit()
    return success(None, "模板已删除")
