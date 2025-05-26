pyvnc: capture screen and send keyboard & mouse
===============================================

.. image:: https://img.shields.io/badge/source-github-orange
    :target: https://github.com/barneygale/pytest-vnc

.. note::
   This library was originally pytest-vnc and has been transformed into a standalone
   VNC client library with significant contributions from Claude AI (Anthropic).

.. image:: https://img.shields.io/pypi/v/pyvnc?style=flat-square
    :target: https://pypi.org/project/pyvnc


pyvnc implements a VNC client in pure Python. It works on Mac, Linux and Windows. Use it to
capture screenshots and send keyboard & mouse input to VNC servers:

**Note**: This library was transformed from pytest-vnc with significant contributions from Claude AI (Anthropic)
to create a standalone, production-ready VNC client library.

.. code-block:: python

    from pyvnc import connect_vnc, VNCConfig, Rect, Point, MOUSE_BUTTON_LEFT, MOUSE_BUTTON_MIDDLE, MOUSE_BUTTON_RIGHT

    # Connect to VNC server
    config = VNCConfig(host='localhost', port=5900, password='secret')
    with connect_vnc(config) as vnc:
        # Screenshot
        print(vnc.rect.width, vnc.rect.height)
        pixels = vnc.capture()  # rgba numpy array of entire screen
        pixels = vnc.capture(Rect(x=100, y=0, width=50, height=75))
        # to use PIL/pillow:
        # image = Image.fromarray(pixels)

        # Keyboard input
        vnc.write('hi there!')  # keys are queued
        vnc.press('Ctrl', 'c')  # keys are stacked
        with vnc.hold_key('Ctrl'):
            vnc.press('Esc')

        # Mouse input
        vnc.move(Point(100, 200))
        vnc.click(MOUSE_BUTTON_LEFT)
        vnc.double_click(MOUSE_BUTTON_LEFT)
        vnc.click(MOUSE_BUTTON_MIDDLE)
        vnc.click(MOUSE_BUTTON_RIGHT)
        vnc.scroll_up()
        vnc.scroll_down(repeat=10)
        with vnc.hold_mouse():
            vnc.move(Point(300, 400))  # Drag with left button
        with vnc.hold_mouse(MOUSE_BUTTON_RIGHT):
            vnc.move(Point(500, 600))  # Drag with right button


Installation
------------

This package requires Python 3.9+.

Install pyvnc by running::

    pip install pyvnc


Configuration
-------------

Create a VNCConfig object to specify connection parameters:

.. code-block:: python

    from pyvnc import VNCConfig

    config = VNCConfig(
        host='localhost',        # VNC hostname (default: localhost)
        port=5900,              # VNC port (default: 5900)
        timeout=5.0,            # Connection timeout in seconds (default: 5)
        pixel_format='rgba',    # Colour channel order (default: rgba)
        username='user',        # VNC username (optional)
        password='secret'       # VNC password (optional)
    )


Testing
-------

For development and testing, create a ``.env`` file in the project root::

    # Test VNC Server Configuration
    VNC_HOST=localhost
    VNC_PORT=5900
    VNC_PASSWORD=your_password_here
    # Optional: VNC_USERNAME=your_username

Run tests::

    # Install test dependencies
    pip install pyvnc[test]
    
    # Run basic tests (no VNC server required)
    python tests/test_basic.py
    
    # Run comprehensive test suite (includes integration tests)
    python tests/test_comprehensive.py
