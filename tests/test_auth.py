# -*- coding: utf-8 -*-
"""
认证与权限测试：登录、查当前用户、未登录 401、越权 403。
作者：贾皓杰 (JHJ)
"""


async def test_admin_login(client):
    response = await client.post("/api/auth/login", json={"username": "admin", "password": "Jhj@123456"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 0
    assert len(body["data"]["token"]) > 20
    assert body["data"]["user"]["role"] == "admin"


async def test_current_user(client, headers):
    response = await client.get("/api/auth/me", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["username"] == "admin"


async def test_not_logged_in_is_401(client):
    response = await client.get("/api/records")
    assert response.status_code == 401, response.text


async def test_buyer_cannot_read_audit_logs(client):
    """buyer 只有 generate + records 权限，看后台日志应该被拒"""
    login = await client.post("/api/auth/login", json={"username": "buyer", "password": "Buyer@123"})
    assert login.status_code == 200, login.text
    buyer_token = login.json()["data"]["token"]

    response = await client.get("/api/admin/audit-logs", headers={"Authorization": "Bearer " + buyer_token})
    assert response.status_code == 403, response.text


async def test_logout_then_token_invalid(client, headers):
    """退出后旧 token 不能再用来查自己"""
    assert (await client.post("/api/auth/logout", headers=headers)).status_code == 200
    response = await client.get("/api/auth/me", headers=headers)
    assert response.status_code == 401, response.text
