# -*- coding: utf-8 -*-
"""
生成记录接口：生成、列表、详情、调整、重新生成、风险预审、导出、版本、批量 Excel。

作者：贾皓杰 (JHJ)
"""
from io import BytesIO
from urllib.parse import quote
import copy

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common import new_generation_no, now_text, success, write_audit
from ..database import get_db
from ..deps import check_permission, current_user
from ..models import Category, Record, User
from ..schemas import AdjustIn, BlockEditIn, RequirementIn
from ..services.document_service import build_docx_bytes, build_sections
from ..services.excel_service import read_requirements, records_to_excel
from ..services.parse_service import ai_review_risks, check_risks, parse_requirement, rule_parse

router = APIRouter(prefix="/api/records", tags=["生成记录"])


def record_to_dict(item: Record) -> dict:
    return {
        "id": item.id,
        "generation_no": item.generation_no,
        "title": item.title,
        "requirement": item.requirement_json,
        "parameters": item.parameters_json,
        "sections": item.sections_json,
        "risks": item.risks_json,
        "version_count": len(item.versions_json or []),
        "status": item.status,
        "parser": item.parser,
        "created_by": item.created_by,
        "parent_id": item.parent_id,
        "create_time": str(item.create_time),
    }


async def load_categories(db: AsyncSession) -> list[dict]:
    """把品类读成普通字典列表，方便给解析函数用"""
    result = await db.execute(select(Category).order_by(Category.id))
    items = result.scalars().all()
    return [
        {
            "code": item.code,
            "name": item.name,
            "keywords_json": item.keywords_json or [],
            "contract_type": item.contract_type,
            "contract_terms_json": item.contract_terms_json or {},
        }
        for item in items
    ]


async def get_record_or_404(db: AsyncSession, record_id: int) -> Record:
    result = await db.execute(select(Record).where(Record.id == record_id))
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return record


@router.post("/generate", summary="根据需求生成全套采购文件")
async def generate_record(
    data: RequirementIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    check_permission(user, "generate")

    requirement = data.model_dump()
    categories = await load_categories(db)

    # 1. 解析参数（正则优先，大模型补充）
    parameters = await parse_requirement(requirement, categories)

    # 2. 生成 5 个章节
    sections = build_sections(parameters)

    # 3. 风险预审（本地规则 + 大模型复核）
    risks = check_risks(requirement, parameters)
    ai_risks = await ai_review_risks(parameters)
    if ai_risks:
        risks = risks + ai_risks

    record = Record(
        generation_no=new_generation_no(),
        title=data.title,
        requirement_json=requirement,
        parameters_json=parameters,
        sections_json=sections,
        risks_json=risks,
        versions_json=[],
        status="SUCCESS",
        parser=parameters.get("parser", "local-rule"),
        created_by=user.username,
    )
    db.add(record)
    await write_audit(db, user.username, "generate", "生成采购文件：" + data.title)
    await db.commit()
    await db.refresh(record)

    return success(record_to_dict(record), "生成成功")


@router.get("", summary="记录列表（分页 + 关键字搜索）")
async def list_records(
    page: int = 1,
    size: int = 10,
    keyword: str = "",
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    check_permission(user, "records")

    if page < 1:
        page = 1
    if size < 1 or size > 50:
        size = 10

    statement = select(Record)
    if keyword:
        statement = statement.where(Record.title.like("%" + keyword + "%"))

    total_result = await db.execute(select(func.count()).select_from(statement.subquery()))
    total = total_result.scalar()

    statement = statement.order_by(Record.id.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(statement)
    items = result.scalars().all()

    return success({
        "total": total,
        "page": page,
        "size": size,
        "items": [record_to_dict(item) for item in items],
    })


@router.post("/import-excel", summary="批量导入需求（Pandas 解析，只走本地规则，速度快）")
async def import_excel(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    check_permission(user, "generate")

    content = await file.read()
    try:
        requirement_list = read_requirements(content)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception:
        raise HTTPException(status_code=400, detail="表格解析失败，请确认是 .xlsx 格式且表头正确")

    if len(requirement_list) == 0:
        raise HTTPException(status_code=400, detail="表格里没有有效数据")

    categories = await load_categories(db)
    count = 0

    for requirement in requirement_list:
        parameters = rule_parse(requirement, categories)
        sections = build_sections(parameters)
        risks = check_risks(requirement, parameters)

        record = Record(
            generation_no=new_generation_no(),
            title=requirement.get("title", ""),
            requirement_json=requirement,
            parameters_json=parameters,
            sections_json=sections,
            risks_json=risks,
            versions_json=[],
            status="SUCCESS",
            parser="local-rule",
            created_by=user.username,
        )
        db.add(record)
        count = count + 1

    await write_audit(db, user.username, "import", "批量导入 " + str(count) + " 条需求")
    await db.commit()

    return success({"count": count}, "批量导入完成")


@router.get("/export-excel", summary="导出记录清单为 Excel")
async def export_excel(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    check_permission(user, "records")

    result = await db.execute(select(Record).order_by(Record.id.desc()).limit(500))
    items = result.scalars().all()

    rows = [
        {
            "generation_no": item.generation_no,
            "title": item.title,
            "parameters_json": item.parameters_json or {},
            "risks_json": item.risks_json or [],
            "parser": item.parser,
            "created_by": item.created_by,
            "create_time": str(item.create_time),
        }
        for item in items
    ]

    content = records_to_excel(rows)
    filename = "采购记录清单.xlsx"
    headers = {"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename)}

    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.get("/{record_id}", summary="记录详情")
async def get_record(
    record_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    check_permission(user, "records")
    record = await get_record_or_404(db, record_id)
    return success(record_to_dict(record))


@router.post("/{record_id}/adjust", summary="调整某个章节（需要复核权限）")
async def adjust_record(
    record_id: int,
    data: AdjustIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    check_permission(user, "review")

    record = await get_record_or_404(db, record_id)
    # ★ 必须 deepcopy：直接改 record.sections_json 再赋回同一个对象，
    #   SQLAlchemy 比对"旧值==新值"时发现是同一个对象，认为没变化，不会发 UPDATE。
    #   复制一份新对象再赋值，才一定触发脏检查（这个坑在 adjust / restore 里也存在）。
    sections = copy.deepcopy(record.sections_json or {})

    if data.section not in sections:
        raise HTTPException(status_code=400, detail="章节名不存在，可选：" + "、".join(sections.keys()))

    old_part = sections[data.section]

    # 记一条版本，方便回滚
    versions = copy.deepcopy(record.versions_json or [])
    versions.append({
        "time": now_text(),
        "user": user.username,
        "section": data.section,
        "before": old_part,
    })

    # 新内容替换该章节
    sections[data.section] = {
        "title": old_part.get("title", data.section),
        "blocks": [{"type": "p", "text": data.content}],
    }

    # 注意：JSON 字段要整体重新赋值，SQLAlchemy 才知道它变了
    record.sections_json = sections
    record.versions_json = versions

    await write_audit(db, user.username, "adjust", "调整章节：" + data.section)
    await db.commit()

    return success(record_to_dict(record), "已更新")


def clean_block(block: dict | None, old_block: dict) -> dict:
    """
    校验并清洗"一块"内容，只允许 p / list / table 三种。
    ★ 为什么必须清洗：块内容会被原样存进 JSON 再回传给前端，
      不做类型和长度校验，脏数据会一直留在库里（而且 Word 导出会报错）。
    """
    if block is None:
        raise HTTPException(status_code=400, detail="replace / insert 必须传 block")

    block_type = str(block.get("type", old_block.get("type", "p")))

    if block_type == "p":
        text = str(block.get("text", "")).strip()
        if text == "":
            raise HTTPException(status_code=400, detail="段落内容不能为空")
        if len(text) > 5000:
            raise HTTPException(status_code=400, detail="单段最多 5000 字")
        return {"type": "p", "text": text}

    if block_type == "list":
        items = block.get("items", [])
        if not isinstance(items, list):
            raise HTTPException(status_code=400, detail="list 的 items 必须是数组")
        cleaned = []
        for item in items:
            text = str(item).strip()
            if text != "":
                cleaned.append(text)
        if len(cleaned) == 0:
            raise HTTPException(status_code=400, detail="列表至少要保留一条内容")
        if len(cleaned) > 50:
            raise HTTPException(status_code=400, detail="列表最多 50 条")
        return {"type": "list", "items": cleaned}

    if block_type == "table":
        rows = block.get("rows", [])
        if not isinstance(rows, list) or len(rows) == 0:
            raise HTTPException(status_code=400, detail="表格至少要有一行")
        if len(rows) > 100:
            raise HTTPException(status_code=400, detail="表格最多 100 行")
        width = len(rows[0])
        if width == 0 or width > 12:
            raise HTTPException(status_code=400, detail="表格列数应在 1 ~ 12 之间")

        cleaned_rows = []
        for row in rows:
            if not isinstance(row, list) or len(row) != width:
                raise HTTPException(status_code=400, detail="每一行的列数必须一致")
            cleaned_rows.append([str(cell).strip() for cell in row])
        return {"type": "table", "rows": cleaned_rows}

    raise HTTPException(status_code=400, detail="type 只能是 p / list / table")


@router.patch("/{record_id}/document", summary="块级编辑：改/增/删某一章节里的某一块")
async def edit_document_block(
    record_id: int,
    data: BlockEditIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    和 /adjust 的区别：
      - /adjust   ：整章替换（一次只能换成一整段文字）
      - /document ：块级编辑（只动第 N 块，其余块、表格、列表都不受影响）
    """
    check_permission(user, "review")

    record = await get_record_or_404(db, record_id)
    # 同 adjust：deepcopy 后再改，保证 SQLAlchemy 能检测到 JSON 列变化
    sections = copy.deepcopy(record.sections_json or {})

    if data.section not in sections:
        raise HTTPException(status_code=400, detail="章节名不存在，可选：" + "、".join(sections.keys()))

    part = sections[data.section]
    blocks = part.get("blocks", [])

    if data.action not in ("replace", "insert", "delete"):
        raise HTTPException(status_code=400, detail="action 只能是 replace / insert / delete")

    # 下标检查：insert 可以插到末尾（index == 块数），replace/delete 必须落在已有块上
    if data.action == "insert":
        if data.index > len(blocks):
            raise HTTPException(
                status_code=400,
                detail="插入位置超出范围，可选 0 ~ " + str(len(blocks)),
            )
    else:
        if data.index >= len(blocks):
            raise HTTPException(
                status_code=400,
                detail="块下标不存在，可选 0 ~ " + str(len(blocks) - 1),
            )

    # 先存快照（整章），回滚接口 /versions/{index}/restore 直接能用
    versions = copy.deepcopy(record.versions_json or [])
    versions.append({
        "time": now_text(),
        "user": user.username,
        "section": data.section,
        "before": part,
    })

    old_block = {"type": "p"}
    if data.action != "insert" and data.index < len(blocks):
        old_block = blocks[data.index]

    if data.action == "delete":
        if len(blocks) <= 1:
            raise HTTPException(status_code=400, detail="每个章节至少保留 1 块，不能删空")
        blocks.pop(data.index)
    else:
        new_block = clean_block(data.block, old_block)
        if data.action == "insert":
            blocks.insert(data.index, new_block)
        else:
            blocks[data.index] = new_block

    # ★ JSON 列要整体赋值，SQLAlchemy 才检测到变化（原地改不会触发 UPDATE）
    part["blocks"] = blocks
    sections[data.section] = part
    record.sections_json = sections
    record.versions_json = versions

    await write_audit(
        db,
        user.username,
        "edit_block",
        "块级编辑 " + data.section + " 第 " + str(data.index) + " 块：" + data.action,
    )
    await db.commit()

    return success(record_to_dict(record), "已保存")


@router.post("/{record_id}/regenerate", summary="按原需求重新生成一版")
async def regenerate_record(
    record_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    check_permission(user, "generate")

    old = await get_record_or_404(db, record_id)
    requirement = old.requirement_json or {}
    categories = await load_categories(db)

    parameters = await parse_requirement(requirement, categories)
    sections = build_sections(parameters)
    risks = check_risks(requirement, parameters)

    record = Record(
        generation_no=new_generation_no(),
        title=old.title,
        requirement_json=requirement,
        parameters_json=parameters,
        sections_json=sections,
        risks_json=risks,
        versions_json=[],
        status="SUCCESS",
        parser=parameters.get("parser", "local-rule"),
        created_by=user.username,
        parent_id=old.id,
    )
    db.add(record)
    await write_audit(db, user.username, "regenerate", "重新生成：" + old.title)
    await db.commit()
    await db.refresh(record)

    return success(record_to_dict(record), "已重新生成")


@router.post("/{record_id}/review-risks", summary="重新做一次风险预审")
async def review_risks(
    record_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    check_permission(user, "review")

    record = await get_record_or_404(db, record_id)
    requirement = record.requirement_json or {}
    parameters = record.parameters_json or {}

    risks = check_risks(requirement, parameters)
    ai_risks = await ai_review_risks(parameters)
    if ai_risks:
        risks = risks + ai_risks

    record.risks_json = risks
    await write_audit(db, user.username, "review", "风险预审：" + record.title)
    await db.commit()

    return success({"risks": risks}, "预审完成")


@router.get("/{record_id}/download", summary="下载 Word 文档")
async def download_docx(
    record_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    check_permission(user, "records")

    record = await get_record_or_404(db, record_id)
    content = build_docx_bytes(record.title, record.sections_json or {})

    filename = record.generation_no + "_" + record.title + ".docx"
    headers = {"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename)}

    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


@router.get("/{record_id}/versions", summary="查看修改历史")
async def list_versions(
    record_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    check_permission(user, "records")
    record = await get_record_or_404(db, record_id)
    return success(record.versions_json or [])


@router.post("/{record_id}/versions/{index}/restore", summary="回滚到某一次修改前")
async def restore_version(
    record_id: int,
    index: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    check_permission(user, "review")

    record = await get_record_or_404(db, record_id)
    versions = copy.deepcopy(record.versions_json or [])

    if index < 0 or index >= len(versions):
        raise HTTPException(status_code=400, detail="版本序号不存在")

    item = versions[index]
    # 同 adjust：deepcopy，否则 JSON 列的修改不会被 SQLAlchemy 检测到
    sections = copy.deepcopy(record.sections_json or {})
    sections[item["section"]] = item["before"]
    record.sections_json = sections

    await write_audit(db, user.username, "restore", "回滚章节：" + item["section"])
    await db.commit()

    return success(record_to_dict(record), "已回滚")
