from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager, ExitStack
from collections import namedtuple
from dataclasses import dataclass, field
from socket import socket, create_connection
from time import sleep
from typing import Callable, Dict, Optional, Union, Set, Tuple, Iterator
from zlib import decompressobj

import numpy as np

from cryptography.hazmat.primitives.ciphers import Cipher
from cryptography.hazmat.primitives.ciphers.modes import ECB

try:
    from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
except ImportError:
    # Fallback for older cryptography versions
    from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES

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


Point = namedtuple('Point', 'x y')
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


def read(sock: socket, length: int) -> bytes:
    """
    Read *length* bytes from the given socket.
    """
    data = b''
    while len(data) < length:
        data += sock.recv(length - len(data))
    return data


def read_int(sock: socket, length: int) -> int:
    """
    Read *length* bytes from the given socket and decode as a big-endian integer.
    """
    return int.from_bytes(read(sock, length), 'big')


@dataclass
class VNCConfig:
    """Configuration for VNC connection."""
    host: str = 'localhost'
    port: int = 5900
    speed: float = 20.0
    timeout: float = 5.0
    pixel_format: str = 'rgba'
    username: Optional[str] = None
    password: Optional[str] = None


def connect_vnc(config: Optional[VNCConfig] = None) -> 'VNCClient':
    """
    Connect to a VNC server and return a VNCClient instance.
    
    Args:
        config: VNC connection configuration. If None, uses default configuration.
        
    Returns:
        VNCClient instance ready for use.
        
    Raises:
        ValueError: If not a VNC server or unsupported authentication.
        PermissionError: If authentication fails.
    """
    if config is None:
        config = VNCConfig()

    # Connect and handshake
    sock = create_connection((config.host, config.port), config.timeout)
    intro = read(sock, VNC_PROTOCOL_HEADER_SIZE)
    if intro[:4] != VNC_PROTOCOL_PREFIX:
        raise ValueError('not a VNC server')
    sock.sendall(VNC_PROTOCOL_VERSION)

    # Negotiate an authentication type
    auth_types = set(read(sock, read_int(sock, 1)))
    if not auth_types:
        reason = read(sock, read_int(sock, 4))
        raise ValueError(reason.decode('utf8'))
    for auth_type in (AUTH_TYPE_VNC, AUTH_TYPE_NONE):
        if auth_type in auth_types:
            break
    else:
        if AUTH_TYPE_APPLE in auth_types:
            raise NotImplementedError(
                "Apple Remote Desktop authentication is not supported in this implementation. "
                "Please use standard VNC authentication or configure your VNC server to allow "
                "password-based or no authentication."
            )
        raise ValueError(f'unsupported VNC auth types: {auth_types}')

    # VNC authentication
    if auth_type == AUTH_TYPE_VNC:
        sock.sendall(b'\x02')
        if not config.password:
            raise ValueError('VNC server requires password')
        des_key = config.password.encode('ascii')[:8].ljust(8, b'\x00')
        des_key = bytes(int(bin(n)[:1:-1].ljust(8, '0'), 2) for n in des_key)
        encryptor = Cipher(TripleDES(des_key), ECB()).encryptor()
        sock.sendall(encryptor.update(read(sock, 16)) + encryptor.finalize())

    # No authentication
    elif auth_type == AUTH_TYPE_NONE:
        sock.sendall(b'\x01')

    # Check auth result
    auth_result = read_int(sock, 4)
    if auth_result == 0:
        pass
    elif auth_result == 1:
        raise PermissionError('VNC auth failed')
    elif auth_result == 2:
        raise PermissionError('VNC auth failed (too many attempts)')
    else:
        reason = read(sock, auth_result)
        raise PermissionError(reason.decode('utf-8'))

    # Negotiate pixel format and encodings
    sock.sendall(b'\x01')
    rect = Rect(0, 0, read_int(sock, 2), read_int(sock, 2))
    read(sock, 16)
    read(sock, read_int(sock, 4))
    sock.sendall(b'\x00\x00\x00\x00' + pixel_formats[config.pixel_format] +
                 b'\x02\x00' + len(encodings).to_bytes(2, 'big') +
                 b''.join(encoding.to_bytes(4, 'big') for encoding in encodings))
    
    return VNCClient(sock, decompressobj().decompress, config.speed, rect)


@dataclass
class VNCClient:
    """
    A VNC client.
    """
    sock: socket = field(repr=False)
    decompress: Callable[[bytes], bytes] = field(repr=False)
    speed: float
    rect: Rect
    mouse_position: Point = Point(0, 0)
    mouse_buttons: int = 0

    def close(self) -> None:
        """Close the VNC connection."""
        self.sock.close()

    def __enter__(self) -> 'VNCClient':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    @contextmanager
    def _write_key(self, key: str) -> Iterator['VNCClient']:
        data = key_codes[key].to_bytes(4, 'big')
        self.sock.sendall(b'\x04\x01\x00\x00' + data)
        self.sleep(1.0 / self.speed)
        try:
            yield
        finally:
            self.sock.sendall(b'\x04\x00\x00\x00' + data)
            self.sleep(1.0 / self.speed)

    def _write_mouse(self) -> None:
        self.sock.sendall(
            b'\x05' +
            self.mouse_buttons.to_bytes(1, 'big') +
            self.mouse_position.x.to_bytes(2, 'big') +
            self.mouse_position.y.to_bytes(2, 'big'))
        self.sleep(1.0 / self.speed)

    @classmethod
    def sleep(cls, duration: float) -> None:
        sleep(duration)

    def get_relative_resolution(self) -> Point:
        """
        Get the relative coordinate resolution based on screen aspect ratio.
        
        For 16:9 screens: 1600x900
        For 31:9 screens: 3100x900  
        For other ratios: scales proportionally with height=900
        
        Returns:
            Point with relative resolution dimensions.
        """
        aspect_ratio = self.rect.width / self.rect.height
        relative_height = 900
        relative_width = int(aspect_ratio * relative_height)
        return Point(relative_width, relative_height)

    def get_relative_screen_rect(self) -> Rect:
        """
        Get the entire screen as a relative coordinate rect.
        
        Returns:
            Rect representing the entire screen in relative coordinates (0, 0, width, height).
        """
        rel_res = self.get_relative_resolution()
        return Rect(0, 0, rel_res.x, rel_res.y)

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

    def capture_full_screen(self) -> np.ndarray:
        """
        Takes a screenshot of the entire screen and returns its pixels as an RGBA numpy array.
        
        Returns:
            RGBA numpy array of the entire screen.
        """
        return self.capture(None)

    def capture(self, rect: Optional[Union[Rect, RectLike]] = None, *, relative: bool = False) -> np.ndarray:
        """
        Takes a screenshot and returns its pixels as an RGBA numpy array.
        
        Args:
            rect: Region to capture. If None, captures entire screen.
            relative: If True, interpret coordinates as relative coordinates.
            
        Returns:
            RGBA numpy array of the specified region.
        """
        if rect is None:
            rect = self.rect
        elif isinstance(rect, RectLike):
            rect = rect.get_rect()
        elif relative:
            rect = self._convert_relative_rect(rect)
        self.sock.sendall(
            b'\x03\x00' +
            rect.x.to_bytes(2, 'big') +
            rect.y.to_bytes(2, 'big') +
            rect.width.to_bytes(2, 'big') +
            rect.height.to_bytes(2, 'big'))
        pixels = np.zeros((self.rect.height, self.rect.width, 4), 'B')
        while True:
            update_type = read_int(self.sock, 1)
            if update_type == MSG_TYPE_CLIPBOARD:
                read(self.sock, read_int(self.sock, 4))
            elif update_type == MSG_TYPE_FRAMEBUFFER_UPDATE:
                read(self.sock, 1)  # padding
                for _ in range(read_int(self.sock, 2)):
                    area_rect = Rect(
                        read_int(self.sock, 2), read_int(self.sock, 2),
                        read_int(self.sock, 2), read_int(self.sock, 2))
                    area_encoding = read_int(self.sock, 4)
                    if area_encoding == ENCODING_RAW:
                        area = read(self.sock, area_rect.height * area_rect.width * 4)
                    elif area_encoding == ENCODING_ZLIB:
                        area = read(self.sock, read_int(self.sock, 4))
                        area = self.decompress(area)
                    else:
                        raise ValueError(f'unsupported VNC encoding: {area_encoding}')
                    area = np.ndarray((area_rect.height, area_rect.width, 4), 'B', area)
                    pixels[slice_rect(area_rect)] = area
                    pixels[slice_rect(area_rect, 3)] = 255
                if pixels[slice_rect(rect, 3)].all():
                    return pixels[slice_rect(rect)]
            else:
                raise ValueError(f'unsupported VNC update type: {update_type}')

    @contextmanager
    def hold(self, *keys: str) -> Iterator['VNCClient']:
        """
        Context manager that pushes the given keys on enter, and releases them (in reverse order) on exit.
        """
        with ExitStack() as stack:
            for key in keys:
                stack.enter_context(self._write_key(key))
            yield self

    def press(self, *keys: str) -> 'VNCClient':
        """
        Pushes all the given keys, and then releases them in reverse order.
        """
        with self.hold(*keys):
            pass
        return self

    def write(self, text: str) -> 'VNCClient':
        """
        Pushes and releases each of the given keys, one after the other.
        """
        for key in text:
            with self.hold(key):
                pass
        return self

    @contextmanager
    def drag(self, button: int = MOUSE_BUTTON_LEFT, *, relative: bool = False) -> Iterator['VNCClient']:
        """
        Context manager that presses a mouse button on enter, and releases it on exit.
        
        Args:
            button: Mouse button to drag with. Use MOUSE_BUTTON_LEFT, MOUSE_BUTTON_MIDDLE, 
                   or MOUSE_BUTTON_RIGHT constants instead of raw numbers.
            relative: If True, use relative coordinates for mouse operations within context.
        """
        mask = 1 << button
        self.mouse_buttons |= mask
        self._write_mouse()
        try:
            # Store the relative flag for use in mouse operations
            old_relative = getattr(self, '_relative_mode', False)
            self._relative_mode = relative
            yield self
        finally:
            self.mouse_buttons &= ~mask
            self._write_mouse()
            self._relative_mode = old_relative


    def click(self, button: int = MOUSE_BUTTON_LEFT, *, relative: bool = False) -> 'VNCClient':
        """
        Presses and releases a mouse button.
        
        Args:
            button: Mouse button to click. Use MOUSE_BUTTON_LEFT, MOUSE_BUTTON_MIDDLE, 
                   or MOUSE_BUTTON_RIGHT constants instead of raw numbers.
            relative: If True, use relative coordinates for current position.
        """
        with self.drag(button, relative=relative):
            pass
        return self

    def double_click(self, button: int = MOUSE_BUTTON_LEFT, *, relative: bool = False) -> 'VNCClient':
        """
        Presses and releases a mouse button twice.
        
        Args:
            button: Mouse button to click. Use MOUSE_BUTTON_LEFT, MOUSE_BUTTON_MIDDLE, 
                   or MOUSE_BUTTON_RIGHT constants instead of raw numbers.
            relative: If True, use relative coordinates for current position.
        """
        self.click(button, relative=relative)
        self.click(button, relative=relative)
        return self


    def scroll_up(self, repeat: int = 1) -> 'VNCClient':
        """
        Scrolls the mouse wheel upwards.
        """
        for _ in range(repeat):
            self.click(MOUSE_BUTTON_SCROLL_UP)
        return self

    def scroll_down(self, repeat: int = 1) -> 'VNCClient':
        """
        Scrolls the mouse wheel downwards.
        """
        for _ in range(repeat):
            self.click(MOUSE_BUTTON_SCROLL_DOWN)
        return self

    def move(self, point: Union[Point, PointLike], *, relative: bool = False) -> 'VNCClient':
        """
        Moves the mouse cursor to the given co-ordinates.
        
        Args:
            point: Target position to move to.
            relative: If True, interpret coordinates as relative coordinates.
        """
        if isinstance(point, PointLike):
            point = point.get_point()
        
        # Check if we're in relative mode from drag context or explicit parameter
        use_relative = relative or getattr(self, '_relative_mode', False)
        if use_relative:
            point = self._convert_relative_point(point)
            
        self.mouse_position = point
        self._write_mouse()
        return self

    def click_at(self, point: Union[Point, PointLike], button: int = MOUSE_BUTTON_LEFT, *, relative: bool = False) -> 'VNCClient':
        """
        Move to a point and click.
        
        Args:
            point: Position to click at.
            button: Mouse button to click. Use MOUSE_BUTTON_LEFT, MOUSE_BUTTON_MIDDLE, 
                   or MOUSE_BUTTON_RIGHT constants instead of raw numbers.
            relative: If True, interpret coordinates as relative coordinates.
        """
        self.move(point, relative=relative)
        self.click(button, relative=relative)
        return self

    def double_click_at(self, point: Union[Point, PointLike], button: int = 0, *, relative: bool = False) -> 'VNCClient':
        """
        Move to a point and double-click.
        
        Args:
            point: Position to double-click at.
            button: Mouse button to click (0=left, 1=middle, 2=right).
            relative: If True, interpret coordinates as relative coordinates.
        """
        self.move(point, relative=relative)
        self.double_click(button, relative=relative)
        return self


# For backwards compatibility, create aliases for the old VNC class
VNC = VNCClient