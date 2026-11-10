# -*- coding: utf-8 -*-
"""
数据库表结构（一共 5 张表）。

1. sys_user          用户
2. user_session      登录凭证（token 存库，重启不丢）
3. purchase_category 采购品类（含默认合同条款）
4. procurement_record 生成记录（需求、参数、文档、风险、版本都用 JSON 存）
5. audit_log         审计日志

作者：贾皓杰 (JHJ)
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有表都继承它"""
    pass


class User(Base):
    __tablename__ = "sys_user"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, comment="登录名")
    display_name: Mapped[str] = mapped_column(String(64), default="", comment="显示名称")
    role: Mapped[str] = mapped_column(String(32), default="buyer", comment="角色：admin/buyer/expert")
    password_hash: Mapped[str] = mapped_column(String(128), comment="密码摘要")
    failed_times: Mapped[int] = mapped_column(Integer, default=0, comment="连续密码错误次数")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None, comment="锁定到什么时候")
    create_time: Mapped[datetime] = mapped_column(DateTime, insert_default=func.now(), comment="创建时间")


class UserSession(Base):
    __tablename__ = "user_session"

    token: Mapped[str] = mapped_column(String(64), primary_key=True, comment="登录凭证")
    username: Mapped[str] = mapped_column(String(64), comment="属于谁")
    expire_at: Mapped[datetime] = mapped_column(DateTime, comment="过期时间")
    create_time: Mapped[datetime] = mapped_column(DateTime, insert_default=func.now())


class Category(Base):
    __tablename__ = "purchase_category"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, comment="品类编码，如 server")
    name: Mapped[str] = mapped_column(String(128), comment="品类名称")
    keywords_json: Mapped[list] = mapped_column(JSON, default=list, comment="用于自动识别品类的关键词")
    contract_type: Mapped[str] = mapped_column(String(64), default="货物采购合同")
    contract_terms_json: Mapped[dict] = mapped_column(JSON, default=dict, comment="默认合同条款")
    template_file: Mapped[str] = mapped_column(String(255), default="", comment="模板文件名，可为空")
    template_placeholders_json: Mapped[list] = mapped_column(JSON, default=list, comment="模板里的占位符")
    create_time: Mapped[datetime] = mapped_column(DateTime, insert_default=func.now())


class Record(Base):
    __tablename__ = "procurement_record"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    generation_no: Mapped[str] = mapped_column(String(32), unique=True, comment="生成编号")
    title: Mapped[str] = mapped_column(String(255), default="", comment="项目名称")

    requirement_json: Mapped[dict] = mapped_column(JSON, default=dict, comment="用户填的原始需求")
    parameters_json: Mapped[dict] = mapped_column(JSON, default=dict, comment="结构化后的参数")
    sections_json: Mapped[dict] = mapped_column(JSON, default=dict, comment="生成的文档各章节")
    risks_json: Mapped[list] = mapped_column(JSON, default=list, comment="风险预审结果")
    versions_json: Mapped[list] = mapped_column(JSON, default=list, comment="修改版本历史")

    status: Mapped[str] = mapped_column(String(32), default="SUCCESS")
    parser: Mapped[str] = mapped_column(String(32), default="local-rule", comment="用了大模型还是本地规则")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None, comment="重新生成时指向上一条")
    create_time: Mapped[datetime] = mapped_column(DateTime, insert_default=func.now())
    update_time: Mapped[datetime] = mapped_column(DateTime, insert_default=func.now(), onupdate=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(32), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, insert_default=func.now())
