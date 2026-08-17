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
    "eating": [
      { "type": "2", "time": 1, "duration": 216 },
      { "type": "1", "time": 1, "duration": 112 }
    ],
    "remaining": 0,
    "desiccantExpire": 0
  }
}
```
`remaining` = probably an estimated remaining food level/portion count; `desiccantExpire` = remaining days for the desiccant bag. Both `0` in the original capture (dispenser empty/disconnected during testing). `eating` = list of feeding entries for the day, each with a `type` (subtype/source of the feeding, e.g. manual vs. scheduled — not yet mapped), a `time` (feeding slot/occurrence number?) and a `duration` (motor run time in some unit — not yet decoded). Not currently used by the integration.

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
- `surplus`: how much food is in the hopper after the refill, as an absolute amount out of `capacity`. In the captured example the user reported entering roughly `53%` full in the app, which produced `surplus: 173` — that's `~54%` of `320`, not exactly `53%`, so the precise rounding/percentage formula used by the app is **not confirmed** (the integration currently does `round(capacity * percent / 100)`, which lands close but may not exactly match the app's own math).

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

`HH`/`MM` are UTC, not local — confirmed: the app displays/edits these times in local time (see the "Feeding Plan" screenshot), converting to/from UTC for the API. The integration converts using Home Assistant's configured timezone (`homeassistant.util.dt`).

**Not yet confirmed**:
- Whether `MM` is ever non-`"00"` — every slot in this capture happens to be on the hour, so the minute digits' format/behavior for non-zero values hasn't actually been exercised.

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

**Recommended approach**: given the low call volume (a few feedings/day), avoid managing token caching/refresh — do login + command in sequence on every trigger. For a real confirmation, add a call to `device/today` a few seconds after the command (see section 4bis) instead of trusting the `PUT` outcome alone.

Implementation options, from simplest to most involved:

1. **`shell_command` + local Python script** (via `pyscript` or an external script invoked with `shell_command`): a `.py` file that logs in, takes the `deviceId` (hardcoded once known), and sends the command. An HA automation calls the script at the desired time.
2. **Native HA `rest_command`**: possible but awkward for the two-step login→command flow (would need two `rest_command`s chained together with temporary token storage in an `input_text`, via `response_variable` + a follow-up action).
3. **Custom component** (`custom_components/hgsmart/`): the cleanest route if you want a native entity (e.g. a "Feed" `button`) instead of calling external scripts — more upfront work, but a proper integration in the UI.

**Security**: `client_secret` and the password should go in `secrets.yaml`, never in plain text in the main configuration. The `client_id`/`client_secret` above are fixed values hardcoded in the app itself (not generated for your account), so they're not "secrets" in the classic sense — but the password is.

**What's still missing before generalizing beyond the "feed now" case**:
- Direct confirmation that the last two digits of `userfoodframe`'s `value` are really the portion count for an *immediate* feed (as opposed to the `plan` frame, where this was confirmed) — the layout is otherwise understood: `"01"` (fixed) + UTC hour + UTC minute + portions, which is why `value` changes on every call even for the same action (the time component changes)
- Token refresh endpoint (if you want to avoid repeated logins in the future)
- Any error codes other than 200/500 (e.g. expired token → probably 401, to be verified)
- Mapping of other `event` values in `device/today` (only `"1_2"` = successful manual feeding seen so far) — useful if in the future you want an HA sensor that distinguishes different event types (e.g. error, refill)
- Exact `surplus`/percentage formula for the refill call (section 7) — the `~53%` → `173` data point doesn't cleanly match a simple `capacity * percent / 100`, so a couple more captures at known percentages would help pin it down
- Meaning of `type`/`time`/`duration` in the `eating` array returned by `feeder/summary` (section 4bis)
- Whether `MM` in `plan0`-`plan5` (section 9) is ever non-`"00"` — every slot captured so far happens to be on the hour
