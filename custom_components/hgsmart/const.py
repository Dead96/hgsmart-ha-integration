"""Constants for the HG Smart integration."""
from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "hgsmart"

BASE_URL = "https://hgsmart.net/hsapi"

# Fixed values hardcoded in the HG Smart app itself, sent with every login.
CLIENT_ID = "r3ptinrmmsl9rnlis6yf"
CLIENT_SECRET = "ss9Ytzb4gSceaPhwhKteAPLiVP4pmU8zxLEcWuscM6Vsnj7wMt"

DEFAULT_ZONEID = "Europe/Rome"

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
