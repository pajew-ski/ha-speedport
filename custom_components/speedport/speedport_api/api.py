import asyncio
import functools
import logging
from datetime import datetime, timedelta

import aiohttp

from . import exceptions
from .connection import Connection

_LOGGER = logging.getLogger(__name__)


def serialized(func):
    """Run one request sequence at a time.

    Cookie jar, httoken and login key belong to the one router session, and
    callers (polling, device list, switches) are independent of each other.
    """

    @functools.wraps(func)
    async def inner(self: "SpeedportApi", *args, **kwargs):
        async with self._lock:
            return await func(self, *args, **kwargs)

    return inner


def need_auth(func):
    """Log in when needed; a lost session pauses logins instead of fighting
    whoever took it over (the router allows one session, e.g. the web UI)."""

    @functools.wraps(func)
    @serialized
    async def inner(self: "SpeedportApi", *args, **kwargs):
        if not self.password:
            error = f'You need to set a password to use "{func.__name__}"'
            _LOGGER.error(error)
            raise PermissionError(error)
        paused = bool(self._paused_until) and datetime.now() < self._paused_until
        # Without a session, or once the pause after a lost one is over.
        login = not self.api.is_logged_in or (bool(self._paused_until) and not paused)
        if login and paused:
            raise exceptions.LoginPausedError(
                f"Login paused until {self._paused_until:%H:%M:%S}"
            )
        try:
            if login:
                await self.api.login(self.password)
                # Logged in: the pause is over even if the request then fails
                # for another reason (404 on a Smart 3). Left in place, it made
                # every later request log in again (#19).
                self._paused_until = None
            # While paused the request still goes out with the session at hand:
            # a router that only hiccupped serves it again without a new login.
            result = await func(self, *args, **kwargs)
        except (exceptions.SessionError, exceptions.LoginException) as exception:
            if not paused:
                self._paused_until = datetime.now() + timedelta(minutes=self.pause_time)
                _LOGGER.log(
                    # Losing a working session is expected, failing right after
                    # a login is not.
                    logging.WARNING if login else logging.INFO,
                    "%s: %s. Next login in %s min",
                    "No working session after login" if login else "Session lost",
                    exception,
                    self.pause_time,
                )
            if isinstance(exception, exceptions.LoginException):
                raise
            raise exceptions.LoginPausedError(str(exception)) from exception
        self._paused_until = None
        return result

    return inner


class SpeedportApi:
    def __init__(
        self,
        host: str,
        password: str,
        https: bool,
        session: aiohttp.ClientSession,
        pause_time: int = 5,
    ):
        self._password: str = password
        self._url = f"https://{host}" if https else f"http://{host}"
        self._api = Connection(self._url, session)
        self._pause_time: int = pause_time
        self._paused_until: datetime | None = None
        self._lock = asyncio.Lock()

    @property
    def api(self) -> Connection:
        return self._api

    @property
    def password(self) -> str:
        return self._password

    @property
    def url(self) -> str:
        return self._url

    @property
    def pause_time(self) -> int:
        return self._pause_time

    @pause_time.setter
    def pause_time(self, pause_time: int):
        self._pause_time = pause_time

    @need_auth
    async def get_secure_status(self):
        return await self.api.get("data/SecureStatus.json", auth=True)

    @need_auth
    async def get_phone_handler(self):
        return await self.api.get("data/IPPhoneHandler.json", auth=True)

    @serialized
    async def get_router(self):
        return await self.api.get("data/Router.json")

    @serialized
    async def get_status(self):
        return await self.api.get("data/Status.json")

    @serialized
    async def get_devices(self):
        return await self.api.get("data/DeviceList.json")

    @serialized
    async def get_login(self):
        return await self.api.get("data/Login.json")

    @need_auth
    async def get_ip_data(self):
        referer = "html/content/internet/con_ipdata.html"
        return await self.api.get("data/IPData.json", referer=referer, auth=True)

    @need_auth
    async def get_wps_state(self):
        referer = "html/content/network/wlan_wps.html"
        return await self.api.get("data/WPSStatus.json", referer=referer)

    @need_auth
    async def set_wifi(self, status=True, guest=False, office=False):
        """Set wifi on/off"""
        extra = "guest" if guest else "office" if office else ""
        _LOGGER.info(
            "Turn %s %s wifi...", ["off", "on"][bool(status)], extra if extra else ""
        )
        data = (
            {f"wlan_{extra}_active": str(int(status))}
            if extra
            else {"use_wlan": str(int(status))}
        )
        referer = f"html/content/network/wlan_{extra if extra else 'basic'}.html"
        return await self.api.post(
            f"data/{'WLANBasic' if extra else 'Modules'}.json", data, referer
        )

    @need_auth
    async def wps_on(self):
        _LOGGER.info("Enable wps connect...")
        await self.api.post(
            "data/WLANAccess.json",
            {"wlan_add": "on", "wps_key": "connect"},
            "html/content/network/wlan_wps.html",
        )

    @need_auth
    async def reconnect(self):
        _LOGGER.info("Reconnect with internet provider...")
        await self.api.post(
            "data/Connect.json",
            {"req_connect": "reconnect"},
            "html/content/internet/con_ipdata.html",
        )

    @need_auth
    async def reboot(self):
        _LOGGER.info("Reboot speedport...")
        await self.api.post(
            "data/Reboot.json",
            {"reboot_device": "true"},
            "html/content/config/restart.html",
        )

    @serialized
    async def login(self, password=""):
        return await self.api.login(password or self.password)
