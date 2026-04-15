from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from piazza_rescue.auth import load_cookies_from_file, parse_cookie_payload, parse_cookie_string


class AuthTests(unittest.TestCase):
    def test_parse_cookie_string(self) -> None:
        cookies = parse_cookie_string("session_id=abc; piazza_session=def")
        self.assertEqual(cookies["session_id"], "abc")
        self.assertEqual(cookies["piazza_session"], "def")

    def test_parse_cookie_payload_dict(self) -> None:
        cookies = parse_cookie_payload({"session_id": "abc", "piazza_session": "def"})
        self.assertEqual(cookies["session_id"], "abc")
        self.assertEqual(cookies["piazza_session"], "def")

    def test_parse_cookie_payload_list(self) -> None:
        cookies = parse_cookie_payload(
            [
                {"name": "session_id", "value": "abc", "domain": ".piazza.com"},
                {"name": "irrelevant", "value": "zzz", "domain": ".example.com"},
            ]
        )
        self.assertEqual(cookies, {"session_id": "abc"})

    def test_load_cookie_file_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cookies.json"
            path.write_text(json.dumps({"session_id": "abc"}), encoding="utf-8")
            cookies = load_cookies_from_file(path)
        self.assertEqual(cookies["session_id"], "abc")


if __name__ == "__main__":
    unittest.main()
