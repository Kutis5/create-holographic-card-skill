#!/usr/bin/env python3
"""Pixel contract for the subject-above-optical-plane composition."""

from __future__ import annotations

import unittest

from PIL import Image


class SubjectIsolationTests(unittest.TestCase):
    def test_subject_alpha_blocks_optical_plane_without_recoloring_subject(self) -> None:
        optical_plane = Image.new("RGBA", (3, 1))
        optical_plane.putdata([(30, 80, 220, 255), (180, 30, 220, 255), (20, 210, 150, 255)])
        subject = Image.new("RGBA", (3, 1))
        subject.putdata([
            (255, 0, 0, 0),       # Fully transparent: optical plane remains visible.
            (16, 130, 52, 255),   # Fully opaque: original subject RGB remains exact.
            (240, 120, 30, 128),  # Soft cutout edge: ordinary alpha compositing only.
        ])

        composed = Image.alpha_composite(optical_plane, subject)

        self.assertEqual(composed.getpixel((0, 0)), optical_plane.getpixel((0, 0)))
        self.assertEqual(composed.getpixel((1, 0)), subject.getpixel((1, 0)))
        self.assertEqual(composed.getpixel((2, 0)), (130, 165, 90, 255))


if __name__ == "__main__":
    unittest.main(verbosity=2)
