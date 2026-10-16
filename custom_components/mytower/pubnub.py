"""Minimal PubNub subscribe listener for MyTower/Akuvox intercom ring events.

The app receives intercom-ring notifications by subscribing to PubNub channels
``akuvox_user_<id>`` and ``user_<id>`` on Akuvox's shared subscribe key. This
listens to the same channels read-only (no SIP, no registration, so it never
conflicts with the phone app) and calls back with each raw message.

No PubNub SDK dependency — this speaks the v2 subscribe REST protocol directly.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from .const import LOGGER, PUBNUB_ORIGIN, PUBNUB_SUBKEY

# PubNub holds the long-poll open ~280s; allow a margin over that.
_SUBSCRIBE_TIMEOUT = 310
_BACKOFF_START = 2
_BACKOFF_MAX = 60


class RingListener:
    """Long-polls PubNub and dispatches intercom messages to a callback."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        user_id: str,
        callback: Callable[[str, Any], Awaitable[None] | None],
        subkey: str = PUBNUB_SUBKEY,
    ) -> None:
        self._session = session
        self._callback = callback
        self._subkey = subkey
        self._channels = f"akuvox_user_{user_id},user_{user_id}"
        self._uuid = f"homeassistant-mytower-{user_id}"
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name="mytower-ringlistener")

    async def async_stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    async def _run(self) -> None:
        timetoken = "0"
        region = None
        backoff = _BACKOFF_START
        while not self._stop.is_set():
            try:
                payload = await self._subscribe(timetoken, region)
                t = payload.get("t", {})
                timetoken = t.get("t", timetoken)
                region = t.get("r", region)
                for msg in payload.get("m", []):
                    channel = msg.get("c", "")
                    data = msg.get("d")
                    try:
                        result = self._callback(channel, data)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:  # noqa: BLE001
                        LOGGER.exception("MyTower ring callback failed")
                backoff = _BACKOFF_START
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                LOGGER.debug("MyTower ring listener error: %s (retry in %ss)", err, backoff)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, _BACKOFF_MAX)

    async def _subscribe(self, timetoken: str, region: int | None) -> dict[str, Any]:
        url = (
            f"https://{PUBNUB_ORIGIN}/v2/subscribe/{self._subkey}/"
            f"{self._channels}/0"
        )
        params = {"tt": timetoken, "uuid": self._uuid, "heartbeat": "300"}
        if region is not None:
            params["tr"] = str(region)
        async with self._session.get(
            url,
            params=params,
            timeout=aiohttp.ClientTimeout(total=_SUBSCRIBE_TIMEOUT),
        ) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)
