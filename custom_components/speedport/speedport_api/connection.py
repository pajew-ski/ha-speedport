import asyncio
import json
import logging
import re
from hashlib import sha256
from json import JSONDecodeError

import aiohttp
from Crypto.Cipher import AES

from . import const, exceptions

_LOGGER = logging.getLogger(__name__)


def decode(data, key: str = "") -> dict[str, list | dict | str] | str:
    """Decode speedport's self-implemented encryption"""
    key = key or const.DEFAULT_KEY
    try:
        ciphertext_tag = bytes.fromhex(data)
    except ValueError as exc:
        raise exceptions.UnexpectedResponseError(
            "Router answered with a page instead of data"
        ) from exc
    cipher = AES.new(bytes.fromhex(key), AES.MODE_CCM, bytes.fromhex(key)[:8])
    try:
        decrypted = cipher.decrypt_and_verify(
            ciphertext_tag[:-16], ciphertext_tag[-16:]
        )
    except ValueError as exc:  # "MAC check failed"
        raise exceptions.DecryptionKeyError("Wrong decryption key") from exc
    try:
        return simplify_response(json.loads(decrypted.decode()))
    except JSONDecodeError:
        return decrypted.decode()


def encode(data, key: str = "") -> str:
    """Encode for speedport's self-implemented encryption"""
    key = key or const.DEFAULT_KEY
    cipher = AES.new(bytes.fromhex(key), AES.MODE_CCM, bytes.fromhex(key)[:8])
    ciphertext, tag = cipher.encrypt_and_digest(data.encode())
    return ciphertext.hex() + tag.hex()


def simplify_response(
    data: list[dict[str, str | list[dict[str, str]]]],
) -> dict[str, list | dict | str]:
    """Remove 'varid' and 'varvalue' to have a flatter data structure without overhead"""
    result = {}
    for item in data:
        if isinstance(item["varvalue"], list):
            list_item = {}
            for sub_item in item["varvalue"]:
                list_item[sub_item["varid"]] = sub_item["varvalue"]
            result.setdefault(item["varid"], []).append(list_item)
        else:
            result[item["varid"]] = item["varvalue"]
    return result


class Connection:
    def __init__(self, host_url: str, session: aiohttp.ClientSession):
        """The session needs a cookie jar that accepts cookies from IP hosts
        (aiohttp.CookieJar(unsafe=True)); the caller owns and closes it."""
        self._login_key = ""
        self._url = host_url
        self._session = session
        # The router's https certificate is self-signed.
        self._kwargs = {"ssl": False, "timeout": aiohttp.ClientTimeout(total=30)}

    @staticmethod
    async def _decode(response: aiohttp.ClientResponse, key: str = ""):
        try:
            return decode(await response.text(), key=key)
        except exceptions.UnexpectedResponseError as exc:
            raise exceptions.UnexpectedResponseError(
                f"{response.url.path} answered HTTP {response.status} with a page "
                "instead of data (not logged in or not available)"
            ) from exc

    async def get(self, path: str, auth: bool = False, referer: str = ""):
        url = f"{self._url}/{path}"
        if referer:
            referer = f"{self._url}/{referer}"
            if token := await self._get_httoken(referer):
                url += f"?_tn={token}"
        async with self._session.get(
            url, headers={"Referer": referer}, **self._kwargs
        ) as response:
            _LOGGER.debug("GET - %s - %s", url, response.status)
            key = self._login_key if auth else const.DEFAULT_KEY
            return await self._decode(response, key)

    async def post(self, path: str, data: dict[str, str], referer: str):
        url = f"{self._url}/{path}"
        referer = f"{self._url}/{referer}"
        if token := await self._get_httoken(referer):
            data.update({"httoken": token})
        data = "&".join([f"{k}={v}" for k, v in data.items()])
        data = encode(data, key=self._login_key)
        async with self._session.post(
            url, headers={"Referer": referer}, data=data, **self._kwargs
        ) as response:
            _LOGGER.debug("POST - %s - %s", url, response.status)
            return await self._decode(response, self._login_key)

    async def _get_httoken(self, url: str) -> str:
        async with self._session.get(url, **self._kwargs) as response:
            _LOGGER.debug("GET - %s - %s", url, response.status)
            if token := re.findall("httoken = (\\d+)", await response.text()):
                return token[0]
            return ""

    async def _get_challenge(self) -> str:
        response = await self.post("data/Login.json", {"getChallenge": "1"}, "/")
        try:
            return response["challenge"]
        except (KeyError, TypeError) as exc:
            raise exceptions.UnexpectedResponseError(
                f"No login challenge in {response!r}"
            ) from exc

    async def login(self, password: str):
        url = f"{self._url}/data/Login.json"
        self.clear()
        challenge = await self._get_challenge()
        login_key = sha256(f"{challenge}:{password}".encode()).hexdigest()
        data = encode("showpw=0&password=" + login_key)
        async with self._session.post(url, data=data, **self._kwargs) as response:
            _LOGGER.debug("POST - %s - %s", url, response.status)
            result = await self._decode(response)
            _LOGGER.debug(result)
        if not isinstance(result, dict):
            raise exceptions.UnexpectedResponseError(f"No login result in {result!r}")
        if (sleep_time := result.get("login_locked")) and int(sleep_time) < 60:
            _LOGGER.warning("Can't login, wait %ss...", sleep_time)
            await asyncio.sleep(int(sleep_time) + 1)
            return await self.login(password)
        if result.get("login") != "success":
            raise exceptions.LoginException(f"Can't login: {result}")
        # Only now: is_logged_in must not be true for a login that failed halfway.
        self._login_key = challenge
        return result["login"]

    @property
    def is_logged_in(self):
        return bool(self._login_key)

    def clear(self):
        # The cookies stay, as they always did with speedport-api (its
        # clear_domain(url) never matched). Emptying the jar before the login is
        # the suspected cause of a login without a usable session on the Smart 3
        # (#19).
        self._login_key = ""
