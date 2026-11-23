"""治理审计服务：审计记录按可追证报告引用打开实际处置。

审计记录保留原始索引号和审计条目号；是否能打开处置由第二版报告引用
的可确证状态决定，待核引用不得直接进入实际处置。
"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService
from app.services import traceability


class GovernAuditService(BaseModuleService):
    MODULE = "govern_audit"
    ENTITY = "审计记录"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["记录编号", "审计条目号", "原始索引号", "审计对象", "审计类型", "检查结果", "问题项", "整改方案", "审计时间", "整改状态"]
    REQUIRED_FIELDS = ["记录编号", "审计对象", "审计类型"]
    STATUS_ORDER = ["待审计", "审计中", "已通过", "整改中"]
    ACTION_RULES = {"发起审计": "审计中", "确认通过": "已通过", "指派整改": "整改中"}
    NEGATIVE_ACTIONS = []

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return traceability.audit_detail(entry_id)

    def run_action(
        self, entry_id: int, action: str, **payload: Any
    ) -> tuple[dict[str, Any] | None, str]:
        if action in {"打开审计处置", "审计处置", "按引用打开处置"}:
            report_id = payload.get("report_id")
            result = traceability.open_audit_disposition(
                entry_id,
                report_id=int(report_id) if report_id else None,
                remark=str(payload.get("remark") or ""),
            )
            entry = traceability.audit_detail(entry_id)
            return (entry, str(result.get("message"))) if result.get("ok") else (None, str(result.get("message")))
        return super().run_action(entry_id, action)
