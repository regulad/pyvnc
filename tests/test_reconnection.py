#!/usr/bin/env python3
"""Tests for VNC retry and reconnection logic."""

import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from pyvnc import VNCClient, VNCConfig, Point, Rect


class TestRetryLogic(unittest.TestCase):
    """Test connection retry logic."""

    def test_connection_retries_exhausted(self):
        """Test that ConnectionError is raised after max_retries exhausted."""

        async def run_test():
            config = VNCConfig(
                host="invalid.host.example.com",
                port=9999,
                connection_timeout=0.1,
                max_retries=2,
                retry_delay=0.01,
                retry_backoff=1.0,
            )

            with self.assertRaises(ConnectionError) as ctx:
                await VNCClient.connect(config)

            self.assertIn("Failed to connect", str(ctx.exception))
            self.assertIn("after 2 attempts", str(ctx.exception))

        asyncio.run(run_test())

    def test_retry_backoff_increases_delay(self):
        """Test that retry delay increases with backoff."""

        async def run_test():
            config = VNCConfig(
                host="invalid.host.example.com",
                port=9999,
                connection_timeout=0.1,
                max_retries=3,
                retry_delay=0.01,
                retry_backoff=2.0,
            )

            start_time = asyncio.get_event_loop().time()
            try:
                await VNCClient.connect(config)
            except ConnectionError:
                pass
            elapsed = asyncio.get_event_loop().time() - start_time

            # Should have at least 0.01 + 0.02 = 0.03 seconds of delays
            self.assertGreater(elapsed, 0.02)

        asyncio.run(run_test())


class TestReconnectionLogic(unittest.IsolatedAsyncioTestCase):
    """Test automatic reconnection functionality."""

    async def test_is_connected_property(self):
        """Test is_connected reflects connection state."""
        # Create client without connecting
        config = VNCConfig(host="localhost", port=5900)
        client = VNCClient(config)

        self.assertFalse(client.is_connected)
        self.assertFalse(client._connected)
        self.assertFalse(client._running)

    async def test_last_error_property(self):
        """Test last_error stores the last connection error."""
        config = VNCConfig(host="localhost", port=5900)
        client = VNCClient(config)

        self.assertIsNone(client.last_error)

        # Simulate setting an error
        client._last_error = ConnectionError("Test error")
        self.assertIsInstance(client.last_error, ConnectionError)
        self.assertEqual(str(client.last_error), "Test error")

    async def test_reconnect_event_initially_set(self):
        """Test that reconnect_event is initially set (not reconnecting)."""
        config = VNCConfig(host="localhost", port=5900)
        client = VNCClient(config)

        # Should be set initially (not reconnecting)
        self.assertTrue(client._reconnect_event.is_set())

    async def test_reconnecting_flag_blocks(self):
        """Test that operations block when _reconnecting is True."""
        config = VNCConfig(host="localhost", port=5900)
        client = VNCClient(config)

        # Simulate reconnection in progress
        client._reconnecting = True
        client._reconnect_event.clear()

        # Create a task that waits for reconnection
        async def wait_for_reconnect():
            await client._reconnect_event.wait()
            return True

        # The event is not set, so this should block
        task = asyncio.create_task(wait_for_reconnect())

        # Complete the reconnection
        client._reconnecting = False
        client._reconnect_event.set()

        # Now the task should complete
        result = await asyncio.wait_for(task, timeout=1.0)
        self.assertTrue(result)


class TestSafeWrite(unittest.IsolatedAsyncioTestCase):
    """Test the _safe_write method."""

    async def test_safe_write_returns_false_when_not_connected(self):
        """Test _safe_write returns False when not connected."""
        config = VNCConfig(host="localhost", port=5900, auto_reconnect=False)
        client = VNCClient(config)

        # Not connected, auto_reconnect disabled
        result = await client._safe_write(b"test data")
        self.assertFalse(result)

    async def test_safe_write_triggers_reconnect_when_disconnected(self):
        """Test _safe_write triggers reconnection when disconnected."""
        config = VNCConfig(
            host="localhost",
            port=5900,
            auto_reconnect=True,
            max_retries=1,
            reconnect_delay=0.01,
        )
        client = VNCClient(config)

        # Mock _reconnect to return False (simulating failed reconnect)
        client._reconnect = AsyncMock(return_value=False)
        client._running = True

        # Try to write when disconnected
        result = await client._safe_write(b"test data")

        # Should have attempted reconnect
        client._reconnect.assert_called_once()
        self.assertFalse(result)


class TestConfigOptions(unittest.TestCase):
    """Test new VNCConfig options."""

    def test_default_config_values(self):
        """Test default configuration values for retry/reconnect."""
        config = VNCConfig()

        # New retry options
        self.assertEqual(config.max_retries, 3)
        self.assertEqual(config.retry_delay, 1.0)
        self.assertEqual(config.retry_backoff, 2.0)

        # New reconnection options
        self.assertTrue(config.auto_reconnect)
        self.assertEqual(config.reconnect_delay, 2.0)

    def test_custom_config_values(self):
        """Test custom configuration values."""
        config = VNCConfig(
            host="vnc.example.com",
            port=5901,
            max_retries=5,
            retry_delay=0.5,
            retry_backoff=1.5,
            auto_reconnect=False,
            reconnect_delay=5.0,
        )

        self.assertEqual(config.max_retries, 5)
        self.assertEqual(config.retry_delay, 0.5)
        self.assertEqual(config.retry_backoff, 1.5)
        self.assertFalse(config.auto_reconnect)
        self.assertEqual(config.reconnect_delay, 5.0)


class TestPropertiesAndState(unittest.TestCase):
    """Test public properties and state management."""

    def test_client_stores_config(self):
        """Test that VNCClient stores config reference."""
        config = VNCConfig(host="test.example.com", port=5900)
        client = VNCClient(config)

        self.assertIs(client._config, config)

    def test_client_initial_state(self):
        """Test initial state of VNCClient."""
        config = VNCConfig()
        client = VNCClient(config)

        # Connection state should be uninitialized
        self.assertIsNone(client._reader)
        self.assertIsNone(client._writer)
        self.assertEqual(client.rect, Rect(0, 0, 0, 0))
        self.assertEqual(client.desktop_name, "")

        # Internal state
        self.assertIsNone(client._pixels_rgba)
        self.assertEqual(client._mouse_position, Point(0, 0))
        self.assertEqual(client._mouse_buttons, 0)

        # Background task state
        self.assertFalse(client._running)
        self.assertIsNone(client._listener_task)

        # Reconnection state
        self.assertFalse(client._connected)
        self.assertFalse(client._reconnecting)
        self.assertTrue(client._reconnect_event.is_set())
        self.assertIsNone(client._last_error)


class TestConnectionLifecycle(unittest.IsolatedAsyncioTestCase):
    """Test connection lifecycle with reconnection."""

    async def test_close_sets_flags(self):
        """Test that close() sets appropriate flags."""
        config = VNCConfig(host="localhost", port=5900, auto_reconnect=True)
        client = VNCClient(config)

        # Set up minimal state
        client._running = True
        client._connected = True

        # Mock writer
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        client._writer = mock_writer

        # Mock listener task
        mock_task = MagicMock()
        mock_task.cancel = MagicMock()
        mock_task.__await__ = MagicMock(return_value=iter([]))
        client._listener_task = None  # Skip task cleanup

        await client.close()

        # Should disable auto_reconnect
        self.assertFalse(config.auto_reconnect)
        # Should stop running
        self.assertFalse(client._running)
        # Should disconnect
        self.assertFalse(client._connected)


class TestCaptureReconnectionHandling(unittest.IsolatedAsyncioTestCase):
    """Test capture() handles reconnection properly."""

    async def test_capture_raises_when_not_connected_and_no_reconnect(self):
        """Test capture raises ConnectionError when not connected."""
        config = VNCConfig(host="localhost", port=5900, auto_reconnect=False)
        client = VNCClient(config)

        with self.assertRaises(ConnectionError) as ctx:
            await client.capture()

        self.assertIn("Connection is closed", str(ctx.exception))

    async def test_capture_waits_for_reconnection(self):
        """Test capture waits for reconnection event if _reconnecting is True."""
        config = VNCConfig(host="localhost", port=5900, auto_reconnect=True)
        client = VNCClient(config)

        # Simulate reconnection in progress
        client._reconnecting = True
        client._reconnect_event.clear()
        client._running = True

        # Track if wait was called
        wait_called = []
        original_wait = client._reconnect_event.wait

        async def tracking_wait():
            wait_called.append(True)
            return await original_wait()

        client._reconnect_event.wait = tracking_wait

        # Test that capture calls wait() on the reconnect event
        async def complete_reconnection():
            await asyncio.sleep(0.01)
            client._reconnecting = False
            client._reconnect_event.set()

        asyncio.create_task(complete_reconnection())

        try:
            await asyncio.wait_for(client.capture(), timeout=1.0)
        except Exception:
            pass  # We don't care about the final error, just that wait was called

        self.assertTrue(wait_called, "_reconnect_event.wait() should have been called")


def main():
    """Run all reconnection tests."""
    print("Running pyvnc reconnection tests...")
    print("=" * 50)

    unittest.main(verbosity=2, exit=False)


if __name__ == "__main__":
    main()
