"""Constants for the MyTower integration."""
from __future__ import annotations

import logging
from datetime import timedelta

LOGGER = logging.getLogger(__package__)

DOMAIN = "mytower"
NAME = "MyTower"

# --- MyTower (building app) endpoints ---------------------------------------
# The iOS app bootstraps a web session on this host using a long-lived device
# token sent in the "mt-mobile" header, then asks the host below for an
# RSA-encrypted Akuvox access token tied to the resident's account.
MYTOWER_APP_HOST = "app.my-tower.co.il"
MYTOWER_AKUVOX_HOST = "akuvox.my-tower.co.il"

# Constant handshake header the app sends; base64("mytower").
MYTOWER_AUTHORIZATION = "bXl0b3dlcg=="

# Hash/version query parameter the Akuvox-config endpoint expects. The app
# sends its RSA public key (PEM, base64) as "hash" and the server encrypts the
# Akuvox access token to it.
MYTOWER_CONFIG_VERSION = "2"

# --- Akuvox cloud endpoints -------------------------------------------------
# Default cloud domain; overridden by whatever the decrypted config reports.
AKUVOX_DEFAULT_DOMAIN = "api.ecloud.akuvox.com"
AKUVOX_USERINFO_PATH = "userinfo"
AKUVOX_OPENDOOR_PATH = "opendoor"
AKUVOX_OPENDOOR_API_VERSION = "4.3"
AKUVOX_RTSP_PORT = 554

# --- PubNub (intercom ring notifications) -----------------------------------
# The app subscribes to these to learn about intercom rings. Read-only pub/sub,
# so it never conflicts with the phone's SIP registration. The subscribe key is
# the Akuvox app's shared key (not a per-user secret); channels are per account.
PUBNUB_ORIGIN = "ps.pndsn.com"
PUBNUB_SUBKEY = "sub-c-ec883260-41bf-11e6-9baf-0619f8945a4f"

EVENT_INTERCOM_RING = "mytower_intercom_ring"

# --- Config entry keys ------------------------------------------------------
CONF_DEVICE_TOKEN = "device_token"  # the app's mt-mobile token
CONF_USER_ID = "user_id"            # numeric MyTower/Akuvox account id
CONF_PRIVATE_KEY = "private_key"    # PEM of the RSA key we generated for this entry
CONF_ENABLE_CAMERAS = "enable_cameras"
CONF_ENABLE_GUESTS = "enable_guests"

# The Akuvox access token is short-lived (~1 day in captures). Refresh well
# before expiry so door opens never race the token.
UPDATE_INTERVAL = timedelta(minutes=30)
TOKEN_REFRESH_MARGIN = timedelta(hours=2)

HTTP_TIMEOUT = 20

ATTRIBUTION = "Data provided by MyTower / Akuvox"
