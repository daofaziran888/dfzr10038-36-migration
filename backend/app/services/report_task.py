"""特征报告服务：在通用状态流转之上接入第二版可追证报告引用。

新版报告详情必须能回查实际采用的审计条目号和原始索引号；历史报告仍保留
原文与原始索引定位信息。状态流转仍只在本服务内完成。
"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService
from app.services import traceability


class ReportTaskService(BaseModuleService):
    MODULE = "report_task"
    ENTITY = "分析报表"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["报告编号", "报告类型", "特征范围", "统计周期", "图表配置", "输出格式", "分发列表", "最近生成"]
    REQUIRED_FIELDS = ["报告编号", "报告类型", "特征范围"]
    STATUS_ORDER = ["草稿", "生成中", "已生成", "生成失败"]
    ACTION_RULES = {"启动生成": "生成中", "中止生成": "已生成", "标记失败": "生成失败"}
    NEGATIVE_ACTIONS = []

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        """报告详情：附上迁移后的报告引用、审计条目和原始索引号。"""
        detail = traceability.report_detail(entry_id)
        if detail is None:
            return None
        return detail

    def run_action(
        self, entry_id: int, action: str, **payload: Any
    ) -> tuple[dict[str, Any] | None, str]:
        if action in traceability.CLOSE_ACTIONS or action in traceability.RETURN_ACTIONS:
            evidence_type = str(payload.get("evidence_type") or "").strip()
            remark = str(payload.get("remark") or "").strip()
            result = traceability.submit_review(
                entry_id, action=action, evidence_type=evidence_type, remark=remark,
            )
            entry = traceability.report_detail(entry_id)
            if not result.get("ok"):
                return None, str(result.get("message"))
            return entry, str(result.get("message"))
        if action == "补交审计更正":
            values = dict(payload.get("values") or {})
            if payload.get("remark") and not values.get("说明"):
                values["说明"] = payload["remark"]
            result = traceability.add_correction(entry_id, values)
            if not result.get("ok"):
                return None, str(result.get("message"))
            return traceability.report_detail(entry_id), str(result.get("message"))
        if action == "迁移审计来源":
            result = traceability.migrate_report(entry_id)
            if not result.get("ok"):
                return None, str(result.get("message"))
            return traceability.report_detail(entry_id), str(result.get("message"))
        return super().run_action(entry_id, action)
