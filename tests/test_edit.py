# -*- coding: utf-8 -*-
"""
章节编辑测试：整章调整、版本、回滚、块级编辑（改/插/删 + 非法输入）。

作者：贾皓杰 (JHJ)

这一组测试专门守住一个真实踩过的坑：
块级编辑曾经"返回 200 但数据没落库"——原因是原地改 JSON 列，SQLAlchemy 没检测到变化。
所以 test_block_replace_persisted 会在改完之后“再发一次请求读库”，而不是只看返回体。
"""
import pytest


async def test_adjust_section(client, headers, record):
    """整章替换：把投标章节换成一段文字，并留一条版本"""
    payload = {"section": "bid", "content": "本项目的采购背景由业务部门提出，现按流程组织采购。"}
    response = await client.post("/api/records/" + str(record["id"]) + "/adjust", json=payload, headers=headers)
    assert response.status_code == 200, response.text

    versions = await client.get("/api/records/" + str(record["id"]) + "/versions", headers=headers)
    assert versions.status_code == 200
    assert len(versions.json()["data"]) == 1
    assert versions.json()["data"][0]["section"] == "bid"


async def test_restore_version(client, headers, record):
    """回滚：把调整前的那一版塞回去"""
    payload = {"section": "bid", "content": "临时改一句，用来造出一个版本。"}
    await client.post("/api/records/" + str(record["id"]) + "/adjust", json=payload, headers=headers)

    response = await client.post("/api/records/" + str(record["id"]) + "/versions/0/restore", headers=headers)
    assert response.status_code == 200, response.text


async def test_block_replace_persisted(client, headers, record):
    """替换第 0 块，并且换一个新请求读库确认真的落盘了"""
    new_text = "这段是块级编辑改出来的内容，中文必须原样回读。"

    payload = {"section": "techSpec", "index": 0, "action": "replace",
               "block": {"type": "p", "text": new_text}}
    response = await client.patch("/api/records/" + str(record["id"]) + "/document",
                                  json=payload, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["sections"]["techSpec"]["blocks"][0]["text"] == new_text

    # ★ 关键断言：另起一次请求从数据库读，防"返回 200 但没写库"
    detail = await client.get("/api/records/" + str(record["id"]), headers=headers)
    assert detail.json()["data"]["sections"]["techSpec"]["blocks"][0]["text"] == new_text


async def test_block_insert(client, headers, record):
    """插到末尾：index = 现有块数（插入允许等于长度，替换/删除不允许）"""
    detail = await client.get("/api/records/" + str(record["id"]), headers=headers)
    before = len(detail.json()["data"]["sections"]["techSpec"]["blocks"])

    payload = {"section": "techSpec", "index": before, "action": "insert",
               "block": {"type": "p", "text": "这是插进来的新段落。"}}
    response = await client.patch("/api/records/" + str(record["id"]) + "/document",
                                  json=payload, headers=headers)
    assert response.status_code == 200, response.text
    assert len(response.json()["data"]["sections"]["techSpec"]["blocks"]) == before + 1


async def test_block_delete(client, headers, record):
    detail = await client.get("/api/records/" + str(record["id"]), headers=headers)
    before = len(detail.json()["data"]["sections"]["techSpec"]["blocks"])

    payload = {"section": "techSpec", "index": 0, "action": "delete"}
    response = await client.patch("/api/records/" + str(record["id"]) + "/document",
                                  json=payload, headers=headers)
    assert response.status_code == 200, response.text
    assert len(response.json()["data"]["sections"]["techSpec"]["blocks"]) == before - 1


@pytest.mark.parametrize("payload,reason", [
    ({"section": "techSpec", "index": 999, "action": "replace",
      "block": {"type": "p", "text": "越界"}}, "下标越界"),
    ({"section": "techSpec", "index": 0, "action": "replace",
      "block": {"type": "p", "text": "   "}}, "空段落"),
    ({"section": "不存在的章节", "index": 0, "action": "replace",
      "block": {"type": "p", "text": "x"}}, "章节名不存在"),
    ({"section": "techSpec", "index": 0, "action": "replace",
      "block": {"type": "unknown", "text": "x"}}, "块类型非法"),
    ({"section": "techSpec", "index": 0, "action": "replace",
      "block": {"type": "table", "rows": [["a", "b"], ["c"]]}}, "表格每行列数不一致"),
])
async def test_block_edit_rejected(client, headers, record, payload, reason):
    response = await client.patch("/api/records/" + str(record["id"]) + "/document",
                                  json=payload, headers=headers)
    assert response.status_code == 400, reason + "：期望 400，实际 " + str(response.status_code) + " " + response.text


async def test_review_risks_again(client, headers, record):
    response = await client.post("/api/records/" + str(record["id"]) + "/review-risks", headers=headers)
    assert response.status_code == 200, response.text
    assert len(response.json()["data"]["risks"]) >= 1
