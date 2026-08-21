#!/usr/bin/env python3
"""Unit tests for PixelFormat decoding and handshake validation."""

import struct
import unittest

import numpy as np

from pyvnc.pyvnc_common import PIXEL_FORMATS, PixelFormat
from pyvnc.pyvnc_async import _valid_16bpp_channels


def _pack_bgra(pixels):
    """Pack an iterable of (R, G, B) tuples as raw BGRA bytes."""
    buf = bytearray()
    for r, g, b in pixels:
        buf.extend((b, g, r, 0))
    return bytes(buf)


def _pack_rgba(pixels):
    buf = bytearray()
    for r, g, b in pixels:
        buf.extend((r, g, b, 0))
    return bytes(buf)


def _pack_rgb565(pixels, big_endian=False):
    buf = bytearray()
    fmt = ">H" if big_endian else "<H"
    for r, g, b in pixels:
        # r,g,b assumed in full 8-bit range; downsample to 5/6/5
        r5 = (r >> 3) & 0x1F
        g6 = (g >> 2) & 0x3F
        b5 = (b >> 3) & 0x1F
        buf.extend(struct.pack(fmt, (r5 << 11) | (g6 << 5) | b5))
    return bytes(buf)


class PixelFormatDecodeTests(unittest.TestCase):
    def test_bgra_regression(self):
        pf = PIXEL_FORMATS["bgra"]
        raw = _pack_bgra([(255, 0, 0), (0, 255, 0), (0, 0, 255), (10, 20, 30)])
        out = pf.decode_to_rgba(raw, 1, 4)
        self.assertEqual(out.shape, (1, 4, 4))
        self.assertEqual(out.dtype, np.uint8)
        np.testing.assert_array_equal(out[0, 0], (255, 0, 0, 255))
        np.testing.assert_array_equal(out[0, 1], (0, 255, 0, 255))
        np.testing.assert_array_equal(out[0, 2], (0, 0, 255, 255))
        np.testing.assert_array_equal(out[0, 3], (10, 20, 30, 255))

    def test_rgba_regression(self):
        pf = PIXEL_FORMATS["rgba"]
        raw = _pack_rgba([(200, 100, 50)])
        out = pf.decode_to_rgba(raw, 1, 1)
        np.testing.assert_array_equal(out[0, 0], (200, 100, 50, 255))

    def test_rgb565_little_endian_fast_path(self):
        pf = PIXEL_FORMATS["rgb565"]
        # Solid red: R=255 -> R5=31 -> scaled back to 255
        raw = _pack_rgb565([(255, 0, 0), (0, 255, 0), (0, 0, 255)], big_endian=False)
        out = pf.decode_to_rgba(raw, 1, 3)
        self.assertEqual(out.shape, (1, 3, 4))
        np.testing.assert_array_equal(out[0, 0], (255, 0, 0, 255))
        np.testing.assert_array_equal(out[0, 1], (0, 255, 0, 255))
        np.testing.assert_array_equal(out[0, 2], (0, 0, 255, 255))

    def test_rgb565_big_endian(self):
        pf = PixelFormat(
            bits_per_pixel=16,
            depth=16,
            big_endian_flag=True,
            true_color_flag=True,
            red_max=31,
            green_max=63,
            blue_max=31,
            red_shift=11,
            green_shift=5,
            blue_shift=0,
        )
        raw = _pack_rgb565([(255, 0, 0), (0, 0, 255)], big_endian=True)
        out = pf.decode_to_rgba(raw, 1, 2)
        np.testing.assert_array_equal(out[0, 0], (255, 0, 0, 255))
        np.testing.assert_array_equal(out[0, 1], (0, 0, 255, 255))

    def test_rgb555_generic_path(self):
        # RGB555 with unused high bit: R5 shift 10, G5 shift 5, B5 shift 0
        pf = PixelFormat(
            bits_per_pixel=16,
            depth=15,
            big_endian_flag=False,
            true_color_flag=True,
            red_max=31,
            green_max=31,
            blue_max=31,
            red_shift=10,
            green_shift=5,
            blue_shift=0,
        )
        # Solid green: g=31 in 5-bit -> scaled to 255
        buf = bytearray()
        buf.extend(struct.pack("<H", (31 << 5)))  # only green
        buf.extend(struct.pack("<H", (31 << 10)))  # only red
        buf.extend(struct.pack("<H", 31))  # only blue
        out = pf.decode_to_rgba(bytes(buf), 1, 3)
        np.testing.assert_array_equal(out[0, 0], (0, 255, 0, 255))
        np.testing.assert_array_equal(out[0, 1], (255, 0, 0, 255))
        np.testing.assert_array_equal(out[0, 2], (0, 0, 255, 255))

    def test_bytes_per_pixel(self):
        self.assertEqual(PIXEL_FORMATS["bgra"].bytes_per_pixel, 4)
        self.assertEqual(PIXEL_FORMATS["rgb565"].bytes_per_pixel, 2)


class Handshake16bppValidationTests(unittest.TestCase):
    def test_rgb565_accepted(self):
        self.assertTrue(_valid_16bpp_channels(PIXEL_FORMATS["rgb565"]))

    def test_rgb555_accepted(self):
        pf = PixelFormat(16, 15, False, True, 31, 31, 31, 10, 5, 0)
        self.assertTrue(_valid_16bpp_channels(pf))

    def test_max_not_power_of_two_minus_one_rejected(self):
        pf = PixelFormat(16, 16, False, True, 30, 63, 31, 11, 5, 0)
        self.assertFalse(_valid_16bpp_channels(pf))

    def test_channel_overflows_16_bits_rejected(self):
        pf = PixelFormat(16, 16, False, True, 31, 63, 31, 12, 5, 0)  # R needs bits 12-16
        self.assertFalse(_valid_16bpp_channels(pf))

    def test_zero_max_rejected(self):
        pf = PixelFormat(16, 16, False, True, 0, 63, 31, 11, 5, 0)
        self.assertFalse(_valid_16bpp_channels(pf))


if __name__ == "__main__":
    unittest.main()
