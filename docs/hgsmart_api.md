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
- Refresh endpoint confirmed — see section 1bis. The integration logs in once, reuses the access token for its lifetime, and refreshes it instead of logging in again on every call (see the "Notes for the integration" section).

---

## 1bis. Refresh token

```
POST /oauth/refreshToken
Authorization: Bearer <current accessToken>
Content-Type: application/json
```

Body:
```json
{
  "refreshtoken": "<refreshToken>"
}
```

Note the request body key is lowercase `refreshtoken`, unlike the `refreshToken` field name used everywhere in responses. The `Authorization` header still carries the *current* (soon-to-expire) access token — confirmed via a real capture, the app doesn't omit it just because it's refreshing.

Response: identical shape to login, except `idToken` is empty:
```json
{
  "code": 200,
  "msg": "Successful operation",
  "data": {
    "idToken": "",
    "accessToken": "<new jwt>",
    "refreshToken": "<new jwt>"
  }
}
```

Both `accessToken` and `refreshToken` are replaced — always store the new `refreshToken` from the response, not just the new `accessToken`. Not yet confirmed: what happens if this is called with an already-expired `refreshToken` — the integration falls back to a full username/password login if this call fails for any reason, regardless of the specific error.

All subsequent calls require:
```
Authorization: Bearer <accessToken>
```

### Session-expired error shape

Confirmed via a real capture: an expired session does **not** come back as an HTTP 401. The transport-level response is a normal HTTP 200; the expiry is only signaled inside the JSON body, in the same `code`/`msg` shape used for every other API error:

```json
{
  "code": 401,
  "msg": "登录状态已过期"
}
```

(`msg` is Chinese for "login status has expired".) This can happen on *any* authenticated call, not just the ones right after a token was supposed to expire — e.g. if the server invalidates a session early. The integration checks `code` (not the HTTP status) on every response, and when it sees `401` there, it forces a fresh token (refresh, or full login if the refresh also fails) and retries the original call exactly once.

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
    "eating": [
      { "type": "2", "time": 1, "duration": 216 },
      { "type": "1", "time": 1, "duration": 112 }
    ],
    "remaining": 0,
    "desiccantExpire": 0
  }
}
```
`remaining` = estimated remaining food level, as a **percentage** (the integration exposes it as `sensor.remaining_food` with a `%` unit). `desiccantExpire` = remaining days for the desiccant bag. Both `0` in the original capture (dispenser empty/disconnected during testing).

`eating` = today's per-bowl eating summary — this dispenser has two bowls, and each entry is one bowl's stats for today. All three fields are confirmed against the app's own "Today's Eating" screen for each bowl (labeled "L"/"R"): `type` is the bowl (`"1"` = left, `"2"` = right — also matches the left/right bowl wording in `device/today`'s `eventDesc` below), `time` is the app's "Today's Eating: N time(s)" (how many eating sessions happened today on that bowl), and `duration` is the app's "Avg Duration" for that bowl today, in seconds. Exposed by the integration as `sensor.eating_count_left`/`_right` and `sensor.eating_avg_duration_left`/`_right`.

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
    { "createTime": "2026-08-17 20:26:25", "eventDesc": "Your pet has eaten from the right bowl for 1m 46s.", "event": "1_10" },
    { "createTime": "2026-08-17 20:25:41", "eventDesc": "Your pet has eaten from the left bowl for 0m 57s.", "event": "1_9" },
    { "createTime": "2026-08-17 20:24:34", "eventDesc": "Manual feeding of 2 portion(s).", "event": "1_2" },
    { "createTime": "2026-08-17 18:29:39", "eventDesc": "Manual feeding of 1 portion(s).", "event": "1_2" },
    { "createTime": "2026-08-17 16:47:59", "eventDesc": "Your pet has eaten from the left bowl for 1m 52s.", "event": "1_9" },
    { "createTime": "2026-08-17 16:46:01", "eventDesc": "Your pet has eaten from the right bowl for 3m 36s.", "event": "1_10" },
    { "createTime": "2026-08-17 16:43:03", "eventDesc": "Manual feeding of 1 portion(s).", "event": "1_2" }
  ],
  "total": 7
}
```
Daily event log for the device (only *today's* events — the list resets at local midnight). `eventDesc` is human-readable text that unambiguously confirms what actually happened. `event` is a type/subtype code; confirmed so far:

| `event` | Meaning |
|---|---|
| `1_2` | Manual feeding |
| `1_9` | Pet ate from the left bowl |
| `1_10` | Pet ate from the right bowl |

Not yet seen/mapped: codes for errors, refills, desiccant resets, or scheduled (as opposed to manual) feedings — this endpoint only ever shows what has *actually happened today*, so codes for things that haven't occurred yet in the current capture stay unmapped. The integration exposes this mapping via `sensor.last_event`'s `event_type` attribute (falls back to the raw `event` code if unmapped).

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

## 6. Reset desiccant

```
PUT /app/device/feeder/desiccant/{deviceId}
```

No request body (`content-length: 0`). Marks the desiccant bag as freshly replaced (resets the "days until desiccant expires" counter server-side).

Response:
```json
{
  "code": 200,
  "msg": "Successful operation",
  "data": null
}
```

---

## 7. Refill food

```
PUT /app/device/feeder/refill
Content-Type: application/json
```

Unlike every other device call, `deviceId` is **not** in the URL — it's a field inside the JSON body:

```json
{
  "deviceId": "<deviceId>",
  "capacity": 320,
  "surplus": 173,
  "capacityModel": "S305D"
}
```

- `capacity`: confirmed fixed at `320` for both known `capacityModel` values — `"S305D"` (5 L version) and `"S303D"` (3.5 L version). It appears to be a fixed protocol value rather than the device's actual hopper size in liters/grams.
- `surplus`: how much food is in the hopper after the refill, as an absolute amount out of `capacity`. Confirmed: `round(capacity * percent / 100)` (as implemented in the integration) matches the app's own behavior.

Response:
```json
{
  "code": 200,
  "msg": "Successful operation",
  "data": null
}
```

As with the feeding command, this only confirms the backend *accepted* the refill — cross-check `desiccantDate`/`refillDate` or `feeder/summary`'s `remaining` on the next poll to see whether it actually changed.

---

## 8. Child lock

Same endpoint as manual feeding (section 4), just a different `identifier`/`value` pair:

```
PUT /app/device/attribute/{deviceId}
Content-Type: multipart/form-data; boundary=----dio-boundary-<random>
```

```
------dio-boundary-<random>
content-disposition: form-data; name="command"

{
  "ctrl": {
    "identifier": "child",
    "value": "0"
  },
  "ctrl_time": "<epoch_ms>",
  "message_id": "<uuid>"
}
------dio-boundary-<random>--
```

- `value: "0"` = child lock **disabled**
- `value: "1"` = child lock **enabled**

Unlike `userfoodframe`'s `value`, this one is a plain literal `"0"`/`"1"`, not an encoded frame.

Response:
```json
{
  "code": 200,
  "msg": "Successful operation",
  "data": null
}
```

As with every other command on this endpoint, the 200 only confirms the backend *accepted* it — the child-lock state itself is read back separately, via the `child` field in `GET /app/device/attribute/{deviceId}`'s full attribute dump (see section 9), which the HA integration's `switch.child_lock` entity polls for its real state rather than assuming success.

This confirms `/app/device/attribute/{deviceId}` is a generic "set device attribute" endpoint, keyed by `identifier` — `userfoodframe` and `child` are the two known identifiers so far.

---

## 9. Feeding schedule (up to 6 scheduled meals)

### `GET /app/device/attribute/{deviceId}` — full attribute dump

```json
{
  "code": 200,
  "msg": "Successful operation",
  "data": {
    "autofoodframe": "04110001",
    "userfoodframe": "01162901",
    "electric": "100",
    "plan": "0",
    "plan0": "00600010",
    "plan1": "12200011",
    "plan2": "01400012",
    "plan3": "01700013",
    "plan4": "11100014",
    "plan5": "02100015",
    "radar1": "112",
    "radar2": "216",
    "ip": "192.168.1.195:3333",
    "music": "0",
    "child": "0",
    "batstate": "1",
    "mac": "<mac-address>",
    "wifiname": "<wifi-ssid>",
    "choosevoice": "0",
    "restart": "0",
    "restoreok": "0",
    "wifidelete": "0"
  }
}
```

This is the full attribute snapshot for the device — every `identifier` that can be set via section 4/8's `PUT .../attribute/{deviceId}` shows up here as a top-level field with its last-known `value`. Of these, `child` (matches section 8) and `plan0`-`plan5` are relevant to this integration; the others (`electric` battery/mains %, `radar1`/`radar2` — likely the same `eating` durations seen in `feeder/summary`, `ip`, `mac`, `wifiname`, `music`, `batstate`, `restart`, `restoreok`, `wifidelete`, `choosevoice`, `autofoodframe`) are device/firmware internals not needed for feeding control and not decoded here.

### Decoding `plan0`-`plan5`

Each of the 6 scheduled-meal slots (`plan0` = meal 1 … `plan5` = meal 6, matching the app's "Feeding Plan" screen) is an 8-character string:

```
plan1: "12200011"
        │└┬┘└┬┘└┬┘└ slot index (0-5, matches the Nth in "planN")
        │ │  │  └── portions (2 digits) — CONFIRMED: changing a scheduled
        │ │  │      meal from 1 to 2 portions in the app changed this
        │ │  │      field from "01" to "02"
        │ │  └───── minute (MM), UTC — always "00" in this capture
        │ └──────── hour (HH), UTC, 00-23
        └────────── enabled: "1" = on, "0" = off
```

Verified against **all six** slots in the capture above, this layout reconstructs every value exactly:

| slot | value | enabled | HH (UTC) | MM (UTC) | portions | index |
|---|---|---|---|---|---|---|
| `plan0` | `00600010` | 0 | 06 | 00 | 01 | 0 |
| `plan1` | `12200011` | 1 | 22 | 00 | 01 | 1 |
| `plan2` | `01400012` | 0 | 14 | 00 | 01 | 2 |
| `plan3` | `01700013` | 0 | 17 | 00 | 01 | 3 |
| `plan4` | `11100014` | 1 | 11 | 00 | 01 | 4 |
| `plan5` | `02100015` | 0 | 21 | 00 | 01 | 5 |

`HH`/`MM` are UTC, not local — confirmed: the app displays/edits these times in local time (see the "Feeding Plan" screenshot), converting to/from UTC for the API. The integration converts using Home Assistant's configured timezone (`homeassistant.util.dt`). Non-`"00"` minute values are also confirmed working, tested against the real backend.

### Writing a schedule slot

```
PUT /app/device/attribute/{deviceId}
Content-Type: multipart/form-data; boundary=----dio-boundary-<random>
```
```
------dio-boundary-<random>
content-disposition: form-data; name="command"

{
  "ctrl": {
    "identifier": "plan",
    "value": "11100014"
  },
  "ctrl_time": "<epoch_ms>",
  "message_id": "<uuid>"
}
------dio-boundary-<random>--
```

The `identifier` is always the literal `"plan"` (**not** `"plan4"`) — the target slot is encoded inside `value` itself (last digit). In the captured example, `value: "11100014"` is byte-for-byte identical to the `plan4` field later returned by `GET .../attribute/{deviceId}`, confirming: to change one slot, send the *entire* 8-character string for that slot (enabled + HH + MM + ?? + index), not a partial update — so toggling just the enabled bit still requires resending the slot's hour/minute/portions unchanged.

Response: same `{"code": 200, "msg": "Successful operation", "data": null}` shape as every other command on this endpoint — accepted, not confirmed. Re-fetch `GET .../attribute/{deviceId}` afterwards to verify the slot actually changed.

---

## Notes for the Home Assistant integration

**Recommended approach**: log in once, cache the access token, and refresh it via `/oauth/refreshToken` (section 1bis) shortly before its ~2h expiry instead of logging in again on every call — this is what the app itself does, and what the integration implements. Fall back to a full username/password login only if the refresh call itself fails (expired refresh token, first run, etc.). For a real confirmation of a feed, add a call to `device/today` a few seconds after the command (see section 4bis) instead of trusting the `PUT` outcome alone.

Implementation options, from simplest to most involved:

1. **`shell_command` + local Python script** (via `pyscript` or an external script invoked with `shell_command`): a `.py` file that logs in, takes the `deviceId` (hardcoded once known), and sends the command. An HA automation calls the script at the desired time.
2. **Native HA `rest_command`**: possible but awkward for the two-step login→command flow (would need two `rest_command`s chained together with temporary token storage in an `input_text`, via `response_variable` + a follow-up action).
3. **Custom component** (`custom_components/hgsmart/`): the cleanest route if you want a native entity (e.g. a "Feed" `button`) instead of calling external scripts — more upfront work, but a proper integration in the UI.

**Security**: `client_secret` and the password should go in `secrets.yaml`, never in plain text in the main configuration. The `client_id`/`client_secret` above are fixed values hardcoded in the app itself (not generated for your account), so they're not "secrets" in the classic sense — but the password is.

**What's still missing**:
- Mapping of further `event` values in `device/today` beyond the three confirmed (`1_2`, `1_9`, `1_10`) — e.g. errors, refills, desiccant resets, scheduled (vs. manual) feedings
