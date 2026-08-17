# HGSmart Home Assistant Integration (unofficial)

Custom integration for the HG Smart kibble dispenser (e.g. model S30D),
based on the reverse-engineered cloud API documented in
[`docs/hgsmart_api.md`](docs/hgsmart_api.md).

## Disclaimer

Unofficial project, not affiliated with or supported by HG Smart/Honeyguardian.
The API was reverse-engineered by capturing the official app's traffic
(HTTP Toolkit), not from public documentation: it can change or break
without notice, and some details (in particular the portion encoding, see
below) are unconfirmed hypotheses. No guarantees: use it knowing it
controls a pet food dispenser.

**Tested devices**: so far this integration has only been tested against a
**Honey Guardian S305D**. Other HG Smart/Honeyguardian devices exposed by
the same account/API (different `type`/`capacityModel` values) should
appear and expose the same entities, but their behavior is **not
guaranteed** — please open an issue if you try it on another model and it
does or doesn't work.

## What it does

- **Config flow**: from *Settings → Devices & services → Add integration →
  HG Smart*, enter your account email and password (the same ones used in
  the app). The login is validated immediately.
- **Automatic discovery**: after login, every device found on the account
  is created. Every 5 minutes the integration re-fetches the device list
  and automatically adds any newly found dispenser.
- **Entities for each dispenser**:
  - `binary_sensor` Online
  - `sensor` Remaining food, Desiccant expiry, Last refill, Last desiccant
    change, Firmware version, Last event (text of the day's latest event,
    e.g. "Manual feeding of 1 portion(s).")
  - `select` Portions (1–6)
  - `button` Manual feed — dispenses the number of portions set in the
    `select`, then re-polls status a few seconds later so the "Last event"
    sensor reflects the real outcome (a `200 OK` from the command call
    alone is not a confirmation, see
    [`docs/hgsmart_api.md`](docs/hgsmart_api.md) §4).

There's no token caching/refresh: every polling cycle and every button
press do a fresh login, as recommended in the docs given the low call
volume.

## Installation

1. Copy the `custom_components/hgsmart` folder into the
   `config/custom_components/` folder of your Home Assistant instance
   (create it if it doesn't exist).
2. Restart Home Assistant.
3. *Settings → Devices & services → Add integration* → search for
   "HG Smart" → enter your email and password.

## ⚠️ Point to verify: portion quantity

The `ctrl.value` encoding used for feeding (`api.py`, function
`build_userfoodframe_value`) is an **unconfirmed hypothesis**:

```
"01" (fixed) + hour (HH) + minute (MM) + portions (2 digits, 01-06)
```

In the original capture the app always dispensed the default 1 portion:
`value` was observed to change on every call even for the same action, but
a feeding with a quantity other than 1 has not yet been captured to
confirm that the last two digits are really the portion count.

**Before trusting portions 2-6**, it's worth doing:

1. Try dispensing 1 portion from the HA `button` and check in the
   "Last event" sensor (or in the app) that exactly 1 portion arrived.
2. Try 2-3 different portion counts and compare the `eventDesc` returned
   by `GET /app/device/today/{deviceId}` (e.g. "Manual feeding of 3
   portion(s).") against what you selected in the `select`.
3. If it doesn't match, only the `build_userfoodframe_value` function in
   `custom_components/hgsmart/api.py` needs updating — the rest of the
   integration stays the same.

To help gather more real samples to compare against, you can capture 2-3
feedings with different quantities directly from the HG Smart app (with
HTTP Toolkit, as in the original capture) and see how `value` changes.

## Debug

For detailed API call logs, in `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.hgsmart: debug
```

(the password is never logged; debug logs only show the feeding command's
body).
