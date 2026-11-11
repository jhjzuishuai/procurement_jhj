# -*- coding: utf-8 -*-
"""
前端与静态资源测试。

作者：贾皓杰 (JHJ)

为什么单独测这一块：静态文件是最容易"改了没人发现"的地方——
首页 200 但 CSS/JS 404，浏览器就是白屏，接口测试一条都发现不了。
"""
import re


async def test_home_page(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "采购技术规格书" in response.text


async def test_static_assets_reachable(client):
    """首页里写的每个 /static/... 地址都必须真能取到"""
    page = (await client.get("/")).text
    refs = re.findall(r'(?:href|src)="(/static[^"]+)"', page)

    assert len(refs) >= 3, "首页引用的静态资源少于 3 个：" + str(refs)
    for ref in refs:
        response = await client.get(ref)
        assert response.status_code == 200, ref + " -> " + str(response.status_code)


async def test_api_docs_available(client):
    """Swagger 文档页要能打开（面试时会用它演示）"""
    response = await client.get("/docs")
    assert response.status_code == 200
