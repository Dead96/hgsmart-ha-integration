"""Constants for the HG Smart integration."""
from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "hgsmart"

BASE_URL = "https://hgsmart.net/hsapi"

# Fixed values hardcoded in the HG Smart app itself, sent with every login.
CLIENT_ID = "r3ptinrmmsl9rnlis6yf"
CLIENT_SECRET = "ss9Ytzb4gSceaPhwhKteAPLiVP4pmU8zxLEcWuscM6Vsnj7wMt"

DEFAULT_ZONEID = "Europe/Rome"

# accessToken lifetime per docs (exp - iat = 7200s). Refresh a bit early to
# avoid a request racing the exact expiry instant.
ACCESS_TOKEN_LIFETIME = timedelta(seconds=7200)
TOKEN_REFRESH_MARGIN = timedelta(seconds=120)

# Fixed cadence for the *discovery* poll only (device list → find new
# devices). Each device's own status polling interval is independent and
# configurable — see MIN/MAX/DEFAULT_UPDATE_INTERVAL_MINUTES below.
DISCOVERY_INTERVAL = timedelta(minutes=5)

POST_FEED_CONFIRM_DELAY = 5  # seconds to wait before re-polling to confirm a feed

MIN_UPDATE_INTERVAL_MINUTES = 1
MAX_UPDATE_INTERVAL_MINUTES = 1440  # 24h
DEFAULT_UPDATE_INTERVAL_MINUTES = 5

MIN_PORTIONS = 1
MAX_PORTIONS = 6
DEFAULT_PORTIONS = 1

MIN_REFILL_PERCENT = 1
MAX_REFILL_PERCENT = 100
DEFAULT_REFILL_PERCENT = 100

# Total food capacity to send in a refill call, keyed by the device's own
# `capacityModel` field. Confirmed at 320 for both known models (S305D,
# 5 L, and S303D, 3.5 L) — capacity appears to be a fixed protocol value
# rather than the actual hopper size.
FOOD_CAPACITY_BY_MODEL = {
    "S305D": 320,
    "S303D": 320,
}
DEFAULT_CAPACITY_MODEL = "S305D"

# Number of scheduled-meal slots the device exposes (`plan0`..`plan5`).
SCHEDULE_SLOTS = 6

# `event` codes seen in GET /app/device/today/{deviceId} (see
# docs/hgsmart_api.md). NOT exhaustive — that endpoint only returns
# *today's* events, so codes for things that haven't happened yet today
# (errors, refills, desiccant resets, ...) are still unmapped.
EVENT_TYPE_MAP = {
    "1_2": "manual_feeding",
    "1_9": "eating_left_bowl",
    "1_10": "eating_right_bowl",
}

# `eating[].type` in feeder/summary — confirmed against the app's own
# per-bowl "Today's Eating" screen (count + average duration).
BOWL_TYPES = {
    "left": "1",
    "right": "2",
}

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.TIME,
]

SIGNAL_NEW_DEVICE = "hgsmart_new_device_{entry_id}"
