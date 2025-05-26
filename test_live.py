#!/usr/bin/env python3
"""
Live tests with actual VNC server.
"""

import tempfile
import os
from pathlib import Path

from pyvnc import (
    VNCClient, VNCConfig, connect_vnc,
    Point, Rect, MOUSE_BUTTON_LEFT
)

# Test server configuration
TEST_HOST = 'localhost'
TEST_PORT = 5900
TEST_PASSWORD = 'W9I^*MUPrMu7wjA@'

def test_connection():
    """Test basic VNC connection."""
    config = VNCConfig(
        host=TEST_HOST,
        port=TEST_PORT,
        password=TEST_PASSWORD,
        timeout=10.0,
        speed=50.0
    )
    
    try:
        with connect_vnc(config) as vnc:
            print(f"✓ Connected to VNC server")
            print(f"  Screen size: {vnc.rect.width}x{vnc.rect.height}")
            
            # Test relative resolution
            rel_res = vnc.get_relative_resolution()
            print(f"  Relative resolution: {rel_res.x}x{rel_res.y}")
            
            return True
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False

def test_screenshot():
    """Test screenshot functionality."""
    config = VNCConfig(
        host=TEST_HOST,
        port=TEST_PORT,
        password=TEST_PASSWORD,
        timeout=10.0
    )
    
    try:
        with connect_vnc(config) as vnc:
            # Test full screen capture
            full_screenshot = vnc.capture_full_screen()
            print(f"✓ Full screenshot: {full_screenshot.shape}")
            
            # Test region capture
            region = Rect(0, 0, min(400, vnc.rect.width), min(300, vnc.rect.height))
            region_screenshot = vnc.capture(region)
            print(f"✓ Region screenshot: {region_screenshot.shape}")
            
            # Test relative coordinate capture and relative screen rect
            rel_screen_rect = vnc.get_relative_screen_rect()
            print(f"✓ Relative screen rect: {rel_screen_rect}")
            
            rel_region = Rect(100, 100, 200, 200)  # Relative coordinates
            rel_screenshot = vnc.capture(rel_region, relative=True)
            print(f"✓ Relative screenshot: {rel_screenshot.shape}")
            
            # Test PNG output to current working directory
            try:
                from PIL import Image
                
                # Save full screenshot as PNG in current directory
                image = Image.fromarray(full_screenshot, 'RGBA')
                png_path = 'test_full_screenshot.png'
                image.save(png_path, 'PNG')
                
                # Save region screenshot as PNG in current directory
                region_image = Image.fromarray(region_screenshot, 'RGBA')
                region_png_path = 'test_region_screenshot.png'
                region_image.save(region_png_path, 'PNG')
                
                # Save relative screenshot as PNG in current directory
                rel_image = Image.fromarray(rel_screenshot, 'RGBA')
                rel_png_path = 'test_relative_screenshot.png'
                rel_image.save(rel_png_path, 'PNG')
                
                print(f"✓ PNG files saved to current directory")
                print(f"  Full: {png_path} ({os.path.getsize(png_path)} bytes)")
                print(f"  Region: {region_png_path} ({os.path.getsize(region_png_path)} bytes)")
                print(f"  Relative: {rel_png_path} ({os.path.getsize(rel_png_path)} bytes)")
                
            except ImportError:
                print("! PIL not available for PNG testing")
            
            return True
            
    except Exception as e:
        print(f"✗ Screenshot test failed: {e}")
        return False

def test_mouse_operations():
    """Test mouse operations."""
    config = VNCConfig(
        host=TEST_HOST,
        port=TEST_PORT,
        password=TEST_PASSWORD,
        timeout=10.0,
        speed=100.0  # Fast for testing
    )
    
    try:
        with connect_vnc(config) as vnc:
            # Test absolute coordinates
            center = Point(vnc.rect.width // 2, vnc.rect.height // 2)
            vnc.move(center)
            print(f"✓ Moved to center: {center}")
            
            # Test relative coordinates
            rel_res = vnc.get_relative_resolution()
            rel_center = Point(rel_res.x // 2, rel_res.y // 2)
            vnc.move(rel_center, relative=True)
            print(f"✓ Moved to relative center: {rel_center}")
            
            # Test clicking
            vnc.click(MOUSE_BUTTON_LEFT)
            print("✓ Left click")
            
            # Test click_at helper
            vnc.click_at(Point(800, 450), relative=True)
            print("✓ Click at relative coordinates")
            
            # Test dragging
            with vnc.drag(relative=True):
                vnc.move(Point(1200, 675))
            print("✓ Drag operation with relative coordinates")
            
            return True
            
    except Exception as e:
        print(f"✗ Mouse operations failed: {e}")
        return False

def test_keyboard():
    """Test keyboard operations."""
    config = VNCConfig(
        host=TEST_HOST,
        port=TEST_PORT,
        password=TEST_PASSWORD,
        timeout=10.0,
        speed=50.0
    )
    
    try:
        with connect_vnc(config) as vnc:
            # Test writing text
            vnc.write('Hello pyvnc!')
            print("✓ Text writing")
            
            # Test key press
            vnc.press('Return')
            print("✓ Key press")
            
            # Test key combination
            vnc.press('Ctrl', 'a')
            print("✓ Key combination")
            
            # Test holding keys
            with vnc.hold('Shift'):
                vnc.press('a')
            print("✓ Holding keys")
            
            return True
            
    except Exception as e:
        print(f"✗ Keyboard operations failed: {e}")
        return False

def main():
    """Run live tests."""
    print("Running pyvnc live tests with VNC server...")
    print(f"Target: {TEST_HOST}:{TEST_PORT}")
    print("=" * 50)
    
    tests = [
        test_connection,
        test_screenshot,
        test_mouse_operations,
        test_keyboard,
    ]
    
    results = []
    for test in tests:
        print(f"\n{test.__name__}:")
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"✗ {test.__name__} failed with exception: {e}")
            results.append(False)
    
    print("\n" + "=" * 50)
    passed = sum(results)
    total = len(results)
    print(f"Tests: {passed}/{total} passed")
    
    if all(results):
        print("✅ All live tests passed!")
        return 0
    else:
        print("❌ Some tests failed!")
        return 1

if __name__ == "__main__":
    exit(main())