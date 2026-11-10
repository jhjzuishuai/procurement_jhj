# -*- coding: utf-8 -*-
"""
文档生成：把结构化参数变成 5 个章节，再导出成 Word。

章节结构说明（sections_json）：
{
  "techSpec": {"title": "技术规格书", "blocks": [
      {"type": "p",    "text": "一段话"},
      {"type": "list", "items": ["条目1", "条目2"]},
      {"type": "table","head": ["参数", "要求"], "rows": [["CPU", "..."]], }
  ]},
  ...
}

作者：贾皓杰 (JHJ)
"""
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt


def money_text(amount: float) -> str:
    """金额加千分位，例如 8,000,000"""
    try:
        return "{:,}".format(int(amount))
    except Exception:
        return str(amount)


def build_sections(parameters: dict) -> dict:
    """根据参数生成 5 个章节"""
    category = parameters.get("category_name", "")
    quantity = parameters.get("quantity", "") or "按实际需求"
    budget = money_text(parameters.get("budget", 0))
    delivery = parameters.get("delivery", "") or "合同签订后按约定执行"
    terms = parameters.get("contract_terms", {}) or {}
    config = parameters.get("configuration", {}) or {}
    technical = parameters.get("technical_requirements", [])
    service = parameters.get("service_requirements", [])
    qualification = parameters.get("qualification_requirements", [])

    config_rows = []
    if config.get("cpu"):
        config_rows.append(["处理器", config["cpu"]])
    if config.get("memory"):
        config_rows.append(["内存", config["memory"]])
    if config.get("storage"):
        config_rows.append(["存储", config["storage"]])
    if config.get("network"):
        config_rows.append(["网络", config["network"]])
    if config.get("warranty"):
        config_rows.append(["质保", config["warranty"]])
    if len(config_rows) == 0:
        config_rows = [["主要参数", "应满足采购人使用需求"]]

    sections = {}

    # ---------- 1. 技术规格书 ----------
    sections["techSpec"] = {
        "title": "技术规格书",
        "blocks": [
            {"type": "p", "text": "一、项目概况"},
            {"type": "p", "text": "本项目采购内容为" + category + "，采购数量 " + quantity
                                 + "，预算金额 " + budget + " 元，交付期限 " + delivery + "。"},
            {"type": "p", "text": "二、技术规格要求"},
            {"type": "list", "items": technical},
            {"type": "p", "text": "三、主要配置参数"},
            {"type": "table", "head": ["参数项", "要求"], "rows": config_rows},
            {"type": "p", "text": "四、服务要求"},
            {"type": "list", "items": service},
            {"type": "p", "text": "五、验收要求"},
            {"type": "p", "text": "供应商应按合同约定完成供货、安装调试和资料移交。验收依据包括本技术规格书、"
                                  "投标响应文件、合同条款及国家或行业相关标准。"},
        ],
    }

    # ---------- 2. 招标公告 ----------
    sections["announcement"] = {
        "title": "招标公告",
        "blocks": [
            {"type": "p", "text": "根据采购计划，现对" + category + "进行公开采购，欢迎符合条件的供应商参与。"},
            {"type": "table",
             "head": ["项目信息", "内容"],
             "rows": [
                 ["项目名称", parameters.get("title", "")],
                 ["采购品类", category],
                 ["采购数量", quantity],
                 ["预算金额", budget + " 元"],
                 ["交付期限", delivery],
                 ["评审方式", parameters.get("evaluation_method", "综合评分法")],
             ]},
            {"type": "p", "text": "供应商资格要求："},
            {"type": "list", "items": qualification},
        ],
    }

    # ---------- 3. 招标文件主体 ----------
    sections["bid"] = {
        "title": "招标文件主体",
        "blocks": [
            {"type": "p", "text": "一、采购背景"},
            {"type": "p", "text": parameters.get("content", "") or "采购人根据业务需要组织本次采购。"},
            {"type": "p", "text": "二、技术要求"},
            {"type": "list", "items": technical},
            {"type": "p", "text": "三、商务要求"},
            {"type": "list", "items": [
                "交付期限：" + delivery,
                "付款方式：" + terms.get("payment", "按合同约定付款"),
                "验收方式：" + terms.get("acceptance", "按技术规格书逐项验收"),
            ]},
            {"type": "p", "text": "四、评审办法"},
            {"type": "p", "text": "本项目采用" + parameters.get("evaluation_method", "综合评分法") + "，"
                                  "从价格、技术响应、服务能力和履约经验等方面综合评审。"},
        ],
    }

    # ---------- 4. 合同条款 ----------
    sections["contract"] = {
        "title": "合同主要条款",
        "blocks": [
            {"type": "table",
             "head": ["条款", "内容"],
             "rows": [
                 ["合同类型", parameters.get("contract_type", "货物采购合同")],
                 ["付款条款", terms.get("payment", "验收合格后30日内付款")],
                 ["交付条款", "供应商应在" + delivery + "内完成供货、安装调试和资料移交"],
                 ["验收条款", terms.get("acceptance", "按技术规格书组织验收")],
                 ["质保条款", config.get("warranty", "按合同约定提供质保及售后服务")],
                 ["争议解决", terms.get("dispute", "协商不成可依法向有管辖权的人民法院提起诉讼")],
             ]},
            {"type": "p", "text": "提示：合同条款应由采购、法务和业务负责人结合项目所在地规定复核后签署。"},
        ],
    }

    # ---------- 5. 评审标准 ----------
    sections["evaluation"] = {
        "title": "评审标准",
        "blocks": [
            {"type": "table",
             "head": ["评分项", "分值", "评分说明"],
             "rows": [
                 ["价格分", "30", "以满足要求的最低报价为基准价计算"],
                 ["技术响应", "40", "技术参数逐项响应，优于要求的适当加分"],
                 ["服务能力", "20", "交付计划、售后响应、培训方案的完整性"],
                 ["履约经验", "10", "同类项目业绩和用户评价"],
             ]},
            {"type": "p", "text": "合计 100 分，得分最高者为中标候选人。"},
        ],
    }

    return sections


def set_run_font(run, size: float = 10.5, bold: bool = False) -> None:
    """统一设置中文字体，避免 Word 里显示成别的字体"""
    run.font.name = "宋体"
    run.font.size = Pt(size)
    run.bold = bold
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")


def build_docx_bytes(title: str, sections: dict) -> bytes:
    """把章节内容拼成一个 Word 文件，返回二进制内容"""
    document = Document()

    # 页边距
    for section in document.sections:
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

    # 大标题
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(title)
    set_run_font(run, size=18, bold=True)

    # 遍历每个章节
    for key in ("techSpec", "announcement", "bid", "contract", "evaluation"):
        part = sections.get(key)
        if not part:
            continue

        heading = document.add_paragraph()
        run = heading.add_run(part.get("title", key))
        set_run_font(run, size=14, bold=True)

        for block in part.get("blocks", []):
            block_type = block.get("type", "p")

            if block_type == "p":
                paragraph = document.add_paragraph()
                run = paragraph.add_run(block.get("text", ""))
                set_run_font(run)

            elif block_type == "list":
                for index, item in enumerate(block.get("items", []), start=1):
                    paragraph = document.add_paragraph()
                    run = paragraph.add_run(str(index) + ". " + str(item))
                    set_run_font(run)

            elif block_type == "table":
                head = block.get("head", [])
                rows = block.get("rows", [])
                if len(head) == 0:
                    continue
                table = document.add_table(rows=1, cols=len(head))
                table.style = "Table Grid"
                for index, text in enumerate(head):
                    cell = table.rows[0].cells[index]
                    cell.text = str(text)
                for row in rows:
                    cells = table.add_row().cells
                    for index, text in enumerate(row):
                        if index < len(cells):
                            cells[index].text = str(text)

        document.add_paragraph("")

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
