"""Client for the MyTower building app and its embedded Akuvox intercom.

Auth model (reverse-engineered from the iOS app traffic):

1. The app holds a long-lived device token, sent as the ``mt-mobile`` header.
   Hitting ``https://app.my-tower.co.il/`` with it establishes a web session
   (cookies).
2. With that session, the app calls
   ``https://akuvox.my-tower.co.il/?id=<uid>&hash=<b64 RSA public key>&version=2``
   with header ``mytower-authorization: base64("mytower")``. The server returns
   ``{config, devices, settings}`` where ``config`` is an RSA-OAEP(SHA-1)
   ciphertext that decrypts to
   ``{access_token, exp, client_id, domain}``.
3. ``access_token`` authorizes the Akuvox cloud API
   (``api.ecloud.akuvox.com``): ``userinfo`` lists the resident's SIP account
   and door devices; ``opendoor`` triggers a relay.

The Akuvox access token expires quickly, so :meth:`async_refresh` repeats
steps 1-2 on a schedule.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .const import (
    AKUVOX_DEFAULT_DOMAIN,
    AKUVOX_OPENDOOR_API_VERSION,
    AKUVOX_OPENDOOR_PATH,
    AKUVOX_RTSP_PORT,
    AKUVOX_USERINFO_PATH,
    HTTP_TIMEOUT,
    LOGGER,
    MYTOWER_AKUVOX_HOST,
    MYTOWER_APP_HOST,
    MYTOWER_AUTHORIZATION,
    MYTOWER_CONFIG_VERSION,
)


class MyTowerAuthError(Exception):
    """Raised when the device token / session is rejected."""


class MyTowerApiError(Exception):
    """Raised for any other API failure."""


@dataclass
class DoorRelay:
    """One openable relay on a door station."""

    name: str
    mac: str
    relay_id: int
    dtmf: str
    location: str


@dataclass
class DoorCamera:
    """An RTSP camera on a door station."""

    name: str
    mac: str
    rtsp_url: str


@dataclass
class MyTowerData:
    """Everything the coordinator needs after a refresh."""

    access_token: str = ""
    domain: str = AKUVOX_DEFAULT_DOMAIN
    expires_at: int = 0
    relays: list[DoorRelay] = field(default_factory=list)
    cameras: list[DoorCamera] = field(default_factory=list)


def generate_private_key_pem() -> str:
    """Create an RSA keypair for a config entry; the public half is the 'hash'."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


class MyTowerClient:
    """Async client that turns a MyTower device token into door controls."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        device_token: str,
        user_id: str,
        private_key_pem: str,
    ) -> None:
        self._session = session
        self._device_token = device_token
        self._user_id = user_id
        key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None
        )
        if not isinstance(key, rsa.RSAPrivateKey):
            raise MyTowerApiError("stored private key is not RSA")
        self._key: rsa.RSAPrivateKey = key
        self._public_hash = base64.b64encode(
            self._key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        ).decode()

    # -- public API ----------------------------------------------------------

    async def async_refresh(self) -> MyTowerData:
        """Run the full bootstrap and return parsed door data."""
        await self._async_bootstrap_session()
        config = await self._async_fetch_akuvox_config()
        data = MyTowerData(
            access_token=config["access_token"],
            domain=config.get("domain", "https://" + AKUVOX_DEFAULT_DOMAIN)
            .replace("https://", "")
            .replace("http://", "")
            .strip("/"),
            expires_at=int(config.get("exp", 0)),
        )
        userinfo = await self._async_akuvox_userinfo(data)
        self._parse_userinfo(userinfo, data)
        return data

    async def async_open_door(self, data: MyTowerData, relay: DoorRelay) -> None:
        """Trigger a door relay via the Akuvox cloud opendoor endpoint."""
        url = f"https://{data.domain}/{AKUVOX_OPENDOOR_PATH}?token={data.access_token}"
        body = f"mac={relay.mac}&relay={relay.relay_id}"
        headers = {
            "X-AUTH-TOKEN": data.access_token,
            "Content-Type": "application/x-www-form-urlencoded",
            "api-version": AKUVOX_OPENDOOR_API_VERSION,
            "Accept": "*/*",
            "x-cloud-lang": "en",
        }
        payload = await self._request("post", url, headers=headers, data=body)
        result = payload.get("result") if isinstance(payload, dict) else None
        if result not in (0, "0", None):
            raise MyTowerApiError(f"opendoor returned result={result}: {payload}")
        LOGGER.debug("Opened door '%s' (relay %s)", relay.name, relay.relay_id)

    # -- guest management (MyTower web session) ------------------------------

    async def async_create_guest(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Register a guest. ``fields`` maps MyTower form names to values.

        Known fields: guestType, name, guestPassport, phone, carNumber,
        allowBloogate, meetingPlace, estimateDate, dueToDate, description,
        visitorType, visitorId.
        """
        await self._async_bootstrap_session()
        form = aiohttp.FormData()
        for key, value in fields.items():
            if value is not None:
                form.add_field(key, str(value))
        url = f"https://{MYTOWER_APP_HOST}/api/createGuest"
        payload = await self._request_form(url, form)
        return self._guest_result(payload, "createGuest")

    async def async_delete_guest(
        self, visitor_id: str, visitor_type: str
    ) -> dict[str, Any]:
        """Remove a previously registered guest."""
        await self._async_bootstrap_session()
        url = f"https://{MYTOWER_APP_HOST}/api/deleteGuest"
        body = f"visitorId={visitor_id}&visitorType={visitor_type}"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }
        payload = await self._request("post", url, headers=headers, data=body)
        return self._guest_result(payload, "deleteGuest")

    @staticmethod
    def _guest_result(payload: Any, label: str) -> dict[str, Any]:
        inner = payload.get("data", {}) if isinstance(payload, dict) else {}
        if inner.get("result") != "success":
            raise MyTowerApiError(f"{label} failed: {payload}")
        return inner

    async def _request_form(self, url: str, form: aiohttp.FormData) -> Any:
        try:
            async with self._session.post(
                url,
                data=form,
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
            ) as resp:
                text = await resp.text()
                if resp.status in (401, 403):
                    raise MyTowerAuthError(f"{url} -> {resp.status}")
                resp.raise_for_status()
        except aiohttp.ClientError as err:
            raise MyTowerApiError(f"POST {url} failed: {err}") from err
        try:
            return json.loads(text)
        except ValueError:
            return text

    # -- bootstrap steps -----------------------------------------------------

    async def _async_bootstrap_session(self) -> None:
        """Establish the MyTower web session from the device token."""
        headers = {
            "mt-mobile": self._device_token,
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 26_6 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
            ),
            "Accept": "text/html,application/xhtml+xml",
        }
        url = f"https://{MYTOWER_APP_HOST}/"
        try:
            async with self._session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
            ) as resp:
                if resp.status in (401, 403):
                    raise MyTowerAuthError(f"device token rejected ({resp.status})")
                resp.raise_for_status()
                await resp.read()
        except aiohttp.ClientError as err:
            raise MyTowerApiError(f"session bootstrap failed: {err}") from err

    async def _async_fetch_akuvox_config(self) -> dict[str, Any]:
        """Fetch and decrypt the Akuvox access token for this resident."""
        url = (
            f"https://{MYTOWER_AKUVOX_HOST}/?id={self._user_id}"
            f"&hash={self._public_hash}&version={MYTOWER_CONFIG_VERSION}"
        )
        headers = {
            "mytower-authorization": MYTOWER_AUTHORIZATION,
            "content-type": "application/json",
            "Accept": "*/*",
        }
        payload = await self._request("get", url, headers=headers)
        if not isinstance(payload, dict) or payload.get("result") != "success":
            raise MyTowerApiError(f"unexpected Akuvox config response: {payload}")
        encrypted = payload.get("data", {}).get("config")
        if not encrypted:
            raise MyTowerApiError("Akuvox config missing 'config' field")
        return self._decrypt_config(encrypted)

    def _decrypt_config(self, encrypted_b64: str) -> dict[str, Any]:
        raw = base64.b64decode(encrypted_b64)
        last_err: Exception | None = None
        for pad in (
            padding.OAEP(
                mgf=padding.MGF1(hashes.SHA1()),
                algorithm=hashes.SHA1(),
                label=None,
            ),
            padding.PKCS1v15(),
        ):
            try:
                plain = self._key.decrypt(raw, pad)
                return json.loads(plain.decode())
            except Exception as err:  # noqa: BLE001 - try next padding
                last_err = err
        raise MyTowerApiError(f"could not decrypt Akuvox config: {last_err}")

    async def _async_akuvox_userinfo(self, data: MyTowerData) -> dict[str, Any]:
        url = f"https://{data.domain}/{AKUVOX_USERINFO_PATH}?token={data.access_token}"
        headers = {
            "X-AUTH-TOKEN": data.access_token,
            "Accept": "*/*",
            "content-type": "application/json",
            "x-cloud-lang": "en",
        }
        payload = await self._request("get", url, headers=headers)
        if not isinstance(payload, dict) or payload.get("result") != 0:
            raise MyTowerApiError(f"userinfo failed: {payload}")
        return payload

    # -- parsing -------------------------------------------------------------

    @staticmethod
    def _parse_userinfo(payload: dict[str, Any], data: MyTowerData) -> None:
        datas = payload.get("datas", {})
        user = datas.get("user", {})
        rtsp_ip = ""
        for key in ("rtsp_server", "rtmp_server"):
            if user.get(key):
                rtsp_ip = str(user[key]).split(":")[0]
                break

        for dev in datas.get("dev_list", []):
            mac = dev.get("mac")
            if not mac:
                continue
            location = str(dev.get("location", "")).strip()
            relays = dev.get("relay", [])
            for relay in relays:
                door_name = str(relay.get("door_name", "")).strip()
                # door_name is often a generic "Relay1"; the human-meaningful
                # label is the device location. Keep door_name only to
                # disambiguate when a station exposes more than one relay.
                if location and len(relays) > 1 and door_name:
                    name = f"{location} - {door_name}"
                else:
                    name = location or door_name or mac
                data.relays.append(
                    DoorRelay(
                        name=name,
                        mac=mac,
                        relay_id=int(relay.get("relay_id", 0)),
                        dtmf=str(relay.get("dtmf", "")),
                        location=location,
                    )
                )
            rtsp_pwd = dev.get("rtsp_pwd")
            if rtsp_ip and rtsp_pwd:
                data.cameras.append(
                    DoorCamera(
                        name=location or mac,
                        mac=mac,
                        rtsp_url=(
                            f"rtsp://ak:{rtsp_pwd}@{rtsp_ip}:{AKUVOX_RTSP_PORT}/{mac}"
                        ),
                    )
                )

    # -- low-level HTTP ------------------------------------------------------

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: str | None = None,
    ) -> Any:
        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                data=data,
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
            ) as resp:
                text = await resp.text()
                if resp.status in (401, 403):
                    raise MyTowerAuthError(f"{url} -> {resp.status}")
                resp.raise_for_status()
        except aiohttp.ClientError as err:
            raise MyTowerApiError(f"{method} {url} failed: {err}") from err
        try:
            return json.loads(text)
        except ValueError:
            return text
