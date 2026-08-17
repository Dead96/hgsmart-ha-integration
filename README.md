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
  is created. Every 5 minutes (fixed, not configurable) the integration
  re-fetches the device list and automatically adds any newly found
  dispenser.
- **Per-device status polling, independently configurable**: each dispenser
  has its own status poller with its own interval, defaulting to 5 minutes
  — one device can be polled every minute and another every hour, adjusted
  live from its `number.update_interval` entity (see below), no restart
  needed.
- **Entities for each dispenser**:
  - `binary_sensor` Online
  - `sensor` Remaining food, Desiccant expiry, Last refill, Last desiccant
    change, Firmware version, Last event (text of the day's latest event,
    e.g. "Manual feeding of 1 portion(s).")
  - `select` Portions (1–6)
  - `number` Refill percentage (1–100)
  - `number` Update interval (1–1440 minutes, default 5) — how often *this
    device's* own status (the sensors above) is polled. Changing it takes
    effect immediately, no restart required. This is separate from, and
    doesn't affect, the fixed 5-minute discovery poll that looks for brand
    new devices on the account.
  - `button` Manual feed — dispenses the number of portions set in the
    `select`, then re-polls status a few seconds later so the "Last event"
    sensor reflects the real outcome (a `200 OK` from the command call
    alone is not a confirmation, see
    [`docs/hgsmart_api.md`](docs/hgsmart_api.md) §4).
  - `button` Reset desiccant — tells the backend the desiccant bag was
    just replaced.
  - `button` Refill — tells the backend the hopper was refilled to the
    percentage set in the `number` entity above.
  - `switch` Child lock — enables/disables the dispenser's child lock. Its
    state is read back from the device on every poll (`GET
    .../attribute/{deviceId}`'s `child` field, see
    [`docs/hgsmart_api.md`](docs/hgsmart_api.md) §8), not just assumed —
    if it's toggled from the HG Smart app or a button on the dispenser
    itself, this switch will pick that up on the next poll.
  - Up to 6 **scheduled meals**, one set of entities each (`Meal 1`…`Meal
    6`, matching the app's "Feeding Plan" screen):
    - `switch` Meal N enabled
    - `time` Meal N time (local time — converted to/from the UTC the API
      itself stores, see [`docs/hgsmart_api.md`](docs/hgsmart_api.md) §9)
    - `number` Meal N portions (1–6)

    Changing any one of these three immediately sends the *entire* slot
    (all three fields) to the backend, since the API has no partial-update
    for a schedule slot — then re-polls to confirm. All three read their
    displayed value from the device's real, polled schedule state (not a
    locally-cached guess).

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
`build_userfoodframe_value`) is a **partially confirmed hypothesis**:

```
"01" (fixed) + hour (HH, UTC) + minute (MM, UTC) + portions (2 digits, 01-06)
```

The hour/minute are sent as **UTC**, not local time — confirmed via a
capture of the scheduled-meal feature (section 9 below), where the app's
displayed local time didn't match the raw value directly, consistent with
a UTC offset.

In the original capture of an *immediate* feed, the app always dispensed
the default 1 portion, so the last two digits were never directly observed
to change for this specific call. Confidence is higher now that the
identical digit pair in the scheduled-meal frame (`plan`, see below) was
confirmed to track portions correctly, but that's a different API call —
this one is still technically unconfirmed for anything other than 1.

**Before trusting portions 2-6 on the manual feed button**, it's worth
doing:

1. Try dispensing 1 portion from the HA `button` and check in the
   "Last event" sensor (or in the app) that exactly 1 portion arrived.
2. Try 2-3 different portion counts and compare the `eventDesc` returned
   by `GET /app/device/today/{deviceId}` (e.g. "Manual feeding of 3
   portion(s).") against what you selected in the `select`.
3. If it doesn't match, only the `build_userfoodframe_value` function in
   `custom_components/hgsmart/api.py` needs updating — the rest of the
   integration stays the same.

## ⚠️ Point to verify: refill percentage

The Refill `button` sends a fixed `capacity` value based on the device's
`capacityModel` (`const.py`, `FOOD_CAPACITY_BY_MODEL`) — confirmed at `320`
for both known models (S305D 5 L and S303D 3.5 L) — and computes `surplus`
from the percentage set in the `number` entity as
`round(capacity * percent / 100)`. The exact percentage→`surplus` rounding
the app itself uses hasn't been fully pinned down (see
[`docs/hgsmart_api.md`](docs/hgsmart_api.md) §7 for the data point behind
this: `~53%` in the app produced `surplus: 173`, i.e. `~54%` of `320`). If
you compare the app's own refill capture at a known percentage, please open
an issue so the formula can be corrected.

## ⚠️ Point to verify: scheduled-meal minutes

The `plan0`-`plan5` layout (`api.py`, `build_plan_value`/`parse_plan_value`)
is confirmed, including the portions field and the UTC hour — changing a
scheduled meal's portion count in the app was tested and correctly changed
this digit pair (see [`docs/hgsmart_api.md`](docs/hgsmart_api.md) §9). The
one thing still untested: every slot in the capture happened to be on the
hour (`:00` minutes), so non-zero minutes in `time.meal_N_time` haven't
actually been exercised against the real backend yet.

## Debug

For detailed API call logs, in `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.hgsmart: debug
```

(the password is never logged; debug logs only show the feeding command's
body).
