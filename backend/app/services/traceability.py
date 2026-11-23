"""可追证报告引用（第二版）：历史目录报告审计来源迁移与治理复查。

历史报告过去用「目录名称 + 触发来源」定位审计证据，同名目录可能来自不同
索引，无法唯一落到审计条目。本模块把这些定位信息迁移为按报告 id 独立的
可追证引用数据（report_reference），并承接审计更正、复查结案/发回补证和
治理审计处置。

关键约束：
- 引用永远按报告 id 建键，同名报告不会被合并。
- 只有唯一定位到索引与审计条目的引用才能确证；其余明确标为「待核」。
- 迁移与更正并发时，已确证的引用不会被覆盖，只有一个引用会被确认。
"""
from __future__ import annotations

import datetime
import threading
from typing import Any

from app.store import store

REFERENCE_TABLE = "report_reference"
CORRECTION_TABLE = "audit_correction"
DISPOSITION_TABLE = "audit_disposition"
REVIEW_TABLE = "report_review_case"

STATUS_PENDING = "待核"
STATUS_CANDIDATE = "候选已确证待签发"
STATUS_CONFIRMED = "已确证"

CLOSE_ACTIONS = {"复核结案", "提交复核结案", "结案"}
RETURN_ACTIONS = {"发回补证", "发回补充证据"}
EVIDENCE_KINDS = {"原签发材料", "后补证据"}

_MUTEX = threading.RLock()


# ---------------------------------------------------------------------------
# 基础读取
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _report(report_id: int) -> dict[str, Any] | None:
    return store.find("report_task", report_id)


def _reference_for_report(report_id: int) -> dict[str, Any] | None:
    for row in store.aux_rows(REFERENCE_TABLE):
        if int(row.get("报告id", 0)) == int(report_id):
            return row
    return None


def _corrections_for(reference_id: int) -> list[dict[str, Any]]:
    return [
        row for row in store.aux_rows(CORRECTION_TABLE)
        if int(row.get("引用id", 0)) == int(reference_id)
    ]


def _review_case(report_id: int) -> dict[str, Any] | None:
    for row in store.aux_rows(REVIEW_TABLE):
        if int(row.get("报告id", 0)) == int(report_id):
            return row
    return None


def _dispositions_for_report(report_id: int) -> list[dict[str, Any]]:
    return [
        row for row in store.aux_rows(DISPOSITION_TABLE)
        if int(row.get("报告id", 0)) == int(report_id)
    ]


def _audit_by_item(item_no: str) -> dict[str, Any] | None:
    if not item_no:
        return None
    for row in store.rows("govern_audit"):
        if str(row.get("审计条目号", "")) == str(item_no):
            return row
    return None


def _audits_for_index(index_no: str) -> list[dict[str, Any]]:
    if not index_no:
        return []
    return [
        row for row in store.rows("govern_audit")
        if str(row.get("原始索引号", "")) == str(index_no)
    ]


def _candidate_indexes(dir_name: str) -> list[str]:
    indexes: list[str] = []
    for row in store.rows("feat_catalog"):
        if str(row.get("目录名称", "")) == str(dir_name):
            index_no = str(row.get("索引编号", ""))
            if index_no and index_no not in indexes:
                indexes.append(index_no)
    return indexes


def _catalogs_for(indexes: list[str]) -> list[dict[str, Any]]:
    result = []
    for row in store.rows("feat_catalog"):
        if str(row.get("索引编号", "")) in indexes:
            result.append({
                "索引编号": row.get("索引编号"),
                "目录名称": row.get("目录名称"),
                "父目录": row.get("父目录"),
                "状态": row.get("status"),
                "创建时间": row.get("创建时间"),
            })
    return result


def _candidate_audit_numbers(indexes: list[str]) -> list[str]:
    numbers: list[str] = []
    for index_no in indexes:
        for row in _audits_for_index(index_no):
            item_no = str(row.get("审计条目号", ""))
            if item_no and item_no not in numbers:
                numbers.append(item_no)
    return numbers


def _legacy_locator(report: dict[str, Any]) -> dict[str, str]:
    return {
        "目录名称": str(report.get("特征范围", "")),
        "触发来源": str(report.get("迁移触发来源") or report.get("triggered_by") or ""),
    }


def _snapshot(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    snapshot = dict(row)
    for key in ("候选索引号列表", "候选审计条目号列表", "待核项", "更正id列表"):
        snapshot[key] = list(snapshot.get(key) or [])
    return snapshot


def _report_audit_numbers(report: dict[str, Any], ref: dict[str, Any] | None) -> list[str]:
    numbers: list[str] = []
    if ref:
        adopted = str(ref.get("采用审计条目号") or "")
        if adopted:
            numbers.append(adopted)
        for item in ref.get("候选审计条目号列表") or []:
            if str(item) not in numbers:
                numbers.append(str(item))
    explicit = str(report.get("审计条目号") or "")
    if explicit and explicit not in numbers:
        numbers.append(explicit)
    return numbers


def _audit_rows(numbers: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item_no in numbers:
        row = _audit_by_item(item_no)
        if row is not None and row not in rows:
            rows.append(row)
    return rows


def _adoptable_audit(index_no: str, item_no: str) -> dict[str, Any] | None:
    row = _audit_by_item(item_no)
    if row is None:
        return None
    if str(row.get("原始索引号", "")) != str(index_no):
        return None
    return row


# ---------------------------------------------------------------------------
# 迁移：目录名称 + 触发来源 → 第二版可追证引用
# ---------------------------------------------------------------------------


def _build_reference(report: dict[str, Any], *, batch: str) -> dict[str, Any]:
    """根据历史定位信息构建引用；能唯一确证时直接落到审计条目。"""
    locator = _legacy_locator(report)
    dir_name = locator["目录名称"]
    trigger = locator["触发来源"]
    indexes = _candidate_indexes(dir_name)

    # 触发来源里若带有某个候选索引号，可在同名目录之间消歧。
    hinted = [index_no for index_no in indexes if index_no and index_no in trigger]

    # 新版报告自身带审计条目号时优先使用，但仍需校验索引归属。
    explicit_item = str(report.get("审计条目号") or "")
    explicit_index = str(report.get("原始索引号") or "")

    reference: dict[str, Any] = {
        "id": store.next_aux_id(REFERENCE_TABLE),
        "报告id": int(report.get("id", 0)),
        "报告编号": str(report.get("报告编号", "")),
        "目录名称": dir_name,
        "来源定位": locator,
        "原始索引号": None,
        "候选索引号列表": list(indexes),
        "候选审计条目号列表": _candidate_audit_numbers(indexes),
        "采用审计条目号": None,
        "状态": STATUS_PENDING,
        "签发来源类型": None,
        "签发时间": None,
        "待核项": ["审计条目唯一归属"],
        "更正id列表": [],
        "revision": 1,
        "来源版本": "v2",
        "迁移批次": batch,
        "创建时间": _now(),
        "更新时间": _now(),
    }

    target_index: str | None = None
    target_audit: dict[str, Any] | None = None

    if explicit_item:
        explicit = _audit_by_item(explicit_item)
        if explicit is not None:
            target_index = explicit_index or str(explicit.get("原始索引号", ""))
            target_audit = explicit
    elif len(hinted) == 1:
        target_index = hinted[0]
        audits = _audits_for_index(target_index)
        if len(audits) == 1:
            target_audit = audits[0]

    if target_index:
        reference["原始索引号"] = target_index
        if not reference.get("候选索引号列表"):
            reference["候选索引号列表"] = [target_index]
    if target_audit is not None:
        reference["采用审计条目号"] = str(target_audit.get("审计条目号", ""))
        # 历史触发来源已指向唯一索引、且审计条目自带签发时间，视为原签发材料。
        issued_at = str(target_audit.get("签发时间", "") or "")
        if issued_at:
            reference["状态"] = STATUS_CONFIRMED
            reference["签发来源类型"] = "原签发材料"
            reference["签发时间"] = issued_at
            reference["待核项"] = []
        else:
            reference["状态"] = STATUS_CANDIDATE
            reference["待核项"] = ["签发时点"]

    if reference["状态"] == STATUS_PENDING:
        if len(indexes) > 1:
            reference["待核项"] = ["同名目录跨索引，审计条目存在多个候选"]
        elif not indexes:
            reference["待核项"] = ["目录索引缺失"]
        elif len(_audits_for_index(indexes[0])) > 1:
            reference["待核项"] = ["同一索引下存在多个审计条目候选"]
    return reference


def migrate_report(report_id: int, *, batch: str = "v2-migration") -> dict[str, Any]:
    """把单个历史报告的审计来源迁移为第二版引用；已有引用不覆盖。"""
    report = _report(report_id)
    if report is None:
        return {"ok": False, "message": f"分析报表 {report_id} 不存在", "reference": None}
    with _MUTEX:
        existing = _reference_for_report(report_id)
        if existing is not None:
            # 并发第迁移/更正后只保留一份引用，后到的迁移不能改写已确认来源。
            return {
                "ok": True,
                "message": "该报告已有可追证引用，迁移跳过，未覆盖既有来源",
                "reference": _snapshot(existing),
                "skipped": True,
            }
        reference = _build_reference(report, batch=batch)
        store.aux_rows(REFERENCE_TABLE).append(reference)
        return {
            "ok": True,
            "message": f"已迁移报告 {report.get('报告编号', report_id)} 的审计来源为第二版引用",
            "reference": _snapshot(reference),
            "skipped": False,
        }


def migrate_historical_reports(*, batch: str = "v2-migration") -> dict[str, Any]:
    """批量迁移：历史目录报告与已带审计条目号的新报告都建立引用。

    迁移按报告 id 逐个建键，同名目录不会被合并；已有引用一律跳过，
    保证转换与更正并发时只保留一份有确切来源的引用。
    """
    migrated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for report in store.rows("report_task"):
        result = migrate_report(int(report.get("id", 0)), batch=batch)
        item = {
            "报告id": int(report.get("id", 0)),
            "报告编号": report.get("报告编号"),
            "来源版本": report.get("来源版本", "legacy"),
            "reference": result.get("reference"),
        }
        if result.get("skipped"):
            skipped.append(item)
        else:
            migrated.append(item)
    return {
        "ok": True,
        "message": f"迁移完成：新迁移 {len(migrated)} 份，跳过已有引用 {len(skipped)} 份",
        "migrated": migrated,
        "skipped": skipped,
    }


# ---------------------------------------------------------------------------
# 审计更正
# ---------------------------------------------------------------------------


def add_correction(report_id: int, values: dict[str, Any], *, actor: str = "治理复查员") -> dict[str, Any]:
    report = _report(report_id)
    if report is None:
        return {"ok": False, "message": f"分析报表 {report_id} 不存在"}

    index_no = str(values.get("原始索引号") or "").strip()
    item_no = str(values.get("审计条目号") or "").strip()
    correction_type = str(values.get("更正类型") or "").strip() or "候选归属"
    proof = str(values.get("证明力") or "").strip()
    issued_at = str(values.get("签发时间") or "").strip()
    submitter = str(values.get("提交人") or actor).strip() or actor
    note = str(values.get("说明") or "").strip()

    if not index_no:
        return {"ok": False, "message": "更正须写明原始索引号，否则无法证明候选归属"}
    if not item_no:
        return {"ok": False, "message": "更正须写明审计条目号"}

    with _MUTEX:
        reference = _reference_for_report(report_id)
        if reference is None:
            reference = _build_reference(report, batch="v2-migration")
            store.aux_rows(REFERENCE_TABLE).append(reference)

        allowed_indexes = set(reference.get("候选索引号列表") or [])
        if reference.get("原始索引号"):
            allowed_indexes.add(str(reference["原始索引号"]))
        explicit_index = str(report.get("原始索引号") or "")
        if explicit_index:
            allowed_indexes.add(explicit_index)
        if index_no not in allowed_indexes:
            return {
                "ok": False,
                "message": f"索引 {index_no} 不在该报告的候选范围内，更正不能成立",
            }

        audit = _adoptable_audit(index_no, item_no)
        if audit is None:
            return {
                "ok": False,
                "message": f"审计条目 {item_no} 不属于索引 {index_no}，更正不能成立",
            }

        # 已由原签发材料确证的引用不再接受改写：并发转换与新更正只能确认一份来源。
        if (
            reference.get("状态") == STATUS_CONFIRMED
            and reference.get("签发来源类型") == "原签发材料"
            and (
                str(reference.get("原始索引号") or "") != index_no
                or str(reference.get("采用审计条目号") or "") != item_no
            )
        ):
            return {
                "ok": False,
                "message": "该报告引用已由原签发材料确证，不能再用更正覆盖为其他索引或审计条目",
                "reference": _snapshot(reference),
            }

        proves_issuance = bool(issued_at) or "签发" in proof or correction_type == "签发时点"
        if proves_issuance and not issued_at:
            issued_at = str(audit.get("签发时间", "") or "")
        if proves_issuance and not issued_at:
            # 只声明证明签发、却没有签发时间，仍按候选归属处理并待核。
            proves_issuance = False

        correction_id = store.next_aux_id(CORRECTION_TABLE)
        correction = {
            "id": correction_id,
            "更正编号": f"CORR-{int(reference['id']):04d}-{correction_id:02d}",
            "报告id": int(report_id),
            "报告编号": report.get("报告编号"),
            "引用id": int(reference["id"]),
            "更正类型": correction_type,
            "证明力": proof or ("候选归属+签发时点" if proves_issuance else "仅候选归属"),
            "原始索引号": index_no,
            "审计条目号": item_no,
            "签发时间": issued_at or None,
            "提交人": submitter,
            "说明": note,
            "状态": "可引用",
            "是否认可": False,
            "提交时间": _now(),
        }
        store.aux_rows(CORRECTION_TABLE).append(correction)

        reference["原始索引号"] = index_no
        reference["候选索引号列表"] = [index_no]
        reference["候选审计条目号列表"] = [
            str(row.get("审计条目号", "")) for row in _audits_for_index(index_no)
            if row.get("审计条目号")
        ]
        reference["采用审计条目号"] = item_no
        reference["更正id列表"] = list(reference.get("更正id列表") or []) + [correction["id"]]
        reference["revision"] = int(reference.get("revision", 1)) + 1
        reference["更新时间"] = _now()

        if proves_issuance:
            reference["状态"] = STATUS_CONFIRMED
            reference["签发来源类型"] = "后补证据"
            reference["签发时间"] = issued_at
            reference["待核项"] = []
            message = f"审计更正 {correction['更正编号']} 已登记：候选归属与签发时点均可引用（待认可）"
        else:
            reference["状态"] = STATUS_CANDIDATE
            reference["签发来源类型"] = "后补证据（待认可）"
            reference["待核项"] = ["签发时点"]
            message = f"审计更正 {correction['更正编号']} 已登记：仅证明候选归属，签发时点仍待核"

        return {
            "ok": True,
            "message": message,
            "correction": dict(correction),
            "reference": _snapshot(reference),
        }


def _accept_corrections(reference: dict[str, Any], *, actor: str) -> list[int]:
    accepted: list[int] = []
    for correction in _corrections_for(int(reference["id"])):
        if not correction.get("是否认可"):
            correction["是否认可"] = True
            correction["状态"] = "已认可"
            correction["认可人"] = actor
            correction["认可时间"] = _now()
            accepted.append(int(correction["id"]))
    return accepted


# ---------------------------------------------------------------------------
# 复查：结案 / 发回补证
# ---------------------------------------------------------------------------


def _case_for(report: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    case = _review_case(int(report["id"]))
    if case is not None:
        return case
    case = {
        "id": store.next_aux_id(REVIEW_TABLE),
        "案件编号": f"REVC-{int(report['id']):04d}",
        "报告id": int(report["id"]),
        "报告编号": report.get("报告编号"),
        "引用id": int(reference["id"]),
        "状态": "待复核",
        "提交次数": 0,
        "处置id列表": [],
        "创建时间": _now(),
        "更新时间": _now(),
    }
    store.aux_rows(REVIEW_TABLE).append(case)
    return case


def _initiating_items(reference: dict[str, Any]) -> list[str]:
    items = list(reference.get("待核项") or [])
    return items or ["签发时点"]


def submit_review(
    report_id: int,
    *,
    action: str,
    evidence_type: str = "",
    remark: str = "",
    actor: str = "治理复查员",
) -> dict[str, Any]:
    report = _report(report_id)
    if report is None:
        return {"ok": False, "message": f"分析报表 {report_id} 不存在"}

    action = str(action or "").strip()
    evidence_type = str(evidence_type or "").strip()

    with _MUTEX:
        reference = _reference_for_report(report_id)
        if reference is None:
            return {"ok": False, "message": "该报告尚未建立可追证引用，请先执行历史审计来源迁移"}

        case = _case_for(report, reference)
        if case.get("状态") == "已结案":
            return {"ok": False, "message": f"案件 {case['案件编号']} 已结案，不能重复提交"}

        if action in RETURN_ACTIONS:
            pending = _initiating_items(reference)
            disposition = _record_disposition(
                reference=reference,
                case=case,
                kind="发回补证",
                evidence_type=evidence_type or "后补证据（待补）",
                pending=pending,
                remark=remark or "审计引用尚不能唯一确证，发回补充证据",
                actor=actor,
            )
            case["状态"] = "待补证"
            case["提交次数"] = int(case.get("提交次数", 0)) + 1
            case["更新时间"] = _now()
            return {
                "ok": True,
                "message": f"已发回补证：{('、'.join(pending)) or '审计引用'} 待补充",
                "case": dict(case),
                "disposition": dict(disposition),
                "reference": _snapshot(reference),
            }

        if action not in CLOSE_ACTIONS:
            return {"ok": False, "message": f"动作「{action}」不属于治理复查范围"}

        if reference.get("状态") == STATUS_PENDING:
            return {
                "ok": False,
                "message": (
                    "审计引用存在多个候选或缺少唯一签发来源，无法确证；"
                    "须明确待核并先发回补证，不能直接结案"
                ),
                "pending": _initiating_items(reference),
                "reference": _snapshot(reference),
            }

        if evidence_type not in EVIDENCE_KINDS:
            return {"ok": False, "message": "处置须写明采用的是「原签发材料」还是「后补证据」"}

        corrections = _corrections_for(int(reference["id"]))
        source_kind = str(reference.get("签发来源类型") or "")
        if evidence_type == "原签发材料" and "后补证据" in source_kind:
            return {"ok": False, "message": "该报告仅登记了后补证据，处置不能声明采用原签发材料"}
        if evidence_type == "后补证据" and not corrections:
            return {"ok": False, "message": "该报告未登记审计更正，没有可引用的后补证据"}

        if reference.get("状态") == STATUS_CANDIDATE:
            # 更正可引用但尚未认可：按已确认部分办理受限复核，余项继续待核。
            pending = _initiating_items(reference)
            accepted = _accept_corrections(reference, actor=actor) if evidence_type == "后补证据" else []
            disposition = _record_disposition(
                reference=reference,
                case=case,
                kind="复核结案（受限）",
                evidence_type=evidence_type,
                pending=pending,
                remark=remark or "按已确证部分办理受限复核，签发时点等余项仍待核",
                actor=actor,
                accepted=accepted,
            )
            case["状态"] = "受限结案"
            case["提交次数"] = int(case.get("提交次数", 0)) + 1
            case["更新时间"] = _now()
            return {
                "ok": True,
                "message": "已按已确认部分办理受限复核结案；"
                + (f"{'、'.join(pending)}仍待核" if pending else "签发证据仍待核"),
                "case": dict(case),
                "disposition": dict(disposition),
                "reference": _snapshot(reference),
            }

        # 已确证：可完整结案。
        accepted = _accept_corrections(reference, actor=actor) if corrections else []
        disposition = _record_disposition(
            reference=reference,
            case=case,
            kind="复核结案",
            evidence_type=evidence_type,
            pending=[],
            remark=remark or "审计引用已确证，提交复核结案",
            actor=actor,
            accepted=accepted,
        )
        case["状态"] = "已结案"
        case["提交次数"] = int(case.get("提交次数", 0)) + 1
        case["更新时间"] = _now()
        return {
            "ok": True,
            "message": "复核结案已提交，处置来源与审计条目已记录",
            "case": dict(case),
            "disposition": dict(disposition),
            "reference": _snapshot(reference),
        }


def _record_disposition(
    *,
    reference: dict[str, Any],
    case: dict[str, Any],
    kind: str,
    evidence_type: str,
    pending: list[str],
    remark: str,
    actor: str,
    accepted: list[int] | None = None,
    audit_entry_id: int | None = None,
) -> dict[str, Any]:
    disposition_id = store.next_aux_id(DISPOSITION_TABLE)
    disposition = {
        "id": disposition_id,
        "处置编号": f"DISP-{disposition_id:04d}",
        "处置类型": kind,
        "报告id": int(reference.get("报告id", 0)),
        "报告编号": reference.get("报告编号"),
        "引用id": int(reference["id"]),
        "采用审计条目号": reference.get("采用审计条目号"),
        "原始索引号": reference.get("原始索引号"),
        "采用证据类型": evidence_type,
        "待核项": list(pending),
        "已认可更正": list(accepted or []),
        "审计记录id": audit_entry_id,
        "处置人": actor,
        "处置时间": _now(),
        "说明": remark,
    }
    store.aux_rows(DISPOSITION_TABLE).append(disposition)
    case["处置id列表"] = list(case.get("处置id列表") or []) + [disposition_id]
    return disposition


# ---------------------------------------------------------------------------
# 治理审计处置
# ---------------------------------------------------------------------------


def open_audit_disposition(
    audit_id: int,
    *,
    report_id: int | None = None,
    evidence_type: str = "",
    remark: str = "",
    actor: str = "治理审计员",
) -> dict[str, Any]:
    audit = store.find("govern_audit", audit_id)
    if audit is None:
        return {"ok": False, "message": f"审计记录 {audit_id} 不存在"}

    item_no = str(audit.get("审计条目号", ""))
    if not item_no:
        return {"ok": False, "message": "该审计记录没有审计条目号，无法按可追证引用打开处置"}

    with _MUTEX:
        references = [
            row for row in store.aux_rows(REFERENCE_TABLE)
            if str(row.get("采用审计条目号", "")) == item_no
            and row.get("状态") == STATUS_CONFIRMED
            and (report_id is None or int(row.get("报告id", 0)) == int(report_id))
        ]
        if not references:
            pending_refs = [
                row for row in store.aux_rows(REFERENCE_TABLE)
                if item_no in (row.get("候选审计条目号列表") or [])
                and row.get("状态") == STATUS_PENDING
            ]
            if pending_refs:
                return {
                    "ok": False,
                    "message": "可追证报告引用仍待核：审计条目存在多个候选，不能打开实际处置",
                    "pending": [_snapshot(row) for row in pending_refs],
                }
            candidate_refs = [
                row for row in store.aux_rows(REFERENCE_TABLE)
                if item_no in (row.get("候选审计条目号列表") or [])
                and row.get("状态") == STATUS_CANDIDATE
            ]
            if candidate_refs:
                return {
                    "ok": False,
                    "message": "报告引用仅确证候选归属、签发时点仍待核，不能打开实际审计处置",
                    "pending": [_snapshot(row) for row in candidate_refs],
                }
            return {
                "ok": False,
                "message": "没有状态可确证的报告引用指向该审计条目，暂不能打开处置",
            }
        if len(references) > 1 and report_id is None:
            return {
                "ok": False,
                "message": "多个报告引用指向同一审计条目，请指定报告后再打开处置",
                "candidates": [_snapshot(row) for row in references],
            }

        reference = references[0]
        case = _review_case(int(reference.get("报告id", 0)))
        if case is None:
            case = _case_for(_report(int(reference["报告id"])) or {}, reference)
        disposition = _record_disposition(
            reference=reference,
            case=case,
            kind="审计处置",
            evidence_type=evidence_type or str(reference.get("签发来源类型") or "原签发材料"),
            pending=list(reference.get("待核项") or []),
            remark=remark or "治理审计按可追证报告引用数据打开实际审计处置",
            actor=actor,
            audit_entry_id=int(audit["id"]),
        )
        audit["整改状态"] = "审计处置中"
        audit["审计处置编号"] = disposition["处置编号"]
        audit["处置引用id"] = reference["id"]
        return {
            "ok": True,
            "message": f"已按引用 {reference['id']} 打开审计处置 {disposition['处置编号']}",
            "disposition": dict(disposition),
            "reference": _snapshot(reference),
            "audit": dict(audit),
        }


# ---------------------------------------------------------------------------
# 详情视图
# ---------------------------------------------------------------------------


def report_detail(report_id: int) -> dict[str, Any] | None:
    report = _report(report_id)
    if report is None:
        return None
    reference = _reference_for_report(report_id)
    numbers = _report_audit_numbers(report, reference)
    corrections = _corrections_for(int(reference["id"])) if reference else []
    case = _review_case(report_id)
    dispositions = _dispositions_for_report(report_id)
    detail: dict[str, Any] = dict(report)
    detail.update({
        "报告原文": report.get("报告原文"),
        "迁移触发来源": report.get("迁移触发来源") or report.get("triggered_by"),
        "历史来源定位": _legacy_locator(report),
        "候选索引号列表": list((reference or {}).get("候选索引号列表") or []),
        "原始索引号": (reference or {}).get("原始索引号") or report.get("原始索引号"),
        "采用审计条目号": (reference or {}).get("采用审计条目号") or report.get("审计条目号"),
        "报告引用": _snapshot(reference),
        "候选目录": _catalogs_for(list((reference or {}).get("候选索引号列表") or [])),
        "审计条目": [dict(row) for row in _audit_rows(numbers)],
        "审计更正": [dict(row) for row in corrections],
        "复查案件": dict(case) if case else None,
        "审计处置": [dict(row) for row in dispositions],
    })
    return detail


def reference_detail(report_id: int) -> dict[str, Any] | None:
    report = _report(report_id)
    if report is None:
        return None
    reference = _reference_for_report(report_id)
    numbers = _report_audit_numbers(report, reference)
    return {
        "报告id": report_id,
        "报告编号": report.get("报告编号"),
        "报告引用": _snapshot(reference),
        "审计条目": [dict(row) for row in _audit_rows(numbers)],
    }


def audit_detail(audit_id: int) -> dict[str, Any] | None:
    audit = store.find("govern_audit", audit_id)
    if audit is None:
        return None
    item_no = str(audit.get("审计条目号", ""))
    references = [
        row for row in store.aux_rows(REFERENCE_TABLE)
        if item_no and str(row.get("采用审计条目号", "")) == item_no
    ]
    dispositions = [
        row for row in store.aux_rows(DISPOSITION_TABLE)
        if int(row.get("审计记录id") or 0) == int(audit_id)
    ]
    detail = dict(audit)
    detail.update({
        "报告引用": [_snapshot(row) for row in references],
        "审计处置": [dict(row) for row in dispositions],
    })
    return detail
