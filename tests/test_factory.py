"""Offline tests: no network, no model, no YouTube. python -m unittest discover -s tests -v"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toon import draw, pipeline, render, sets, writer, youtube  # noqa: E402


class WriterTests(unittest.TestCase):
    def test_sample_is_clean(self):
        ep = writer.clean(writer.SAMPLE)
        self.assertEqual(pipeline.review(ep), [])
        self.assertEqual(ep["location"], "tapri")

    def test_clean_fixes_unknown_directions(self):
        raw = json.loads(json.dumps(writer.SAMPLE))
        raw["lines"][0]["pose"] = "moonwalk"
        raw["lines"][1]["face"] = "?"
        raw["location"] = "mars"
        ep = writer.clean(raw)
        self.assertEqual(ep["lines"][0]["pose"], "talk")
        self.assertEqual(ep["lines"][1]["face"], "neutral")
        self.assertEqual(ep["location"], "tapri")

    def test_devanagari_caption_is_dropped(self):
        raw = json.loads(json.dumps(writer.SAMPLE))
        raw["lines"][0]["caption"] = raw["lines"][0]["hi"]
        self.assertEqual(len(writer.clean(raw)["lines"]), len(raw["lines"]) - 1)

    def test_review_catches_bad_words_and_politics(self):
        ep = writer.clean(writer.SAMPLE)
        ep["lines"][0]["caption"] = "Saala Pappu"
        ep["lines"][1]["caption"] = "BJP ki chai"
        probs = " ".join(pipeline.review(ep))
        self.assertIn("bad word", probs)
        self.assertIn("sensitive", probs)

    def test_review_ignores_substrings(self):
        ep = writer.clean(writer.SAMPLE)
        ep["lines"][0]["caption"] = "ABC wala dabba"  # contains 'bc' inside a word
        self.assertEqual(pipeline.review(ep), [])


class DrawTests(unittest.TestCase):
    def test_every_pose_face_prop_draws(self):
        pen = draw.Pen()
        for i, pose in enumerate(draw.POSES):
            sk = draw.skeleton(200 + (i % 3) * 300, draw.GROUND, pose, i * 0.3, 1 if i % 2 else -1, 1.0)
            draw.draw_character(pen, ["pappu", "golu", "chhotu"][i % 3], sk, draw.FACES[i % len(draw.FACES)], 1.0, 0.5, True,
                                draw.PROPS[i % len(draw.PROPS)])
            draw.draw_fx(pen, draw.FX[i % len(draw.FX)], sk["head"], sk["r"], 1.0, 0.2)
        self.assertEqual(pen.done().size, (draw.W, draw.STAGE_Y1 - draw.STAGE_Y0))

    def test_sets(self):
        for name in sets.LOCATIONS:
            self.assertEqual(sets.background(name).size, (draw.W, draw.H))


class RenderTests(unittest.TestCase):
    def test_frames_without_audio(self):
        ep = writer.clean(writer.SAMPLE)
        lines, t = [], 0.3
        for i in range(len(ep["lines"])):
            lines.append({"i": i, "start": t, "end": t + 2.0, "env": [0.5] * 60})
            t += 2.2
        plan = {"lines": lines, "end_lines": lines[-1]["end"], "total": lines[-1]["end"] + render.HOLD + render.OUTRO}
        sc = render.Scene(ep, plan)
        for tt in (0.1, 1.0, 5.0, plan["end_lines"] - 0.5, plan["end_lines"] + 0.3, plan["total"] - 0.2):
            self.assertEqual(sc.frame(tt).size, (draw.W, draw.H))

    def test_chunks(self):
        self.assertEqual(render.caption_chunks("ek do teen char paanch chhe saat"), ["ek do teen char paanch", "chhe saat"])

    def test_sfx_lengths(self):
        for name in ("pop", "boing", "rimshot", "jingle"):
            self.assertGreater(len(render.sfx(name)), 100)


class UploadBodyTests(unittest.TestCase):
    def test_body(self):
        body = youtube.build_body("Golu ki chai", "desc", ["a"], "private")
        self.assertIn("#Shorts", body["snippet"]["description"])
        self.assertEqual(body["snippet"]["categoryId"], "23")
        self.assertEqual(body["snippet"]["defaultAudioLanguage"], "hi")

    def test_job_id_validation(self):
        with self.assertRaises(ValueError):
            pipeline.job_dir("../../etc")


if __name__ == "__main__":
    unittest.main()
