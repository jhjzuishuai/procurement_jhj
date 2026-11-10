# -*- coding: utf-8 -*-
"""
需求解析 + 风险预审。

解析策略：
    先用正则从文字里捞固定格式的东西（预算、数量、交付期、CPU、内存、质保……）
    再让大模型补全正则捞不到的
    最后统一整理成一份标准参数字典

作者：贾皓杰 (JHJ)
"""
import logging
import re

from .ai_service import call_ai, read_json

logger = logging.getLogger("procurement.parse")

# 中文标点，用来切句子
SPLIT_CHARS = "。；;，,、\n\r"


def split_sentences(text: str) -> list[str]:
    """把一段话切成一句一句的"""
    text = text or ""
    for ch in SPLIT_CHARS:
        text = text.replace(ch, "|")
    return [item.strip() for item in text.split("|") if item.strip()]


def first_match(text: str, patterns: list[str]) -> str:
    """按顺序试多个正则，返回第一个匹配到的内容"""
    for pattern in patterns:
        result = re.search(pattern, text or "")
        if result:
            return result.group(0).strip()
    return ""


def find_budget(text: str) -> float:
    """从文字里找预算金额"""
    result = re.search(r"预算[^0-9]{0,6}([0-9]+(?:\.[0-9]+)?)\s*(万元|万|元)", text or "")
    if result is None:
        return 0
    number = float(result.group(1))
    unit = result.group(2)
    if unit in ("万元", "万"):
        return number * 10000
    return number


def find_quantity(text: str) -> str:
    """找采购数量，例如 100台"""
    result = re.search(r"([0-9]+)\s*(台|套|个|件|批|台套)", text or "")
    if result:
        return result.group(0)
    return ""


def find_delivery(text: str) -> str:
    """找交付周期，例如 45天"""
    result = re.search(r"([0-9]+)\s*(个工作日|工作日|天|日|周|个月)", text or "")
    if result:
        return result.group(0)
    return ""


def guess_category(categories: list[dict], text: str, selected_code: str) -> dict | None:
    """
    判断这是哪一类采购。
    先看用户选没选，再按关键词命中数量打分。
    """
    if selected_code:
        for item in categories:
            if item["code"] == selected_code:
                return item

    best = None
    best_score = 0
    for item in categories:
        score = 0
        for keyword in item["keywords_json"]:
            if keyword and keyword in text:
                score += 1
        if score > best_score:
            best_score = score
            best = item

    if best is None and categories:
        return categories[0]
    return best


def rule_parse(requirement: dict, categories: list[dict]) -> dict:
    """
    纯正则解析，不依赖大模型。
    大模型挂了、断网了、没配 key，都靠它兜底。
    """
    content = requirement.get("content", "")
    title = requirement.get("title", "")

    category = guess_category(categories, title + content, requirement.get("category_code", "") or "")

    budget = requirement.get("budget") or 0
    if budget == 0:
        budget = find_budget(content)

    delivery = requirement.get("delivery", "") or find_delivery(content)
    quantity = find_quantity(content)

    configuration = {
        "cpu": first_match(content, [r"CPU[^。；，]*", r"处理器[^。；，]*"]),
        "memory": first_match(content, [r"内存[^。；，]*"]),
        "storage": first_match(content, [r"硬盘[^。；，]*", r"存储[^。；，]*", r"SSD[^。；，]*"]),
        "network": first_match(content, [r"网卡[^。；，]*", r"网络[^。；，]*"]),
        "warranty": first_match(content, [r"质保[^。；，]*", r"保修[^。；，]*"]),
    }

    # 技术要求：把正文里比较长的句子拿过来（预算、合同这类商务条款不算技术要求）
    sentences = split_sentences(content)
    technical = []
    for item in sentences:
        if len(item) < 6:
            continue
        if "预算" in item or "合同签订" in item or "万元" in item:
            continue
        technical.append(item)
    technical = technical[:8]
    if len(technical) == 0:
        technical = ["应满足采购人提出的功能、性能、安全和稳定性要求。"]

    # 服务要求：默认给几条通用的
    service = ["供应商应提供交付计划、安装调试、验收配合和售后响应服务。"]
    if "培训" in content:
        service.append("供应商应提供操作培训和资料移交。")
    if "运维" in content or "质保" in content:
        service.append("供应商应在质保期内提供远程或上门技术支持。")

    # 资质要求：用户填了就按标点拆开，没填给默认
    qualification_text = requirement.get("supplier", "")
    if qualification_text:
        qualification = [item.strip() for item in re.split(r"[、，；;]", qualification_text) if item.strip()]
    else:
        qualification = ["具备合法营业执照", "具备同类项目供货经验", "具备履约能力"]

    return {
        "title": title,
        "content": content,
        "budget": budget,
        "quantity": quantity,
        "delivery": delivery,
        "supplier": qualification_text,
        "category_code": category["code"] if category else "",
        "category_name": category["name"] if category else "",
        "contract_type": category["contract_type"] if category else "货物采购合同",
        "contract_terms": category["contract_terms_json"] if category else {},
        "configuration": configuration,
        "technical_requirements": technical,
        "service_requirements": service,
        "qualification_requirements": qualification,
        "evaluation_method": "综合评分法",
    }


def fill_empty(base: dict, extra: dict) -> dict:
    """
    用大模型的结果补正则没捞到的字段（正则优先，模型补充）。
    """
    for key in ("quantity", "delivery", "supplier", "category_name", "evaluation_method"):
        if base.get(key, "") == "" and extra.get(key):
            base[key] = extra[key]

    if base.get("budget", 0) == 0 and extra.get("budget"):
        try:
            base["budget"] = float(extra["budget"])
        except Exception:
            pass

    config_extra = extra.get("configuration", {}) or {}
    for key in ("cpu", "memory", "storage", "network", "warranty"):
        if base["configuration"].get(key, "") == "" and config_extra.get(key):
            base["configuration"][key] = config_extra[key]

    for key in ("technical_requirements", "service_requirements", "qualification_requirements"):
        if len(base.get(key, [])) == 0 and isinstance(extra.get(key), list):
            base[key] = extra[key]

    return base


async def parse_requirement(requirement: dict, categories: list[dict]) -> dict:
    """
    对外只暴露这一个函数：输入原始需求，输出标准参数。
    返回值里带 parser 字段，说明这次是 local-rule 还是 ai。
    """
    parameters = rule_parse(requirement, categories)

    system_prompt = (
        "你是政府采购需求结构化解析助手。只输出严格 JSON，不要任何解释文字。\n"
        "JSON 字段：budget(数字，单位元)、quantity(文字)、delivery(文字)、"
        "supplier(文字)、category_code(server/office-device/software-service)、"
        "configuration(cpu/memory/storage/network/warranty 均为文字)、"
        "technical_requirements(字符串数组)、service_requirements(字符串数组)、"
        "qualification_requirements(字符串数组)、evaluation_method(文字)"
    )
    user_prompt = (
        "需求标题：" + requirement.get("title", "") + "\n"
        "需求正文：" + requirement.get("content", "") + "\n"
        "用户填的预算：" + str(requirement.get("budget", 0)) + "\n"
        "用户填的交付周期：" + requirement.get("delivery", "") + "\n"
        "用户填的资质要求：" + requirement.get("supplier", "")
    )

    text = await call_ai(system_prompt, user_prompt)
    parsed = read_json(text)

    if parsed is None:
        parameters["parser"] = "local-rule"
        return parameters

    parameters = fill_empty(parameters, parsed)
    parameters["parser"] = "ai"
    return parameters


# ============================================================
#  风险预审（本地规则）
# ============================================================

def check_risks(requirement: dict, parameters: dict) -> list[dict]:
    """用规则挑毛病，返回风险列表"""
    risks = []

    def add(level: str, title: str, description: str, suggestion: str, section: str):
        risks.append({
            "type": "RULE_CHECK",
            "level": level,
            "title": title,
            "description": description,
            "suggestion": suggestion,
            "section": section,
        })

    # 1. 预算
    if parameters.get("budget", 0) <= 0:
        add("HIGH", "缺少预算金额",
            "需求里没有明确预算金额，无法判断采购是否可行。",
            "请补充预算金额，或说明资金来源。", "预算参数")

    # 2. 预算和数量的匹配度（简单算一下单价）
    budget = parameters.get("budget", 0)
    quantity_text = parameters.get("quantity", "")
    quantity = 0
    nums = re.findall(r"[0-9]+", quantity_text or "")
    if nums:
        quantity = int(nums[0])

    if budget > 0 and quantity > 0:
        unit_price = budget / quantity
        if unit_price < 3000:
            add("MEDIUM", "预算单价可能偏低",
                "按预算除以数量算，单价约 " + str(round(unit_price, 2)) + " 元，可能低于市场价。",
                "建议核对市场价格，或调整技术要求和数量。", "预算参数")

    # 3. 交付周期
    if not parameters.get("delivery"):
        add("MEDIUM", "缺少交付周期",
            "没有约定交付时间，容易产生履约争议。",
            "建议明确交付期限，例如“合同签订后45天内”。", "交付条款")

    # 4. 资质要求
    if len(parameters.get("qualification_requirements", [])) < 2:
        add("MEDIUM", "供应商资质要求不完整",
            "资质要求过少，可能无法有效筛选供应商。",
            "建议补充营业执照、同类项目经验、履约能力等要求。", "资格条款")

    # 5. 技术要求
    if len(parameters.get("technical_requirements", [])) < 2:
        add("MEDIUM", "技术参数过于笼统",
            "技术规格书内容太少，验收时缺少依据。",
            "建议按品类补充关键性能参数。", "技术规格")

    # 6. 正文太短
    if len(requirement.get("content", "")) < 30:
        add("LOW", "需求描述过于简略",
            "需求正文较短，解析结果可能不准确。",
            "建议补充使用场景、数量、性能要求等信息。", "整体文件")

    if len(risks) == 0:
        add("LOW", "未发现明显高风险项",
            "规则检查未发现问题，仍建议人工复核。",
            "建议由采购、法务和业务负责人共同复核。", "整体文件")

    return risks


async def ai_review_risks(parameters: dict) -> list[dict] | None:
    """让大模型再看一遍，失败返回 None"""
    system_prompt = (
        "你是政府采购文件风险审查员。只输出严格 JSON 数组，不要解释。\n"
        "每个元素字段：level(HIGH/MEDIUM/LOW)、title、description、suggestion、section"
    )
    user_prompt = (
        "采购品类：" + parameters.get("category_name", "") + "\n"
        "预算：" + str(parameters.get("budget", 0)) + "\n"
        "数量：" + parameters.get("quantity", "") + "\n"
        "交付周期：" + parameters.get("delivery", "") + "\n"
        "技术要求：" + "；".join(parameters.get("technical_requirements", [])) + "\n"
        "资质要求：" + "；".join(parameters.get("qualification_requirements", []))
    )

    text = await call_ai(system_prompt, user_prompt)
    if not text:
        return None

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1:
        return None

    import json
    try:
        data = json.loads(cleaned[start:end + 1])
    except Exception:
        return None

    if not isinstance(data, list):
        return None

    risks = []
    for item in data:
        if not isinstance(item, dict):
            continue
        risks.append({
            "type": "AI_REVIEW",
            "level": str(item.get("level", "LOW")).upper(),
            "title": str(item.get("title", "模型提示风险")),
            "description": str(item.get("description", "")),
            "suggestion": str(item.get("suggestion", "")),
            "section": str(item.get("section", "整体文件")),
        })
    return risks if len(risks) > 0 else None
