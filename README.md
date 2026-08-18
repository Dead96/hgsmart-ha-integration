# HGSmart Home Assistant Integration (unofficial)

Custom integration for the HG Smart kibble dispenser (e.g. model S30D),
based on the reverse-engineered cloud API documented in
[`docs/hgsmart_api.md`](docs/hgsmart_api.md).

## Disclaimer

Unofficial project, not affiliated with or supported by HG Smart/Honeyguardian.
The API was reverse-engineered by capturing the official app's traffic
(HTTP Toolkit), not from public documentation: it can change or break
without notice. No guarantees: use it knowing it controls a pet food
dispenser.

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
- **Entities for each dispenser**, organized to match Home Assistant's
  device-page sections (`entity_category`) — note HA sorts entities
  *alphabetically by name within each section*, not in any custom order:
  - **Sensors**: Online (`binary_sensor`), Remaining food (`%`), Desiccant
    expiry, Last event (text of the day's latest event, e.g. "Manual
    feeding of 1 portion(s)."; also carries an `event_type` attribute —
    `manual_feeding`/`eating_left_bowl`/`eating_right_bowl`/etc., mapped
    from the raw `event` code, see
    [`docs/hgsmart_api.md`](docs/hgsmart_api.md) §4bis — falls back to the
    raw code for anything not yet mapped), and per-bowl (left/right) Eating
    count and Average eating duration for today (matches the app's own
    "Today's Eating"/"Avg Duration" screen — see
    [`docs/hgsmart_api.md`](docs/hgsmart_api.md) §4bis)
  - **Diagnostic**: Last refill, Last desiccant change, Firmware version
  - **Controls**: `button` Manual feed (dispenses the portions set in
    `select` Manual feed portions, then re-polls so "Last event" reflects
    the real outcome — a `200 OK` alone isn't a confirmation, see
    [`docs/hgsmart_api.md`](docs/hgsmart_api.md) §4), `select` Manual feed
    portions (1–6), `button` Reset desiccant, `number` Refill percentage
    (1–100, a precise text/box input, not a slider), `button` Refill (uses
    the percentage above)
  - **Configuration**: `switch` Child lock (state read back from the
    device on every poll — `GET .../attribute/{deviceId}`'s `child` field,
    see [`docs/hgsmart_api.md`](docs/hgsmart_api.md) §8 — not just assumed:
    if toggled from the HG Smart app or a button on the dispenser itself,
    this switch picks that up on the next poll); `number` Update interval
    (1–1440 minutes, default 5) — how often *this device's* own status is
    polled, effective immediately with no restart required, separate from
    and not affecting the fixed 5-minute discovery poll that looks for
    brand new devices on the account; and up to 6 **scheduled meals**
    (`Meal 1`…`Meal 6`, matching the app's "Feeding Plan" screen):
    `switch` Meal N enabled, `time` Meal N time (local time, converted
    to/from the UTC the API itself stores — see
    [`docs/hgsmart_api.md`](docs/hgsmart_api.md) §9), `number` Meal N
    portions (1–6). Changing any one of these three immediately sends the
    *entire* slot to the backend (no partial-update support), then
    re-polls to confirm — all three read the device's real, polled
    schedule state.

  Home Assistant doesn't support a custom section beyond
  Sensors/Controls/Configuration/Diagnostic, so the 6 scheduled meals live
  under Configuration alongside Child lock and Update interval rather than
  in a dedicated area.

**Session handling mirrors the app**: log in once, reuse the access token
for its ~2h lifetime, and refresh it via `/oauth/refreshToken` shortly
before it expires — instead of logging in again on every poll/button
press. A full username/password login only happens on the very first call
and as a fallback if the refresh itself fails (see
[`docs/hgsmart_api.md`](docs/hgsmart_api.md) §1bis). If the backend reports
the session as expired mid-call — which arrives as a normal `200 OK` with
`{"code": 401, ...}` in the body, not an HTTP 401 — the integration forces
a fresh token and retries that one call automatically, once.

## Installation

### Option A: HACS (custom repository)

1. HACS → ⋮ (top-right menu) → **Custom repositories**.
2. Add `https://github.com/Dead96/hgsmart-ha-integration` as an
   **Integration**.
3. Find **"HGSmart (Unofficial)"** in HACS and install it.
4. Restart Home Assistant.

### Option B: Manual copy

1. Copy the `custom_components/hgsmart` folder into the
   `config/custom_components/` folder of your Home Assistant instance
   (create it if it doesn't exist).
2. Restart Home Assistant.

### Adding the integration

*Settings → Devices & services → Add integration* → search for
**"HGSmart"** → enter your email and password.

## Debug

For detailed API call logs, in `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.hgsmart: debug
```

(the password is never logged; debug logs only show the feeding command's
body).

## License

[MIT](LICENSE)
