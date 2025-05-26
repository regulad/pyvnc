#!/usr/bin/env python3
"""
Basic syntax and import tests for pyvnc library.
"""

import sys

def test_syntax():
    """Test that the main module has valid syntax."""
    try:
        import ast
        with open('pyvnc/pyvnc.py', 'r') as f:
            source = f.read()
        ast.parse(source)
        print("✓ Main module syntax is valid")
        return True
    except Exception as e:
        print(f"✗ Syntax error: {e}")
        return False

def test_basic_imports():
    """Test basic imports without external dependencies."""
    try:
        # Test importing core Python modules used
        from abc import ABC, abstractmethod
        from contextlib import contextmanager, ExitStack
        from collections import namedtuple
        from dataclasses import dataclass, field
        from socket import socket, create_connection
        from time import sleep
        from typing import Callable, Dict, Optional, Union, Set, Tuple, Iterator
        from zlib import decompressobj
        
        print("✓ All core Python imports work")
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

def test_constants_and_types():
    """Test that constants and types are properly defined."""
    try:
        from pyvnc.pyvnc import (
            VNC_PROTOCOL_VERSION, VNC_PROTOCOL_HEADER_SIZE, VNC_PROTOCOL_PREFIX,
            AUTH_TYPE_NONE, AUTH_TYPE_VNC, AUTH_TYPE_APPLE,
            MSG_TYPE_FRAMEBUFFER_UPDATE, MSG_TYPE_CLIPBOARD,
            ENCODING_RAW, ENCODING_ZLIB,
            MOUSE_BUTTON_LEFT, MOUSE_BUTTON_MIDDLE, MOUSE_BUTTON_RIGHT,
            MOUSE_BUTTON_SCROLL_UP, MOUSE_BUTTON_SCROLL_DOWN,
            Point, Rect, PointLike, RectLike, slice_rect
        )
        
        # Test Point and Rect
        point = Point(10, 20)
        assert point.x == 10 and point.y == 20
        
        rect = Rect(5, 10, 100, 200)
        assert rect.x == 5 and rect.y == 10 and rect.width == 100 and rect.height == 200
        
        # Test slice_rect
        slices = slice_rect(rect)
        assert len(slices) == 2
        assert slices[0] == slice(10, 210)  # y, y+height
        assert slices[1] == slice(5, 105)   # x, x+width
        
        print("✓ Constants and types work correctly")
        return True
    except Exception as e:
        print(f"✗ Constants/types error: {e}")
        return False

def test_vnc_config():
    """Test VNCConfig without external dependencies."""
    try:
        from pyvnc.pyvnc import VNCConfig
        
        # Test default config
        config = VNCConfig()
        assert config.host == 'localhost'
        assert config.port == 5900
        assert config.timeout == 5.0
        assert config.pixel_format == 'rgba'
        assert config.username is None
        assert config.password is None
        
        # Test custom config
        config2 = VNCConfig(
            host='test.com',
            port=5901,
            password='secret'
        )
        assert config2.host == 'test.com'
        assert config2.port == 5901
        assert config2.password == 'secret'
        
        print("✓ VNCConfig works correctly")
        return True
    except Exception as e:
        print(f"✗ VNCConfig error: {e}")
        return False

def test_interfaces():
    """Test PointLike and RectLike interfaces."""
    try:
        from pyvnc.pyvnc import Point, Rect, PointLike, RectLike
        
        class TestPoint(PointLike):
            def get_point(self) -> Point:
                return Point(50, 75)
        
        class TestRect(RectLike):
            def get_rect(self) -> Rect:
                return Rect(10, 20, 100, 200)
        
        test_point = TestPoint()
        point = test_point.get_point()
        assert point.x == 50 and point.y == 75
        
        test_rect = TestRect()
        rect = test_rect.get_rect()
        assert rect.x == 10 and rect.y == 20 and rect.width == 100 and rect.height == 200
        
        print("✓ PointLike and RectLike interfaces work")
        return True
    except Exception as e:
        print(f"✗ Interface error: {e}")
        return False

def test_relative_coordinates():
    """Test relative coordinate calculations."""
    try:
        from pyvnc.pyvnc import VNCClient, Point, Rect
        from socket import socket
        from zlib import decompressobj
        
        # Create a mock VNCClient for testing coordinate conversion
        mock_sock = socket()
        mock_client = VNCClient(
            sock=mock_sock,
            decompress=decompressobj().decompress,
            rect=Rect(0, 0, 1920, 1080)  # 16:9 1920x1080 screen
        )
        
        # Test relative resolution calculation
        rel_res = mock_client.get_relative_resolution()
        # For 1920x1080 (16:9), width > height, so width should be 99900
        assert rel_res.x == 99900
        expected_rel_height = int(99900 / (1920 / 1080))  # Should be ~56200 (rounded down to multiple of 100)
        expected_rel_height = (expected_rel_height // 100) * 100
        assert rel_res.y == expected_rel_height
        
        # Verify both dimensions are multiples of 100
        assert rel_res.x % 100 == 0
        assert rel_res.y % 100 == 0
        
        # Test point conversion
        rel_point = Point(rel_res.x // 2, rel_res.y // 2)  # Center of relative coords
        abs_point = mock_client._convert_relative_point(rel_point)
        expected_x = int((rel_point.x / rel_res.x) * 1920)
        expected_y = int((rel_point.y / rel_res.y) * 1080)
        assert abs_point.x == expected_x
        assert abs_point.y == expected_y
        
        # Test rect conversion
        rel_rect = Rect(rel_res.x // 4, rel_res.y // 4, rel_res.x // 4, rel_res.y // 4)
        abs_rect = mock_client._convert_relative_rect(rel_rect)
        assert abs_rect.x == int((rel_rect.x / rel_res.x) * 1920)
        assert abs_rect.y == int((rel_rect.y / rel_res.y) * 1080)
        assert abs_rect.width == int((rel_rect.width / rel_res.x) * 1920)
        assert abs_rect.height == int((rel_rect.height / rel_res.y) * 1080)
        
        print(f"✓ Relative coordinates work (relative res: {rel_res.x}x{rel_res.y})")
        return True
    except Exception as e:
        print(f"✗ Relative coordinate error: {e}")
        return False

def test_error_detection():
    """Test that Apple authentication error is properly defined."""
    try:
        from pyvnc.pyvnc import AUTH_TYPE_APPLE
        assert AUTH_TYPE_APPLE == 33
        print("✓ Apple authentication detection constant defined")
        return True
    except Exception as e:
        print(f"✗ Error detection test failed: {e}")
        return False

def main():
    """Run all basic tests."""
    print("Running pyvnc basic tests...")
    print("=" * 40)
    
    tests = [
        test_syntax,
        test_basic_imports,
        test_constants_and_types,
        test_vnc_config,
        test_interfaces,
        test_relative_coordinates,
        test_error_detection,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"✗ {test.__name__} failed with exception: {e}")
            results.append(False)
        print()
    
    print("=" * 40)
    passed = sum(results)
    total = len(results)
    print(f"Tests: {passed}/{total} passed")
    
    if all(results):
        print("✅ All basic tests passed!")
        return 0
    else:
        print("❌ Some tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())