# -*- coding: utf-8 -*-
"""
密码与登录凭证处理，只用 Python 标准库（hashlib + secrets），不引入额外依赖。

作者：贾皓杰 (JHJ)
"""
import hashlib
import secrets
from datetime import datetime, timedelta

from . import config

# 密码加密迭代次数（越大越安全，也越慢，10 万次约几十毫秒，够用）
PBKDF2_ITERATIONS = 100000


def hash_password(password: str) -> str:
    """
    把明文密码变成 "盐$摘要"。
    每次加密都随机生成盐，所以同一个密码两次加密结果不一样。
    """
    salt = secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return salt + "$" + digest


def check_password(password: str, saved: str) -> bool:
    """校验密码对不对"""
    if not saved or "$" not in saved:
        return False
    salt, digest = saved.split("$", 1)
    new_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    # 用 compare_digest 比较，防止时间攻击
    return secrets.compare_digest(new_digest, digest)


def new_token() -> str:
    """随机生成登录 token（48 位十六进制）"""
    return secrets.token_hex(24)


def token_expire_time() -> datetime:
    """token 什么时候过期"""
    return datetime.now() + timedelta(minutes=config.TOKEN_EXPIRE_MINUTES)
