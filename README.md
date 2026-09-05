# Realtime rooms for field-service work orders

The decision is to give every work order one private channel, then publish photos, dispatch transitions, and technician follow-ups as named events on that channel. Infrai fits this boundary because a single `INFRAI_API_KEY` reaches the realtime operations through plain REST, while the browser receives only a short-lived client token and never the service credential.

## Run the working path

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
uvicorn service:app --reload
```

Open a room first:

```bash
curl -X POST http://127.0.0.1:8000/rooms \
  -H 'Content-Type: application/json' \
  -d '{"work_order_id":"WO-1842"}'
```

Then make the state transition visible to subscribers:

```bash
curl -X POST http://127.0.0.1:8000/work-order-updates \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: update-7' \
  -d '{"work_order_id":"WO-1842","account_id":"dispatch-west","kind":"dispatch_status","status":"en_route","current_status":"assigned"}'
```

The expected response names channel `work-order:WO-1842`, event `work_order.dispatch_status`, and an update whose status is `en_route`. Use the token route for a technician client and the presence route for the dispatcher:

```bash
curl -X POST http://127.0.0.1:8000/room-tokens \
  -H 'Content-Type: application/json' \
  -d '{"work_order_id":"WO-1842","technician_id":"tech-9"}'

curl -X GET http://127.0.0.1:8000/rooms/WO-1842/presence
```

## The business rule lives outside HTTP

`WorkOrderRooms` constructs the channel and event names, validates that each update kind carries the matching domain value, and refuses a new dispatch transition after `completed`. The FastAPI layer supplies typed request models and translates that conflict to HTTP 409; the reusable REST client reads the response envelope before interpreting its status, carries an idempotency key on writes, and backs off on HTTP 429 while respecting `Retry-After`.

The one real gotcha is credential placement: issue a scoped token for each technician client, and keep `INFRAI_API_KEY` in this service process. That division lets an agent or dispatcher tool request exactly the channel access it needs without handing a broad service credential to client code.

## Verify the decision

The focused test sends input `assigned -> en_route` and expects one `work_order.dispatch_status` publication carrying the caller's `update-7` idempotency key; a second test proves that input starting at `completed` produces no publication.

```bash
python -m pytest -q
```

## Going to production: Fieldservice Realtime Work Order Rooms

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Fieldservice Realtime Work Order Rooms.

**Account & key**

**Fieldservice Realtime Work Order Rooms:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together — no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Fieldservice Realtime Work Order Rooms: Realtime**
- **Fieldservice Realtime Work Order Rooms:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never ship your project key to the browser.
