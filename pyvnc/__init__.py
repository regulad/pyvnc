"""
pyvnc: A pure Python VNC client library.

This library provides VNC client functionality for capturing screenshots
and sending keyboard & mouse input to VNC servers.

Quick Start::

    from pyvnc import connect_vnc, VNCConfig, Point, Rect

    # Configure connection
    config = VNCConfig(
        host='localhost',
        port=5900,
        password='your_password'
    )

    # Connect and interact with VNC server
    with connect_vnc(config) as vnc:
        # Take screenshots
        screenshot = vnc.capture_full_screen()
        
        # Move mouse and click
        vnc.move(Point(100, 200))
        vnc.click(MOUSE_BUTTON_LEFT)  # Left click
        vnc.click(MOUSE_BUTTON_MIDDLE)  # Middle click
        vnc.click(MOUSE_BUTTON_RIGHT)  # Right click
        
        # Type text
        vnc.write('Hello VNC!')
        vnc.press('Return')

Relative Coordinates:
    pyvnc provides a resolution-independent coordinate system:
    - Height is always 900 in relative coordinates
    - Width scales proportionally based on aspect ratio
    - 16:9 screens → 1600×900 relative coordinates
    - Use relative=True parameter in mouse/capture methods

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

from .pyvnc import (
    VNCClient,
    VNCConfig,
    connect_vnc,
    Point,
    Rect,
    PointLike,
    RectLike,
    slice_rect,
    key_codes,
    # Mouse button constants
    MOUSE_BUTTON_LEFT,
    MOUSE_BUTTON_MIDDLE,
    MOUSE_BUTTON_RIGHT,
    MOUSE_BUTTON_SCROLL_UP,
    MOUSE_BUTTON_SCROLL_DOWN,
    # Backwards compatibility
    VNC,
)

__version__ = "2.0.0"
__all__ = [
    "VNCClient",
    "VNCConfig", 
    "connect_vnc",
    "Point",
    "Rect",
    "PointLike",
    "RectLike",
    "slice_rect",
    "key_codes",
    "MOUSE_BUTTON_LEFT",
    "MOUSE_BUTTON_MIDDLE", 
    "MOUSE_BUTTON_RIGHT",
    "MOUSE_BUTTON_SCROLL_UP",
    "MOUSE_BUTTON_SCROLL_DOWN",
    "VNC",
]