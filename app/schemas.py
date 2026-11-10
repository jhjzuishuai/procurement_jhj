# -*- coding: utf-8 -*-
"""
请求参数模型（Pydantic），负责校验前端传进来的 JSON。

作者：贾皓杰 (JHJ)
"""
from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, description="登录名")
    password: str = Field(..., min_length=6, max_length=32, description="密码")
    display_name: str = Field(default="", description="显示名称")


class LoginIn(BaseModel):
    username: str = Field(..., description="登录名")
    password: str = Field(..., description="密码")


class RequirementIn(BaseModel):
    """用户填的采购需求"""
    title: str = Field(..., description="项目名称，例如：服务器采购项目")
    content: str = Field(..., description="需求正文，随便写，系统会自动解析")
    budget: float = Field(default=0, description="预算金额（元），不知道可以填 0")
    delivery: str = Field(default="", description="交付周期，例如：45天")
    supplier: str = Field(default="", description="供应商资质要求")
    category_code: str = Field(default="", description="品类编码，不填就自动判断")


class AdjustIn(BaseModel):
    """调整某一个章节"""
    section: str = Field(..., description="章节名：techSpec/announcement/bid/contract/evaluation")
    content: str = Field(..., description="新的章节正文")


class BlockEditIn(BaseModel):
    """
    块级编辑：只动某一章节里的「某一块」，其余块原样保留。
    章节结构：{"title": "技术规格书", "blocks": [{"type": "p", "text": "..."}, ...]}
    """
    section: str = Field(..., description="章节名：techSpec/announcement/bid/contract/evaluation")
    index: int = Field(..., ge=0, description="块下标，从 0 开始；insert 时表示插到第几个位置")
    action: str = Field(default="replace", description="replace 替换 / insert 插入 / delete 删除")
    block: dict | None = Field(default=None, description="新的块内容，delete 时不用传")
