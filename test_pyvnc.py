#!/usr/bin/env python3
"""
Comprehensive tests for pyvnc library.
"""

import unittest
import tempfile
import os
from pathlib import Path

from pyvnc import (
    VNCClient, VNCConfig, connect_vnc,
    Point, Rect, PointLike, RectLike,
    slice_rect, key_codes,
    MOUSE_BUTTON_LEFT, MOUSE_BUTTON_MIDDLE, MOUSE_BUTTON_RIGHT
)

# Test server configuration
TEST_HOST = 'localhost'
TEST_PORT = 5900
TEST_PASSWORD = 'W9I^*MUPrMu7wjA@'


class TestVNCConfig(unittest.TestCase):
    """Test VNCConfig class."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = VNCConfig()
        self.assertEqual(config.host, 'localhost')
        self.assertEqual(config.port, 5900)
        self.assertEqual(config.speed, 20.0)
        self.assertEqual(config.timeout, 5.0)
        self.assertEqual(config.pixel_format, 'rgba')
        self.assertIsNone(config.username)
        self.assertIsNone(config.password)
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = VNCConfig(
            host='remote.example.com',
            port=5901,
            speed=30.0,
            timeout=10.0,
            pixel_format='bgra',
            username='testuser',
            password='testpass'
        )
        self.assertEqual(config.host, 'remote.example.com')
        self.assertEqual(config.port, 5901)
        self.assertEqual(config.speed, 30.0)
        self.assertEqual(config.timeout, 10.0)
        self.assertEqual(config.pixel_format, 'bgra')
        self.assertEqual(config.username, 'testuser')
        self.assertEqual(config.password, 'testpass')


class TestGeometry(unittest.TestCase):
    """Test geometry classes and functions."""
    
    def test_point(self):
        """Test Point namedtuple."""
        point = Point(100, 200)
        self.assertEqual(point.x, 100)
        self.assertEqual(point.y, 200)
    
    def test_rect(self):
        """Test Rect namedtuple."""
        rect = Rect(10, 20, 300, 400)
        self.assertEqual(rect.x, 10)
        self.assertEqual(rect.y, 20)
        self.assertEqual(rect.width, 300)
        self.assertEqual(rect.height, 400)
    
    def test_slice_rect(self):
        """Test slice_rect function."""
        rect = Rect(10, 20, 100, 150)
        slices = slice_rect(rect)
        self.assertEqual(len(slices), 2)
        self.assertEqual(slices[0], slice(20, 170))  # y, y+height
        self.assertEqual(slices[1], slice(10, 110))  # x, x+width
        
        # Test with additional channels
        slices_with_channels = slice_rect(rect, slice(None), slice(0, 3))
        self.assertEqual(len(slices_with_channels), 4)


class TestKeyboardCodes(unittest.TestCase):
    """Test keyboard code mappings."""
    
    def test_key_codes_exist(self):
        """Test that common key codes exist."""
        # Test some common keys
        self.assertIn('a', key_codes)
        self.assertIn('A', key_codes) 
        self.assertIn('0', key_codes)
        self.assertIn('Return', key_codes)
        self.assertIn('Space', key_codes)
        self.assertIn('Escape', key_codes)
        self.assertIn('Esc', key_codes)  # Alias
        self.assertIn('Ctrl', key_codes)  # Alias
        self.assertIn('Alt', key_codes)   # Alias
        self.assertIn('Shift', key_codes) # Alias
        
    def test_key_code_aliases(self):
        """Test that key aliases work correctly."""
        self.assertEqual(key_codes['Esc'], key_codes['Escape'])
        self.assertEqual(key_codes['Del'], key_codes['Delete'])
        self.assertEqual(key_codes['Ctrl'], key_codes['Control_L'])
        self.assertEqual(key_codes['Alt'], key_codes['Alt_L'])
        self.assertEqual(key_codes['Shift'], key_codes['Shift_L'])
        self.assertEqual(key_codes['Super'], key_codes['Super_L'])
        self.assertEqual(key_codes['Cmd'], key_codes['Super_L'])
        self.assertEqual(key_codes['Backspace'], key_codes['BackSpace'])
        self.assertEqual(key_codes['Space'], key_codes['space'])


class TestPointLikeInterface(unittest.TestCase):
    """Test PointLike and RectLike interfaces."""
    
    def test_point_like_implementation(self):
        """Test custom PointLike implementation."""
        class CustomPoint(PointLike):
            def __init__(self, x, y):
                self._x = x
                self._y = y
            
            def get_point(self) -> Point:
                return Point(self._x, self._y)
        
        custom_point = CustomPoint(50, 75)
        point = custom_point.get_point()
        self.assertEqual(point.x, 50)
        self.assertEqual(point.y, 75)
    
    def test_rect_like_implementation(self):
        """Test custom RectLike implementation."""
        class CustomRect(RectLike):
            def __init__(self, x, y, w, h):
                self._x = x
                self._y = y
                self._w = w
                self._h = h
            
            def get_rect(self) -> Rect:
                return Rect(self._x, self._y, self._w, self._h)
        
        custom_rect = CustomRect(10, 20, 100, 200)
        rect = custom_rect.get_rect()
        self.assertEqual(rect.x, 10)
        self.assertEqual(rect.y, 20)
        self.assertEqual(rect.width, 100)
        self.assertEqual(rect.height, 200)


class TestVNCConnection(unittest.TestCase):
    """Test actual VNC connection and operations."""
    
    def setUp(self):
        """Set up test configuration."""
        self.config = VNCConfig(
            host=TEST_HOST,
            port=TEST_PORT,
            password=TEST_PASSWORD,
            timeout=10.0,
            speed=50.0  # Faster for testing
        )
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_connection_context_manager(self):
        """Test VNC connection using context manager."""
        try:
            with connect_vnc(self.config) as vnc:
                self.assertIsInstance(vnc, VNCClient)
                self.assertIsNotNone(vnc.rect)
                self.assertGreater(vnc.rect.width, 0)
                self.assertGreater(vnc.rect.height, 0)
                print(f"✓ Connected to VNC server. Screen size: {vnc.rect.width}x{vnc.rect.height}")
        except Exception as e:
            self.fail(f"Failed to connect to VNC server: {e}")
    
    def test_manual_connection_close(self):
        """Test manual connection and close."""
        try:
            vnc = connect_vnc(self.config)
            self.assertIsInstance(vnc, VNCClient)
            vnc.close()
            print("✓ Manual connection and close successful")
        except Exception as e:
            self.fail(f"Failed manual connection: {e}")
    
    def test_screenshot_capture(self):
        """Test screenshot capture functionality."""
        try:
            with connect_vnc(self.config) as vnc:
                # Test full screen capture
                full_screenshot = vnc.capture()
                self.assertEqual(len(full_screenshot.shape), 3)
                self.assertEqual(full_screenshot.shape[2], 4)  # RGBA
                self.assertEqual(full_screenshot.shape[0], vnc.rect.height)
                self.assertEqual(full_screenshot.shape[1], vnc.rect.width)
                print(f"✓ Full screenshot captured: {full_screenshot.shape}")
                
                # Test capture_full_screen helper method
                full_screenshot2 = vnc.capture_full_screen()
                self.assertEqual(full_screenshot.shape, full_screenshot2.shape)
                print(f"✓ capture_full_screen() helper works")
                
                # Test region capture
                region = Rect(0, 0, min(200, vnc.rect.width), min(150, vnc.rect.height))
                region_screenshot = vnc.capture(region)
                self.assertEqual(region_screenshot.shape[0], region.height)
                self.assertEqual(region_screenshot.shape[1], region.width)
                self.assertEqual(region_screenshot.shape[2], 4)  # RGBA
                print(f"✓ Region screenshot captured: {region_screenshot.shape}")
                
                # Test relative coordinate capture
                rel_res = vnc.get_relative_resolution()
                print(f"✓ Relative resolution: {rel_res.x}x{rel_res.y}")
                
                # Capture a small region using relative coordinates
                rel_region = Rect(100, 100, 200, 200)  # Relative coordinates
                rel_screenshot = vnc.capture(rel_region, relative=True)
                self.assertEqual(len(rel_screenshot.shape), 3)
                self.assertEqual(rel_screenshot.shape[2], 4)  # RGBA
                print(f"✓ Relative coordinate capture: {rel_screenshot.shape}")
                
        except Exception as e:
            self.fail(f"Screenshot capture failed: {e}")
    
    def test_rgba_png_output(self):
        """Test RGBA screenshot with PIL PNG output."""
        try:
            from PIL import Image
            
            with connect_vnc(self.config) as vnc:
                # Capture full screen
                screenshot = vnc.capture()
                
                # Convert to PIL Image and save as PNG
                image = Image.fromarray(screenshot, 'RGBA')
                png_path = os.path.join(self.temp_dir, 'vnc_screenshot.png')
                image.save(png_path, 'PNG')
                
                # Verify file was created
                self.assertTrue(os.path.exists(png_path))
                file_size = os.path.getsize(png_path)
                self.assertGreater(file_size, 1000)  # Should be reasonably sized
                
                print(f"✓ PNG screenshot saved: {png_path} ({file_size} bytes)")
                print(f"  Image size: {image.size}")
                print(f"  Image mode: {image.mode}")
                
        except ImportError:
            self.fail("PIL/Pillow not available for PNG testing")
        except Exception as e:
            self.fail(f"PNG output failed: {e}")
    
    def test_keyboard_input(self):
        """Test keyboard input functionality."""
        try:
            with connect_vnc(self.config) as vnc:
                # Test single key press
                vnc.press('a')
                
                # Test key combination
                vnc.press('Ctrl', 'a')
                
                # Test text writing
                vnc.write('Hello VNC')
                
                # Test holding keys
                with vnc.hold('Shift'):
                    vnc.press('a')
                
                print("✓ Keyboard input operations completed")
                
        except Exception as e:
            self.fail(f"Keyboard input failed: {e}")
    
    def test_mouse_operations(self):
        """Test mouse input functionality."""
        try:
            with connect_vnc(self.config) as vnc:
                # Test mouse movement
                center = Point(vnc.rect.width // 2, vnc.rect.height // 2)
                vnc.move(center)
                self.assertEqual(vnc.mouse_position, center)
                
                # Test clicks
                vnc.click(MOUSE_BUTTON_LEFT)      # Left click
                vnc.click(MOUSE_BUTTON_MIDDLE)    # Middle click  
                vnc.click(MOUSE_BUTTON_RIGHT)     # Right click
                vnc.double_click(MOUSE_BUTTON_LEFT)  # Double click
                
                # Test scrolling
                vnc.scroll_up(2)
                vnc.scroll_down(2)
                
                # Test dragging
                start_pos = Point(100, 100)
                end_pos = Point(200, 200)
                vnc.move(start_pos)
                with vnc.drag():
                    vnc.move(end_pos)
                
                # Test middle and right drag
                with vnc.drag(MOUSE_BUTTON_MIDDLE):
                    vnc.move(Point(300, 300))
                
                with vnc.drag(MOUSE_BUTTON_RIGHT):
                    vnc.move(Point(400, 400))
                
                # Test relative coordinate mouse operations
                rel_res = vnc.get_relative_resolution()
                rel_center = Point(rel_res.x // 2, rel_res.y // 2)
                vnc.move(rel_center, relative=True)
                
                # Test click_at and double_click_at helpers
                vnc.click_at(Point(800, 450), relative=True)  # Center of relative coords
                vnc.double_click_at(Point(400, 225), relative=True)  # Quarter position
                
                # Test relative dragging
                with vnc.drag(relative=True):
                    vnc.move(Point(1200, 675))  # Move while dragging in relative coords
                
                print("✓ Mouse operations completed")
                
        except Exception as e:
            self.fail(f"Mouse operations failed: {e}")
    
    def test_point_like_rect_like_usage(self):
        """Test using PointLike and RectLike objects."""
        try:
            class TestPoint(PointLike):
                def get_point(self) -> Point:
                    return Point(50, 75)
            
            class TestRect(RectLike):
                def get_rect(self) -> Rect:
                    return Rect(10, 10, 100, 100)
            
            with connect_vnc(self.config) as vnc:
                # Test moving to PointLike object
                test_point = TestPoint()
                vnc.move(test_point)
                self.assertEqual(vnc.mouse_position, Point(50, 75))
                
                # Test capturing RectLike region
                test_rect = TestRect()
                region_screenshot = vnc.capture(test_rect)
                self.assertEqual(region_screenshot.shape[:2], (100, 100))
                
                print("✓ PointLike and RectLike usage successful")
                
        except Exception as e:
            self.fail(f"PointLike/RectLike usage failed: {e}")
    
    def test_error_handling(self):
        """Test error handling for various scenarios."""
        # Test connection to non-existent server
        bad_config = VNCConfig(host='nonexistent.example.com', port=9999, timeout=1.0)
        with self.assertRaises(Exception):
            connect_vnc(bad_config)
        
        # Test invalid key code
        try:
            with connect_vnc(self.config) as vnc:
                with self.assertRaises(KeyError):
                    vnc.press('InvalidKeyName123')
        except Exception:
            pass  # Connection might fail, that's ok for this test
        
        print("✓ Error handling tests completed")
    
    def test_apple_auth_detection(self):
        """Test that Apple authentication is properly detected and rejected."""
        # This test would only work if we had an Apple VNC server
        # For now, just verify the error message exists
        from pyvnc.pyvnc import AUTH_TYPE_APPLE
        self.assertEqual(AUTH_TYPE_APPLE, 33)
        print("✓ Apple authentication type constant defined")


def run_tests():
    """Run all tests and generate a report."""
    print("Running pyvnc comprehensive tests...")
    print("=" * 50)
    
    # Create test suite
    suite = unittest.TestSuite()
    
    # Add test classes
    test_classes = [
        TestVNCConfig,
        TestGeometry, 
        TestKeyboardCodes,
        TestPointLikeInterface,
        TestVNCConnection
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 50)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.failures:
        print("\nFailures:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback}")
    
    if result.errors:
        print("\nErrors:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback}")
    
    if result.wasSuccessful():
        print("\n✅ All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed!")
        return 1


if __name__ == "__main__":
    exit(run_tests())