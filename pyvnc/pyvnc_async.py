"""
Asynchronous VNC client implementation.

This module provides an asynchronous VNC client for capturing screenshots
and sending keyboard & mouse input to VNC servers using asyncio.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, AsyncExitStack
from typing import Callable, Optional, Union, AsyncIterator
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


async def read(reader: asyncio.StreamReader, length: int) -> bytes:
    """
    Read *length* bytes from the given stream reader.
    """
    data = b''
    while len(data) < length:
        chunk = await reader.read(length - len(data))
        if not chunk:
            raise ConnectionError("Connection closed unexpectedly")
        data += chunk
    return data


async def read_int(reader: asyncio.StreamReader, length: int) -> int:
    """
    Read *length* bytes from the given stream reader and decode as a big-endian integer.
    """
    return int.from_bytes(await read(reader, length), 'big')


async def _async_connect_vnc(config: Optional[VNCConfig] = None) -> 'AsyncVNCClient':
    """
    Internal function to connect to a VNC server and return an AsyncVNCClient instance.
    Use AsyncVNCClient.connect() instead.
    """
    if config is None:
        config = VNCConfig()

    # Connect and handshake
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(config.host, config.port),
        timeout=config.timeout
    )
    
    intro = await read(reader, VNC_PROTOCOL_HEADER_SIZE)
    if intro[:4] != VNC_PROTOCOL_PREFIX:
        raise ValueError('not a VNC server')
    writer.write(VNC_PROTOCOL_VERSION)
    await writer.drain()

    # Negotiate an authentication type
    auth_types = set(await read(reader, await read_int(reader, 1)))
    if not auth_types:
        reason = await read(reader, await read_int(reader, 4))
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
        writer.write(b'\x02')
        await writer.drain()
        if not config.password:
            raise ValueError('VNC server requires password')
        des_key = config.password.encode('ascii')[:8].ljust(8, b'\x00')
        des_key = bytes(int(bin(n)[:1:-1].ljust(8, '0'), 2) for n in des_key)
        encryptor = Cipher(TripleDES(des_key), ECB()).encryptor()
        challenge = await read(reader, 16)
        writer.write(encryptor.update(challenge) + encryptor.finalize())
        await writer.drain()

    # No authentication
    elif auth_type == AUTH_TYPE_NONE:
        writer.write(b'\x01')
        await writer.drain()

    # Check auth result
    auth_result = await read_int(reader, 4)
    if auth_result == 0:
        pass
    elif auth_result == 1:
        raise PermissionError('VNC auth failed')
    elif auth_result == 2:
        raise PermissionError('VNC auth failed (too many attempts)')
    else:
        reason = await read(reader, auth_result)
        raise PermissionError(reason.decode('utf-8'))

    # Negotiate pixel format and encodings
    writer.write(b'\x01')
    await writer.drain()
    rect = Rect(0, 0, await read_int(reader, 2), await read_int(reader, 2))
    await read(reader, 16)
    await read(reader, await read_int(reader, 4))
    writer.write(b'\x00\x00\x00\x00' + pixel_formats[config.pixel_format] +
                 b'\x02\x00' + len(encodings).to_bytes(2, 'big') +
                 b''.join(encoding.to_bytes(4, 'big') for encoding in encodings))
    await writer.drain()
    
    return AsyncVNCClient(reader, writer, decompressobj().decompress, rect)


class AsyncVNCClient(CommonVNCClient):
    """
    An asynchronous VNC client.
    """
    
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, 
                 decompress: Callable[[bytes], bytes], rect: Rect):
        super().__init__(rect)
        self.reader = reader
        self.writer = writer
        self.decompress = decompress

    @classmethod
    async def connect(cls, config: Optional[VNCConfig] = None) -> 'AsyncVNCClient':
        """
        Connect to a VNC server and return an AsyncVNCClient instance.
        
        Args:
            config: VNC connection configuration. If None, uses default configuration.
            
        Returns:
            AsyncVNCClient instance ready for use.
            
        Raises:
            ValueError: If not a VNC server or unsupported authentication.
            PermissionError: If authentication fails.
        """
        return await _async_connect_vnc(config)

    async def close(self) -> None:
        """Close the VNC connection."""
        self.writer.close()
        await self.writer.wait_closed()

    async def __aenter__(self) -> 'AsyncVNCClient':
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    @asynccontextmanager
    async def _write_key(self, key: str) -> AsyncIterator['AsyncVNCClient']:
        data = key_codes[key].to_bytes(4, 'big')
        self.writer.write(b'\x04\x01\x00\x00' + data)
        await self.writer.drain()
        try:
            yield
        finally:
            self.writer.write(b'\x04\x00\x00\x00' + data)
            await self.writer.drain()
    
    async def _write_mouse(self) -> None:
        self.writer.write(
            b'\x05' +
            self.mouse_buttons.to_bytes(1, 'big') +
            self.mouse_position.x.to_bytes(2, 'big') +
            self.mouse_position.y.to_bytes(2, 'big'))
        await self.writer.drain()



    async def capture(self, rect: Optional[Union[Rect, RectLike]] = None, *, relative: bool = False) -> np.ndarray:
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
        
        self.writer.write(
            b'\x03\x00' +
            rect.x.to_bytes(2, 'big') +
            rect.y.to_bytes(2, 'big') +
            rect.width.to_bytes(2, 'big') +
            rect.height.to_bytes(2, 'big'))
        await self.writer.drain()
        
        pixels = np.zeros((self.rect.height, self.rect.width, 4), 'B')
        while True:
            update_type = await read_int(self.reader, 1)
            if update_type == MSG_TYPE_CLIPBOARD:
                await read(self.reader, await read_int(self.reader, 4))
            elif update_type == MSG_TYPE_FRAMEBUFFER_UPDATE:
                await read(self.reader, 1)  # padding
                for _ in range(await read_int(self.reader, 2)):
                    area_rect = Rect(
                        await read_int(self.reader, 2), await read_int(self.reader, 2),
                        await read_int(self.reader, 2), await read_int(self.reader, 2))
                    area_encoding = await read_int(self.reader, 4)
                    if area_encoding == ENCODING_RAW:
                        area = await read(self.reader, area_rect.height * area_rect.width * 4)
                    elif area_encoding == ENCODING_ZLIB:
                        area = await read(self.reader, await read_int(self.reader, 4))
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

    @asynccontextmanager
    async def hold_key(self, *keys: str) -> AsyncIterator['AsyncVNCClient']:
        """
        Context manager that pushes the given keys on enter, and releases them (in reverse order) on exit.
        """
        async with AsyncExitStack() as stack:
            for key in keys:
                await stack.enter_async_context(self._write_key(key))
            yield self

    async def press(self, *keys: str) -> 'AsyncVNCClient':
        """
        Pushes all the given keys, and then releases them in reverse order.
        """
        async with self.hold_key(*keys):
            pass
        return self

    async def write(self, text: str) -> 'AsyncVNCClient':
        """
        Pushes and releases each of the given keys, one after the other.
        """
        for key in text:
            async with self.hold_key(key):
                pass
        return self

    @asynccontextmanager
    async def hold_mouse(self, button: int = MOUSE_BUTTON_LEFT, *, relative: bool = False) -> AsyncIterator['AsyncVNCClient']:
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
        await self._write_mouse()
        try:
            # Store the relative flag for use in mouse operations
            old_relative = getattr(self, '_relative_mode', False)
            self._relative_mode = relative
            yield self
        finally:
            self.mouse_buttons &= ~mask
            await self._write_mouse()
            self._relative_mode = old_relative

    async def click(self, button: int = MOUSE_BUTTON_LEFT, *, relative: bool = False) -> 'AsyncVNCClient':
        """
        Presses and releases a mouse button.
        
        Args:
            button: Mouse button to click. Use MOUSE_BUTTON_LEFT, MOUSE_BUTTON_MIDDLE, 
                   or MOUSE_BUTTON_RIGHT constants instead of raw numbers.
            relative: If True, use relative coordinates for current position.
        """
        async with self.hold_mouse(button, relative=relative):
            pass
        return self

    async def double_click(self, button: int = MOUSE_BUTTON_LEFT, *, relative: bool = False) -> 'AsyncVNCClient':
        """
        Presses and releases a mouse button twice.
        
        Args:
            button: Mouse button to click. Use MOUSE_BUTTON_LEFT, MOUSE_BUTTON_MIDDLE, 
                   or MOUSE_BUTTON_RIGHT constants instead of raw numbers.
            relative: If True, use relative coordinates for current position.
        """
        await self.click(button, relative=relative)
        await self.click(button, relative=relative)
        return self

    async def scroll_up(self, repeat: int = 1) -> 'AsyncVNCClient':
        """
        Scrolls the mouse wheel upwards.
        """
        for _ in range(repeat):
            await self.click(MOUSE_BUTTON_SCROLL_UP)
        return self

    async def scroll_down(self, repeat: int = 1) -> 'AsyncVNCClient':
        """
        Scrolls the mouse wheel downwards.
        """
        for _ in range(repeat):
            await self.click(MOUSE_BUTTON_SCROLL_DOWN)
        return self

    async def move(self, point: Union[Point, PointLike], *, relative: bool = False) -> 'AsyncVNCClient':
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
        await self._write_mouse()
        return self

    async def click_at(self, point: Union[Point, PointLike], button: int = MOUSE_BUTTON_LEFT, *, relative: bool = False) -> 'AsyncVNCClient':
        """
        Move to a point and click.
        
        Args:
            point: Position to click at.
            button: Mouse button to click. Use MOUSE_BUTTON_LEFT, MOUSE_BUTTON_MIDDLE, 
                   or MOUSE_BUTTON_RIGHT constants instead of raw numbers.
            relative: If True, interpret coordinates as relative coordinates.
        """
        await self.move(point, relative=relative)
        await self.click(button, relative=relative)
        return self

    async def double_click_at(self, point: Union[Point, PointLike], button: int = 0, *, relative: bool = False) -> 'AsyncVNCClient':
        """
        Move to a point and double-click.
        
        Args:
            point: Position to double-click at.
            button: Mouse button to click (0=left, 1=middle, 2=right).
            relative: If True, interpret coordinates as relative coordinates.
        """
        await self.move(point, relative=relative)
        await self.double_click(button, relative=relative)
        return self


__all__ = [
    'AsyncVNCClient',
]