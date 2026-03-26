"""
Common constants, data structures, and utilities for pyvnc sync/async clients.

This module contains sync/async agnostic code that can be shared between
synchronous and asynchronous VNC client implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import namedtuple
from dataclasses import dataclass
from dataclasses import astuple
from struct import unpack, pack
from typing import Dict, Optional, Self, Tuple

from frozendict import frozendict

from keysymdef import keysymdef  # type: ignore


# Constants
VNC_PROTOCOL_HEADER = b"RFB 003.008\n"
VNC_PROTOCOL_HEADER_SIZE = len(VNC_PROTOCOL_HEADER)
VNC_PROTOCOL_PREFIX = b"RFB "

# Authentication types
AUTH_TYPE_NONE = 1
AUTH_TYPE_VNC = 2
AUTH_TYPE_APPLE = 33

# Authentication response codes
AUTH_STATE_PERMITTED = 0
AUTH_STATE_FAILED = 1
AUTH_STATE_LOCKOUT = 2

# VNC message types
MSG_TYPE_FRAMEBUFFER_UPDATE = 0
MSG_TYPE_CLIPBOARD = 2

# VNC encodings
ENCODING_RAW = 0
ENCODING_ZLIB = 6

# Mouse buttons
MOUSE_BUTTON_LEFT = 0
MOUSE_BUTTON_MIDDLE = 1
MOUSE_BUTTON_RIGHT = 2
MOUSE_BUTTON_SCROLL_UP = 3
MOUSE_BUTTON_SCROLL_DOWN = 4

# Keyboard keys
_key_codes_mut: Dict[str, int] = {}
_key_codes_mut.update((name, code) for name, code, char in keysymdef)
_key_codes_mut.update((chr(char), code) for name, code, char in keysymdef if char)
_key_codes_mut["Del"] = _key_codes_mut["Delete"]
_key_codes_mut["Esc"] = _key_codes_mut["Escape"]
_key_codes_mut["Cmd"] = _key_codes_mut["Super_L"]
_key_codes_mut["Alt"] = _key_codes_mut["Alt_L"]
_key_codes_mut["Ctrl"] = _key_codes_mut["Control_L"]
_key_codes_mut["Super"] = _key_codes_mut["Super_L"]
_key_codes_mut["Shift"] = _key_codes_mut["Shift_L"]
_key_codes_mut["Backspace"] = _key_codes_mut["BackSpace"]
_key_codes_mut["Space"] = _key_codes_mut["space"]
key_codes = frozendict(_key_codes_mut)
del _key_codes_mut


# Colour channel orders
@dataclass
class PixelFormat:
    bits_per_pixel: int
    depth: int
    big_endian_flag: bool
    true_color_flag: bool
    red_max: int
    green_max: int
    blue_max: int
    red_shift: int
    green_shift: int
    blue_shift: int

    PYTHON_STRUCT_PIXEL_FORMAT = (
        "!"  # big-endian marker
        "B"
        "B"
        "?"
        "?"
        "H"
        "H"
        "H"
        "B"
        "B"
        "B"
        "3x"
    )

    @classmethod
    def deserialize(cls, pf_bytes: bytes) -> Self:
        return cls(*unpack(cls.PYTHON_STRUCT_PIXEL_FORMAT, pf_bytes))

    def serialize(self) -> bytes:
        return pack(self.PYTHON_STRUCT_PIXEL_FORMAT, *astuple(self))


PIXEL_FORMATS = frozendict(
    {
        "bgra": PixelFormat.deserialize(
            b"\x20\x18\x00\x01\x00\xff\x00\xff\x00\xff\x10\x08\x00\x00\x00\x00"
        ),
        "rgba": PixelFormat.deserialize(
            b"\x20\x18\x00\x01\x00\xff\x00\xff\x00\xff\x00\x08\x10\x00\x00\x00"
        ),
        "argb": PixelFormat.deserialize(
            b"\x20\x18\x01\x01\x00\xff\x00\xff\x00\xff\x10\x08\x00\x00\x00\x00"
        ),
        "abgr": PixelFormat.deserialize(
            b"\x20\x18\x01\x01\x00\xff\x00\xff\x00\xff\x00\x08\x10\x00\x00\x00"
        ),
    }
)


# Point with x, y coordinates (int or float)
Point = namedtuple("Point", "x y")

# Rectangle with x, y position and width, height dimensions (int or float)
Rect = namedtuple("Rect", "x y width height")


class PointLike(ABC):
    @abstractmethod
    def get_point(self) -> Point:
        pass


class RectLike(ABC):
    @abstractmethod
    def get_rect(self) -> Rect:
        pass


def slice_rect(rect: Rect, *channels: slice) -> Tuple[slice, ...]:
    """
    A sequence of slice objects that can be used to address a numpy array.
    """
    return (
        slice(rect.y, rect.y + rect.height),
        slice(rect.x, rect.x + rect.width),
    ) + channels


# no type for a byte string of a particular length
# see https://github.com/python/typing/issues/997
def pack_apple_remote_desktop(material: str) -> bytes:
    """
    Wraps a component of key material for use in Apple Remote Desktop (ARD) authentication.
    """

    material_cstr_bytes = material.encode("utf-8") + b"\x00"
    material_cstr_bytes_len_wterminator = len(material_cstr_bytes)

    # if the cstring is greater than 64 bytes in length, truncate
    if material_cstr_bytes_len_wterminator > 64:
        truncated_material = material_cstr_bytes[:64]
        assert len(truncated_material) == 64
        return truncated_material
    else:
        padding_bytes_needed = 64 - material_cstr_bytes_len_wterminator
        # while pytest-vnc (the library from which much of this library is adapted from)
        # uses random bytes to pad the credential to 64 bytes, this is actually unnecessary
        # since the entire key is only used once to encrypt a single block
        material_cstr_bytes += b"\x00" * padding_bytes_needed
        assert len(material_cstr_bytes) == 64
        return material_cstr_bytes


@dataclass
class VNCConfig:
    """Configuration for VNC connection."""

    host: str = "localhost"
    port: int = 5900
    connection_timeout: float = 5.0
    username: Optional[str] = None
    password: Optional[str] = None


__all__ = [
    # Constants
    "VNC_PROTOCOL_HEADER",
    "VNC_PROTOCOL_HEADER_SIZE",
    "VNC_PROTOCOL_PREFIX",
    "AUTH_TYPE_NONE",
    "AUTH_TYPE_VNC",
    "AUTH_TYPE_APPLE",
    "MSG_TYPE_FRAMEBUFFER_UPDATE",
    "MSG_TYPE_CLIPBOARD",
    "ENCODING_RAW",
    "ENCODING_ZLIB",
    "MOUSE_BUTTON_LEFT",
    "MOUSE_BUTTON_MIDDLE",
    "MOUSE_BUTTON_RIGHT",
    "MOUSE_BUTTON_SCROLL_UP",
    "MOUSE_BUTTON_SCROLL_DOWN",
    "AUTH_STATE_PERMITTED",
    "AUTH_STATE_FAILED",
    "AUTH_STATE_LOCKOUT",
    # Data structures
    "Point",
    "Rect",
    "PointLike",
    "RectLike",
    "VNCConfig",
    # Utilities
    "slice_rect",
    "key_codes",
    "PIXEL_FORMATS",
    "pack_apple_remote_desktop",
]
