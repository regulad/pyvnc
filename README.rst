pyvnc: capture screen and send keyboard & mouse
===============================================

.. image:: https://img.shields.io/badge/source-github-orange
   :target: https://github.com/regulad/pyvnc


pyvnc implements an asynchronous VNC client in pure Python. It works on Mac, Linux and Windows. Use it to
capture screenshots and send keyboard & mouse input to VNC servers:

**Note**: This library was transformed from pytest-vnc with significant contributions from Claude AI (Anthropic)
to create a standalone, production-ready async VNC client library.

Async VNC client with background event loop

Quick Start
-----------

.. code-block:: python

    import asyncio
    from pyvnc import VNCClient, VNCConfig, Rect, Point, MOUSE_BUTTON_LEFT, MOUSE_BUTTON_MIDDLE, MOUSE_BUTTON_RIGHT
    from PIL import Image

    async def main():
        # Connect to VNC server
        config = VNCConfig(host='localhost', port=5900, password='secret')
        async with await VNCClient.connect(config) as vnc:
            # Screenshot
            print(vnc.rect.width, vnc.rect.height)
            pixels = await vnc.capture()  # rgba numpy array of entire screen
            pixels = await vnc.capture(Rect(x=100, y=0, width=50, height=75))

            # Save as PNG using PIL
            image = Image.fromarray(pixels, 'RGBA')
            image.save('screenshot.png')

            # Keyboard input
            await vnc.write('hi there!')
            await vnc.press('Ctrl', 'c')
            async with vnc.hold_key('Ctrl'):
                await vnc.press('Esc')

            # Mouse input
            await vnc.move(Point(100, 200))
            await vnc.click(MOUSE_BUTTON_LEFT)
            await vnc.click(MOUSE_BUTTON_MIDDLE)
            await vnc.click(MOUSE_BUTTON_RIGHT)
            await vnc.double_click(MOUSE_BUTTON_LEFT)
            await vnc.scroll_up()
            await vnc.scroll_down(repeat=10)
            async with vnc.hold_mouse():
                await vnc.move(Point(300, 400))  # Drag with left button

    asyncio.run(main())


Installation
------------

This package requires Python 3.9+.

Install pyvnc directly from GitHub::

    # Latest version (may be unstable)
    pip install git+https://github.com/regulad/pyvnc.git

    # Specific commit (recommended for production)
    pip install git+https://github.com/regulad/pyvnc.git@<commit-hash>

Or for development, clone and install locally::

    git clone https://github.com/regulad/pyvnc.git
    cd pyvnc
    pip install -e .


Configuration
-------------

Create a VNCConfig object to specify connection parameters:

.. code-block:: python

    from pyvnc import VNCConfig

    config = VNCConfig(
        host='localhost',         # VNC hostname (default: localhost)
        port=5900,                # VNC port (default: 5900)
        connection_timeout=5.0,   # Connection timeout in seconds (default: 5)
        username='user',          # VNC username (optional, Apple auth only)
        password='secret',        # VNC password (optional)

        # Retry behaviour for the initial connection
        max_retries=3,            # Connection attempts (default: 3)
        retry_delay=1.0,          # Delay before the first retry (default: 1)
        retry_backoff=2.0,        # Multiplier applied after each retry (default: 2)

        # Reconnection behaviour once connected
        auto_reconnect=True,      # Reconnect if the connection drops (default: True)
        reconnect_delay=2.0,      # Delay before the first reconnect (default: 2)
    )

The pixel format is not configurable. pyvnc uses whatever true-colour format the
server offers, and only asks the server to change it (via ``SetPixelFormat``) when
that format cannot be decoded. Captures are always returned as RGBA regardless of
the channel order on the wire.

Coordinates are absolute pixels in the server's framebuffer. Read the framebuffer
size from ``vnc.rect`` and scale your own values against ``vnc.rect.width`` and
``vnc.rect.height``.


RFC 6143 compliance
-------------------

pyvnc is a fully RFC 6143 compliant RFB 3.8 client. Every message it sends and
every message it accepts follows the layouts in `RFC 6143
<https://www.rfc-editor.org/rfc/rfc6143>`_, and compliance is enforced by an
automated conformance suite (``tests/test_rfc6143.py``) that runs the client
against a scripted mock server. Specifically:

* **ProtocolVersion (7.1.1)** -- the client never requests a version higher than
  the server offered. A server advertising an older version (3.3 or 3.7, which use
  a different security handshake) is rejected with ``NotImplementedError`` rather
  than spoken to incorrectly; a newer server is negotiated down to 3.8.
* **Security handshake (7.1.2, 7.2)** -- the strongest security type the server
  offers and the client has credentials for is chosen, in the order Apple Remote
  Desktop, VNC password, then None. ``SecurityResult`` is always read, including
  after the ``None`` type, as 3.8 requires.
* **SecurityResult (7.1.3)** -- the reason string a server sends after a failed
  handshake is read and reported, rather than discarded.
* **Client messages (7.5)** -- ``SetPixelFormat``, ``SetEncodings`` (with signed
  encoding numbers), ``FramebufferUpdateRequest``, ``KeyEvent`` and
  ``PointerEvent`` are emitted with exactly the specified fields and padding.
* **Server messages (7.6)** -- ``FramebufferUpdate`` (0),
  ``SetColourMapEntries`` (1), ``Bell`` (2) and ``ServerCutText`` (3) are each
  framed and consumed exactly. Messages the client does not act on are still
  drained in full, so the stream cannot desynchronise. Every rectangle is
  validated to lie inside the framebuffer.

The RFC requires clients to support the ``raw`` encoding; pyvnc does, and also
negotiates ``zlib``. The RFC's other encodings (``CopyRect``, ``RRE``,
``Hextile``, ``TRLE``, ``ZRLE``) are optional and not implemented -- a server
only sends encodings the client advertises, so this does not affect compliance.

pyvnc decodes true-colour pixel formats at 32 bits per pixel with 8 bits per
channel and byte-aligned, little-endian channel shifts (colour depth 24 or 32).
When a server's own format falls outside that, the client asks for one it can
decode via ``SetPixelFormat``, which section 7.5.1 requires servers to honour.
Palette (non true-colour) servers are not supported.

Authentication: none, VNC password, and Apple Remote Desktop.


Tested servers
--------------

Tested against:

* **TrollVNC** (iOS/iPadOS) -- reports colour depth 32 with BGRA channel order;
  full-frame updates in 21-row zlib strips. Screen capture, pointer input
  (including drag and scroll wheel) and keyboard input all work.
* **UltraVNC** (Windows)
* **VMware** VNC servers -- these ignore ``SetPixelFormat``, so pyvnc keeps the
  server's own format and converts channel order client-side.


Testing
-------

For development and testing, create a ``.env`` file in the project root::

    # Test VNC Server Configuration
    VNC_HOST=localhost
    VNC_PORT=5900
    VNC_PASSWORD=your_password_here
    # Optional: VNC_USERNAME=your_username

Run tests::

    # Install test dependencies
    pip install -e ".[test]"

    # RFC 6143 conformance tests, against an in-process mock server
    # (no VNC server required)
    PYTHONPATH=. python tests/test_rfc6143.py

    # Unit tests for the reconnection logic (no VNC server required)
    PYTHONPATH=. python tests/test_reconnection.py

    # Comprehensive test suite (includes integration tests)
    PYTHONPATH=. python tests/test_comprehensive.py

    # Async integration tests
    PYTHONPATH=. python tests/test_async.py

    # Integration tests for the refactored client
    PYTHONPATH=. python tests/test_refactor.py

The integration tests need a reachable VNC server matching the ``.env`` settings
above.
