# BEFORE (lines 1-8 area):
import machine
import psram
from picovector import ...
from presto import Presto

psram.mkramfs()
try:
    with open("/ramfs/launch.txt", "r") as f: ...
#...

# AFTER — wrap everything hardware-specific:
try:
    import machine, psram
    from picovector import ANTIALIAS_FAST, HALIGN_CENTER, PicoVector, Polygon, Transform
    from presto import Presto, Buzzer
    psram.mkramfs()
    # ... rest of boot block
    _ON_HARDWARE = True
except ImportError:
    from headless import Presto, Buzzer, micropython, machine
    _ON_HARDWARE = False