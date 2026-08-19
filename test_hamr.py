"""Тесты: hamr.compress() должен бит-в-бит совпадать с оригинальным compress() из ha.mr.

Эталонные векторы (test_vectors.json) сгенерированы оригинальным JS-кодом
из репозитория ha.mr через gen_vectors.mjs (Node.js). Перегенерировать:
    python extract_js.py && python build_data.py && node gen_vectors.mjs

Запуск:  python test_hamr.py   (или: python -m unittest test_hamr -v)
"""

import json
import unittest
from pathlib import Path

import hamr
from hamr_data import (
    OUTPUT_ALPHABET_ASCII,
    OUTPUT_ALPHABET_QR,
    OUTPUT_ALPHABET_EMOJI,
)

ROOT = Path(__file__).parent
VECTORS = json.loads((ROOT / "test_vectors.json").read_text(encoding="utf-8"))
# Дополнительные наборы, если были сгенерированы (gen_fuzz.mjs / edge-прогон)
for extra in ("fuzz_vectors.json", "edge_vectors.json"):
    p = ROOT / extra
    if p.exists():
        VECTORS.extend(json.loads(p.read_text(encoding="utf-8")))

DEVECTORS_FILE = ROOT / "decompress_vectors.json"
DEVECTORS = (
    json.loads(DEVECTORS_FILE.read_text(encoding="utf-8"))
    if DEVECTORS_FILE.exists()
    else []
)
ALPHABETS = {
    "ascii": OUTPUT_ALPHABET_ASCII,
    "qr": OUTPUT_ALPHABET_QR,
    "emoji": OUTPUT_ALPHABET_EMOJI,
}


class TestAgainstOriginalVectors(unittest.TestCase):
    """Каждый вектор — это вход + payload, посчитанный оригинальным JS."""

    def test_ascii_payloads_match(self):
        fails = []
        for v in VECTORS:
            if "error" in v:
                continue
            try:
                got = hamr.compress(v["input"], OUTPUT_ALPHABET_ASCII)
            except hamr.HamrError as e:
                fails.append((v["input"], f"raised {e}", v["ascii"]))
                continue
            if got != v["ascii"]:
                fails.append((v["input"], got, v["ascii"]))
        self.assertEqual(fails, [])

    def test_qr_payloads_match(self):
        fails = []
        for v in VECTORS:
            if "error" in v or "qr" not in v:
                continue
            try:
                got = hamr.compress(v["input"], OUTPUT_ALPHABET_QR)
            except hamr.HamrError as e:
                fails.append((v["input"], f"raised {e}", v["qr"]))
                continue
            if got != v["qr"]:
                fails.append((v["input"], got, v["qr"]))
        self.assertEqual(fails, [])

    def test_emoji_payloads_match(self):
        fails = []
        for v in VECTORS:
            if "error" in v or "emoji" not in v:
                continue
            try:
                got = hamr.compress(v["input"], OUTPUT_ALPHABET_EMOJI)
            except hamr.HamrError as e:
                fails.append((v["input"], f"raised {e}", v["emoji"]))
                continue
            if got != v["emoji"]:
                fails.append((v["input"], got, v["emoji"]))
        self.assertEqual(fails, [])

    def test_full_short_link_matches(self):
        """shorten() == 'http://ha.mr#' + payload (формат сайта)."""
        for v in VECTORS:
            if "error" in v or "link" not in v:
                continue
            with self.subTest(input=v["input"]):
                self.assertEqual(hamr.shorten(v["input"]), v["link"])

    def test_invalid_inputs_raise(self):
        """Оригинал падает -> наш порт тоже обязан упасть (HamrError)."""
        for v in VECTORS:
            if "error" not in v:
                continue
            with self.subTest(input=v["input"]):
                with self.assertRaises(hamr.HamrError):
                    hamr.compress(v["input"], OUTPUT_ALPHABET_ASCII)


class TestDecompressAgainstOriginal(unittest.TestCase):
    """decompress() сверяется с оригинальным decompress() из ha.mr (JS)."""

    def test_decompress_payloads_match(self):
        fails = []
        for row in DEVECTORS:
            if "error" in row:
                continue
            try:
                got = hamr.decompress(row["payload"], ALPHABETS[row["alphabet"]])
            except hamr.HamrError as e:
                fails.append((row["payload"], f"raised {e}", row["expected"]))
                continue
            if got != row["expected"]:
                fails.append((row["payload"], got, row["expected"]))
        self.assertEqual(fails, [])

    def test_decompress_invalid_payloads_raise(self):
        for row in DEVECTORS:
            if "error" not in row:
                continue
            with self.subTest(payload=row["payload"]):
                with self.assertRaises(hamr.HamrError):
                    hamr.decompress(row["payload"], ALPHABETS[row["alphabet"]])

    def test_roundtrip_python_only(self):
        """decompress(compress(x)) == результату оригинального decompress."""
        for v in VECTORS:
            if "error" in v or "roundtrip" not in v:
                continue
            with self.subTest(input=v["input"]):
                payload = hamr.compress(v["input"], OUTPUT_ALPHABET_ASCII)
                self.assertEqual(hamr.decompress(payload), v["roundtrip"])

    def test_unshorten_roundtrip(self):
        for v in VECTORS:
            if "error" in v or "link" not in v:
                continue
            with self.subTest(input=v["input"]):
                self.assertEqual(hamr.unshorten(v["link"]), v["roundtrip"])


class TestEdgeSemantics(unittest.TestCase):
    """Точечные проверки семантики, сверённые с поведением Node/JS."""

    def test_equivalent_inputs_give_equal_payloads(self):
        # http://example.com, example.com, http://example.com/ — одно и то же
        base = hamr.compress("example.com")
        self.assertEqual(hamr.compress("http://example.com"), base)
        self.assertEqual(hamr.compress("http://example.com/"), base)
        self.assertEqual(hamr.compress("EXAMPLE.COM"), base)

    def test_https_differs_from_http(self):
        self.assertNotEqual(hamr.compress("https://example.com"),
                            hamr.compress("http://example.com"))

    def test_malformed_percent_raises(self):
        # decodeURI бросает URIError на lone '%' -> "Invalid link"
        with self.assertRaises(hamr.HamrError):
            hamr.compress("example.com/?q=100%")

    def test_empty_input_raises(self):
        with self.assertRaises(hamr.HamrError):
            hamr.compress("")

    def test_scheme_like_prefix_swallowed(self):
        # URL.canParse('example.com:8080/path') === true в JS:
        # 'example.com:' трактуется как схема, порт НЕ распознаётся
        self.assertEqual(hamr.compress("example.com:8080/path"),
                         hamr.compress("example.com:8080/path"))  # не падает
        self.assertNotEqual(hamr.compress("example.com:8080/path"),
                            hamr.compress("http://example.com:8080/path"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
