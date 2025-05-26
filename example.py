#!/usr/bin/env python3
"""
Simple example demonstrating pyvnc library usage.
"""

from pyvnc import connect_vnc, VNCConfig, Point, Rect, MOUSE_BUTTON_LEFT, MOUSE_BUTTON_MIDDLE, MOUSE_BUTTON_RIGHT

def main():
    """Example VNC client usage."""
    # Configure connection
    config = VNCConfig(
        host='localhost',
        port=5900,
        password='your_password_here'  # Replace with actual password or None for no auth
    )
    
    try:
        # Connect to VNC server
        with connect_vnc(config) as vnc:
            print(f"Connected to VNC server. Screen size: {vnc.rect.width}x{vnc.rect.height}")
            
            # Take a screenshot of the entire screen
            full_screenshot = vnc.capture()
            print(f"Full screenshot shape: {full_screenshot.shape}")
            
            # Take a screenshot of a specific region
            region = Rect(x=100, y=100, width=200, height=150)
            region_screenshot = vnc.capture(region)
            print(f"Region screenshot shape: {region_screenshot.shape}")
            
            # Send keyboard input
            vnc.write('Hello, VNC!')
            vnc.press('Enter')
            
            # Send key combinations
            vnc.press('Ctrl', 'a')  # Select all
            vnc.press('Ctrl', 'c')  # Copy
            
            # Mouse operations
            vnc.move(Point(300, 400))
            vnc.click(MOUSE_BUTTON_LEFT)  # Left click
            vnc.double_click(MOUSE_BUTTON_LEFT)
            
            # Middle and right click
            vnc.click(MOUSE_BUTTON_MIDDLE)
            vnc.click(MOUSE_BUTTON_RIGHT)
            
            # Scroll wheel
            vnc.scroll_up(3)
            vnc.scroll_down(2)
            
            # Drag operations
            with vnc.hold_mouse():
                vnc.move(Point(500, 600))
            
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
    main()