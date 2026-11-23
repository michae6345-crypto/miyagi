"""shared/capture_file.py, offline: the engine's reader for the app's circle-to-ask capture.

Run: python -m unittest shared/tests/test_capture_file.py  (or pytest). The end-to-end case (the real helper's file,
read and deleted by this reader) is in app/native/listen/test-capture.py."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
import unittest
import uuid

from shared.capture_file import capture_dirs, crop_to_screen, take_capture

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"


class TakeCapture(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tempfile.mkdtemp(prefix="miyagi-capfile-")
        self.dir = os.path.join(self.root, "miyagi-capture")
        os.mkdir(self.dir, 0o700)
        os.chmod(self.dir, 0o700)
        self.dirs = [self.dir]

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def put(self, data: bytes = JPEG, mode: int = 0o600, name: str | None = None) -> str:
        p = os.path.join(self.dir, name or f"cap-{uuid.uuid4()}.jpg")
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        os.write(fd, data)
        os.close(fd)
        os.chmod(p, mode)
        return p

    def cap(self, path: str, **kw: object) -> dict:
        return {"path": path, "w": 520, "h": 260, "rect": {"x": 70, "y": 85, "w": 260, "h": 130}, "displayId": 1, **kw}

    def test_good_capture_is_read_and_deleted(self) -> None:
        p = self.put()
        c = take_capture(self.cap(p), dirs=self.dirs)
        self.assertIsNotNone(c)
        assert c is not None
        self.assertEqual((c.jpeg, c.w, c.h, c.rect, c.displayId), (JPEG, 520, 260, (70.0, 85.0, 260.0, 130.0), 1))
        self.assertFalse(os.path.exists(p))

    def test_pydantic_like_object(self) -> None:
        class R:
            x, y, w, h = 0, 0, 10, 10

        class C:
            path, w, h, rect, displayId = self.put(), 20, 20, R(), 3

        c = take_capture(C(), dirs=self.dirs)
        self.assertIsNotNone(c)

    def test_none_and_junk(self) -> None:
        self.assertIsNone(take_capture(None, dirs=self.dirs))
        self.assertIsNone(take_capture({}, dirs=self.dirs))
        self.assertIsNone(take_capture("x", dirs=self.dirs))

    def test_bad_mode_is_refused_but_still_deleted(self) -> None:
        p = self.put(mode=0o644)
        self.assertIsNone(take_capture(self.cap(p), dirs=self.dirs))
        self.assertFalse(os.path.exists(p))

    def test_not_a_jpeg(self) -> None:
        p = self.put(data=b"GIF89a....")
        self.assertIsNone(take_capture(self.cap(p), dirs=self.dirs))
        self.assertFalse(os.path.exists(p))

    def test_bad_fields_refused_and_deleted(self) -> None:
        for bad in ({"w": 0}, {"w": 1093}, {"h": 1.5}, {"w": True}, {"rect": {"x": 0, "y": 0, "w": 0, "h": 5}},
                    {"rect": {"x": 0, "y": 0, "w": float("nan"), "h": 5}}, {"rect": None}, {"displayId": -1},
                    {"displayId": "1"}):
            p = self.put()
            self.assertIsNone(take_capture(self.cap(p, **bad), dirs=self.dirs), bad)
            self.assertFalse(os.path.exists(p), bad)

    def test_wrong_name_or_folder_is_never_touched(self) -> None:
        other = os.path.join(self.root, f"cap-{uuid.uuid4()}.jpg")
        with open(other, "wb") as f:
            f.write(JPEG)
        os.chmod(other, 0o600)
        odd = self.put(name="photo.jpg")
        for p in (other, odd, os.path.join(self.dir, "..", os.path.basename(other)), "relative/cap-x.jpg"):
            self.assertIsNone(take_capture(self.cap(p), dirs=self.dirs), p)
        self.assertTrue(os.path.exists(other))
        self.assertTrue(os.path.exists(odd))

    def test_symlink_is_refused_and_target_kept(self) -> None:
        target = os.path.join(self.root, "secret.jpg")
        with open(target, "wb") as f:
            f.write(JPEG)
        link = os.path.join(self.dir, f"cap-{uuid.uuid4()}.jpg")
        os.symlink(target, link)
        self.assertIsNone(take_capture(self.cap(link), dirs=self.dirs))
        self.assertTrue(os.path.exists(target))

    def test_hard_link_is_refused(self) -> None:
        p = self.put()
        os.link(p, os.path.join(self.root, "kept.jpg"))
        self.assertIsNone(take_capture(self.cap(p), dirs=self.dirs))
        self.assertFalse(os.path.exists(p))

    def test_open_folder_is_refused(self) -> None:
        p = self.put()
        os.chmod(self.dir, 0o755)
        self.assertIsNone(take_capture(self.cap(p), dirs=self.dirs))

    def test_missing_file(self) -> None:
        self.assertIsNone(take_capture(self.cap(os.path.join(self.dir, f"cap-{uuid.uuid4()}.jpg")), dirs=self.dirs))

    def test_default_dirs_are_real_paths(self) -> None:
        for d in capture_dirs():
            self.assertEqual(d, os.path.realpath(d))
            self.assertTrue(d.endswith("/miyagi-capture"))


class CropToScreen(unittest.TestCase):
    cap = {"w": 520, "h": 260, "rect": {"x": 70, "y": 85, "w": 260, "h": 130}}

    def test_corners_and_center(self) -> None:
        self.assertEqual(crop_to_screen(self.cap, 0, 0), (70, 85, 0))
        self.assertEqual(crop_to_screen(self.cap, 260, 130, 40), (200, 150, 20))
        self.assertEqual(crop_to_screen(self.cap, 520, 260), (330, 215, 0))

    def test_clamped_first(self) -> None:
        self.assertEqual(crop_to_screen(self.cap, -50, 9999, -3), (70, 215, 0))
        self.assertEqual(crop_to_screen(self.cap, float("nan"), float("inf")), (70, 85, 0))

    def test_second_display_negative_origin_1x(self) -> None:
        c = {"w": 400, "h": 300, "rect": {"x": -1000, "y": 0, "w": 400, "h": 300}}
        self.assertEqual(crop_to_screen(c, 100, 50, 10), (-900, 50, 10))

    def test_scaled_down_crop(self) -> None:
        c = {"w": 1092, "h": 546, "rect": (0.0, 0.0, 1200.0, 600.0)}
        x, y, r = crop_to_screen(c, 546, 273, 91)
        self.assertAlmostEqual(x, 600)
        self.assertAlmostEqual(y, 300)
        self.assertAlmostEqual(r, 100)


if __name__ == "__main__":
    unittest.main()
