import math, random

SHIP_SPRITE = [
    "        #####        ",
    "        #   #        ",
    "    #####   #####    ",
    "  ###           ###  ",
    " ##    ####       ## ",
    " #     #  #        # ",
    " #     ####  ####### ",
    "##           #  #####",
    "#########    ########",
    "######  #           #",
    "#########           #",
    "#########    ########",
    "##           #  #####",
    " #     ####  ####### ",
    " #     #  #        # ",
    " ##    ####       ## ",
    "  ###           ###  ",
    "    #####   #####    ",
    "        #   #        ",
    "        #####        "
]

SHIP_LINES = []
for _y, row in enumerate(SHIP_SPRITE):
    start = -1
    for _x, char in enumerate(row):
        if char == '#' and start == -1:
            start = _x
        elif char != '#' and start != -1:
            SHIP_LINES.append((start - 10, _y - 10, _x - 1 - 10))
            start = -1
    if start != -1:
        SHIP_LINES.append((start - 10, _y - 10, len(row) - 1 - 10))

del SHIP_SPRITE
import gc; gc.collect()

class Ship:
    __slots__ = ('display', 'x', 'y', 'recoil', 'boss_mode', 'aim_up', 'nuke_ready',
                 'pen_flare_day', 'pen_flare_night', 'pen_nuke_flare',
                 'pen_hull_day', 'pen_hull_night', 'ox', 'oy', 'fire_cooldown')

    def __init__(self, display):
        self.display = display
        self.y = 120; self.recoil = 0; self.x = 45; self.boss_mode = False; self.aim_up = False; self.nuke_ready = False
        self.fire_cooldown = 0
        self.ox = 0; self.oy = 0
        # Pre-cache pens once — no heap alloc during draw
        self.pen_flare_day   = display.create_pen(255, 100, 0)
        self.pen_flare_night = display.create_pen(255, 250, 0)
        self.pen_nuke_flare  = display.create_pen(255, 0, 0)
        self.pen_hull_day    = display.create_pen(20, 20, 20)
        self.pen_hull_night  = display.create_pen(230, 240, 255)

    def update(self, t):
        if self.boss_mode:
            # Eratic animation offsets
            self.oy = int(math.sin(t/10) * 60 + math.cos(t/6) * 30 + math.sin(t/3) * 10)
            self.ox = int(math.sin(t/8) * 35 + math.cos(t/5) * 15)
        else:
            # Ambience animation offsets
            self.oy = int(math.sin(t/14) * 45 + math.cos(t/9) * 25)
            self.ox = int(math.sin(t/11) * 20)
        
        if self.recoil > 0: self.recoil -= 1
        if self.fire_cooldown > 0: self.fire_cooldown -= 1

    def draw(self, is_night, t):
        d = self.display
        # Visual offsets for recoil and boss oscillations
        bx = self.ox - (0 if self.aim_up else self.recoil)
        by = self.oy + (self.recoil if self.aim_up else 0)
        sx = int(self.x + bx)
        sy = int(self.y + by)

        # Rocket flare flickering effect
        flare_radius = random.randint(3, 6)
        flare_offset = random.randint(15, 18)
        if self.nuke_ready:
            # Dangerous red pulsing flare
            d.set_pen(self.pen_nuke_flare if (t // 4) % 2 == 0 else self.pen_flare_night)
        else:
            d.set_pen(self.pen_flare_night if is_night else self.pen_flare_day)
        
        if self.aim_up:
            d.circle(sx, sy + flare_offset, flare_radius) # Flare below when aiming up
        else:
            d.circle(sx - flare_offset, sy, flare_radius) # Flare left when aiming right

        # Hull Sprite Loop
        d.set_pen(self.pen_hull_night if is_night else self.pen_hull_day)
        for rx1, ry, rx2 in SHIP_LINES:
            if self.aim_up:
                # Vertical line (rotated 90deg CCW: rx, ry -> -ry, rx)
                d.line(sx - ry, sy + rx1, sx - ry, sy + rx2)
            else:
                # Horizontal line
                d.line(sx + rx1, sy + ry, sx + rx2, sy + ry)