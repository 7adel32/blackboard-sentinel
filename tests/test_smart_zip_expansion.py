import io
import os
import pathlib
import stat
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import check_lms


def _write_zip(path, entries, *, flag_bits=0, external_attr=0):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zi = zipfile.ZipInfo(name, date_time=(2026, 3, 1, 10, 0, 0))
            if flag_bits:
                zi.flag_bits |= flag_bits
            if external_attr:
                zi.external_attr = external_attr
            zf.writestr(zi, data)


class TestSmartZipExpansion(unittest.TestCase):
    def _run_expand(self, zip_path, *, delete_zip=False, bb_ts=None, allow_overwrite=False):
        with mock.patch.object(check_lms, "EXPAND_ZIPS", True), \
             mock.patch.object(check_lms, "DELETE_ORIGINAL_ZIP", delete_zip):
            return check_lms.expand_zip_archive(
                zip_path, bb_ts=bb_ts, allow_overwrite=allow_overwrite
            )

    def test_single_matching_folder_unwraps_redundant_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            zp = os.path.join(tmp, "folder.zip")
            _write_zip(zp, [
                ("folder/a.pdf", b"pdf-a"),
                ("folder/sub/b.txt", b"txt-b"),
            ])
            dest = self._run_expand(zp, delete_zip=True)
            self.assertEqual(dest, os.path.join(tmp, "folder_zip"))
            self.assertTrue(os.path.isfile(os.path.join(dest, "a.pdf")))
            self.assertTrue(os.path.isfile(os.path.join(dest, "sub", "b.txt")))
            self.assertFalse(os.path.exists(os.path.join(dest, "folder")))
            self.assertFalse(os.path.exists(zp))

    def test_single_differently_named_folder_preserved_inside_stem_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            zp = os.path.join(tmp, "week3.zip")
            _write_zip(zp, [
                ("Lab_Sockets/server.py", b"print('hi')"),
                ("Lab_Sockets/readme.txt", b"lab3"),
            ])
            dest = self._run_expand(zp)
            self.assertEqual(dest, os.path.join(tmp, "week3_zip"))
            self.assertTrue(os.path.isfile(os.path.join(dest, "Lab_Sockets", "server.py")))
            self.assertTrue(os.path.isfile(os.path.join(dest, "Lab_Sockets", "readme.txt")))

    def test_collapses_multilevel_single_child_directory_chains(self):
        with tempfile.TemporaryDirectory() as tmp:
            zp = os.path.join(tmp, "week3.zip")
            _write_zip(zp, [
                ("week3/export/Lab_Sockets/a.py", b"a"),
                ("week3/export/Lab_Sockets/b.py", b"b"),
            ])
            dest = self._run_expand(zp)
            self.assertEqual(dest, os.path.join(tmp, "week3_zip"))
            self.assertTrue(os.path.isfile(os.path.join(dest, "Lab_Sockets", "a.py")))
            self.assertTrue(os.path.isfile(os.path.join(dest, "Lab_Sockets", "b.py")))
            self.assertFalse(os.path.exists(os.path.join(dest, "week3")))
            self.assertFalse(os.path.exists(os.path.join(dest, "export")))

    def test_multiple_top_level_documents_stay_in_stem_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            zp = os.path.join(tmp, "materials.zip")
            _write_zip(zp, [
                ("one.pdf", b"1"),
                ("two.docx", b"2"),
                ("extra/three.txt", b"3"),
            ])
            dest = self._run_expand(zp)
            self.assertEqual(dest, os.path.join(tmp, "materials_zip"))
            self.assertTrue(os.path.isfile(os.path.join(dest, "one.pdf")))
            self.assertTrue(os.path.isfile(os.path.join(dest, "two.docx")))
            self.assertTrue(os.path.isfile(os.path.join(dest, "extra", "three.txt")))

    def test_generic_single_document_stays_inside_stem_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            zp = os.path.join(tmp, "Week_04_Slides.zip")
            _write_zip(zp, [
                ("Week_04_Slides/slides.pdf", b"slides-data"),
                ("__MACOSX/._slides.pdf", b"junk"),
                (".DS_Store", b"junk"),
            ])
            dest = self._run_expand(zp, delete_zip=True)
            self.assertEqual(dest, os.path.join(tmp, "Week_04_Slides_zip"))
            self.assertTrue(os.path.isfile(os.path.join(dest, "slides.pdf")))
            self.assertFalse(os.path.exists(os.path.join(tmp, "slides.pdf")))
            self.assertFalse(os.path.exists(os.path.join(dest, "__MACOSX")))
            self.assertFalse(os.path.exists(os.path.join(dest, ".DS_Store")))

    def test_descriptive_or_matching_single_document_unwraps_directly(self):
        with tempfile.TemporaryDirectory() as tmp:
            zp = os.path.join(tmp, "Week_04_Slides.zip")
            _write_zip(zp, [
                ("Week_04_Slides/Week_04_Slides.pdf", b"real-pdf"),
                ("Thumbs.db", b"junk"),
            ])
            dest = self._run_expand(zp, delete_zip=True, bb_ts=1700000000)
            expected = os.path.join(tmp, "Week_04_Slides.pdf")
            self.assertEqual(dest, expected)
            self.assertTrue(os.path.isfile(expected))
            self.assertFalse(os.path.exists(os.path.join(tmp, "Week_04_Slides_zip")))
            self.assertFalse(os.path.exists(zp))
            self.assertAlmostEqual(os.path.getmtime(expected), 1700000000, delta=2)

    def test_empty_and_directory_stub_only_zips_are_not_extracted_or_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty_zp = os.path.join(tmp, "empty.zip")
            _write_zip(empty_zp, [])
            self.assertIsNone(self._run_expand(empty_zp, delete_zip=True))
            self.assertTrue(os.path.isfile(empty_zp))
            self.assertFalse(os.path.exists(os.path.join(tmp, "empty_zip")))

            dirs_zp = os.path.join(tmp, "dirs_only.zip")
            _write_zip(dirs_zp, [("only_dir/", b""), ("only_dir/nested/", b""), ("__MACOSX/.DS_Store", b"x")])
            self.assertIsNone(self._run_expand(dirs_zp, delete_zip=True))
            self.assertTrue(os.path.isfile(dirs_zp))
            self.assertFalse(os.path.exists(os.path.join(tmp, "dirs_only_zip")))

    def test_encrypted_and_corrupt_zips_remain_zipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            enc_zp = os.path.join(tmp, "secret.zip")
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("secret.pdf", b"cipher")
            raw = bytearray(buf.getvalue())
            lfh = raw.index(b"PK\x03\x04")
            cdh = raw.index(b"PK\x01\x02")
            raw[lfh + 6] |= 0x01
            raw[cdh + 8] |= 0x01
            with open(enc_zp, "wb") as f:
                f.write(raw)

            self.assertIsNone(self._run_expand(enc_zp, delete_zip=True))
            self.assertTrue(os.path.isfile(enc_zp))
            self.assertFalse(os.path.exists(os.path.join(tmp, "secret_zip")))

            bad_zp = os.path.join(tmp, "corrupt.zip")
            with open(bad_zp, "wb") as f:
                f.write(b"not a real zip archive")
            self.assertIsNone(self._run_expand(bad_zp, delete_zip=True))
            self.assertTrue(os.path.isfile(bad_zp))

    def test_nested_zips_expand_recursively_with_depth_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            inner1_buf = io.BytesIO()
            with zipfile.ZipFile(inner1_buf, "w") as zf:
                zf.writestr("Lab1/code.py", b"print(1)")

            inner2_buf = io.BytesIO()
            with zipfile.ZipFile(inner2_buf, "w") as zf:
                zf.writestr("Lab2_Guide.pdf", b"guide2")

            outer_zp = os.path.join(tmp, "All_Labs.zip")
            _write_zip(outer_zp, [
                ("Lab1.zip", inner1_buf.getvalue()),
                ("Lab2.zip", inner2_buf.getvalue()),
            ])
            dest = self._run_expand(outer_zp, delete_zip=True)
            self.assertEqual(dest, os.path.join(tmp, "All_Labs_zip"))
            self.assertTrue(os.path.isfile(os.path.join(dest, "Lab1_zip", "code.py")))
            self.assertTrue(os.path.isfile(os.path.join(dest, "Lab2_Guide.pdf")))
            self.assertFalse(os.path.exists(os.path.join(dest, "Lab1.zip")))
            self.assertFalse(os.path.exists(os.path.join(dest, "Lab2.zip")))

    def test_single_doc_collision_does_not_clobber_unrelated_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = os.path.join(tmp, "CSC101_Report.pdf")
            with open(existing, "wb") as f:
                f.write(b"existing-unrelated-file")

            zp = os.path.join(tmp, "Submission_2.zip")
            _write_zip(zp, [("CSC101_Report.pdf", b"new-different-content")])

            dest = self._run_expand(zp, allow_overwrite=False)
            self.assertEqual(dest, os.path.join(tmp, "Submission_2_zip"))
            self.assertTrue(os.path.isfile(os.path.join(dest, "CSC101_Report.pdf")))
            with open(existing, "rb") as f:
                self.assertEqual(f.read(), b"existing-unrelated-file")

            dest_overwrite = self._run_expand(zp, allow_overwrite=True)
            self.assertEqual(dest_overwrite, existing)
            with open(existing, "rb") as f:
                self.assertEqual(f.read(), b"new-different-content")

    def test_security_zip_slip_symlinks_reserved_names_and_cp1256(self):
        with tempfile.TemporaryDirectory() as tmp:
            zp = os.path.join(tmp, "edge.zip")
            arabic_bytes = "محاضرة.txt".encode("cp1256")
            placeholder = b"A" * (len(arabic_bytes) - 4) + b".txt"
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("../../outside.txt", b"bad")
                zf.writestr("CON.txt", b"reserved")
                zf.writestr("bad:name?.txt", b"chars")
                zi_sym = zipfile.ZipInfo("link.txt")
                zi_sym.external_attr = (stat.S_IFLNK | 0o777) << 16
                zf.writestr(zi_sym, b"/etc/passwd")
                zf.writestr(placeholder.decode("ascii"), b"arabic-content")
            raw = buf.getvalue().replace(placeholder, arabic_bytes)
            with open(zp, "wb") as f:
                f.write(raw)

            dest = self._run_expand(zp)
            self.assertEqual(dest, os.path.join(tmp, "edge_zip"))
            self.assertFalse(os.path.exists(os.path.join(tmp, "outside.txt")))
            self.assertFalse(os.path.exists(os.path.join(dest, "link.txt")))
            self.assertTrue(os.path.isfile(os.path.join(dest, "_CON.txt")))
            self.assertTrue(os.path.isfile(os.path.join(dest, "bad_name_.txt")))
            self.assertTrue(os.path.isfile(os.path.join(dest, "محاضرة.txt")))

    def test_zip_bomb_aborted_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            zp = os.path.join(tmp, "bomb.zip")
            _write_zip(zp, [("huge.bin", b"A" * 1024)])
            with mock.patch.object(check_lms, "_ZIP_MAX_BYTES", 100):
                self.assertIsNone(self._run_expand(zp, delete_zip=True))
            self.assertTrue(os.path.isfile(zp))
            self.assertFalse(os.path.exists(os.path.join(tmp, "bomb_zip")))

    def test_state_recording_and_course_merge_for_unwrapped_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = os.path.join(tmp, "CS101")
            os.makedirs(course_dir, exist_ok=True)
            unwrapped = os.path.join(course_dir, "Lectures", "Week1.pdf")
            os.makedirs(os.path.dirname(unwrapped), exist_ok=True)
            with open(unwrapped, "wb") as f:
                f.write(b"pdf")

            expanded_zips = {}
            key = "c1_i1_f1_Week1.zip"
            check_lms._record_expanded_zip_path(expanded_zips, key, course_dir, unwrapped)
            self.assertEqual(expanded_zips[key], os.path.join("Lectures", "Week1.pdf"))

            resolved = check_lms._resolve_recorded_zip_path(
                expanded_zips, key, course_dir,
                fallback_zip_path=os.path.join(course_dir, "Lectures", "Week1.zip"),
            )
            self.assertEqual(resolved, unwrapped)

            global_state = {"expanded_zips": {}}
            check_lms._merge_course_state(global_state, {"expanded_zips": expanded_zips})
            self.assertEqual(global_state["expanded_zips"][key], os.path.join("Lectures", "Week1.pdf"))


if __name__ == "__main__":
    unittest.main()
