import io
import unittest
import zipfile

import package


def make_zip(members: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for k, v in members.items():
            zf.writestr(k, v)
    return buf.getvalue()


class ScannerTest(unittest.TestCase):
    def hit(self, text, name="f.txt"):
        return package.scan_bytes(name, text.encode("utf-8") if isinstance(text, str) else text)

    def test_clean(self):
        self.assertEqual(self.hit("Armory edits soldiers. Support: https://ko-fi.com/sajuuk2033 by Sajuuk"), [])

    def test_allowed_image_url(self):
        url = package.ALLOWED[-1]
        self.assertEqual(self.hit(f"[img]{url}[/img]"), [])

    def test_each_literal_hits_case_insensitive(self):
        # built from pieces so this test file itself stays clean when packaged
        j = "".join
        for s in [j(["AL", "EX"]), j(["Apo", "ggi94"]), j(["x@GM", "AIL.com"]), j(["id 3686", "9244"]),
                  j(["GoodLuck", "Claude"]), j(["C:", "\\Users\\bob"]), j(["c:", "/users/bob"]),
                  j(["F:", "\\Games"]), j(["Steam", "Library"]), j(["mod_", "3814488828"]),
                  j(["7656", "1198012345678"]), j(["D:", "/stuff"]), j(["name", "@example.org"])]:
            with self.subTest(s=s):
                self.assertTrue(self.hit("x " + s + " y"), s)

    def test_http_is_not_a_drive_path(self):
        self.assertEqual(self.hit("see https://example.org/x and http://127.0.0.1:8791/"), [])

    def test_hit_in_filename(self):
        self.assertTrue(package.scan_bytes("backups/GOODLUCK" + "CLAUDE.sav", b"clean"))

    def test_nested_zip_member_is_scanned(self):
        inner = make_zip({"status": "{name " + "GoodLuck" + "Claude}", "ok": "fine"})
        hits = package.scan_bytes("fixtures/a.sav", inner)
        self.assertTrue(any("a.sav!status" in h for h in hits))
        clean = make_zip({"status": "{name TESTCAMPAIGN}"})
        self.assertEqual(package.scan_bytes("fixtures/b.sav", clean), [])

    def test_doubly_nested_zip(self):
        deep = make_zip({"in.sav": make_zip({"s": "mod_" + "3814488828"})})
        self.assertTrue(package.scan_bytes("o.zip", deep))

    def test_utf16_text(self):
        self.assertTrue(package.scan_bytes("u.txt", ("hello apo" + "ggi").encode("utf-16-le")))

    def test_scan_zip_and_build_fail_path(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "t.zip"
            z.write_bytes(make_zip({"a.txt": "ok", "b.txt": "contact me" + "@x.org"}))
            self.assertTrue(package.scan_zip(z))
            ok = Path(d) / "ok.zip"
            ok.write_bytes(make_zip({"a.txt": "ok"}))
            self.assertEqual(package.scan_zip(ok), [])

    def test_allowlists_have_no_forbidden_files(self):
        everything = package.NEXUS_FILES + package.GITHUB_FILES
        for rel in everything:
            low = rel.lower()
            for bad in ("catalog.json", "config.json", "backups", "__pycache__", "armory-handoff", "dist/", ".tmp",
                        "modlog"):
                self.assertNotIn(bad, low)
        for rel in package.NEXUS_FILES:
            self.assertFalse(rel.startswith(("test_", "fixtures", "docs", "workshop", "nexus")), rel)

    def test_workshop_has_no_code(self):
        self.assertNotIn(".py", package.WORKSHOP_MOD_INFO)
        self.assertEqual(package.scan_bytes("mod.info", package.WORKSHOP_MOD_INFO.encode()), [])


if __name__ == "__main__":
    unittest.main()
