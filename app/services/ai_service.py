# -*- coding: utf-8 -*-
"""
调用大模型（OpenAI 兼容协议）的小封装。

关键点：
1. 没配 AI_API_KEY 就直接返回 None，上层自动改用本地规则 —— 保证没网也能跑
2. 任何异常都返回 None，不让模型故障拖垮接口
3. 模型爱把 JSON 包在 ```json 里，read_json 负责把它洗干净

作者：贾皓杰 (JHJ)
"""
import json
import logging

import httpx

from .. import config

logger = logging.getLogger("procurement.ai")


async def call_ai(system_prompt: str, user_prompt: str) -> str | None:
    """调用大模型，返回文字内容；失败返回 None"""
    if config.AI_API_KEY == "":
        logger.info("没有配置 AI_API_KEY，使用本地规则")
        return None

    url = config.AI_BASE_URL + "/chat/completions"
    headers = {
        "Authorization": "Bearer " + config.AI_API_KEY,
        "Content-Type": "application/json",
    }
    body = {
        "model": config.AI_MODEL,
        "temperature": 0.1,          # 越小越稳定，抽取任务要稳定
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    # DeepSeek 默认开着「思考模式」：token 会先花在 reasoning_content 上，
    # 结果 content 可能是空字符串、耗时变长、费用更高。抽取任务不需要思考，显式关掉。
    if "deepseek" in config.AI_BASE_URL:
        body["thinking"] = {"type": "disabled"}

    try:
        async with httpx.AsyncClient(timeout=config.AI_TIMEOUT_SECONDS) as client:
            response = await client.post(url, headers=headers, json=body)
            if response.status_code != 200:
                logger.warning("大模型接口异常 status=%s body=%s",
                               response.status_code, response.text[:200])
                return None
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as error:
        logger.warning("调用大模型失败：%s", error)
        return None


def read_json(text: str | None) -> dict | None:
    """把模型返回的文字转成字典，失败返回 None"""
    if not text:
        return None

    cleaned = text.strip()
    # 去掉 markdown 代码围栏
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()

    # 只取第一个 { 到最后一个 } 之间的内容
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        return None
    cleaned = cleaned[start:end + 1]

    try:
        data = json.loads(cleaned)
    except Exception:
        logger.warning("模型返回的不是合法 JSON：%s", cleaned[:200])
        return None

    if isinstance(data, dict):
        return data
    return None
