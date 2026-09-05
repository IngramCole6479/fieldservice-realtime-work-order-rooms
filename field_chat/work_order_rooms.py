from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


class DispatchStatus(StrEnum):
    ASSIGNED = "assigned"
    EN_ROUTE = "en_route"
    ON_SITE = "on_site"
    COMPLETED = "completed"


class WorkflowConflict(ValueError):
    """A requested update contradicts the work-order state."""


class RealtimePort(Protocol):
    def create_channel(self, channel: str, channel_type: str = "public") -> dict[str, Any]:
        """Create a channel."""

    def issue_token(self, client_id: str, channel: str) -> dict[str, Any]:
        """Issue channel access to a client."""

    def publish(self, channel: str, event: str, data: dict[str, Any], account_id: str, idempotency_key: str) -> dict[str, Any]:
        """Publish one work-order event."""

    def presence(self, channel: str) -> dict[str, Any]:
        """Read the active channel members."""


@dataclass
class WorkOrderRooms:
    realtime: RealtimePort

    @staticmethod
    def channel_for(work_order_id: str) -> str:
        return f"work-order:{work_order_id}"

    def open_room(self, work_order_id: str) -> dict[str, Any]:
        channel = self.channel_for(work_order_id)
        result = self.realtime.create_channel(channel, "private")
        return {"work_order_id": work_order_id, "channel": channel, "realtime": result}

    def technician_token(self, work_order_id: str, technician_id: str) -> dict[str, Any]:
        channel = self.channel_for(work_order_id)
        token = self.realtime.issue_token(technician_id, channel)
        return {"channel": channel, "client_id": technician_id, "token": token}

    def publish_update(
        self,
        *,
        work_order_id: str,
        update_id: str,
        account_id: str,
        kind: str,
        photo_url: str | None = None,
        status: DispatchStatus | None = None,
        note: str | None = None,
        current_status: DispatchStatus | None = None,
    ) -> dict[str, Any]:
        if current_status == DispatchStatus.COMPLETED and kind == "dispatch_status":
            raise WorkflowConflict("a completed work order cannot move to another dispatch status")

        values: dict[str, Any] = {"work_order_id": work_order_id, "update_id": update_id, "kind": kind}
        if kind == "photo" and photo_url:
            values["photo_url"] = photo_url
        elif kind == "dispatch_status" and status:
            values["status"] = status.value
        elif kind == "technician_follow_up" and note:
            values["note"] = note
        else:
            raise WorkflowConflict(f"payload does not match update kind {kind}")

        channel = self.channel_for(work_order_id)
        published = self.realtime.publish(channel, f"work_order.{kind}", values, account_id, update_id)
        return {"channel": channel, "event": f"work_order.{kind}", "update": values, "realtime": published}

    def room_presence(self, work_order_id: str) -> dict[str, Any]:
        channel = self.channel_for(work_order_id)
        return {"channel": channel, "presence": self.realtime.presence(channel)}
