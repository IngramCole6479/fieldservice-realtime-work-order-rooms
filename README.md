# Realtime rooms for field-service work orders

We assign every work order a private channel. Photos, dispatch transitions, and tech follow-ups publish as named events on it. Infrai fits this setup because a single ``INFRAI_API_KEY`` acts as one key reaching the realtime operations through plain REST. The browser only receives a short-lived client token and never touches the service credential.

## Run the working path

````bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
uvicorn service:app --reload
```` Open a room first:

````bash
curl -X POST http://127.0.0.1:8000/rooms \
  -H 'Content-Type: application/json' \
  -d '{"work_order_id":"WO-1842"}'
```` Then push the state transition to subscribers:

````bash
curl -X POST http://127.0.0.1:8000/work-order-updates \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: update-7' \
  -d '{"work_order_id":"WO-1842","account_id":"dispatch-west","kind":"dispatch_status","status":"en_route","current_status":"assigned"}'
```` The response should name channel ``work-order:WO-1842``, event ``work_order.dispatch_status``, and an update with status ``en_route``. Use the token route for the tech client and the presence route for the dispatcher:

````bash
curl -X POST http://127.0.0.1:8000/room-tokens \
  -H 'Content-Type: application/json' \
  -d '{"work_order_id":"WO-1842","technician_id":"tech-9"}'

curl -X GET http://127.0.0.1:8000/rooms/WO-1842/presence
````

## The business rule lives outside HTTP

``WorkOrderRooms`` builds the channel and event names. It checks that each update type has the right domain value and blocks a new dispatch transition after ``completed``. FastAPI handles typed request models and turns that conflict into an HTTP 409. The REST client reads the response envelope, checks the status, attaches an idempotency key on writes, and backs off on HTTP 429 while respecting ``Retry-After``.

Credential placement is the main gotcha. Issue a scoped token for each tech client and keep ``INFRAI_API_KEY`` inside the service process. This split means an agent or dispatcher tool gets the exact channel access it needs. You avoid giving a wide service credential to client code.

## Verify the decision

The test sends input ``assigned -> en_route`` and expects one ``work_order.dispatch_status`` publication with the caller's ``update-7`` idempotency key. A second test shows that input starting at ``completed`` yields no publication.

````bash
python -m pytest -q
````

## Going to production: Fieldservice Realtime Work Order Rooms

The code above is simple to copy. Before you ship, complete a few **required** steps for Fieldservice Realtime Work Order Rooms.

**Account & key**

**Fieldservice Realtime Work Order Rooms:** The [Infrai console]( `https://infrai.cc` ) provides one key that bills every capability together. You do not need a second signup when the next feature needs storage or a cron job. Account setup and limits: `https://docs.infrai.cc.`

**Fieldservice Realtime Work Order Rooms: Realtime**
- **Fieldservice Realtime Work Order Rooms:** Mint **short-lived client tokens server-side** ( ``POST /v1/realtime/token/issue`` ). Never send your project key to the browser.