# headless.py  — mock layer for running dandare.py on desktop
# Place in same directory as dandare.py.
# Import this BEFORE dandare.py in your training harness.

import sys, math, random

# ── micropython shim ────────────────────────────────────────────────────────
class _MicroPython:
    def native(self, f):   return f   # @micropython.native  → no-op
    def viper(self, f):    return f   # @micropython.viper   → no-op
    def kbd_intr(self, v): pass

micropython = _MicroPython()
sys.modules["micropython"] = micropython

# ── machine shim ────────────────────────────────────────────────────────────
class Pin:
    def __init__(self, *a, **kw): pass

class _Machine:
    Pin = Pin
    def reset(self): raise SystemExit("machine.reset()")

machine = _Machine()
sys.modules["machine"] = machine

# ── display shim ────────────────────────────────────────────────────────────
_pen_counter = 0

class FakeDisplay:
    def __init__(self):
        self._layer = 0

    def get_bounds(self):         return (320, 240)
    def create_pen(self, r=0, g=0, b=0):
        global _pen_counter
        _pen_counter += 1
        return _pen_counter           # unique int, just like the real thing
    def create_pen_hsv(self, h, s, v): return self.create_pen()
    def set_pen(self, pen):        pass
    def set_layer(self, n):        self._layer = n
    def clear(self):               pass
    def pixel(self, x, y):         pass
    def line(self, *a):            pass
    def circle(self, *a):          pass
    def rectangle(self, *a):       pass
    def triangle(self, *a):        pass
    def text(self, *a, **kw):      pass

# ── buzzer shim ─────────────────────────────────────────────────────────────
class Buzzer:
    def __init__(self, pin=None): pass
    def set_tone(self, freq):     pass

# ── presto shim ─────────────────────────────────────────────────────────────
class FakeTouch:
    state = False
    x = 0
    y = 0
    def poll(self): pass

class Presto:
    def __init__(self, **kw):
        self.display = FakeDisplay()
        self.touch   = FakeTouch()

    def update(self):              pass
    def set_led_hsv(self, *a):     pass

sys.modules["presto"] = type(sys)("presto")
sys.modules["presto"].Presto = Presto
sys.modules["presto"].Buzzer = Buzzer

# ── psram shim ───────────────────────────────────────────────────────────────
class _PSRam:
    def mkramfs(self): pass

psram = _PSRam()
sys.modules["psram"] = psram