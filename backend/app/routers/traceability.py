"""可追证报告引用（第二版）接口：迁移、更正、复查和治理审计处置。

这些路由必须比通用 `/{module}/{entry_id}` 更早注册，否则固定后缀会被
动态路径抢先匹配。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.schemas import AuditDispositionPayload, CorrectionPayload, MigrationPayload, ReviewPayload
from app.services import traceability
from app.services.traceability import REFERENCE_TABLE, _snapshot

router = APIRouter(prefix="/api/trace", tags=["可追证报告引用"])


@router.get("/references")
def list_references() -> dict[str, Any]:
    """列出全部第二版报告引用，按报告 id 独立，同名报告不合并。"""
    rows = [_snapshot(row) for row in traceability.store.aux_rows(REFERENCE_TABLE)]
    return {"items": rows, "total": len(rows)}


@router.post("/migrate")
def migrate(payload: MigrationPayload) -> dict[str, Any]:
    """把历史目录报告的审计来源迁移为第二版可追证引用。"""
    if not payload.report_ids:
        return traceability.migrate_historical_reports(batch=payload.batch)
    results = [traceability.migrate_report(report_id, batch=payload.batch) for report_id in payload.report_ids]
    return {
        "ok": all(result.get("ok") for result in results),
        "message": "；".join(str(result.get("message")) for result in results),
        "results": results,
    }


@router.get("/reports/{report_id}")
def report_detail(report_id: int) -> dict[str, Any]:
    detail = traceability.report_detail(report_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"分析报表 {report_id} 不存在")
    return detail


@router.get("/reports/{report_id}/reference")
def report_reference(report_id: int) -> dict[str, Any]:
    detail = traceability.reference_detail(report_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"分析报表 {report_id} 不存在")
    return detail


@router.post("/reports/{report_id}/corrections")
def add_correction(report_id: int, payload: CorrectionPayload) -> dict[str, Any]:
    values = dict(payload.values)
    if payload.remark and not values.get("说明"):
        values["说明"] = payload.remark
    result = traceability.add_correction(report_id, values)
    if not result.get("ok") and "不存在" in str(result.get("message", "")):
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@router.post("/reports/{report_id}/review")
def submit_review(report_id: int, payload: ReviewPayload) -> dict[str, Any]:
    result = traceability.submit_review(
        report_id,
        action=payload.action,
        evidence_type=payload.evidence_type,
        remark=payload.remark,
    )
    if not result.get("ok") and "不存在" in str(result.get("message", "")):
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@router.get("/audits/{audit_id}")
def audit_detail(audit_id: int) -> dict[str, Any]:
    detail = traceability.audit_detail(audit_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"审计记录 {audit_id} 不存在")
    return detail


@router.post("/audits/{audit_id}/dispositions")
def open_audit_disposition(
    audit_id: int,
    payload: AuditDispositionPayload | None = None,
) -> dict[str, Any]:
    payload = payload or AuditDispositionPayload()
    result = traceability.open_audit_disposition(
        audit_id,
        report_id=payload.report_id,
        evidence_type=payload.evidence_type,
        remark=payload.remark,
    )
    if not result.get("ok") and "不存在" in str(result.get("message", "")):
        raise HTTPException(status_code=404, detail=result["message"])
    return result

