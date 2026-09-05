from __future__ import annotations

import os
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, HttpUrl, model_validator

from field_chat.infrai_realtime import InfraiError, InfraiRealtime, InfraiTransportError
from field_chat.work_order_rooms import DispatchStatus, WorkOrderRooms, WorkflowConflict


class OpenRoomRequest(BaseModel):
    work_order_id: str = Field(min_length=1)


class TechnicianTokenRequest(BaseModel):
    work_order_id: str = Field(min_length=1)
    technician_id: str = Field(min_length=1)


class WorkOrderUpdateRequest(BaseModel):
    work_order_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    kind: Literal["photo", "dispatch_status", "technician_follow_up"]
    photo_url: HttpUrl | None = None
    status: DispatchStatus | None = None
    note: str | None = Field(default=None, min_length=1, max_length=2000)
    current_status: DispatchStatus | None = None

    @model_validator(mode="after")
    def require_kind_payload(self) -> "WorkOrderUpdateRequest":
        selected = {"photo": self.photo_url, "dispatch_status": self.status, "technician_follow_up": self.note}
        if selected[self.kind] is None:
            raise ValueError(f"{self.kind} requires its matching payload")
        return self


def rooms() -> WorkOrderRooms:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="INFRAI_API_KEY is required")
    return WorkOrderRooms(InfraiRealtime(api_key))


Rooms = Annotated[WorkOrderRooms, Depends(rooms)]
app = FastAPI(title="Field-service work-order rooms")


def call(action):
    try:
        return action()
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InfraiError as exc:
        client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=client_status, detail={"code": exc.code, "message": str(exc)}) from exc
    except InfraiTransportError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/rooms")
def open_room(request: OpenRoomRequest, workflow: Rooms):
    return call(lambda: workflow.open_room(request.work_order_id))


@app.post("/room-tokens")
def issue_room_token(request: TechnicianTokenRequest, workflow: Rooms):
    return call(lambda: workflow.technician_token(request.work_order_id, request.technician_id))


@app.post("/work-order-updates")
def publish_update(
    request: WorkOrderUpdateRequest,
    workflow: Rooms,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
):
    return call(lambda: workflow.publish_update(
        work_order_id=request.work_order_id,
        update_id=idempotency_key,
        account_id=request.account_id,
        kind=request.kind,
        photo_url=str(request.photo_url) if request.photo_url else None,
        status=request.status,
        note=request.note,
        current_status=request.current_status,
    ))


@app.get("/rooms/{work_order_id}/presence")
def room_presence(work_order_id: str, workflow: Rooms):
    return call(lambda: workflow.room_presence(work_order_id))

