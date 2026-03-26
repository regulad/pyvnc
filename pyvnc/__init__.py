"""
pyvnc: An asynchronous pure Python VNC client library.

This library provides asynchronous VNC client functionality for capturing
screenshots and sending keyboard & mouse input to VNC servers.

Quick Start::

    import asyncio
    from pyvnc import VNCClient, VNCConfig, Point, Rect
    from PIL import Image

    async def main():
        # Configure connection
        config = VNCConfig(
            host='localhost',
            port=5900,
            password='your_password'
        )

        # Connect and interact with VNC server
        async with await VNCClient.connect(config) as vnc:
            # Take screenshots
            screenshot = await vnc.capture()

            # Save as PNG using PIL
            image = Image.fromarray(screenshot, 'RGBA')
            image.save('screenshot.png')

            # Move mouse and click
            await vnc.move(Point(100, 200))
            await vnc.click(MOUSE_BUTTON_LEFT)
            await vnc.click(MOUSE_BUTTON_MIDDLE)
            await vnc.click(MOUSE_BUTTON_RIGHT)

            # Type text
            await vnc.write('Hello VNC!')
            await vnc.press('Return')

            # Hold keys for combinations
            async with vnc.hold_key('Ctrl'):
                await vnc.press('c')  # Ctrl+C

            # Drag operations
            async with vnc.hold_mouse(MOUSE_BUTTON_LEFT):
                await vnc.move(Point(500, 600))

    asyncio.run(main())

Relative Coordinates:
    pyvnc provides a resolution-independent coordinate system:
    - Automatically scales to maintain aspect ratio close to actual screen
    - Both width and height are multiples of 100 (easy mental math)
    - Maximum dimensions are 99900 (for any aspect ratio)
    - Use relative=True parameter in mouse/capture methods
    - Get dimensions with vnc.get_relative_resolution()

Mouse Button Constants:
    Use these constants instead of raw numbers:
    - MOUSE_BUTTON_LEFT (0)
    - MOUSE_BUTTON_MIDDLE (1)
    - MOUSE_BUTTON_RIGHT (2)
    - MOUSE_BUTTON_SCROLL_UP (3)
    - MOUSE_BUTTON_SCROLL_DOWN (4)

Authentication:
    Supports VNC password and no authentication.
    Apple Remote Desktop auth raises NotImplementedError with helpful message.
"""

from .pyvnc_common import (
    AUTH_TYPE_APPLE,
    AUTH_TYPE_NONE,
    AUTH_TYPE_VNC,
    ENCODING_RAW,
    ENCODING_ZLIB,
    MOUSE_BUTTON_LEFT,
    MOUSE_BUTTON_MIDDLE,
    MOUSE_BUTTON_RIGHT,
    MOUSE_BUTTON_SCROLL_DOWN,
    MOUSE_BUTTON_SCROLL_UP,
    MSG_TYPE_CLIPBOARD,
    MSG_TYPE_FRAMEBUFFER_UPDATE,
    Point,
    PointLike,
    Rect,
    RectLike,
    VNCConfig,
    VNC_PROTOCOL_HEADER_SIZE,
    VNC_PROTOCOL_PREFIX,
    VNC_PROTOCOL_VERSION,
    encodings,
    key_codes,
    pixel_formats,
    slice_rect,
)
from .pyvnc_async import VNCClient

__version__ = "3.0.0"

__all__ = [
    "AUTH_TYPE_APPLE",
    "AUTH_TYPE_NONE",
    "AUTH_TYPE_VNC",
    "ENCODING_RAW",
    "ENCODING_ZLIB",
    "MOUSE_BUTTON_LEFT",
    "MOUSE_BUTTON_MIDDLE",
    "MOUSE_BUTTON_RIGHT",
    "MOUSE_BUTTON_SCROLL_DOWN",
    "MOUSE_BUTTON_SCROLL_UP",
    "MSG_TYPE_CLIPBOARD",
    "MSG_TYPE_FRAMEBUFFER_UPDATE",
    "Point",
    "PointLike",
    "Rect",
    "RectLike",
    "VNCConfig",
    "VNC_PROTOCOL_HEADER_SIZE",
    "VNC_PROTOCOL_PREFIX",
    "VNC_PROTOCOL_VERSION",
    "encodings",
    "key_codes",
    "pixel_formats",
    "slice_rect",
    "VNCClient",
]
