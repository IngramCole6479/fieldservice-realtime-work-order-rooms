from typing import Any

import pytest

from field_chat.work_order_rooms import DispatchStatus, WorkOrderRooms, WorkflowConflict


class RecordingRealtime:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    def create_channel(self, channel: str, channel_type: str = "public") -> dict[str, Any]:
        return {"created": True}

    def issue_token(self, client_id: str, channel: str) -> dict[str, Any]:
        return {"value": "client-token"}

    def publish(self, channel: str, event: str, data: dict[str, Any], account_id: str, idempotency_key: str) -> dict[str, Any]:
        self.published.append({"channel": channel, "event": event, "data": data, "account_id": account_id, "key": idempotency_key})
        return {"published": True}

    def presence(self, channel: str) -> dict[str, Any]:
        return {"members": []}


def test_dispatch_update_is_domain_shaped_and_idempotent() -> None:
    realtime = RecordingRealtime()
    result = WorkOrderRooms(realtime).publish_update(
        work_order_id="WO-1842",
        update_id="update-7",
        account_id="dispatch-west",
        kind="dispatch_status",
        status=DispatchStatus.EN_ROUTE,
        current_status=DispatchStatus.ASSIGNED,
    )

    assert result["event"] == "work_order.dispatch_status"
    assert realtime.published == [{
        "channel": "work-order:WO-1842",
        "event": "work_order.dispatch_status",
        "data": {"work_order_id": "WO-1842", "update_id": "update-7", "kind": "dispatch_status", "status": "en_route"},
        "account_id": "dispatch-west",
        "key": "update-7",
    }]


def test_completed_work_order_rejects_another_dispatch_transition() -> None:
    realtime = RecordingRealtime()
    with pytest.raises(WorkflowConflict, match="completed work order"):
        WorkOrderRooms(realtime).publish_update(
            work_order_id="WO-1842",
            update_id="update-8",
            account_id="dispatch-west",
            kind="dispatch_status",
            status=DispatchStatus.ON_SITE,
            current_status=DispatchStatus.COMPLETED,
        )
    assert realtime.published == []

