#!/usr/bin/env python3
"""
Refactor tests for pyvnc library - testing background task and async functionality.
Includes unit tests and integration tests using .env configuration.
"""

import asyncio
import unittest
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from pyvnc import VNCClient, VNCConfig, Point, Rect, MOUSE_BUTTON_LEFT


def load_test_config() -> VNCConfig:
    """Load VNC configuration from .env file or environment."""
    host = os.getenv("VNC_HOST", "localhost")
    port = int(os.getenv("VNC_PORT", "5900"))
    password = os.getenv("VNC_PASSWORD")
    username = os.getenv("VNC_USERNAME")

    if not password:
        return None

    return VNCConfig(
        host=host,
        port=port,
        username=username,
        password=password,
        connection_timeout=10.0,
    )


@unittest.skipIf(load_test_config() is None, "VNC_PASSWORD not configured")
class TestRefactoredVNCClient(unittest.TestCase):
    """Tests for refactored VNC client with background task."""

    def setUp(self):
        """Set up test configuration."""
        self.config = load_test_config()

    def test_background_task_running(self):
        """Test that background task is running during connection."""

        async def run_test():
            vnc = await VNCClient.connect(self.config)
            try:
                self.assertIsNotNone(vnc._listener_task)
                self.assertTrue(vnc._running)
                self.assertEqual(vnc._listener_task.get_name(), "vnc_frame_listener")
            finally:
                await vnc.close()
            self.assertFalse(vnc._running)

        asyncio.run(run_test())

    def test_capture_full_screen(self):
        """Test capturing full screen with background task."""

        async def run_test():
            async with await VNCClient.connect(self.config) as vnc:
                screenshot = await vnc.capture()
                self.assertEqual(len(screenshot.shape), 3)
                self.assertEqual(screenshot.shape[2], 4)  # RGBA
                self.assertEqual(screenshot.shape[0], vnc.rect.height)
                self.assertEqual(screenshot.shape[1], vnc.rect.width)

        asyncio.run(run_test())

    def test_capture_region(self):
        """Test capturing a specific region."""

        async def run_test():
            async with await VNCClient.connect(self.config) as vnc:
                region = Rect(0, 0, 100, 100)
                screenshot = await vnc.capture(region)
                self.assertEqual(screenshot.shape, (100, 100, 4))

        asyncio.run(run_test())

    def test_capture_without_wait(self):
        """Test capture without waiting (returns immediately)."""

        async def run_test():
            async with await VNCClient.connect(self.config) as vnc:
                # Wait for first frame
                await vnc.capture(wait=True)
                # Now get current buffer without waiting
                screenshot = await vnc.capture(wait=False)
                self.assertEqual(screenshot.shape[2], 4)  # RGBA

        asyncio.run(run_test())

    def test_mouse_operations(self):
        """Test mouse move and click operations."""

        async def run_test():
            async with await VNCClient.connect(self.config) as vnc:
                await vnc.move(Point(100, 100))
                await vnc.click(MOUSE_BUTTON_LEFT)

        asyncio.run(run_test())

    def test_mouse_drag_operations(self):
        """Test mouse drag operations."""

        async def run_test():
            async with await VNCClient.connect(self.config) as vnc:
                await vnc.move(Point(100, 100))
                async with vnc.hold_mouse(MOUSE_BUTTON_LEFT):
                    await vnc.move(Point(200, 200))

        asyncio.run(run_test())

    def test_keyboard_operations(self):
        """Test keyboard write and press operations."""

        async def run_test():
            async with await VNCClient.connect(self.config) as vnc:
                await vnc.write("Hello")
                await vnc.press("Return")

        asyncio.run(run_test())

    def test_key_combinations(self):
        """Test key combinations with hold_key."""

        async def run_test():
            async with await VNCClient.connect(self.config) as vnc:
                async with vnc.hold_key("Ctrl"):
                    await vnc.press("a")

        asyncio.run(run_test())

    def test_click_at(self):
        """Test click_at helper method."""

        async def run_test():
            async with await VNCClient.connect(self.config) as vnc:
                await vnc.click_at(Point(150, 150), MOUSE_BUTTON_LEFT)

        asyncio.run(run_test())

    def test_double_click_at(self):
        """Test double_click_at helper method."""

        async def run_test():
            async with await VNCClient.connect(self.config) as vnc:
                await vnc.double_click_at(Point(150, 150), MOUSE_BUTTON_LEFT)

        asyncio.run(run_test())


class TestErrorHandling(unittest.TestCase):
    """Test error handling scenarios."""

    def test_invalid_connection(self):
        """Test connection to non-existent server."""

        async def run_test():
            bad_config = VNCConfig(
                host="nonexistent.example.com", port=9999, connection_timeout=1.0
            )
            with self.assertRaises(Exception):
                await VNCClient.connect(bad_config)

        asyncio.run(run_test())


def main():
    """Run all refactor tests."""
    print("Running pyvnc refactor tests...")
    print("=" * 50)

    if not os.path.exists(".env"):
        print("Note: .env file not found. Integration tests will be skipped.")
        print()

    unittest.main(verbosity=2, exit=False)


if __name__ == "__main__":
    main()
