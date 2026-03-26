#!/usr/bin/env python3
"""
Example demonstrating async pyvnc library usage.
"""

import asyncio
from pyvnc import (
    VNCClient,
    VNCConfig,
    Point,
    Rect,
    MOUSE_BUTTON_LEFT,
    MOUSE_BUTTON_MIDDLE,
    MOUSE_BUTTON_RIGHT,
)


async def main():
    """Example VNC client usage."""
    # Configure connection
    config = VNCConfig(
        host="localhost",
        port=5900,
        password="your_password_here",  # Replace with actual password or None for no auth
    )

    try:
        # Connect to VNC server (connection happens in __aenter__)
        async with await VNCClient.connect(config) as vnc:
            print(
                f"Connected to VNC server. Screen size: {vnc.rect.width}x{vnc.rect.height}"
            )

            # Take a screenshot of the entire screen
            full_screenshot = await vnc.capture()
            print(f"Full screenshot shape: {full_screenshot.shape}")

            # Take a screenshot of a specific region
            region = Rect(x=100, y=100, width=200, height=150)
            region_screenshot = await vnc.capture(region)
            print(f"Region screenshot shape: {region_screenshot.shape}")

            # Send keyboard input
            await vnc.write("Hello, VNC!")
            await vnc.press("Enter")

            # Send key combinations
            await vnc.press("Ctrl", "a")  # Select all
            await vnc.press("Ctrl", "c")  # Copy

            # Mouse operations
            await vnc.move(Point(300, 400))
            await vnc.click(MOUSE_BUTTON_LEFT)  # Left click
            await vnc.double_click(MOUSE_BUTTON_LEFT)

            # Middle and right click
            await vnc.click(MOUSE_BUTTON_MIDDLE)
            await vnc.click(MOUSE_BUTTON_RIGHT)

            # Scroll wheel
            await vnc.scroll_up(3)
            await vnc.scroll_down(2)

            # Drag operations
            async with vnc.hold_mouse():
                await vnc.move(Point(500, 600))

            print("VNC operations completed successfully!")

    except ConnectionError:
        print("Could not connect to VNC server. Make sure it's running and accessible.")
    except PermissionError:
        print("Authentication failed. Check your username/password.")
    except ValueError as e:
        print(f"VNC protocol error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
