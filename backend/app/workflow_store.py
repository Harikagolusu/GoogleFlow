"""Workflow persistence.

- Firebase configured  -> Cloud Firestore, scoped per user:
      users/{uid}/flows/{workflowId}
- Firebase not configured (demo mode) -> in-memory dict, API-compatible.

All functions take a `uid`; in demo mode it may be None. Persistence shape
keeps the exact frontend Workflow contract plus createdAt/updatedAt stamps
(stripped automatically by the Pydantic response model).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_firestore: Any = None
_memory_workflows: dict[str, dict[str, Any]] = {}


def init(firestore_client: Any) -> None:
    """Wire the store to Firestore (or None for demo mode). Called at startup."""
    global _firestore
    _firestore = firestore_client


def is_persistent() -> bool:
    return _firestore is not None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _flows_collection(uid: str) -> Any:
    return _firestore.collection("users").document(uid).collection("flows")


def _doc(uid: str, workflow_id: str) -> Any:
    return _flows_collection(uid).document(workflow_id)


def save_workflow(uid: str | None, workflow: dict[str, Any], *, is_new: bool = False) -> None:
    """Upsert a workflow. is_new=True stamps createdAt (ask flow)."""
    if _firestore is None:
        _memory_workflows[workflow["id"]] = workflow
        return

    doc = _doc(uid or "", workflow["id"])
    now = _now_iso()
    if is_new:
        data = {**workflow, "createdAt": now, "updatedAt": now}
        doc.set(data)
    else:
        doc.set({**workflow, "updatedAt": now}, merge=True)


def get_workflow(uid: str | None, workflow_id: str) -> dict[str, Any] | None:
    if _firestore is None:
        return _memory_workflows.get(workflow_id)

    snapshot = _doc(uid or "", workflow_id).get()
    if not snapshot.exists:
        return None
    return dict(snapshot.to_dict() or {})


def list_workflows(uid: str | None, limit: int = 50) -> list[dict[str, Any]]:
    if _firestore is None:
        return list(_memory_workflows.values())

    snapshots = (
        _flows_collection(uid or "")
        .order_by("updatedAt", direction="DESCENDING")
        .limit(limit)
        .stream()
    )
    return [dict(snapshot.to_dict() or {}) for snapshot in snapshots]


# ---------------------------------------------------------------------------
# Checklist updates (recompute readiness / status / nextUp)
# ---------------------------------------------------------------------------


def apply_checklist_update(
    workflow: dict[str, Any], item_id: str, completed: bool
) -> dict[str, Any] | None:
    """Set one checklist item and recompute derived fields.

    Returns the updated workflow dict, or None when the item does not exist.
    """
    checklist: list[dict[str, Any]] = list(workflow.get("checklist") or [])
    if not any(item.get("id") == item_id for item in checklist):
        return None

    for item in checklist:
        if item.get("id") == item_id:
            item["completed"] = bool(completed)

    total = len(checklist)
    done = sum(1 for item in checklist if item.get("completed"))
    readiness = round(done / total * 100) if total else 0

    if readiness >= 100:
        status = "Completed"
    elif readiness > 0:
        status = "In Progress"
    else:
        status = "Action Needed"

    next_item = next((item["title"] for item in checklist if not item.get("completed")), None)

    updated = dict(workflow)
    updated["checklist"] = checklist
    updated["readiness"] = readiness
    updated["status"] = status
    updated["nextUp"] = next_item or "Review your plan"
    return updated