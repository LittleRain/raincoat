"""CDP cookie dump → Playwright storageState conversion."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import import_state  # noqa: E402

DUMP = {
    "cookies": [
        {"name": "SESSION", "value": "abc", "domain": ".mktindex.com", "path": "/",
         "expires": 1790000000, "httpOnly": True, "secure": True, "sameSite": "Lax"},
        {"name": "other", "value": "x", "domain": ".example.com", "path": "/"},
        {"name": "MARKET", "value": "y", "domain": "market1.mktindex.com", "path": "/",
         "expires": -1, "sameSite": "weird"},
        {"name": "no-value", "domain": ".mktindex.com"},
    ]
}


class ConvertTests(unittest.TestCase):
    def test_keeps_only_mktindex(self):
        state = import_state.to_state(DUMP)
        names = {c["name"] for c in state["cookies"]}
        self.assertEqual(names, {"SESSION", "MARKET"})
        self.assertEqual(state["origins"], [])

    def test_session_cookie_expiry(self):
        state = import_state.to_state(DUMP)
        market = next(c for c in state["cookies"] if c["name"] == "MARKET")
        self.assertEqual(market["expires"], -1)

    def test_unknown_same_site_falls_back_to_lax(self):
        state = import_state.to_state(DUMP)
        market = next(c for c in state["cookies"] if c["name"] == "MARKET")
        self.assertEqual(market["sameSite"], "Lax")

    def test_bare_list_accepted(self):
        state = import_state.to_state([{"name": "A", "value": "1", "domain": "mktindex.com"}])
        self.assertEqual(len(state["cookies"]), 1)

    def test_no_match_raises(self):
        with self.assertRaises(ValueError):
            import_state.to_state({"cookies": [{"name": "x", "value": "1", "domain": ".foo.com"}]})

    def test_bad_payload_raises(self):
        with self.assertRaises(ValueError):
            import_state.to_state("nope")


if __name__ == "__main__":
    unittest.main()
