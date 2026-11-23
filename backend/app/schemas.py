"""通用接口契约；模块字段由领域服务持有，不再为每个模块复制一份模型类。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None
    flow: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class ActionPayload(BaseModel):
    action: str
    remark: str | None = None
    evidence_type: str = ""
    values: dict[str, Any] = Field(default_factory=dict)
    report_id: int | None = None


class AuditDispositionPayload(BaseModel):
    """按可追证引用打开审计处置；说明采用的证据来源。"""

    report_id: int | None = None
    evidence_type: str = ""
    remark: str = ""


class MigrationPayload(BaseModel):
    """历史报告审计来源迁移入参：不传报告 id 时迁移全部报告。"""

    report_ids: list[int] = Field(default_factory=list)
    batch: str = "v2-migration"


class CorrectionPayload(BaseModel):
    """审计更正：可引用但需复查员认可后才能用于结案。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class ReviewPayload(BaseModel):
    """复查提交：结案或发回补证，处置必须写明证据来源类型。"""

    action: str
    evidence_type: str = ""
    remark: str = ""
