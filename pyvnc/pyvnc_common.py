"""
Common constants, data structures, and utilities for pyvnc sync/async clients.

This module contains sync/async agnostic code that can be shared between
synchronous and asynchronous VNC client implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import namedtuple
from dataclasses import dataclass
from typing import Dict, Optional, Set, Tuple, Union

from keysymdef import keysymdef  # type: ignore


# Constants
VNC_PROTOCOL_VERSION = b'RFB 003.008\n'
VNC_PROTOCOL_HEADER_SIZE = 12
VNC_PROTOCOL_PREFIX = b'RFB '

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
key_codes['Del'] = key_codes['Delete']
key_codes['Esc'] = key_codes['Escape']
key_codes['Cmd'] = key_codes['Super_L']
key_codes['Alt'] = key_codes['Alt_L']
key_codes['Ctrl'] = key_codes['Control_L']
key_codes['Super'] = key_codes['Super_L']
key_codes['Shift'] = key_codes['Shift_L']
key_codes['Backspace'] = key_codes['BackSpace']
key_codes['Space'] = key_codes['space']

encodings: Set[int] = {
    ENCODING_ZLIB,
}

# Colour channel orders
pixel_formats: Dict[str, bytes] = {
     'bgra': b'\x20\x18\x00\x01\x00\xff\x00\xff\x00\xff\x10\x08\x00\x00\x00\x00',
     'rgba': b'\x20\x18\x00\x01\x00\xff\x00\xff\x00\xff\x00\x08\x10\x00\x00\x00',
     'argb': b'\x20\x18\x01\x01\x00\xff\x00\xff\x00\xff\x10\x08\x00\x00\x00\x00',
     'abgr': b'\x20\x18\x01\x01\x00\xff\x00\xff\x00\xff\x00\x08\x10\x00\x00\x00',
}


# Point with x, y coordinates (int or float)
Point = namedtuple('Point', 'x y')

# Rectangle with x, y position and width, height dimensions (int or float)  
Rect = namedtuple('Rect', 'x y width height')


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
    return (slice(rect.y, rect.y + rect.height),
            slice(rect.x, rect.x + rect.width)) + channels


@dataclass
class VNCConfig:
    """Configuration for VNC connection."""
    host: str = 'localhost'
    port: int = 5900
    timeout: float = 5.0
    pixel_format: str = 'rgba'
    username: Optional[str] = None
    password: Optional[str] = None


class CommonVNCClient(ABC):
    """
    Abstract base class for VNC clients with shared functionality.
    
    This class contains coordinate conversion methods that are shared
    between sync and async implementations.
    """
    
    def __init__(self, rect: Rect):
        self.rect = rect
        self.mouse_position: Point = Point(0, 0)
        self.mouse_buttons: int = 0
    
    def get_relative_resolution(self) -> Point:
        """
        Get the relative coordinate resolution based on screen aspect ratio.
        
        This method creates a coordinate system where both width and height are
        multiples of 100 (for easy mental math), neither exceeds 99900, and the
        aspect ratio closely matches the actual screen.
        
        The relative coordinate system allows you to write resolution-independent
        automation scripts. Use relative=True parameter in mouse and capture 
        methods to work with these coordinates:
        
        Examples:
            # Get relative dimensions - always multiples of 100
            rel_res = vnc.get_relative_resolution()  # e.g., Point(99900, 56200) for 16:9
            center_x, center_y = rel_res.x // 2, rel_res.y // 2  # Easy mental math
            
            # Use relative coordinates
            vnc.move(Point(center_x, center_y), relative=True)
            screenshot = vnc.capture(Rect(0, 0, rel_res.x//2, rel_res.y//2), relative=True)
        
        Returns:
            Point with relative resolution dimensions (both multiples of 100, ≤ 99900).
        """
        aspect_ratio = self.rect.width / self.rect.height
        
        # Find the largest dimensions where both width and height ≤ 99900 and are multiples of 100
        # This ensures clean float division and 5 digits max
        max_dimension = 99900  # Multiple of 100, 5 digits
        
        if aspect_ratio >= 1.0:  # Width >= height
            relative_width = max_dimension
            relative_height = int(max_dimension / aspect_ratio)
            # Round down to nearest multiple of 100
            relative_height = (relative_height // 100) * 100
        else:  # Height > width
            relative_height = max_dimension
            relative_width = int(max_dimension * aspect_ratio)
            # Round down to nearest multiple of 100
            relative_width = (relative_width // 100) * 100
        
        return Point(relative_width, relative_height)

    def _convert_relative_point(self, point: Union[Point, PointLike]) -> Point:
        """Convert relative coordinates to absolute pixel coordinates."""
        if isinstance(point, PointLike):
            point = point.get_point()
        
        rel_res = self.get_relative_resolution()
        abs_x = int((point.x / rel_res.x) * self.rect.width)
        abs_y = int((point.y / rel_res.y) * self.rect.height)
        return Point(abs_x, abs_y)

    def _convert_relative_rect(self, rect: Union[Rect, RectLike]) -> Rect:
        """Convert relative coordinates to absolute pixel coordinates."""
        if isinstance(rect, RectLike):
            rect = rect.get_rect()
        
        rel_res = self.get_relative_resolution()
        abs_x = int((rect.x / rel_res.x) * self.rect.width)
        abs_y = int((rect.y / rel_res.y) * self.rect.height)
        abs_width = int((rect.width / rel_res.x) * self.rect.width)
        abs_height = int((rect.height / rel_res.y) * self.rect.height)
        return Rect(abs_x, abs_y, abs_width, abs_height)


__all__ = [
    # Constants
    'VNC_PROTOCOL_VERSION',
    'VNC_PROTOCOL_HEADER_SIZE', 
    'VNC_PROTOCOL_PREFIX',
    'AUTH_TYPE_NONE',
    'AUTH_TYPE_VNC',
    'AUTH_TYPE_APPLE',
    'MSG_TYPE_FRAMEBUFFER_UPDATE',
    'MSG_TYPE_CLIPBOARD',
    'ENCODING_RAW',
    'ENCODING_ZLIB',
    'MOUSE_BUTTON_LEFT',
    'MOUSE_BUTTON_MIDDLE',
    'MOUSE_BUTTON_RIGHT',
    'MOUSE_BUTTON_SCROLL_UP',
    'MOUSE_BUTTON_SCROLL_DOWN',
    
    # Data structures
    'Point',
    'Rect',
    'PointLike',
    'RectLike',
    'VNCConfig',
    
    # Utilities
    'slice_rect',
    'key_codes',
    'encodings',
    'pixel_formats',
]