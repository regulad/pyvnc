#!/usr/bin/env python3
"""RFC 6143 conformance tests for the pyvnc client.

These run against a scripted in-process RFB 3.8 server, so no external VNC server
is required. They pin the wire layouts that are easy to get subtly wrong:

* server-to-client message type numbers (section 7.6) - Bell is 2 and
  ServerCutText is 3, and both must be drained exactly or the stream desyncs
* client-to-server message layouts (section 7.5)
* the ProtocolVersion handshake (section 7.1.1)
* the SecurityResult failure reason (section 7.1.3)
"""

import asyncio
import struct
import sys
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyvnc import VNCClient, VNCConfig  # noqa: E402
from pyvnc.pyvnc_common import PIXEL_FORMATS  # noqa: E402

WIDTH, HEIGHT = 64, 32
PIXEL_FORMAT = PIXEL_FORMATS["bgra"]
VERSION_38 = b"RFB 003.008" + bytes([10])

# The mock server paints every pixel with this BGRx value, so a correctly decoded
# frame reads back as RGBA (9, 8, 7, 255).
FILL_BGRX = [7, 8, 9, 0]
EXPECTED_RGBA = [9, 8, 7, 255]


def framebuffer_update(rectangles):
    """Serialise a FramebufferUpdate message (RFC 6143 section 7.6.1)."""
    out = bytes([0, 0]) + struct.pack("!H", len(rectangles))
    for x, y, width, height, encoding, data in rectangles:
        out += struct.pack("!HHHH", x, y, width, height)
        out += struct.pack("!i", encoding) + data
    return out


class MockRFBServer:
    """A scripted RFB 3.8 server.

    ``injected`` is written immediately before the first FramebufferUpdate, which
    lets a test slip an out-of-band server message into the stream and assert that
    the client consumes it without losing framing.
    """

    def __init__(
        self, version=VERSION_38, security=(1,), injected=b"", security_result=0
    ):
        self.version = version
        self.security = security
        self.injected = injected
        self.security_result = security_result
        self.client_messages = []
        self.client_version = None
        self.chosen_security = None
        self._server = None

    async def start(self):
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self._server.sockets[0].getsockname()[1]

    def close(self):
        if self._server is not None:
            self._server.close()

    def message(self, kind):
        """Return the last client message of the given kind, or b''."""
        return dict(self.client_messages).get(kind, b"")

    async def _handle(self, reader, writer):
        try:
            writer.write(self.version)
            await writer.drain()
            self.client_version = await reader.readexactly(12)

            writer.write(bytes([len(self.security)]) + bytes(self.security))
            await writer.drain()
            self.chosen_security = (await reader.readexactly(1))[0]
            chosen = self.chosen_security
            if chosen == 2:  # VNC authentication: challenge then response
                writer.write(bytes(16))
                await writer.drain()
                await reader.readexactly(16)

            writer.write(struct.pack("!I", self.security_result))
            await writer.drain()
            if self.security_result != 0:
                reason = b"too many bad passwords"
                writer.write(struct.pack("!I", len(reason)) + reason)
                await writer.drain()
                return

            await reader.readexactly(1)  # ClientInit
            writer.write(
                struct.pack("!HH", WIDTH, HEIGHT)
                + PIXEL_FORMAT.serialize()
                + struct.pack("!I", 8)
                + b"MockRFB1"
            )
            await writer.drain()
            await self._serve_messages(reader, writer)
        except (
            asyncio.IncompleteReadError,
            ConnectionResetError,
            ConnectionAbortedError,
        ):
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass

    async def _serve_messages(self, reader, writer):
        compressor = zlib.compressobj()
        while True:
            message_type = (await reader.readexactly(1))[0]
            if message_type == 0:
                self.client_messages.append(
                    ("SetPixelFormat", await reader.readexactly(19))
                )
            elif message_type == 2:
                header = await reader.readexactly(3)
                count = struct.unpack("!H", header[1:3])[0]
                self.client_messages.append(
                    ("SetEncodings", await reader.readexactly(4 * count))
                )
            elif message_type == 3:
                self.client_messages.append(
                    ("FramebufferUpdateRequest", await reader.readexactly(9))
                )
                pixels = bytes(bytearray(FILL_BGRX * (WIDTH * HEIGHT)))
                blob = compressor.compress(pixels)
                blob += compressor.flush(zlib.Z_SYNC_FLUSH)
                payload = self.injected + framebuffer_update(
                    [(0, 0, WIDTH, HEIGHT, 6, struct.pack("!I", len(blob)) + blob)]
                )
                self.injected = b""
                writer.write(payload)
                await writer.drain()
            elif message_type == 4:
                self.client_messages.append(("KeyEvent", await reader.readexactly(7)))
            elif message_type == 5:
                self.client_messages.append(
                    ("PointerEvent", await reader.readexactly(5))
                )
            else:
                self.client_messages.append((f"Unknown{message_type}", b""))
                return


def config(port, **overrides):
    return VNCConfig(host="127.0.0.1", port=port, max_retries=1, **overrides)


class TestServerMessageFraming(unittest.IsolatedAsyncioTestCase):
    """Out-of-band server messages must be drained without losing stream framing."""

    async def _capture_after(self, injected):
        server = MockRFBServer(injected=injected)
        port = await server.start()
        try:
            async with await VNCClient.connect(config(port)) as vnc:
                return await vnc.capture()
        finally:
            server.close()

    async def test_bell_is_message_type_2_with_no_payload(self):
        """Bell (7.6.3) is a bare message type; reading a payload would desync."""
        pixels = await self._capture_after(bytes([2]))
        self.assertEqual(pixels.shape, (HEIGHT, WIDTH, 4))
        self.assertEqual(pixels[0, 0].tolist(), EXPECTED_RGBA)

    async def test_server_cut_text_is_type_3_with_padding_and_length(self):
        """ServerCutText (7.6.4) is padding(3) + length(4) + text."""
        text = b"clipboard contents"
        injected = bytes([3, 0, 0, 0]) + struct.pack("!I", len(text)) + text
        pixels = await self._capture_after(injected)
        self.assertEqual(pixels.shape, (HEIGHT, WIDTH, 4))
        self.assertEqual(pixels[0, 0].tolist(), EXPECTED_RGBA)

    async def test_set_colour_map_entries_is_type_1(self):
        """SetColourMapEntries (7.6.2) is pad(1) + first(2) + count(2) + count*6."""
        count = 3
        injected = bytes([1, 0]) + struct.pack("!HH", 0, count) + bytes(count * 6)
        pixels = await self._capture_after(injected)
        self.assertEqual(pixels.shape, (HEIGHT, WIDTH, 4))
        self.assertEqual(pixels[0, 0].tolist(), EXPECTED_RGBA)


class TestClientMessageLayouts(unittest.IsolatedAsyncioTestCase):
    """Client-to-server message layouts (RFC 6143 section 7.5)."""

    async def asyncSetUp(self):
        self.server = MockRFBServer()
        port = await self.server.start()
        async with await VNCClient.connect(config(port)) as vnc:
            await vnc.press("a")
        await asyncio.sleep(0.1)

    async def asyncTearDown(self):
        self.server.close()

    async def test_set_encodings_advertises_zlib_then_raw(self):
        body = self.server.message("SetEncodings")
        encodings = [
            struct.unpack("!i", body[i : i + 4])[0] for i in range(0, len(body), 4)
        ]
        self.assertEqual(encodings, [6, 0])

    async def test_framebuffer_update_request_layout(self):
        body = self.server.message("FramebufferUpdateRequest")
        self.assertEqual(len(body), 9)
        self.assertEqual(struct.unpack("!HHHH", body[1:9]), (0, 0, WIDTH, HEIGHT))

    async def test_key_event_layout(self):
        body = self.server.message("KeyEvent")
        self.assertEqual(len(body), 7)  # down-flag(1) + padding(2) + key(4)
        self.assertEqual(struct.unpack("!I", body[3:7])[0], ord("a"))

    async def test_pointer_event_layout(self):
        body = self.server.message("PointerEvent")
        self.assertEqual(len(body), 5)  # button-mask(1) + x(2) + y(2)


class TestProtocolVersionHandshake(unittest.IsolatedAsyncioTestCase):
    """RFC 6143 section 7.1.1."""

    async def test_rejects_server_older_than_3_8(self):
        """A client must never request a version higher than the server offered."""
        server = MockRFBServer(version=b"RFB 003.003" + bytes([10]))
        port = await server.start()
        try:
            with self.assertRaises(NotImplementedError):
                await VNCClient.connect(config(port))
        finally:
            server.close()

    async def test_accepts_newer_server_and_still_requests_3_8(self):
        server = MockRFBServer(version=b"RFB 004.001" + bytes([10]))
        port = await server.start()
        try:
            async with await VNCClient.connect(config(port)):
                pass
            self.assertEqual(server.client_version, VERSION_38)
        finally:
            server.close()

    async def test_rejects_non_rfb_greeting(self):
        server = MockRFBServer(version=b"NOTVNC" + bytes([10]) + bytes(5))
        port = await server.start()
        try:
            with self.assertRaises(ValueError):
                await VNCClient.connect(config(port))
        finally:
            server.close()


class TestSecurityResult(unittest.IsolatedAsyncioTestCase):
    """RFC 6143 section 7.1.3."""

    async def test_failure_reason_is_surfaced(self):
        """3.8 sends a reason string after a failed SecurityResult; report it.

        PermissionError subclasses OSError, so this also pins that a rejected
        password is not swallowed by the connection retry loop.
        """
        server = MockRFBServer(security=(2,), security_result=1)
        port = await server.start()
        try:
            with self.assertRaises(PermissionError) as caught:
                await VNCClient.connect(config(port, password="wrong"))
            self.assertIn("too many bad passwords", str(caught.exception))
        finally:
            server.close()


class TestSecurityTypePreference(unittest.IsolatedAsyncioTestCase):
    """The client prefers the strongest security type it can actually perform.

    Order is Apple (33) -> VNC (2) -> None (1), but a type whose credentials are
    missing is skipped rather than selected and then failed.
    """

    async def _negotiate(self, offered, **credentials):
        server = MockRFBServer(security=offered)
        port = await server.start()
        try:
            async with await VNCClient.connect(config(port, **credentials)):
                pass
            return server.chosen_security
        finally:
            server.close()

    async def test_prefers_vnc_auth_over_none(self):
        """With a password available, VNC auth beats unauthenticated access."""
        self.assertEqual(await self._negotiate((1, 2), password="secret"), 2)

    async def test_falls_back_to_none_without_a_password(self):
        self.assertEqual(await self._negotiate((1, 2)), 1)

    async def test_skips_apple_auth_without_a_username(self):
        """Apple auth needs both credentials; VNC auth must still be reachable."""
        self.assertEqual(await self._negotiate((1, 2, 33), password="secret"), 2)

    async def test_none_is_the_last_resort(self):
        server = MockRFBServer(security=(1,))
        port = await server.start()
        try:
            async with await VNCClient.connect(config(port, password="secret")):
                pass
            self.assertEqual(server.chosen_security, 1)
        finally:
            server.close()

    async def test_errors_when_no_offered_type_is_usable(self):
        server = MockRFBServer(security=(2,))  # VNC auth, but no password configured
        port = await server.start()
        try:
            with self.assertRaises(ValueError) as caught:
                await VNCClient.connect(config(port))
            self.assertIn("no usable VNC auth type", str(caught.exception))
        finally:
            server.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
