"""
Common constants, data structures, and utilities for pyvnc sync/async clients.

This module contains sync/async agnostic code that can be shared between
synchronous and asynchronous VNC client implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import namedtuple
from dataclasses import dataclass
from typing import Dict, Optional, Set, Tuple

from keysymdef import keysymdef  # type: ignore


# Constants
VNC_PROTOCOL_VERSION = b"RFB 003.008\n"
VNC_PROTOCOL_HEADER_SIZE = 12
VNC_PROTOCOL_PREFIX = b"RFB "

# Authentication types
AUTH_TYPE_NONE = 1
AUTH_TYPE_VNC = 2
AUTH_TYPE_APPLE = 33

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
key_codes: Dict[str, int] = {}
key_codes.update((name, code) for name, code, char in keysymdef)
key_codes.update((chr(char), code) for name, code, char in keysymdef if char)
key_codes["Del"] = key_codes["Delete"]
key_codes["Esc"] = key_codes["Escape"]
key_codes["Cmd"] = key_codes["Super_L"]
key_codes["Alt"] = key_codes["Alt_L"]
key_codes["Ctrl"] = key_codes["Control_L"]
key_codes["Super"] = key_codes["Super_L"]
key_codes["Shift"] = key_codes["Shift_L"]
key_codes["Backspace"] = key_codes["BackSpace"]
key_codes["Space"] = key_codes["space"]

encodings: Set[int] = {
    ENCODING_ZLIB,
}

# Colour channel orders
pixel_formats: Dict[str, bytes] = {
    "bgra": b"\x20\x18\x00\x01\x00\xff\x00\xff\x00\xff\x10\x08\x00\x00\x00\x00",
    "rgba": b"\x20\x18\x00\x01\x00\xff\x00\xff\x00\xff\x00\x08\x10\x00\x00\x00",
    "argb": b"\x20\x18\x01\x01\x00\xff\x00\xff\x00\xff\x10\x08\x00\x00\x00\x00",
    "abgr": b"\x20\x18\x01\x01\x00\xff\x00\xff\x00\xff\x00\x08\x10\x00\x00\x00",
}


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


@dataclass
class VNCConfig:
    """Configuration for VNC connection."""

    host: str = "localhost"
    port: int = 5900
    timeout: float = 5.0
    pixel_format: str = "rgba"
    username: Optional[str] = None
    password: Optional[str] = None


class CommonVNCClient(ABC):
    """
    Abstract base class for VNC clients with shared functionality.

    This class contains shared attributes for VNC client implementations.
    """

    def __init__(self, rect: Rect):
        self.rect = rect
        self.mouse_position: Point = Point(0, 0)
        self.mouse_buttons: int = 0


__all__ = [
    # Constants
    "VNC_PROTOCOL_VERSION",
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
    # Data structures
    "Point",
    "Rect",
    "PointLike",
    "RectLike",
    "VNCConfig",
    "CommonVNCClient",
    # Utilities
    "slice_rect",
    "key_codes",
    "encodings",
    "pixel_formats",
]
