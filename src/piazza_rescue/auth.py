from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import browser_cookie3
from piazza_api.piazza import Piazza
from piazza_api.rpc import PiazzaRPC


SUPPORTED_BROWSERS = {
    "brave": browser_cookie3.brave,
    "chrome": browser_cookie3.chrome,
    "chromium": browser_cookie3.chromium,
    "edge": browser_cookie3.edge,
    "firefox": browser_cookie3.firefox,
    "opera": browser_cookie3.opera,
    "safari": browser_cookie3.safari,
    "vivaldi": browser_cookie3.vivaldi,
}


def load_cookies(
    cookie_file: str | None = None,
    cookie_string: str | None = None,
    browser: str | None = None,
) -> dict[str, str]:
    cookies: dict[str, str] = {}
    if browser:
        cookies.update(load_browser_cookies(browser))
    if cookie_file:
        cookies.update(load_cookies_from_file(Path(cookie_file)))
    if cookie_string:
        cookies.update(parse_cookie_string(cookie_string))
    return cookies


def load_browser_cookies(browser: str) -> dict[str, str]:
    loader = SUPPORTED_BROWSERS.get(browser.lower())
    if loader is None:
        available = ", ".join(sorted(SUPPORTED_BROWSERS))
        raise ValueError(f"Unsupported browser '{browser}'. Choose one of: {available}")
    jar = loader(domain_name="piazza.com")
    cookies: dict[str, str] = {}
    for cookie in jar:
        if "piazza.com" in cookie.domain:
            cookies[cookie.name] = cookie.value
    return cookies


def load_cookies_from_file(path: Path) -> dict[str, str]:
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return parse_cookie_string(raw)
    return parse_cookie_payload(parsed)


def parse_cookie_payload(payload: Any) -> dict[str, str]:
    if isinstance(payload, dict):
        if "cookies" in payload and isinstance(payload["cookies"], list):
            return _parse_cookie_list(payload["cookies"])
        return {
            str(name): str(value)
            for name, value in payload.items()
            if isinstance(name, str) and not isinstance(value, (dict, list)) and value is not None
        }
    if isinstance(payload, list):
        return _parse_cookie_list(payload)
    raise ValueError("Unsupported cookie payload format.")


def _parse_cookie_list(payload: Iterable[Any]) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        domain = item.get("domain", "")
        if name and value is not None and (not domain or "piazza.com" in str(domain)):
            cookies[str(name)] = str(value)
    return cookies


def parse_cookie_string(raw: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in raw.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name:
            cookies[name] = value
    return cookies


def build_piazza_client(cookies: dict[str, str]) -> tuple[Piazza, PiazzaRPC]:
    if not cookies:
        raise ValueError("No Piazza cookies were provided.")
    rpc = PiazzaRPC()
    rpc.set_cookies(cookies)
    return Piazza(rpc), rpc
