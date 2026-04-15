from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin


URL_RE = re.compile(r"https?://[^\s<>'\"]+")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(dt: datetime | None = None) -> str:
    value = dt or utc_now()
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stamp_for_path(dt: datetime | None = None) -> str:
    value = dt or utc_now()
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def append_jsonl(path: Path, payload: Any) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def slugify(value: str, fallback: str = "file") -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_value).strip("-._")
    return safe or fallback


def listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def first_nonempty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        return value
    return None


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._href_stack: list[str | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag in {"br", "p", "div", "li", "tr"}:
            self.parts.append("\n")
        if tag == "a":
            self._href_stack.append(attr_map.get("href"))
        elif tag in {"img", "source"} and attr_map.get("src"):
            self.links.append((attr_map["src"] or "", ""))

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href_stack:
            self._href_stack.pop()
        if tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not data:
            return
        self.parts.append(data)
        if self._href_stack and self._href_stack[-1]:
            self.links.append((self._href_stack[-1] or "", data.strip()))


def html_to_text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        return str(value)
    if "<" not in value and "&" not in value:
        return value.strip()
    parser = _HTMLTextExtractor()
    parser.feed(value)
    text = unescape(" ".join(part.strip() for part in parser.parts if part.strip()))
    return re.sub(r"\s+", " ", text).strip()


def extract_html_links(value: Any) -> list[tuple[str, str]]:
    if value is None or not isinstance(value, str) or "<" not in value:
        return []
    parser = _HTMLTextExtractor()
    parser.feed(value)
    return [(normalize_url(url), text.strip()) for url, text in parser.links if normalize_url(url)]


def extract_urls(value: Any) -> list[str]:
    if value is None or not isinstance(value, str):
        return []
    urls = [normalize_url(match) for match in URL_RE.findall(value)]
    return [url for url in urls if url]


def normalize_url(url: str | None) -> str:
    if not url:
        return ""
    clean = url.strip().strip("\"'()[],")
    if clean.startswith("//"):
        return "https:" + clean
    if clean.startswith("/"):
        return urljoin("https://piazza.com", clean)
    if clean.startswith("http://") or clean.startswith("https://"):
        return clean
    return ""
