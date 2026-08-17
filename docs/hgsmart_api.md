# HG Smart — Reverse-engineered API (Kibble Dispenser)

Documentation obtained by capturing traffic (HTTP Toolkit) from the HG Smart app. Proprietary backend, not directly Tuya Cloud — no HMAC signature required, only a JWT Bearer token.

**Base URL**: `https://hgsmart.net/hsapi`

---

## App credentials (client)

Fixed, hardcoded in the app, sent with every login:

```
client_id: r3ptinrmmsl9rnlis6yf
client_secret: ss9Ytzb4gSceaPhwhKteAPLiVP4pmU8zxLEcWuscM6Vsnj7wMt
```

## Headers common to all calls

```
client: r3ptinrmmsl9rnlis6yf
host: hgsmart.net
tunit: 0
wunit: 0
zoneid: Europe/Berlin
user-agent: Dart/3.6 (dart:io)
```

`tunit`/`wunit` are probably units of measurement (temperature/weight, 0 = metric) — not verified whether the server actually validates them, for now keep them identical to the app.

---

## 1. Login

```
POST /oauth/login
Content-Type: application/json
```

Body:
```json
{
  "account_num": "<your-email>@example.com",
  "pwd": "<password>",
  "captcha_uuid": "",
  "client_id": "r3ptinrmmsl9rnlis6yf",
  "client_secret": "ss9Ytzb4gSceaPhwhKteAPLiVP4pmU8zxLEcWuscM6Vsnj7wMt"
}
```

Response:
```json
{
  "code": 200,
  "msg": "Successful operation",
  "data": {
    "idToken": "<jwt>",
    "accessToken": "<jwt>",
    "refreshToken": "<jwt>"
  }
}
```

- `idToken` and `accessToken` are identical (the same JWT).
- `accessToken`: expires after **2 hours** (7200s, from `exp - iat` in the payload).
- `refreshToken`: expires after **30 days** (2,592,000s).
- No refresh endpoint captured yet — not tested. Given the low expected call volume, the approach chosen for the integration is **login on every call** instead of caching/refreshing the token (see the "Notes for the integration" section).

All subsequent calls require:
```
Authorization: Bearer <accessToken>
```

---

## 2. User info

```
GET /app/user/info
Authorization: Bearer <accessToken>
```

Response:
```json
{
  "code": 200,
  "msg": "Successful operation",
  "data": {
    "userId": "<userId>",
    "userName": "<your-email>@example.com",
    "nickName": "<nickname>",
    "email": "<your-email>@example.com",
    "sex": -1,
    "avatarName": "_01",
    "country": "IT",
    "status": 0
  }
}
```

Not needed for automation, only useful as a connectivity/token-validity check.

---

## 3. Device list

```
GET /app/device/list
Authorization: Bearer <accessToken>
```

Response:
```json
{
  "code": 200,
  "msg": "Successful operation",
  "data": [
    {
      "deviceId": "<deviceId>",
      "name": "Kibble Dispenser",
      "refillDate": "2025-06-07T19:52:09.000+08:00",
      "desiccantDate": "2025-06-07T19:52:00.000+08:00",
      "type": "S30D",
      "capacityModel": "S305D",
      "fwVersion": "1.0.97",
      "online": true,
      "tz": "Europe/Rome",
      "autoCleanLimit": 24,
      "isOwner": true
    }
  ]
}
```

`deviceId` must be used literally in the URL of the command call (point 4).

---

## 4. Manual feeding (command)

```
PUT /app/device/attribute/{deviceId}
Content-Type: multipart/form-data; boundary=----dio-boundary-<random>
```

Body (multipart, a single `command` field containing a JSON string):
```
------dio-boundary-<random>
content-disposition: form-data; name="command"

{
  "ctrl": {
    "identifier": "userfoodframe",
    "value": "01162801"
  },
  "ctrl_time": "<epoch_ms>",
  "message_id": "<uuid>"
}
------dio-boundary-<random>--
```

Fields to regenerate on every call:
- `ctrl_time`: Unix timestamp in milliseconds, e.g. `"1786976888206"`
- `message_id`: UUID v4 without dashes in the observed format, e.g. `"ddf061f09a4711f1a5b7336cfdfd2a1d"` (unclear whether it must be unique or is an idempotency key — set a different value every time regardless, to be safe)
- `identifier`/`value` (`"userfoodframe"` / `"01162801"`): **meaning not yet decoded**. Hypothesis to verify: it might encode the portion/quantity, or a frame/time. Before generalizing the automation to variable quantities, it's worth capturing 2-3 feedings with different portions from the app to see how `value` changes.

Response (command accepted):
```json
{
  "code": 200,
  "msg": "Successful operation",
  "data": null
}
```

**Note**: HTTP Toolkit sometimes flags a warning like *"Expected a JSON object, array or literal. json(0)"* on this request's body — that's a false positive from its linter, which tries to parse the whole multipart body as plain JSON instead of only looking at the `command` field. It's not an API error, the request still succeeds.

**The 200/`data: null` is not a confirmation that feeding actually happened** — confirmed empirically: the response to this call is **identical whether the device is online or (until it times out) offline**. The app itself doesn't trust this response: right after sending the command, it calls three more endpoints in sequence to verify what actually happened (see below).

The `value` field inside `ctrl` (e.g. `"01162801"`, `"01162701"`, `"01164201"` across different calls) **changes on every invocation even for the same action** (always "feed manually", always the default 1 portion) — not yet clear whether it encodes a timestamp/checksum or something else. Unresolved.

---

## 4bis. Post-command verification (calls made by the app right after the PUT)

After sending the feeding command, the app calls these three endpoints in sequence to update the UI and verify the real outcome:

### `GET /app/device/feeder/summary/{deviceId}`
```json
{
  "code": 200,
  "msg": "Successful operation",
  "data": {
    "remaining": 0,
    "desiccantExpire": 0
  }
}
```
`remaining` = probably an estimated remaining food level/portion count; `desiccantExpire` = remaining days for the desiccant bag. Both `0` in this capture (dispenser empty/disconnected during testing).

### `GET /app/device/info/{deviceId}`
Same as `device/list` but for a single device, with an extra `accessories` field (links to buy spare parts):
```json
{
  "code": 200,
  "msg": "Successful operation",
  "data": {
    "deviceId": "<deviceId>",
    "name": "Kibble Dispenser",
    "refillDate": "2025-06-07T19:52:09.000+08:00",
    "desiccantDate": "2025-06-07T19:52:00.000+08:00",
    "type": "S30D",
    "capacityModel": "S305D",
    "fwVersion": "1.0.97",
    "online": true,
    "tz": "Europe/Rome",
    "accessories": [
      { "id": "S30D", "url": "https://www.honeyguardian.com/products/feeder-desiccant-bags-for-sf35" },
      { "id": "S30D-5G", "url": "https://www.honeyguardian.com/products/feeder-desiccants?variant=51799892689189" }
    ],
    "autoCleanLimit": 24,
    "isOwner": true
  }
}
```

### `GET /app/device/today/{deviceId}` — **this is the real confirmation**
```json
{
  "code": 200,
  "data": [
    {
      "createTime": "2026-08-17 16:43:03",
      "eventDesc": "Manual feeding of 1 portion(s).",
      "event": "1_2"
    }
  ],
  "total": 1
}
```
Daily event log for the device. `eventDesc` is human-readable text that unambiguously confirms what actually happened (here: manual feeding of 1 portion, executed successfully). `event: "1_2"` is probably a type/subtype code for the event (not yet mapped for other values — e.g. errors, refills, etc.).

**Implication for the HA integration**: to know whether the feeding *actually* succeeded (not just accepted by the backend), the correct flow is: `PUT` command → wait a few seconds → `GET /app/device/today/{deviceId}` → check whether a new event appeared with a recent `createTime` and an `eventDesc` mentioning "feeding". An HA sensor based on this endpoint (periodic polling, e.g. every 5-10 minutes, or right after each command) would give a real confirmation instead of trusting the outcome of the `PUT` alone.

---

## 5. Server-Sent Events (real-time push — optional)

```
POST /app/sse
Accept: text/event-stream
Authorization: Bearer <accessToken>
Cache-Control: no-cache
```

Long-lived connection, probably used by the app for push notifications (e.g. "feeding completed", "tank empty", online/offline status). Not necessary to operate the dispenser — only useful if in the future you want a real confirmation of a completed feeding instead of relying on the acceptance 200 alone.

---

## Notes for the Home Assistant integration

**Recommended approach**: given the low call volume (a few feedings/day), avoid managing token caching/refresh — do login + command in sequence on every trigger. For a real confirmation, add a call to `device/today` a few seconds after the command (see section 4bis) instead of trusting the `PUT` outcome alone.

Implementation options, from simplest to most involved:

1. **`shell_command` + local Python script** (via `pyscript` or an external script invoked with `shell_command`): a `.py` file that logs in, takes the `deviceId` (hardcoded once known), and sends the command. An HA automation calls the script at the desired time.
2. **Native HA `rest_command`**: possible but awkward for the two-step login→command flow (would need two `rest_command`s chained together with temporary token storage in an `input_text`, via `response_variable` + a follow-up action).
3. **Custom component** (`custom_components/hgsmart/`): the cleanest route if you want a native entity (e.g. a "Feed" `button`) instead of calling external scripts — more upfront work, but a proper integration in the UI.

**Security**: `client_secret` and the password should go in `secrets.yaml`, never in plain text in the main configuration. The `client_id`/`client_secret` above are fixed values hardcoded in the app itself (not generated for your account), so they're not "secrets" in the classic sense — but the password is.

**What's still missing before generalizing beyond the "feed now" case**:
- Decoding of `value` in `ctrl` (changes on every call even for the same action — timestamp? checksum? not understood) — doesn't block the current use case (1 manual portion) but prevents generalizing to variable portions without capturing other feedings from the app with different quantities
- Token refresh endpoint (if you want to avoid repeated logins in the future)
- Any error codes other than 200/500 (e.g. expired token → probably 401, to be verified)
- Mapping of other `event` values in `device/today` (only `"1_2"` = successful manual feeding seen so far) — useful if in the future you want an HA sensor that distinguishes different event types (e.g. error, refill)
