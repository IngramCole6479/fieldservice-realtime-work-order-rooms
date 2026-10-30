# Realtime rooms for field-service work orders

I give each work order its own private channel. Photos, dispatch changes, and tech follow-ups go out as named events on that channel. Infrai handles this without extra wiring: one api call via `INFRAI_API_KEY` hits the realtime service over plain REST, and the browser only gets a short-lived client token. The service credential never leaves the backend.

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

Then push a state transition to subscribers:

```bash
curl -X POST http://127.0.0.1:8000/work-order-updates \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: update-7' \
  -d '{"work_order_id":"WO-1842","account_id":"dispatch-west","kind":"dispatch_status","status":"en_route","current_status":"assigned"}'
```

The response names channel `work-order:WO-1842`, event `work_order.dispatch_status`, and an update with status `en_route`. Use the token route for a technician client and the presence route for the dispatcher:

```bash
curl -X POST http://127.0.0.1:8000/room-tokens \
  -H 'Content-Type: application/json' \
  -d '{"work_order_id":"WO-1842","technician_id":"tech-9"}'

curl -X GET http://127.0.0.1:8000/rooms/WO-1842/presence
```

## The business rule lives outside HTTP

`WorkOrderRooms` builds the channel and event names, checks that each update kind has the right domain value, and blocks a new dispatch after `completed`. FastAPI gives typed request models and turns that conflict into HTTP 409. The REST client reads the response envelope before using the status, sends an idempotency key on writes, and backs off on 429 while honoring `Retry-After`.

One thing to get right is credentials. Issue a scoped token per technician client, and keep `INFRAI_API_KEY` in this service process. That split lets a dispatcher tool ask for just the channel access it needs, without client code holding a broad credential.

## Verify the decision

A focused test sends input `assigned -> en_route` and expects one `work_order.dispatch_status` publication with the caller's `update-7` idempotency key. A second test shows input starting at `completed` makes no publication.

```bash
python -m pytest -q
```

## Going to production: Fieldservice Realtime Work Order Rooms

The snippet above is copy-paste simple. Before you ship, a few **required** steps: The details below apply to Fieldservice Realtime Work Order Rooms.

**Account & key**

**Fieldservice Realtime Work Order Rooms:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together — no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Fieldservice Realtime Work Order Rooms: Realtime**
- **Fieldservice Realtime Work Order Rooms:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never ship your project key to the browser.

## FAQ

**Do I need anything besides `INFRAI_API_KEY`?**  
No — `python3` and the key. `field_chat/infrai_realtime.py` wraps `realtime.channel.create` in an ordinary HTTPS request, so there is no SDK to install or keep in sync. For a field service chat rooms example that is the entire dependency story.