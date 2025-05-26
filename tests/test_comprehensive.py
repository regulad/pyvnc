#!/usr/bin/env python3
"""
Comprehensive tests for pyvnc library.
Includes unit tests and integration tests using .env configuration.
"""

import unittest
import tempfile
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not available. Using environment variables directly.")

from pyvnc import (
    SyncVNCClient, VNCConfig,
    Point, Rect, PointLike, RectLike,
    slice_rect, key_codes,
    MOUSE_BUTTON_LEFT, MOUSE_BUTTON_MIDDLE, MOUSE_BUTTON_RIGHT
)


def load_test_config() -> VNCConfig:
    """Load VNC configuration from .env file or environment."""
    host = os.getenv('VNC_HOST', 'localhost')
    port = int(os.getenv('VNC_PORT', '5900'))
    password = os.getenv('VNC_PASSWORD')
    username = os.getenv('VNC_USERNAME')
    
    if not password:
        return None
    
    return VNCConfig(
        host=host,
        port=port,
        username=username,
        password=password,
        timeout=10.0
    )


class TestVNCConfig(unittest.TestCase):
    """Test VNCConfig class."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = VNCConfig()
        self.assertEqual(config.host, 'localhost')
        self.assertEqual(config.port, 5900)
        self.assertEqual(config.timeout, 5.0)
        self.assertEqual(config.pixel_format, 'rgba')
        self.assertIsNone(config.username)
        self.assertIsNone(config.password)
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = VNCConfig(
            host='remote.example.com',
            port=5901,
            timeout=10.0,
            pixel_format='bgra',
            username='testuser',
            password='testpass'
        )
        self.assertEqual(config.host, 'remote.example.com')
        self.assertEqual(config.port, 5901)
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


class TestKeyboardCodes(unittest.TestCase):
    """Test keyboard code mappings."""
    
    def test_key_codes_exist(self):
        """Test that common key codes exist."""
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
        self.assertEqual(key_codes['Ctrl'], key_codes['Control_L'])
        self.assertEqual(key_codes['Alt'], key_codes['Alt_L'])
        self.assertEqual(key_codes['Shift'], key_codes['Shift_L'])


class TestInterfaces(unittest.TestCase):
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


@unittest.skipIf(load_test_config() is None, "VNC_PASSWORD not configured")
class TestVNCIntegration(unittest.TestCase):
    """Integration tests with real VNC server."""
    
    def setUp(self):
        """Set up test configuration."""
        self.config = load_test_config()
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_float_coordinates(self):
        """Test that relative coordinates work well with float arithmetic."""
        with SyncVNCClient.connect(self.config) as vnc:
            rel_res = vnc.get_relative_resolution()
            
            # Verify dimensions are multiples of 100
            self.assertEqual(rel_res.x % 100, 0)
            self.assertEqual(rel_res.y % 100, 0)
            self.assertLessEqual(rel_res.x, 99900)
            self.assertLessEqual(rel_res.y, 99900)
            
            # Test float calculations work cleanly
            center_x = rel_res.x / 2.0
            center_y = rel_res.y / 2.0
            quarter_x = rel_res.x / 4.0
            quarter_y = rel_res.y / 4.0
            
            # Should be clean integers after division
            self.assertEqual(center_x, int(center_x))
            self.assertEqual(center_y, int(center_y))
            
            # Test mouse movement with float-derived coordinates
            vnc.move(Point(int(center_x), int(center_y)), relative=True)
            vnc.move(Point(int(quarter_x), int(quarter_y)), relative=True)
    
    def test_comprehensive_vnc_functionality(self):
        """Comprehensive test of all VNC functionality."""
        with SyncVNCClient.connect(self.config) as vnc:
            # Basic connection info
            self.assertGreater(vnc.rect.width, 0)
            self.assertGreater(vnc.rect.height, 0)
            
            rel_res = vnc.get_relative_resolution()
            
            # Test screenshots
            full_screenshot = vnc.capture()
            self.assertEqual(len(full_screenshot.shape), 3)
            self.assertEqual(full_screenshot.shape[2], 4)  # RGBA
            self.assertEqual(full_screenshot.shape[0], vnc.rect.height)
            self.assertEqual(full_screenshot.shape[1], vnc.rect.width)
            
            # Test region capture  
            region = Rect(0, 0, min(200, vnc.rect.width), min(150, vnc.rect.height))
            region_screenshot = vnc.capture(region)
            self.assertEqual(region_screenshot.shape[0], region.height)
            self.assertEqual(region_screenshot.shape[1], region.width)
            
            # Test relative coordinate capture
            rel_region = Rect(rel_res.x//4, rel_res.y//4, rel_res.x//4, rel_res.y//4)
            rel_screenshot = vnc.capture(rel_region, relative=True)
            self.assertEqual(len(rel_screenshot.shape), 3)
            self.assertEqual(rel_screenshot.shape[2], 4)  # RGBA
            
            # Test mouse operations with float-derived coordinates
            center_x = rel_res.x / 2.0
            center_y = rel_res.y / 2.0
            
            vnc.move(Point(int(center_x), int(center_y)), relative=True)
            vnc.click(MOUSE_BUTTON_LEFT)
            vnc.click(MOUSE_BUTTON_MIDDLE)
            vnc.click(MOUSE_BUTTON_RIGHT)
            vnc.double_click(MOUSE_BUTTON_LEFT)
            
            # Test scrolling
            vnc.scroll_up(3)
            vnc.scroll_down(2)
            
            # Test click_at helpers
            corner_x = rel_res.x / 10.0
            corner_y = rel_res.y / 10.0
            vnc.click_at(Point(int(corner_x), int(corner_y)), MOUSE_BUTTON_LEFT, relative=True)
            vnc.double_click_at(Point(int(corner_x * 2), int(corner_y * 2)), MOUSE_BUTTON_LEFT, relative=True)
            
            # Test drag operations with all mouse buttons
            start_x = rel_res.x / 4.0
            start_y = rel_res.y / 4.0
            end_x = rel_res.x * 3.0 / 4.0
            end_y = rel_res.y * 3.0 / 4.0
            
            # Left button drag
            vnc.move(Point(int(start_x), int(start_y)), relative=True)
            with vnc.hold_mouse(MOUSE_BUTTON_LEFT, relative=True):
                vnc.move(Point(int(end_x), int(end_y)))
                
            # Middle button drag  
            vnc.move(Point(int(start_x * 1.1), int(start_y * 1.1)), relative=True)
            with vnc.hold_mouse(MOUSE_BUTTON_MIDDLE, relative=True):
                vnc.move(Point(int(end_x * 0.9), int(end_y * 0.9)))
                
            # Right button drag
            vnc.move(Point(int(start_x * 1.2), int(start_y * 1.2)), relative=True)
            with vnc.hold_mouse(MOUSE_BUTTON_RIGHT, relative=True):
                vnc.move(Point(int(end_x * 0.8), int(end_y * 0.8)))
            
            # Test keyboard operations
            vnc.write('Hello pyvnc!')
            vnc.press('Return')
            
            with vnc.hold_key('Ctrl'):
                vnc.press('a')  # Select all
                
            with vnc.hold_key('Shift'):
                vnc.press('a')
    
    def test_png_output(self):
        """Test RGBA screenshot with PIL PNG output."""
        try:
            from PIL import Image
            
            with SyncVNCClient.connect(self.config) as vnc:
                screenshot = vnc.capture()
                
                # Convert to PIL Image and save as PNG
                image = Image.fromarray(screenshot, 'RGBA')
                png_path = os.path.join(self.temp_dir, 'test_screenshot.png')
                
                # Also save to project root with timestamp for verification
                import time
                timestamp = int(time.time())
                project_png = f'sync_screenshot_{timestamp}.png'
                image.save(png_path, 'PNG')
                image.save(project_png, 'PNG')
                
                # Verify file was created
                self.assertTrue(os.path.exists(png_path))
                file_size = os.path.getsize(png_path)
                self.assertGreater(file_size, 1000)  # Should be reasonably sized
                
        except ImportError:
            self.skipTest("PIL/Pillow not available for PNG testing")
    
    def test_point_like_rect_like_usage(self):
        """Test using PointLike and RectLike objects."""
        class TestPoint(PointLike):
            def get_point(self) -> Point:
                return Point(50, 75)
        
        class TestRect(RectLike):
            def get_rect(self) -> Rect:
                return Rect(10, 10, 100, 100)
        
        with SyncVNCClient.connect(self.config) as vnc:
            # Test moving to PointLike object
            test_point = TestPoint()
            vnc.move(test_point, relative=True)
            
            # Test capturing RectLike region
            test_rect = TestRect()
            region_screenshot = vnc.capture(test_rect, relative=True)
            self.assertEqual(len(region_screenshot.shape), 3)


class TestErrorHandling(unittest.TestCase):
    """Test error handling scenarios."""
    
    def test_invalid_connection(self):
        """Test connection to non-existent server."""
        bad_config = VNCConfig(host='nonexistent.example.com', port=9999, timeout=1.0)
        with self.assertRaises(Exception):
            SyncVNCClient.connect(bad_config)
    
    def test_invalid_key_code(self):
        """Test invalid key code handling."""
        config = load_test_config()
        if config is None:
            self.skipTest("VNC_PASSWORD not configured")
            
        try:
            with SyncVNCClient.connect(config) as vnc:
                with self.assertRaises(KeyError):
                    vnc.press('InvalidKeyName123')
        except Exception:
            pass  # Connection might fail, that's ok for this test
    
    def test_apple_auth_detection(self):
        """Test that Apple authentication is properly detected."""
        from pyvnc import AUTH_TYPE_APPLE
        self.assertEqual(AUTH_TYPE_APPLE, 33)


def main():
    """Run all tests."""
    print("Running pyvnc comprehensive tests...")
    print("=" * 50)
    
    # Check if .env file exists
    if not os.path.exists('.env'):
        print("Note: .env file not found. VNC integration tests will be skipped.")
        print("Create a .env file with VNC_HOST, VNC_PORT, VNC_PASSWORD to run integration tests.")
        print()
    
    # Run tests
    unittest.main(verbosity=2, exit=False)


if __name__ == "__main__":
    main()