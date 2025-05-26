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
        
        # Hold keys for combinations
        with vnc.hold_key('Ctrl'):
            vnc.press('c')  # Ctrl+C
        
        # Drag operations
        with vnc.hold_mouse(MOUSE_BUTTON_LEFT):
            vnc.move(Point(500, 600))  # Drag from current to new position

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