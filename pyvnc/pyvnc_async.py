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
    PIXEL_FORMATS,
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
        config: VNCConfig,
    ):
        self._config = config

        # Connection state (initialized in _perform_handshake)
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self.rect: Rect = Rect(0, 0, 0, 0)
        self.pixel_format: PixelFormat = PIXEL_FORMATS["bgra"]
        self.desktop_name: str = ""

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

        # Reconnection state
        self._connected = False
        self._reconnecting = False
        self._reconnect_event = asyncio.Event()
        self._reconnect_event.set()  # Initially not reconnecting
        self._last_error: Optional[Exception] = None

    async def _perform_handshake(self) -> None:
        """Perform VNC protocol handshake and authentication.

        Sets self._reader, self._writer, self.rect, self.pixel_format, self.desktop_name.
        """
        # Connect and handshake
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self._config.host, self._config.port),
            timeout=self._config.connection_timeout,
        )
        assert self._reader is not None and self._writer is not None

        intro = await _read_bytes(self._reader, VNC_PROTOCOL_HEADER_SIZE)
        if intro[:4] != VNC_PROTOCOL_PREFIX:
            raise ValueError("not a VNC server")
        self._writer.write(VNC_PROTOCOL_HEADER)
        await self._writer.drain()

        # Negotiate an authentication type
        auth_types = set(
            await _read_bytes(self._reader, await _read_int(self._reader, 1))
        )
        if not auth_types:
            reason = await _read_bytes(self._reader, await _read_int(self._reader, 4))
            raise ValueError(reason.decode("utf8"))
        for auth_type in (AUTH_TYPE_NONE, AUTH_TYPE_VNC, AUTH_TYPE_APPLE):
            if auth_type in auth_types:
                break
        else:
            raise ValueError(f"unsupported VNC auth types: {auth_types}")

        # Authentication routines are taken from https://github.com/barneygale/pytest-vnc/blob/main/pytest_vnc.py

        # VNC authentication
        if auth_type == AUTH_TYPE_VNC:
            self._writer.write(b"\x02")
            await self._writer.drain()
            if self._config.password is None:
                raise ValueError("VNC server requires password")
            des_key = self._config.password.encode(RFC_6143_CANON_STRING_ENCODING)[
                :8
            ].ljust(8, b"\x00")
            des_key = bytes(int(bin(n)[:1:-1].ljust(8, "0"), 2) for n in des_key)
            encryptor = Cipher(TripleDES(des_key), ECB()).encryptor()
            challenge = await _read_bytes(self._reader, 16)
            self._writer.write(encryptor.update(challenge) + encryptor.finalize())
            await self._writer.drain()

        # Apple authentication
        elif auth_type == AUTH_TYPE_APPLE:
            self._writer.write(b"\x21\x00\x00\x00\x0a\x01\x00RSA1\x00\x00\x00\x00")
            await self._writer.drain()
            if self._config.password is None or self._config.username is None:
                raise ValueError("VNC server requires username & password")
            await _read_bytes(self._reader, 6)  # padding
            host_key_bytes = await _read_bytes(
                self._reader, await _read_int(self._reader, 4)
            )
            host_key = cast(RSAPublicKey, load_der_public_key(host_key_bytes))
            await _read_bytes(self._reader, 1)  # padding
            aes_key_bytes = token_bytes(16)
            # ECB is ok since only a single 128-byte block is encrypted
            encryptor = Cipher(AES128(aes_key_bytes), ECB()).encryptor()
            aes_block = pack_apple_remote_desktop(
                self._config.username
            ) + pack_apple_remote_desktop(self._config.password)
            assert len(aes_block) == 128
            encrypted_creds = encryptor.update(aes_block)
            del encryptor  # further uses of the encryptor compromise the security model, delete to prevent accdl. uses
            encrypted_session_key = host_key.encrypt(aes_key_bytes, PKCS1v15())
            response_payload = (
                b"\x00\x00\x01\x8a\x01\x00RSA1"
                + (b"\x00\x01" + encrypted_creds)
                + (b"\x00\x01" + encrypted_session_key)
            )
            self._writer.write(response_payload)
            await self._writer.drain()
            # server will calculate a response and will either close connection or allow following read
            # to succeed
            await _read_bytes(self._reader, 4)

        # No authentication
        elif auth_type == AUTH_TYPE_NONE:
            self._writer.write(b"\x01")
            await self._writer.drain()

        # Check auth result
        auth_result = await _read_int(self._reader, 4)
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
        self._writer.write(shared_flag)
        await self._writer.drain()
        # https://datatracker.ietf.org/doc/html/rfc6143#section-7.3.2)
        framebuffer_width = await _read_int(self._reader, 2)
        framebuffer_height = await _read_int(self._reader, 2)
        self.pixel_format = PixelFormat.deserialize(await _read_bytes(self._reader, 16))
        self.desktop_name = (
            await _read_bytes(self._reader, await _read_int(self._reader, 4))
        ).decode(RFC_6143_CANON_STRING_ENCODING)

        # at this point in time, the connection is live
        self.rect = Rect(0, 0, framebuffer_width, framebuffer_height)

        # some servers, like VMw, ignore sent pixel formats, so if it's possible to use the one that has been sent to us we will use it
        if not self.pixel_format.true_color_flag:
            raise NotImplementedError("Pallet encoding is not supported")
        elif (self.pixel_format.bits_per_pixel != 32) or (
            self.pixel_format.depth != 24
        ):
            raise NotImplementedError("Non-32bpp servers are not supported")
        elif (
            (self.pixel_format.blue_max != 255)
            or (self.pixel_format.red_max != 255)
            or (self.pixel_format.green_max != 255)
        ):
            raise NotImplementedError("Only 8bit color is support")
        elif self.pixel_format.big_endian_flag:
            raise NotImplementedError("Only little-endian pixel colors are supported.")

        await self._set_encodings(*SUPPORTED_ENCODINGS)

    @classmethod
    async def connect(cls, config: VNCConfig) -> "VNCClient":
        """
        Connect to a VNC server with retry logic and start the background event loop.

        Args:
            config: VNC connection configuration.

        Returns:
            Connected VNCClient instance with running background task.

        Raises:
            ConnectionError: If unable to connect after max_retries.
        """
        client = cls(config)

        # Retry loop for initial connection
        last_error: Optional[Exception] = None
        delay = config.retry_delay

        for attempt in range(config.max_retries):
            try:
                logger.debug(f"Connection attempt {attempt + 1}/{config.max_retries}")
                await client._perform_handshake()
                client._connected = True
                break
            except (OSError, ConnectionError, asyncio.TimeoutError) as e:
                last_error = e
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < config.max_retries - 1:
                    logger.debug(f"Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
                    delay *= config.retry_backoff
            except Exception:
                # Non-retryable errors (auth failure, protocol errors, etc.)
                raise
        else:
            # All retries exhausted
            raise ConnectionError(
                f"Failed to connect to VNC server at {config.host}:{config.port} "
                f"after {config.max_retries} attempts"
            ) from last_error

        client._last_error = None

        # we're good to start listening for server -> client messages now
        client._running = True
        client._listener_task = asyncio.create_task(
            client._framebuffer_listener(), name="vnc_frame_listener"
        )

        # run an initial capture to populate the framebuffer, since some servers defer
        # opening a draw context until after the first request for framebuffer has been made
        await client.capture()

        # ditto, to make sure the mouse position is where the client specifies for the first caller
        await client.move(client._mouse_position)

        return client

    @property
    def is_connected(self) -> bool:
        """Check if the client is currently connected."""
        return self._connected and self._running

    @property
    def last_error(self) -> Optional[Exception]:
        """Return the last error that occurred during connection/reconnection."""
        return self._last_error

    async def _cleanup_connection(self) -> None:
        """Clean up the current connection resources."""
        self._connected = False

        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
        self._reader = None

    async def _reconnect(self) -> bool:
        """Attempt to reconnect to the VNC server.

        Returns:
            True if reconnection succeeded, False otherwise.
        """
        if self._reconnecting:
            # Wait for existing reconnection attempt to complete
            await self._reconnect_event.wait()
            return self._connected

        self._reconnecting = True
        self._reconnect_event.clear()

        try:
            # Clean up old connection
            await self._cleanup_connection()

            # Cancel old listener task
            if self._listener_task:
                self._listener_task.cancel()
                try:
                    await self._listener_task
                except asyncio.CancelledError:
                    pass
                self._listener_task = None

            # Attempt reconnection with the same retry logic as initial connect
            delay = self._config.reconnect_delay
            last_error: Optional[Exception] = None

            for attempt in range(self._config.max_retries):
                try:
                    logger.debug(
                        f"Reconnection attempt {attempt + 1}/{self._config.max_retries}"
                    )
                    await self._perform_handshake()
                    self._connected = True
                    self._last_error = None

                    # Restart the listener task
                    self._listener_task = asyncio.create_task(
                        self._framebuffer_listener(), name="vnc_frame_listener"
                    )

                    # Reset framebuffer since dimensions may have changed
                    self._pixels_rgba = None

                    # Restore mouse position on reconnect
                    await self.move(self._mouse_position)

                    logger.info("VNC reconnection successful")
                    return True

                except (OSError, ConnectionError, asyncio.TimeoutError) as e:
                    last_error = e
                    logger.warning(f"Reconnection attempt {attempt + 1} failed: {e}")
                    if attempt < self._config.max_retries - 1:
                        await asyncio.sleep(delay)
                        delay *= self._config.retry_backoff
                except Exception as e:
                    # Non-retryable errors
                    logger.error(f"Reconnection failed with non-retryable error: {e}")
                    self._last_error = e
                    return False

            # All retries exhausted
            logger.error(
                f"Failed to reconnect after {self._config.max_retries} attempts"
            )
            self._last_error = last_error
            self._running = False
            return False

        finally:
            self._reconnecting = False
            self._reconnect_event.set()

    async def close(self) -> None:
        """Close the VNC connection and stop background task."""
        self._running = False
        self._config.auto_reconnect = False  # Prevent auto-reconnect on close

        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        await self._cleanup_connection()

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
                if self._reader is None:
                    raise ConnectionError("Reader is None")
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
                # Connection closed - attempt reconnection if enabled
                logger.warning("Connection lost, attempting to reconnect...")
                self._connected = False

                if self._config.auto_reconnect:
                    success = await self._reconnect()
                    if not success:
                        # Reconnection failed, stop the listener
                        logger.error("Reconnection failed, stopping listener")
                        break
                else:
                    # Auto-reconnect disabled
                    logger.info("Auto-reconnect disabled, closing connection")
                    break
            except Exception:
                # Log and continue
                logger.exception("Error in framebuffer listener")
                continue

    async def _handle_framebuffer_update(self) -> None:
        """Process a framebuffer update message from the server."""
        if self._reader is None:
            raise ConnectionError("Reader is None")
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
    async def _safe_write(self, data: bytes) -> bool:
        """Safely write data to the connection, handling reconnection.

        Returns:
            True if write succeeded, False if connection is down and reconnection failed.
        """
        # Wait for any ongoing reconnection
        if self._reconnecting:
            await self._reconnect_event.wait()

        if self._writer is None or not self._connected:
            if self._config.auto_reconnect and self._running:
                success = await self._reconnect()
                if not success:
                    return False
            else:
                return False

        try:
            assert self._writer is not None
            self._writer.write(data)
            await self._writer.drain()
            return True
        except (ConnectionError, OSError) as e:
            logger.warning(f"Write failed: {e}")
            self._connected = False
            if self._config.auto_reconnect and self._running:
                success = await self._reconnect()
                if success and self._writer is not None:
                    # Retry the write after reconnection
                    self._writer.write(data)
                    await self._writer.drain()
                    return True
            return False

    async def _set_pixel_format(self, new_pixel_format: PixelFormat) -> None:
        await self._safe_write(b"\x00" + b"\x00\x00\x00" + new_pixel_format.serialize())
        self.pixel_format = new_pixel_format

    # 2
    async def _set_encodings(self, *encodings: int) -> None:
        await self._safe_write(
            b"\x02\x00"
            + len(encodings).to_bytes(2, "big")
            + b"".join(encoding.to_bytes(4, "big") for encoding in encodings)
        )

    # 3
    async def _framebuffer_update_request(self, rect: Rect) -> bool:
        """Send a framebuffer update request to the VNC server."""
        return await self._safe_write(
            b"\x03\x00"
            + rect.x.to_bytes(2, "big")
            + rect.y.to_bytes(2, "big")
            + rect.width.to_bytes(2, "big")
            + rect.height.to_bytes(2, "big")
        )

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

        Raises:
            ConnectionError: If connection is down and reconnection failed.
            RuntimeError: If no framebuffer data is available.
        """
        # Wait for any ongoing reconnection first
        if self._reconnecting:
            await self._reconnect_event.wait()

        if not self._connected:
            if self._config.auto_reconnect and self._running:
                success = await self._reconnect()
                if not success:
                    raise ConnectionError("Connection down and reconnection failed")
            else:
                raise ConnectionError("Connection is closed")

        # Convert rect to absolute coordinates
        target_rect = (
            self.rect
            if rect is None
            else (rect.get_rect() if isinstance(rect, RectLike) else rect)
        )

        # Ensure we have a valid target rect
        assert isinstance(target_rect, Rect)

        # Request update from server
        success = await self._framebuffer_update_request(target_rect)
        if not success:
            raise ConnectionError(
                "Failed to send framebuffer request - connection down"
            )

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
        success = await self._safe_write(b"\x04\x01\x00\x00" + data)
        if not success:
            raise ConnectionError("Failed to send key press - connection down")
        try:
            yield self
        finally:
            await self._safe_write(b"\x04\x00\x00\x00" + data)

    async def _write_mouse(self) -> None:
        await self._safe_write(
            b"\x05"
            + self._mouse_buttons.to_bytes(1, "big")
            + self._mouse_position.x.to_bytes(2, "big")
            + self._mouse_position.y.to_bytes(2, "big")
        )

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
