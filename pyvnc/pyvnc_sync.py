"""
Synchronous VNC client implementation.

This module provides a synchronous VNC client for capturing screenshots
and sending keyboard & mouse input to VNC servers.
"""

from __future__ import annotations

from contextlib import contextmanager, ExitStack
from socket import socket, create_connection
from typing import Callable, Optional, Union, Iterator
from zlib import decompressobj

import numpy as np

from cryptography.hazmat.primitives.ciphers import Cipher
from cryptography.hazmat.primitives.ciphers.modes import ECB

try:
    from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
except ImportError:
    # Fallback for older cryptography versions
    from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES

from .pyvnc_common import (
    VNC_PROTOCOL_VERSION,
    VNC_PROTOCOL_HEADER_SIZE,
    VNC_PROTOCOL_PREFIX,
    AUTH_TYPE_NONE,
    AUTH_TYPE_VNC,
    AUTH_TYPE_APPLE,
    MSG_TYPE_FRAMEBUFFER_UPDATE,
    MSG_TYPE_CLIPBOARD,
    ENCODING_RAW,
    ENCODING_ZLIB,
    MOUSE_BUTTON_LEFT,
    MOUSE_BUTTON_MIDDLE,
    MOUSE_BUTTON_RIGHT,
    MOUSE_BUTTON_SCROLL_UP,
    MOUSE_BUTTON_SCROLL_DOWN,
    Point,
    Rect,
    PointLike,
    RectLike,
    VNCConfig,
    CommonVNCClient,
    slice_rect,
    key_codes,
    encodings,
    pixel_formats,
)


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


def _sync_connect_vnc(config: Optional[VNCConfig] = None) -> 'SyncVNCClient':
    """
    Internal function to connect to a VNC server and return a SyncVNCClient instance.
    Use SyncVNCClient.connect() instead.
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
    
    return SyncVNCClient(sock, decompressobj().decompress, rect)


class SyncVNCClient(CommonVNCClient):
    """
    A synchronous VNC client.
    """
    
    def __init__(self, sock: socket, decompress: Callable[[bytes], bytes], rect: Rect):
        super().__init__(rect)
        self.sock = sock
        self.decompress = decompress

    @classmethod
    def connect(cls, config: Optional[VNCConfig] = None) -> 'SyncVNCClient':
        """
        Connect to a VNC server and return a SyncVNCClient instance.
        
        Args:
            config: VNC connection configuration. If None, uses default configuration.
            
        Returns:
            SyncVNCClient instance ready for use.
            
        Raises:
            ValueError: If not a VNC server or unsupported authentication.
            PermissionError: If authentication fails.
        """
        return _sync_connect_vnc(config)

    def close(self) -> None:
        """Close the VNC connection."""
        self.sock.close()

    def __enter__(self) -> 'SyncVNCClient':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    @contextmanager
    def _write_key(self, key: str) -> Iterator['SyncVNCClient']:
        data = key_codes[key].to_bytes(4, 'big')
        self.sock.sendall(b'\x04\x01\x00\x00' + data)
        try:
            yield
        finally:
            self.sock.sendall(b'\x04\x00\x00\x00' + data)
    
    def _write_mouse(self) -> None:
        self.sock.sendall(
            b'\x05' +
            self.mouse_buttons.to_bytes(1, 'big') +
            self.mouse_position.x.to_bytes(2, 'big') +
            self.mouse_position.y.to_bytes(2, 'big'))



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
    def hold_key(self, *keys: str) -> Iterator['SyncVNCClient']:
        """
        Context manager that pushes the given keys on enter, and releases them (in reverse order) on exit.
        """
        with ExitStack() as stack:
            for key in keys:
                stack.enter_context(self._write_key(key))
            yield self

    def press(self, *keys: str) -> 'SyncVNCClient':
        """
        Pushes all the given keys, and then releases them in reverse order.
        """
        with self.hold_key(*keys):
            pass
        return self

    def write(self, text: str) -> 'SyncVNCClient':
        """
        Pushes and releases each of the given keys, one after the other.
        """
        for key in text:
            with self.hold_key(key):
                pass
        return self

    @contextmanager
    def hold_mouse(self, button: int = MOUSE_BUTTON_LEFT, *, relative: bool = False) -> Iterator['SyncVNCClient']:
        """
        Context manager that holds down a mouse button for dragging operations.
        
        The button is pressed on enter and released on exit. Move the mouse while
        in this context to perform drag operations.
        
        Args:
            button: Mouse button to hold down. Use MOUSE_BUTTON_LEFT, MOUSE_BUTTON_MIDDLE, 
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


    def click(self, button: int = MOUSE_BUTTON_LEFT, *, relative: bool = False) -> 'SyncVNCClient':
        """
        Presses and releases a mouse button.
        
        Args:
            button: Mouse button to click. Use MOUSE_BUTTON_LEFT, MOUSE_BUTTON_MIDDLE, 
                   or MOUSE_BUTTON_RIGHT constants instead of raw numbers.
            relative: If True, use relative coordinates for current position.
        """
        with self.hold_mouse(button, relative=relative):
            pass
        return self

    def double_click(self, button: int = MOUSE_BUTTON_LEFT, *, relative: bool = False) -> 'SyncVNCClient':
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


    def scroll_up(self, repeat: int = 1) -> 'SyncVNCClient':
        """
        Scrolls the mouse wheel upwards.
        """
        for _ in range(repeat):
            self.click(MOUSE_BUTTON_SCROLL_UP)
        return self

    def scroll_down(self, repeat: int = 1) -> 'SyncVNCClient':
        """
        Scrolls the mouse wheel downwards.
        """
        for _ in range(repeat):
            self.click(MOUSE_BUTTON_SCROLL_DOWN)
        return self

    def move(self, point: Union[Point, PointLike], *, relative: bool = False) -> 'SyncVNCClient':
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

    def click_at(self, point: Union[Point, PointLike], button: int = MOUSE_BUTTON_LEFT, *, relative: bool = False) -> 'SyncVNCClient':
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

    def double_click_at(self, point: Union[Point, PointLike], button: int = 0, *, relative: bool = False) -> 'SyncVNCClient':
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


__all__ = [
    'SyncVNCClient',
]