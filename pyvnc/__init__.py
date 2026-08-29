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

Coordinates:
    All coordinates are absolute pixels in the server's framebuffer. Read the
    framebuffer size from ``vnc.rect`` (a ``Rect`` whose ``x``/``y`` are always 0)
    and scale your own values against ``vnc.rect.width`` / ``vnc.rect.height``.

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
    MOUSE_BUTTON_LEFT,
    MOUSE_BUTTON_MIDDLE,
    MOUSE_BUTTON_RIGHT,
    MOUSE_BUTTON_SCROLL_DOWN,
    MOUSE_BUTTON_SCROLL_UP,
    Point,
    PointLike,
    Rect,
    RectLike,
    VNCConfig,
    key_codes,
    slice_rect,
)
from .pyvnc_async import VNCClient

__version__ = "3.1.0"

__all__ = [
    "MOUSE_BUTTON_LEFT",
    "MOUSE_BUTTON_MIDDLE",
    "MOUSE_BUTTON_RIGHT",
    "MOUSE_BUTTON_SCROLL_DOWN",
    "MOUSE_BUTTON_SCROLL_UP",
    "Point",
    "PointLike",
    "Rect",
    "RectLike",
    "VNCConfig",
    "key_codes",
    "slice_rect",
    "VNCClient",
]
