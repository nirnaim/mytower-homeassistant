# MyTower for Home Assistant

A custom (HACS-compatible) integration that controls the **MyTower** building app's
intercom — opening doors and viewing door cameras — from Home Assistant, plus
registering guests.

MyTower's intercom is an **Akuvox** cloud system. The app bootstraps a session
from a device token, asks MyTower's server for a short-lived Akuvox access token,
and then uses the Akuvox cloud API (`api.ecloud.akuvox.com`) to list your
doors/cameras and open relays. This integration reproduces that flow.

> Not affiliated with, authorised, or endorsed by MyTower or Akuvox. Community
> project, provided as-is. It talks to your own building account using a token
> from your own app.

## Features

- **Door buttons** — one `button` entity per door relay on your account.
- **Door cameras** — `camera` entities streaming the door-station RTSP feeds.
- **Guest management** — `mytower.create_guest` / `mytower.delete_guest` services.

## Install (HACS)

1. HACS → ⋮ → *Custom repositories* → add this repo, category **Integration**.
2. Install **MyTower**, then restart Home Assistant.
3. *Settings → Devices & Services → Add Integration → MyTower*.

Or copy `custom_components/mytower/` into your HA `config/custom_components/` and
restart.

## Configuration

The config flow asks for two values from the app:

- **Device token (`mt-mobile`)** — the app's long-lived device token.
- **Account id** — your numeric MyTower/Akuvox user id.

Both are read from the app's own network traffic (the same capture used to build
this). The Akuvox access token itself is **not** entered — it expires in about a
day, so the integration re-derives it from the device token every 30 minutes.

### Getting the two values

Capture the app's traffic once (e.g. with mitmproxy, trusting its CA on the
phone) and look at the request to `https://akuvox.my-tower.co.il/` — the `id`
query parameter is your **account id**, and the request to
`https://app.my-tower.co.il/` carries the **`mt-mobile`** header.

## How it works

```
device token (mt-mobile)
      │  GET https://app.my-tower.co.il/        → web session (cookies)
      ▼
GET https://akuvox.my-tower.co.il/?id=<id>&hash=<RSA pubkey>&version=2
      │  → { config: RSA-OAEP(SHA1) } → { access_token, exp, client_id, domain }
      ▼
GET  https://api.ecloud.akuvox.com/userinfo?token=<access_token>  → doors + cameras
POST https://api.ecloud.akuvox.com/opendoor?token=<access_token>  (mac, relay)  → open
```

## Credentials & privacy

Your device token and the derived Akuvox credentials stay in your Home Assistant
instance. Don't commit `*.creds`, captures, or tokens to a public repo. If you
believe a token leaked, log out and back in to the app to rotate it.

## Status

Validated against the live API end-to-end (token bootstrap, config decrypt,
device/camera listing). The **relay-open REST call is not yet confirmed** against
a live door — test the button on your own entrance first.
