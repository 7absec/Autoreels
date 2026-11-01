"""Offline tests for SEO, analytics weights, Telegram commands and Instagram captions. No network is used."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toon import analytics, config, instagram, seo, telegram, writer  # noqa: E402


class SeoTests(unittest.TestCase):
    def setUp(self):
        self.ep = writer.clean(writer.SAMPLE)

    def test_keyword_phrase_follows_festival(self):
        ep = dict(self.ep, description="Golu ki Diwali mithai")
        self.assertEqual(seo.keyword_phrase(ep), "Diwali Comedy Cartoon")

    def test_keyword_phrase_by_location(self):
        self.assertIn(seo.keyword_phrase(self.ep), seo.KW["phrases"]["tapri"])

    def test_tags_start_with_phrase_and_block_kids(self):
        with mock.patch.object(seo.vidiq, "extra_tags", return_value=["funny cartoon for kids", "motu patlu comedy", "desi jokes"]):
            tags = seo.tags(self.ep, "Cartoon Comedy Video")
        self.assertEqual(tags[0], "cartoon comedy video")
        self.assertNotIn("funny cartoon for kids", tags)
        self.assertFalse(any("motu" in t for t in tags))
        self.assertLess(sum(len(t) + 3 for t in tags), 500)

    def test_title_shape_without_network(self):
        with mock.patch.object(seo.provider, "chat_json", return_value={"hooks": ["Golu ko kainchi chahiye? ✂️", "Pappu ka chai jugaad"]}), \
             mock.patch.object(seo.vidiq, "call", return_value=None):
            t = seo.pick_title(self.ep)
        self.assertIn(" | ", t["title"])
        self.assertTrue(t["title"].endswith("#cartoon"))
        self.assertLessEqual(len(t["title"]), 100)

    def test_rule_score_prefers_short_question_with_name(self):
        self.assertGreater(seo.rule_score("Golu ko kainchi chahiye? ✂️", self.ep),
                           seo.rule_score("A VERY LONG TITLE WITHOUT ANY CHARACTER NAME AT ALL HERE OK", self.ep))

    def test_srt(self):
        tl = {"lines": [{"start": 0.1 + i * 3, "end": 2.9 + i * 3} for i in range(len(self.ep["lines"]))]}
        out = seo.srt(self.ep, tl)
        self.assertIn("00:00:00,100 --> 00:00:02,900", out)
        self.assertIn(self.ep["lines"][0]["hi"], out)


class AnalyticsTests(unittest.TestCase):
    def test_weight_needs_enough_videos(self):
        data = {"by_location": {"school": {"n": 2, "view_pct": 90}, "tapri": {"n": 5, "view_pct": 40}}}
        with mock.patch.object(analytics, "load", return_value=data):
            self.assertEqual(analytics.weight("by_location", "school", "view_pct"), 1.0)

    def test_weight_is_bounded(self):
        data = {"by_location": {"school": {"n": 5, "view_pct": 90}, "tapri": {"n": 5, "view_pct": 10}}}
        with mock.patch.object(analytics, "load", return_value=data):
            self.assertLessEqual(analytics.weight("by_location", "school", "view_pct"), 2.0)
            self.assertGreaterEqual(analytics.weight("by_location", "tapri", "view_pct"), 0.5)


class TelegramTests(unittest.TestCase):
    def test_commands_without_network(self):
        sent = []
        with mock.patch.object(telegram, "send", side_effect=lambda t, c=None: sent.append(t) or True), \
             tempfile.TemporaryDirectory() as tmp, mock.patch.object(telegram, "PAUSE_FLAG", Path(tmp) / "paused"):
            telegram.handle("/pause", "1")
            self.assertTrue((Path(tmp) / "paused").exists())
            telegram.handle("/status", "1")
            telegram.handle("/resume", "1")
            self.assertFalse((Path(tmp) / "paused").exists())
            telegram.handle("/nonsense", "1")
        self.assertIn("PAUSED", sent[1])
        self.assertIn("/status", sent[-1])

    def test_send_is_quiet_without_token(self):
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}):
            self.assertFalse(telegram.send("hi"))


class InstagramTests(unittest.TestCase):
    def test_caption(self):
        jid = next((p.name for p in config.OUTPUT.iterdir() if (p / "meta.json").exists() and (p / "episode.json").exists()), None)
        if not jid:
            self.skipTest("no rendered job on this machine")
        cap = instagram.caption(jid)
        self.assertIn("#autoreels", cap)
        self.assertLessEqual(len(cap), 2200)

    def test_off_does_nothing(self):
        with mock.patch.dict(os.environ, {"IG_MODE": "off"}):
            self.assertEqual(instagram.publish_due(), [])


if __name__ == "__main__":
    unittest.main()
