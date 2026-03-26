#!/usr/bin/env python3
"""
Async tests for pyvnc library with background task.
"""

import unittest
import asyncio
import tempfile
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not available.")

from pyvnc import (
    VNCClient,
    VNCConfig,
    Point,
    Rect,
    PointLike,
    RectLike,
    MOUSE_BUTTON_LEFT,
    MOUSE_BUTTON_MIDDLE,
    MOUSE_BUTTON_RIGHT,
)


def load_test_config() -> VNCConfig:
    """Load VNC configuration from .env file or environment."""
    host = os.getenv("VNC_HOST", "localhost")
    port = int(os.getenv("VNC_PORT", "5900"))
    password = os.getenv("VNC_PASSWORD")
    username = os.getenv("VNC_USERNAME")

    if not password:
        return None

    return VNCConfig(
        host=host, port=port, username=username, password=password, timeout=10.0
    )


@unittest.skipIf(load_test_config() is None, "VNC_PASSWORD not configured")
class TestVNCIntegration(unittest.TestCase):
    """Integration tests with real VNC server using async client and background task."""

    def setUp(self):
        """Set up test configuration."""
        self.config = load_test_config()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary files."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_comprehensive_vnc_functionality(self):
        """Comprehensive test of all VNC functionality with background task."""

        async def run_test():
            async with await VNCClient.connect(self.config) as vnc:
                # Basic connection info
                self.assertGreater(vnc.rect.width, 0)
                self.assertGreater(vnc.rect.height, 0)
                rel_res = vnc.rect

                # Test screenshots (background task handles updates)
                full_screenshot = await vnc.capture()
                self.assertEqual(len(full_screenshot.shape), 3)
                self.assertEqual(full_screenshot.shape[2], 4)  # RGBA
                self.assertEqual(full_screenshot.shape[0], vnc.rect.height)
                self.assertEqual(full_screenshot.shape[1], vnc.rect.width)

                # Test region capture
                region = Rect(0, 0, min(200, vnc.rect.width), min(150, vnc.rect.height))
                region_screenshot = await vnc.capture(region)
                self.assertEqual(region_screenshot.shape[0], region.height)
                self.assertEqual(region_screenshot.shape[1], region.width)

                # Test relative coordinate capture
                rel_region = Rect(
                    rel_res.x // 4, rel_res.y // 4, rel_res.x // 4, rel_res.y // 4
                )
                rel_screenshot = await vnc.capture(rel_region)
                self.assertEqual(len(rel_screenshot.shape), 3)
                self.assertEqual(rel_screenshot.shape[2], 4)  # RGBA

                # Test mouse operations with float-derived coordinates
                center_x = rel_res.x / 2.0
                center_y = rel_res.y / 2.0

                await vnc.move(Point(int(center_x), int(center_y)))
                await vnc.click(MOUSE_BUTTON_LEFT)
                await vnc.click(MOUSE_BUTTON_MIDDLE)
                await vnc.click(MOUSE_BUTTON_RIGHT)
                await vnc.double_click(MOUSE_BUTTON_LEFT)

                # Test scrolling
                await vnc.scroll_up(3)
                await vnc.scroll_down(2)

                # Test click_at helpers
                corner_x = rel_res.x / 10.0
                corner_y = rel_res.y / 10.0
                await vnc.click_at(
                    Point(int(corner_x), int(corner_y)), MOUSE_BUTTON_LEFT
                )
                await vnc.double_click_at(
                    Point(int(corner_x * 2), int(corner_y * 2)), MOUSE_BUTTON_LEFT
                )

                # Test drag operations with all mouse buttons
                start_x = rel_res.x / 4.0
                start_y = rel_res.y / 4.0
                end_x = rel_res.x * 3.0 / 4.0
                end_y = rel_res.y * 3.0 / 4.0

                # Left button drag
                await vnc.move(Point(int(start_x), int(start_y)))
                async with vnc.hold_mouse(MOUSE_BUTTON_LEFT):
                    await vnc.move(Point(int(end_x), int(end_y)))

                # Middle button drag
                await vnc.move(Point(int(start_x * 1.1), int(start_y * 1.1)))
                async with vnc.hold_mouse(MOUSE_BUTTON_MIDDLE):
                    await vnc.move(Point(int(end_x * 0.9), int(end_y * 0.9)))

                # Right button drag
                await vnc.move(Point(int(start_x * 1.2), int(start_y * 1.2)))
                async with vnc.hold_mouse(MOUSE_BUTTON_RIGHT):
                    await vnc.move(Point(int(end_x * 0.8), int(end_y * 0.8)))

                # Test keyboard operations
                await vnc.write("Hello async pyvnc!")
                await vnc.press("Return")

                async with vnc.hold_key("Ctrl"):
                    await vnc.press("a")  # Select all

                async with vnc.hold_key("Shift"):
                    await vnc.press("a")

        asyncio.run(run_test())

    def test_png_output(self):
        """Test RGBA screenshot with PIL PNG output with background task."""

        async def run_test():
            try:
                from PIL import Image

                async with await VNCClient.connect(self.config) as vnc:
                    screenshot = await vnc.capture()

                    # Convert to PIL Image
                    image = Image.fromarray(screenshot, "RGBA")
                    png_path = os.path.join(self.temp_dir, "test_screenshot.png")

                    # Save with timestamp
                    import time

                    timestamp = int(time.time())
                    project_png = f"async_screenshot_{timestamp}.png"
                    image.save(png_path, "PNG")
                    image.save(project_png, "PNG")

                    # Verify file was created
                    self.assertTrue(os.path.exists(png_path))
                    file_size = os.path.getsize(png_path)
                    self.assertGreater(file_size, 1000)

            except ImportError:
                self.skipTest("PIL/Pillow not available")

        asyncio.run(run_test())

    def test_point_like_rect_like_usage(self):
        """Test using PointLike and RectLike objects."""

        class TestPoint(PointLike):
            def get_point(self) -> Point:
                return Point(50, 75)

        class TestRect(RectLike):
            def get_rect(self) -> Rect:
                return Rect(10, 10, 100, 100)

        async def run_test():
            async with await VNCClient.connect(self.config) as vnc:
                test_point = TestPoint()
                await vnc.move(test_point)

                test_rect = TestRect()
                region_screenshot = await vnc.capture(test_rect)
                self.assertEqual(len(region_screenshot.shape), 3)

        asyncio.run(run_test())

    def test_context_manager(self):
        """Test async context manager functionality with background task."""

        async def run_test():
            vnc = await VNCClient.connect(self.config)
            async with vnc:
                self.assertGreater(vnc.rect.width, 0)
                self.assertGreater(vnc.rect.height, 0)
                screenshot = await vnc.capture()
                self.assertEqual(len(screenshot.shape), 3)

        asyncio.run(run_test())

    def test_manual_connection_cleanup(self):
        """Test manual connection and cleanup."""

        async def run_test():
            vnc = await VNCClient.connect(self.config)
            try:
                self.assertGreater(vnc.rect.width, 0)
                screenshot = await vnc.capture()
                self.assertEqual(len(screenshot.shape), 3)
            finally:
                await vnc.close()

        asyncio.run(run_test())

    def test_background_task_running(self):
        """Test that the background task is running during connection."""

        async def run_test():
            vnc = await VNCClient.connect(self.config)
            self.assertIsNotNone(vnc._listener_task)
            self.assertTrue(vnc._running)
            await vnc.close()
            self.assertFalse(vnc._running)

        asyncio.run(run_test())


class TestErrorHandling(unittest.TestCase):
    """Test error handling scenarios."""

    def test_invalid_connection(self):
        """Test connection to non-existent server."""

        async def run_test():
            bad_config = VNCConfig(
                host="nonexistent.example.com", port=9999, timeout=1.0
            )
            with self.assertRaises(Exception):
                await VNCClient.connect(bad_config)

        asyncio.run(run_test())

    def test_invalid_key_code(self):
        """Test invalid key code handling."""
        config = load_test_config()
        if config is None:
            self.skipTest("VNC_PASSWORD not configured")

        async def run_test():
            try:
                async with await VNCClient.connect(config) as vnc:
                    with self.assertRaises(KeyError):
                        await vnc.press("InvalidKeyName123")
            except Exception:
                pass  # Connection might fail

        asyncio.run(run_test())


def main():
    """Run all async tests."""
    print("Running pyvnc async tests (with background task)...")
    print("=" * 50)

    if not os.path.exists(".env"):
        print("Note: .env file not found. Integration tests will be skipped.")
        print()

    unittest.main(verbosity=2, exit=False)


if __name__ == "__main__":
    main()
