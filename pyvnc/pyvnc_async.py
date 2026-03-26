"""
Asynchronous VNC client implementation.

This module provides an asynchronous VNC client for capturing screenshots
and sending keyboard & mouse input to VNC servers using asyncio.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, AsyncExitStack
import logging
from secrets import token_bytes
from typing import Any, Optional, Union, AsyncIterator, cast
from zlib import decompressobj

import numpy as np

from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.ciphers import Cipher
from cryptography.hazmat.primitives.ciphers.modes import ECB
from cryptography.hazmat.primitives.serialization import load_der_public_key
from cryptography.hazmat.primitives.ciphers.algorithms import AES128

try:
    from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
except ImportError:
    # Fallback for older cryptography versions
    from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES

from .pyvnc_common import (
    AUTH_STATE_FAILED,
    AUTH_STATE_LOCKOUT,
    AUTH_STATE_PERMITTED,
    VNC_PROTOCOL_HEADER,
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
    MOUSE_BUTTON_SCROLL_UP,
    MOUSE_BUTTON_SCROLL_DOWN,
    PixelFormat,
    Point,
    Rect,
    PointLike,
    RectLike,
    VNCConfig,
    pack_apple_remote_desktop,
    slice_rect,
    key_codes,
)

logger = logging.getLogger(__name__)


RFC_6143_CANON_STRING_ENCODING = "latin-1"
SUPPORTED_ENCODINGS = {
    ENCODING_ZLIB,
}


async def _read_bytes(reader: asyncio.StreamReader, length: int) -> bytes:
    """Read *length* bytes from the given stream reader."""
    data = b""
    while len(data) < length:
        chunk = await reader.read(length - len(data))
        if not chunk:
            raise ConnectionError("Connection closed unexpectedly")
        data += chunk
    return data


async def _read_int(reader: asyncio.StreamReader, length: int) -> int:
    """Read *length* bytes and decode as big-endian integer."""
    return int.from_bytes(await _read_bytes(reader, length), "big")


class VNCClient:
    """An asynchronous VNC client with a persistent background event loop."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        rect: Rect,
        pixel_format: PixelFormat,
        desktop_name: str,
    ):
        self.rect = rect
        self.pixel_format = pixel_format
        self.desktop_name = desktop_name

        self._reader = reader
        self._writer = writer
        self._zlib_decompress = decompressobj().decompress

        # internal state
        self._pixels_rgba: Optional[np.ndarray] = None
        self._pixels_lock = asyncio.Lock()
        self._mouse_position: Point = Point(0, 0)  # not a literal type
        self._mouse_buttons: int = 0  # not a literal type

        # Background task management
        self._running = False
        self._listener_task: Optional[asyncio.Task[None]] = None
        self._capture_event = asyncio.Event()

    @classmethod
    async def connect(cls, config: VNCConfig) -> "VNCClient":
        """
        Connect to a VNC server and start the background event loop.

        Args:
            config: VNC connection configuration. If None, uses default.

        Returns:
            Connected VNCClient instance with running background task.
        """

        # Connect and handshake
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(config.host, config.port),
            timeout=config.connection_timeout,
        )

        intro = await _read_bytes(reader, VNC_PROTOCOL_HEADER_SIZE)
        if intro[:4] != VNC_PROTOCOL_PREFIX:
            raise ValueError("not a VNC server")
        writer.write(VNC_PROTOCOL_HEADER)
        await writer.drain()

        # Negotiate an authentication type
        auth_types = set(await _read_bytes(reader, await _read_int(reader, 1)))
        if not auth_types:
            reason = await _read_bytes(reader, await _read_int(reader, 4))
            raise ValueError(reason.decode("utf8"))
        for auth_type in (AUTH_TYPE_NONE, AUTH_TYPE_VNC, AUTH_TYPE_APPLE):
            if auth_type in auth_types:
                break
        else:
            raise ValueError(f"unsupported VNC auth types: {auth_types}")

        # Authentication routines are taken from https://github.com/barneygale/pytest-vnc/blob/main/pytest_vnc.py

        # VNC authentication
        if auth_type == AUTH_TYPE_VNC:
            writer.write(b"\x02")
            await writer.drain()
            if config.password is None:
                raise ValueError("VNC server requires password")
            des_key = config.password.encode(RFC_6143_CANON_STRING_ENCODING)[:8].ljust(
                8, b"\x00"
            )
            des_key = bytes(int(bin(n)[:1:-1].ljust(8, "0"), 2) for n in des_key)
            encryptor = Cipher(TripleDES(des_key), ECB()).encryptor()
            challenge = await _read_bytes(reader, 16)
            writer.write(encryptor.update(challenge) + encryptor.finalize())
            await writer.drain()

        # Apple authentication
        elif auth_type == AUTH_TYPE_APPLE:
            writer.write(b"\x21\x00\x00\x00\x0a\x01\x00RSA1\x00\x00\x00\x00")
            await writer.drain()
            if config.password is None or config.username is None:
                raise ValueError("VNC server requires username & password")
            await _read_bytes(reader, 6)  # padding
            host_key_bytes = await _read_bytes(reader, await _read_int(reader, 4))
            host_key = cast(RSAPublicKey, load_der_public_key(host_key_bytes))
            await _read_bytes(reader, 1)  # padding
            aes_key_bytes = token_bytes(16)
            # ECB is ok since only a single 128-byte block is encrypted
            encryptor = Cipher(AES128(aes_key_bytes), ECB()).encryptor()
            aes_block = pack_apple_remote_desktop(
                config.username
            ) + pack_apple_remote_desktop(config.password)
            assert len(aes_block) == 128
            encrypted_creds = encryptor.update(aes_block)
            del encryptor  # further uses of the encryptor compromise the security model, delete to prevent accdl. uses
            encrypted_session_key = host_key.encrypt(aes_key_bytes, PKCS1v15())
            response_payload = (
                b"\x00\x00\x01\x8a\x01\x00RSA1"
                + (b"\x00\x01" + encrypted_creds)
                + (b"\x00\x01" + encrypted_session_key)
            )
            writer.write(response_payload)
            await writer.drain()
            # server will calculate a response and will either close connection or allow following read
            # to succeed
            await _read_bytes(reader, 4)

        # No authentication
        elif auth_type == AUTH_TYPE_NONE:
            writer.write(b"\x01")
            await writer.drain()

        # Check auth result
        auth_result = await _read_int(reader, 4)
        if auth_result == AUTH_STATE_PERMITTED:
            pass
        elif auth_result == AUTH_STATE_FAILED:
            raise PermissionError("VNC auth failed (retry permitted)")
        elif auth_result == AUTH_STATE_LOCKOUT:
            raise PermissionError("VNC auth failed (too many attempts)")
        else:
            raise PermissionError(f"VNC auth failed (unknown reason {auth_result})")

        # Negotiate pixel format and encodings
        # https://datatracker.ietf.org/doc/html/rfc6143#section-7.3.1
        shared_flag = b"\x01"  # could be 0 if we want exclusive
        writer.write(shared_flag)
        await writer.drain()
        # https://datatracker.ietf.org/doc/html/rfc6143#section-7.3.2)
        framebuffer_width = await _read_int(reader, 2)
        framebuffer_height = await _read_int(reader, 2)
        pixel_format = PixelFormat.deserialize(await _read_bytes(reader, 16))
        desktop_name = (await _read_bytes(reader, await _read_int(reader, 4))).decode(
            RFC_6143_CANON_STRING_ENCODING
        )

        # at this point in time, the connection is live and the object can be initialized
        rect = Rect(0, 0, framebuffer_width, framebuffer_height)
        vnc_client = cls(
            reader,
            writer,
            rect=rect,
            pixel_format=pixel_format,
            desktop_name=desktop_name,
        )

        # some servers, like VMw, ignore sent pixel formats, so if it's possible to use the one that has been sent to us we will use it
        if not pixel_format.true_color_flag:
            raise NotImplementedError("Pallet encoding is not supported")
        elif (pixel_format.bits_per_pixel != 32) or (pixel_format.depth != 24):
            raise NotImplementedError("Non-32bpp servers are not supported")
        elif (
            (pixel_format.blue_max != 255)
            or (pixel_format.red_max != 255)
            or (pixel_format.green_max != 255)
        ):
            raise NotImplementedError("Only 8bit color is support")
        elif pixel_format.big_endian_flag:
            raise NotImplementedError("Only little-endian pixel colors are supported.")

        await vnc_client._set_encodings(*SUPPORTED_ENCODINGS)

        # we're good to start listening for server -> client messages now
        vnc_client._running = True
        vnc_client._listener_task = asyncio.create_task(
            vnc_client._framebuffer_listener(), name="vnc_frame_listener"
        )

        # run an initial capture to populate the framebuffer, since some servers defer
        # opening a draw context until after the first request for framebuffer has been made
        await vnc_client.capture()

        # ditto, to make sure the mouse position is where the client specifies for the first caller
        await vnc_client.move(vnc_client._mouse_position)

        return vnc_client

    async def close(self) -> None:
        """Close the VNC connection and stop background task."""
        self._running = False

        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        self._writer.close()
        await self._writer.wait_closed()

    async def __aenter__(self) -> "VNCClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any | None,
    ) -> None:
        await self.close()

    async def _framebuffer_listener(self) -> None:
        """
        Background task: continuously listens for VNC server framebuffer updates.
        Runs until _running is set to False.
        """
        while self._running:
            try:
                update_type = await _read_int(self._reader, 1)

                if update_type == MSG_TYPE_CLIPBOARD:
                    # Skip clipboard data - not implementing clipboard sync
                    await _read_bytes(self._reader, await _read_int(self._reader, 4))

                elif update_type == MSG_TYPE_FRAMEBUFFER_UPDATE:
                    await self._handle_framebuffer_update()

                else:
                    # Unknown message type - log and skip to avoid blocking
                    logger.warning(f"Unknown VNC message type: {update_type}, skipping")

            except asyncio.CancelledError:
                break
            except ConnectionError:
                # Connection closed
                break
            except Exception:
                # Log and continue
                continue

    async def _handle_framebuffer_update(self) -> None:
        """Process a framebuffer update message from the server."""
        await _read_bytes(self._reader, 1)  # padding

        num_rects = await _read_int(self._reader, 2)

        async with self._pixels_lock:
            if self._pixels_rgba is None:
                # Initialize framebuffer on first update
                self._pixels_rgba = np.zeros(
                    (self.rect.height, self.rect.width, 4), "B"
                )

            for _ in range(num_rects):
                area_rect = Rect(
                    await _read_int(self._reader, 2),
                    await _read_int(self._reader, 2),
                    await _read_int(self._reader, 2),
                    await _read_int(self._reader, 2),
                )
                area_encoding = await _read_int(self._reader, 4)

                if area_encoding == ENCODING_RAW:
                    area = await _read_bytes(
                        self._reader, area_rect.height * area_rect.width * 4
                    )
                elif area_encoding == ENCODING_ZLIB:
                    compressed = await _read_bytes(
                        self._reader, await _read_int(self._reader, 4)
                    )
                    area = self._zlib_decompress(compressed)
                else:
                    # Skip unsupported encoding
                    logger.warning(
                        f"Unsupported VNC encoding: {area_encoding}, skipping rectangle"
                    )
                    continue

                area_pixels_native = np.ndarray(
                    (area_rect.height, area_rect.width, 4), "B", area
                )
                area_pixels_rgba = area_pixels_native.copy()

                # Channel index = shift // 8 (each channel is 8 bits wide)
                r_idx = self.pixel_format.red_shift // 8
                g_idx = self.pixel_format.green_shift // 8
                b_idx = self.pixel_format.blue_shift // 8

                # Determine if any channel is out of standard RGBA order (R=0, G=1, B=2)
                if r_idx != 0 or g_idx != 1 or b_idx != 2:
                    area_pixels_rgba[:, :, 0] = area_pixels_native[:, :, r_idx]  # R
                    area_pixels_rgba[:, :, 1] = area_pixels_native[:, :, g_idx]  # G
                    area_pixels_rgba[:, :, 2] = area_pixels_native[:, :, b_idx]  # B

                self._pixels_rgba[slice_rect(area_rect)] = area_pixels_rgba
                self._pixels_rgba[slice_rect(area_rect, slice(3, 4))] = (
                    255  # Set alpha channel
                )

        # Signal that new framebuffer data is available
        self._capture_event.set()

    # 0
    async def _set_pixel_format(self, new_pixel_format: PixelFormat) -> None:
        self._writer.write(b"\x00" + b"\x00\x00\x00" + new_pixel_format.serialize())
        await self._writer.drain()
        self.pixel_format = new_pixel_format

    # 2
    async def _set_encodings(self, *encodings: int) -> None:
        self._writer.write(
            b"\x02\x00"
            + len(encodings).to_bytes(2, "big")
            + b"".join(encoding.to_bytes(4, "big") for encoding in encodings)
        )
        await self._writer.drain()

    # 3
    async def _framebuffer_update_request(self, rect: Rect) -> None:
        """Send a framebuffer update request to the VNC server."""
        self._writer.write(
            b"\x03\x00"
            + rect.x.to_bytes(2, "big")
            + rect.y.to_bytes(2, "big")
            + rect.width.to_bytes(2, "big")
            + rect.height.to_bytes(2, "big")
        )
        await self._writer.drain()

    # 6
    async def _client_cut_text(self) -> None:
        raise NotImplementedError

    async def capture(
        self,
        rect: Optional[Union[Rect, RectLike]] = None,
        *,
        wait: bool = True,
        timeout: Optional[float] = 10.0,
    ) -> np.ndarray:
        """
        Take a screenshot and return pixels as an RGBA numpy array.

        Args:
            rect: Region to capture. If None, captures entire screen.
            wait: If True, wait for the server to send an update before returning.
                  If False, return current buffer (may be None if no data yet).
            timeout: Maximum time to wait for update (seconds). None for no timeout.

        Returns:
            RGBA numpy array of the specified region.
        """
        # Convert rect to absolute coordinates
        target_rect = (
            self.rect
            if rect is None
            else (rect.get_rect() if isinstance(rect, RectLike) else rect)
        )

        # Ensure we have a valid target rect
        assert isinstance(target_rect, Rect)

        # Request update from server
        await self._framebuffer_update_request(target_rect)

        if wait:
            # Clear event and wait for update
            self._capture_event.clear()
            try:
                await asyncio.wait_for(self._capture_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass  # Return whatever we have

        async with self._pixels_lock:
            if self._pixels_rgba is None:
                raise RuntimeError("No framebuffer data available yet")

            return self._pixels_rgba[slice_rect(target_rect)].copy()

    # Keyboard and mouse methods unchanged from original

    @asynccontextmanager
    async def _write_key(self, key: str) -> AsyncIterator["VNCClient"]:
        data = key_codes[key].to_bytes(4, "big")
        self._writer.write(b"\x04\x01\x00\x00" + data)
        await self._writer.drain()
        try:
            yield self
        finally:
            self._writer.write(b"\x04\x00\x00\x00" + data)
            await self._writer.drain()

    async def _write_mouse(self) -> None:
        self._writer.write(
            b"\x05"
            + self._mouse_buttons.to_bytes(1, "big")
            + self._mouse_position.x.to_bytes(2, "big")
            + self._mouse_position.y.to_bytes(2, "big")
        )
        await self._writer.drain()

    @asynccontextmanager
    async def hold_key(self, *keys: str) -> AsyncIterator["VNCClient"]:
        """Context manager that presses keys on enter, releases them on exit."""
        async with AsyncExitStack() as stack:
            for key in keys:
                await stack.enter_async_context(self._write_key(key))
            yield self

    async def press(self, *keys: str) -> "VNCClient":
        """Push all given keys, then release them in reverse order."""
        async with self.hold_key(*keys):
            pass
        return self

    async def write(self, text: str) -> "VNCClient":
        """Push and release each key one after the other."""
        for key in text:
            async with self.hold_key(key):
                pass
        return self

    @asynccontextmanager
    async def hold_mouse(
        self, button: int = MOUSE_BUTTON_LEFT
    ) -> AsyncIterator["VNCClient"]:
        """Context manager that holds a mouse button for dragging."""
        mask = 1 << button
        self._mouse_buttons |= mask
        await self._write_mouse()
        try:
            yield self
        finally:
            self._mouse_buttons &= ~mask
            await self._write_mouse()

    async def click(self, button: int = MOUSE_BUTTON_LEFT) -> "VNCClient":
        """Press and release a mouse button."""
        async with self.hold_mouse(button):
            pass
        return self

    async def double_click(self, button: int = MOUSE_BUTTON_LEFT) -> "VNCClient":
        """Press and release a mouse button twice."""
        await self.click(button)
        await self.click(button)
        return self

    async def scroll_up(self, repeat: int = 1) -> "VNCClient":
        """Scroll the mouse wheel upwards."""
        for _ in range(repeat):
            await self.click(MOUSE_BUTTON_SCROLL_UP)
        return self

    async def scroll_down(self, repeat: int = 1) -> "VNCClient":
        """Scroll the mouse wheel downwards."""
        for _ in range(repeat):
            await self.click(MOUSE_BUTTON_SCROLL_DOWN)
        return self

    async def move(self, point: Union[Point, PointLike]) -> "VNCClient":
        """Move the mouse cursor to the given coordinates."""
        if isinstance(point, PointLike):
            point = point.get_point()

        self._mouse_position = point
        await self._write_mouse()
        return self

    async def click_at(
        self, point: Union[Point, PointLike], button: int = MOUSE_BUTTON_LEFT
    ) -> "VNCClient":
        """Move to a point and click."""
        await self.move(point)
        await self.click(button)
        return self

    async def double_click_at(
        self, point: Union[Point, PointLike], button: int = MOUSE_BUTTON_LEFT
    ) -> "VNCClient":
        """Move to a point and double-click."""
        await self.move(point)
        await self.double_click(button)
        return self


__all__ = [
    "VNCClient",
]
