"""Session handling of the vendored router API against a fake Speedport.

The fake models what the issue reports of a Speedport Smart 3 show (#16): one
logged-in session at a time, and the login page instead of data for a session
that is not logged in.
"""

import asyncio
import json
import secrets
import unittest
from datetime import datetime
from hashlib import sha256
from types import SimpleNamespace

import aiohttp
from aiohttp import web
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.speedport.device import SpeedportCoordinator
from custom_components.speedport.speedport_api import Speedport
from custom_components.speedport.speedport_api.connection import decode, encode
from custom_components.speedport.speedport_api.exceptions import (
    DecryptionKeyError,
    LoginException,
    LoginPausedError,
    UnexpectedResponseError,
)

PASSWORD = "secret"
LOGIN_PAGE = '<html><div id="is_login_page"></div><script>_httoken = 1;</script></html>'
PAUSE = 0.002  # minutes
# What the debug log of a Speedport Smart 3 shows as HTTP 404 (#19).
SMART_3_MISSING = {"", "html/content/internet/con_ipdata.html", "data/IPData.json"}
PAUSE_OVER = PAUSE * 60 + 0.05  # seconds


def encrypted(data: dict, key: str = "") -> str:
    return encode(
        json.dumps([{"varid": k, "varvalue": v} for k, v in data.items()]), key
    )


class FakeRouter:
    def __init__(self):
        self.sessions = {}
        self.requests = []
        self.pages = {}  # path -> how often to answer with the login page
        self.missing = set()  # paths this router does not have: HTTP 404
        self.wrong_key = False
        self.inflight = self.max_inflight = 0

    def kick(self):
        """What a login in the web UI does to our session."""
        for session in self.sessions.values():
            session["auth"] = False

    def count(self, path):
        return self.requests.count(path)

    async def handle(self, request):
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            await asyncio.sleep(0.005)
            return await self._answer(request)
        finally:
            self.inflight -= 1

    async def _answer(self, request):
        path = request.path.lstrip("/")
        self.requests.append(path)
        response = web.Response(content_type="text/html")
        sid = request.cookies.get("SessionID_R3")
        if sid not in self.sessions:
            sid = secrets.token_hex(8)
            self.sessions[sid] = {"auth": False, "challenge": ""}
            response.set_cookie("SessionID_R3", sid, path="/")
        session = self.sessions[sid]
        response.text = LOGIN_PAGE
        if path in self.missing:
            response.set_status(404)
        elif self.pages.get(path, 0) > 0:
            self.pages[path] -= 1
        elif path == "data/Status.json":
            response.text = encrypted({"device_name": "Smart 3", "serial_number": "1"})
        elif path == "data/DeviceList.json":
            response.text = encrypted({})
        elif path == "data/Login.json":
            form = dict(
                pair.split("=") for pair in decode(await request.text()).split("&")
            )
            if "getChallenge" in form:
                session.update(challenge=secrets.token_hex(32), auth=False)
                response.text = encrypted({"challenge": session["challenge"]})
            else:
                secret = f"{session['challenge']}:{PASSWORD}".encode()
                if ok := form["password"] == sha256(secret).hexdigest():
                    self.kick()
                    session["auth"] = True
                response.text = encrypted(
                    {"login": "success" if ok else "failed", "t_password": "ACCESS"}
                )
        elif path.endswith(".html") and session["auth"]:
            response.text = "<script>_httoken = 2;</script>"
        elif path == "data/IPData.json" and session["auth"]:
            if request.query.get("_tn") == "2":
                key = secrets.token_hex(32) if self.wrong_key else session["challenge"]
                response.text = encrypted({"public_ip_v4": "192.0.2.1"}, key)
        return response


class SpeedportApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.router = FakeRouter()
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self.router.handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.host = "127.0.0.1:%s" % site._server.sockets[0].getsockname()[1]
        self.session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
        self.speedport = await self.connect()
        await self.speedport.update_ip_data()

    async def asyncTearDown(self):
        await self.session.close()
        await self.runner.cleanup()

    async def connect(self, password=PASSWORD):
        return await Speedport(self.host, password, False, self.session, PAUSE).create()

    async def test_reads_status_and_ip_data(self):
        self.assertEqual(self.speedport.device_name, "Smart 3")
        self.assertEqual(self.speedport.public_ip_v4, "192.0.2.1")
        self.assertEqual(await self.speedport.devices, {})

    async def test_lost_session_pauses_then_logs_in_again(self):
        self.router.kick()
        with self.assertRaises(LoginPausedError) as raised:
            await self.speedport.update_ip_data()
        # The reported symptom, named for what it is.
        self.assertIsInstance(raised.exception.__cause__, UnexpectedResponseError)
        self.assertIn("/data/IPData.json answered HTTP 200", str(raised.exception))

        # Paused: no login, so nobody using the web UI is logged out.
        logins = self.router.count("data/Login.json")
        with self.assertRaises(LoginPausedError):
            await self.speedport.update_ip_data()
        self.assertEqual(self.router.count("data/Login.json"), logins)
        self.assertEqual(self.speedport.public_ip_v4, "192.0.2.1")  # kept

        await asyncio.sleep(PAUSE_OVER)
        await self.speedport.update_ip_data()
        self.assertEqual(self.router.count("data/Login.json"), logins + 2)

    async def test_session_that_works_again_needs_no_login(self):
        """A page from a router that still knows the session, also right after
        a login (#19): the next request is served without logging in again."""
        for after_login in (False, True):
            with self.subTest(after_login=after_login):
                if after_login:
                    self.router.kick()
                    with self.assertRaises(LoginPausedError):
                        await self.speedport.update_ip_data()
                    await asyncio.sleep(PAUSE_OVER)
                self.router.pages["data/IPData.json"] = 1
                with self.assertRaises(LoginPausedError):
                    await self.speedport.update_ip_data()
                logins = self.router.count("data/Login.json")
                await self.speedport.update_ip_data()
                await self.speedport.update_ip_data()  # and the pause is over
                self.assertEqual(self.router.count("data/Login.json"), logins)

    async def test_failed_login_is_not_repeated_during_the_pause(self):
        self.router.kick()
        with self.assertRaises(LoginPausedError):
            await self.speedport.update_ip_data()
        await asyncio.sleep(PAUSE_OVER)
        self.router.pages["data/Login.json"] = 1
        with self.assertRaises(LoginPausedError):  # used to be a raw error (#16)
            await self.speedport.update_ip_data()
        requests = len(self.router.requests)
        with self.assertRaises(LoginPausedError):
            await self.speedport.update_ip_data()
        self.assertEqual(len(self.router.requests), requests)
        await asyncio.sleep(PAUSE_OVER)
        await self.speedport.update_ip_data()

    async def test_rejected_password_is_not_retried_during_the_pause(self):
        speedport = await self.connect("wrong")
        with self.assertRaises(LoginException):
            await speedport.update_ip_data()
        logins = self.router.count("data/Login.json")
        with self.assertRaises(LoginPausedError):
            await speedport.update_ip_data()
        self.assertEqual(self.router.count("data/Login.json"), logins)
        with self.assertRaises(LoginException):  # the config flow's direct check
            await speedport.login()

    async def test_router_without_ip_data_is_not_asked_again(self):
        """A Speedport Smart 3 answers the IP data page and the data with 404
        (#19): no pause, no further login, and no further request."""
        # "" is the page the login reads its token from: also 404 there.
        self.router.missing = SMART_3_MISSING
        speedport = await self.connect()
        logins = self.router.count("data/Login.json")
        for _ in range(3):
            await speedport.update_ip_data()
        self.router.kick()  # the router drops the idle session
        speedport._ip_data_retry_at = datetime.now()  # not even after an hour
        await speedport.update_ip_data()
        self.assertEqual(self.router.count("data/Login.json"), logins + 2)
        self.assertEqual(self.router.count("data/IPData.json"), 2)  # setUp + 1
        self.assertEqual(speedport.public_ip_v4, "")

    async def test_router_that_had_ip_data_is_asked_again_later(self):
        """404 from a router that delivered before, e.g. while it restarts."""
        self.router.missing = {"data/IPData.json"}
        await self.speedport.update_ip_data()
        await self.speedport.update_ip_data()  # within the retry time
        self.assertEqual(self.router.count("data/IPData.json"), 2)  # setUp + 1
        self.assertEqual(self.speedport.public_ip_v4, "192.0.2.1")  # kept

        self.router.missing = set()
        self.speedport._ip_data_retry_at = datetime.now()
        logins = self.router.count("data/Login.json")
        await self.speedport.update_ip_data()
        self.assertEqual(self.router.count("data/IPData.json"), 3)
        self.assertEqual(self.router.count("data/Login.json"), logins)

    async def test_login_after_a_pause_is_not_repeated(self):
        """#19: once a pause was over and the login worked, an answer that is no
        session problem (404) left the pause in place, and every later request
        logged in again; on a Smart 3 polled every 30 min that was every 90 min."""
        self.router.pages["data/IPData.json"] = 1  # e.g. the session expired
        with self.assertRaises(LoginPausedError):
            await self.speedport.update_ip_data()
        await asyncio.sleep(PAUSE_OVER)
        self.router.missing = {"data/IPData.json"}
        await self.speedport.update_ip_data()  # logs in, then 404
        logins = self.router.count("data/Login.json")
        self.speedport._ip_data_retry_at = datetime.now()
        await self.speedport.update_ip_data()
        self.assertEqual(self.router.count("data/Login.json"), logins)

    async def test_login_answer_is_not_logged(self):
        """It carries more than the result, e.g. a t_password field."""
        with self.assertLogs("custom_components.speedport", "DEBUG") as logs:
            await self.speedport.login()
            with self.assertRaises(LoginException) as raised:
                await (await self.connect("wrong")).login()
        self.assertNotIn("ACCESS", "".join(logs.output) + str(raised.exception))
        self.assertIn("Can't login: failed", str(raised.exception))

    async def test_answer_with_another_key(self):
        self.router.wrong_key = True
        with self.assertRaises(LoginPausedError) as raised:
            await self.speedport.update_ip_data()
        self.assertIsInstance(raised.exception.__cause__, DecryptionKeyError)

    async def test_login_keeps_the_cookies(self):
        """As speedport-api always did; emptying the jar is suspected in #19."""
        cookie = next(iter(self.session.cookie_jar)).value
        await self.speedport.login()
        self.assertEqual([c.value for c in self.session.cookie_jar], [cookie])

    async def test_request_sequences_never_overlap(self):
        self.router.kick()  # includes a login
        self.speedport.set_pause_time(0)
        api = self.speedport.api
        calls = [api.get_status, api.get_devices, api.get_ip_data, api.reconnect]
        await asyncio.gather(*(call() for call in calls * 5), return_exceptions=True)
        self.assertEqual(self.router.max_inflight, 1)
        await self.speedport.update_ip_data()

    async def test_coordinator_keeps_status_while_login_is_paused(self):
        coordinator = SimpleNamespace(_speedport=self.speedport)
        self.router.kick()
        await SpeedportCoordinator._async_update_data(coordinator)  # pauses
        await SpeedportCoordinator._async_update_data(coordinator)  # paused

        self.router.pages["data/Status.json"] = 1
        with self.assertRaises(UpdateFailed):
            await SpeedportCoordinator._async_update_data(coordinator)
        self.router.missing = {"data/Status.json"}  # e.g. while it restarts
        with self.assertRaises(UpdateFailed):
            await SpeedportCoordinator._async_update_data(coordinator)
        await self.runner.cleanup()  # router gone
        with self.assertRaises(UpdateFailed):
            await SpeedportCoordinator._async_update_data(coordinator)


if __name__ == "__main__":
    unittest.main()
