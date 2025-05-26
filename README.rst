pyvnc: capture screen and send keyboard & mouse
===============================================

.. image:: https://img.shields.io/badge/source-github-orange
    :target: https://github.com/barneygale/pytest-vnc

.. image:: https://img.shields.io/pypi/v/pyvnc?style=flat-square
    :target: https://pypi.org/project/pyvnc


pyvnc implements a VNC client in pure Python. It works on Mac, Linux and Windows. Use it to
capture screenshots and send keyboard & mouse input to VNC servers:

**Note**: This library was transformed from pytest-vnc with significant contributions from Claude AI (Anthropic)
to create a standalone, production-ready VNC client library.

.. code-block:: python

    from pyvnc import connect_vnc, VNCConfig, Rect, Point

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
        with vnc.hold('Ctrl'):
            vnc.press('Esc')

        # Mouse input
        vnc.move(Point(100, 200))
        vnc.click()
        vnc.double_click()
        vnc.middle_click()
        vnc.right_click()
        vnc.scroll_up()
        vnc.scroll_down(repeat=10)
        with vnc.drag():
            vnc.move(Point(300, 400))
        with vnc.middle_drag():
            vnc.move(Point(500, 600))
        with vnc.right_drag():
            vnc.move(Point(700, 800))


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
        speed=20.0,             # Interactions per second (default: 20)
        timeout=5.0,            # Connection timeout in seconds (default: 5)
        pixel_format='rgba',    # Colour channel order (default: rgba)
        username='user',        # VNC username (default: env: PYVNC_USER or current user)
        password='secret'       # VNC password (default: env: PYVNC_PASSWD)
    )

The following attributes can be set on the VNCClient object:

``speed``
  Interactions per second (default: 20)
``sleep``
  Callable that accepts a duration in seconds and waits for that long (default: ``time.sleep()``)
