"""
pyvnc: A pure Python VNC client library.

This library provides both synchronous and asynchronous VNC client functionality 
for capturing screenshots and sending keyboard & mouse input to VNC servers.

Synchronous Quick Start::

    from pyvnc import SyncVNCClient, VNCConfig, Point, Rect
    from PIL import Image

    # Configure connection
    config = VNCConfig(
        host='localhost',
        port=5900,
        password='your_password'
    )

    # Connect and interact with VNC server
    with SyncVNCClient.connect(config) as vnc:
        # Take screenshots
        screenshot = vnc.capture()
        
        # Save as PNG using PIL
        image = Image.fromarray(screenshot, 'RGBA')
        image.save('screenshot.png')
        
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

Asynchronous Quick Start::

    import asyncio
    from pyvnc import AsyncVNCClient, VNCConfig, Point, Rect
    from PIL import Image

    async def main():
        # Configure connection
        config = VNCConfig(
            host='localhost',
            port=5900,
            password='your_password'
        )

        # Connect and interact with VNC server
        vnc = await AsyncVNCClient.connect(config)
        async with vnc:
            # Take screenshots
            screenshot = await vnc.capture()
            
            # Save as PNG using PIL (Note: PIL is sync, wrap in asyncio.to_thread if needed)
            image = Image.fromarray(screenshot, 'RGBA')
            image.save('async_screenshot.png')
            
            # Move mouse and click
            await vnc.move(Point(100, 200))
            await vnc.click(MOUSE_BUTTON_LEFT)  # Left click
            await vnc.click(MOUSE_BUTTON_MIDDLE)  # Middle click
            await vnc.click(MOUSE_BUTTON_RIGHT)  # Right click
            
            # Type text  
            await vnc.write('Hello Async VNC!')
            await vnc.press('Return')
            
            # Hold keys for combinations
            async with vnc.hold_key('Ctrl'):
                await vnc.press('c')  # Ctrl+C
            
            # Drag operations
            async with vnc.hold_mouse(MOUSE_BUTTON_LEFT):
                await vnc.move(Point(500, 600))  # Drag from current to new position

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

from .pyvnc_common import *
from .pyvnc_sync import *
from .pyvnc_async import *

__version__ = "2.0.0"