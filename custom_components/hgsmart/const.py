"""Constants for the HG Smart integration."""
from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "hgsmart"

BASE_URL = "https://hgsmart.net/hsapi"

# Fixed values hardcoded in the HG Smart app itself, sent with every login.
CLIENT_ID = "r3ptinrmmsl9rnlis6yf"
CLIENT_SECRET = "ss9Ytzb4gSceaPhwhKteAPLiVP4pmU8zxLEcWuscM6Vsnj7wMt"

DEFAULT_ZONEID = "Europe/Rome"

SCAN_INTERVAL = timedelta(minutes=5)
POST_FEED_CONFIRM_DELAY = 5  # seconds to wait before re-polling to confirm a feed

MIN_PORTIONS = 1
MAX_PORTIONS = 6
DEFAULT_PORTIONS = 1

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SELECT, Platform.BUTTON]

SIGNAL_NEW_DEVICE = "hgsmart_new_device_{entry_id}"
