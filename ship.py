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

class Ship:
    __slots__ = ('display', 'x', 'y', 'recoil', 'boss_mode', 'aim_up',
                 'pen_flare_day', 'pen_flare_night',
                 'pen_hull_day', 'pen_hull_night')

    def __init__(self, display):
        self.display = display
        self.y = 120; self.recoil = 0; self.x = 45; self.boss_mode = False; self.aim_up = False
        # Pre-cache pens once — no heap alloc during draw
        self.pen_flare_day   = display.create_pen(255, 100, 0)
        self.pen_flare_night = display.create_pen(255, 250, 0)
        self.pen_hull_day    = display.create_pen(20, 20, 20)
        self.pen_hull_night  = display.create_pen(230, 240, 255)

    def update(self, t):
        if self.boss_mode:
            # Eratic, complex evasive maneuvers for boss fight
            self.y = int(120 + math.sin(t/10) * 60 + math.cos(t/6) * 30 + math.sin(t/3) * 10)
            self.x = int(60 + math.sin(t/8) * 35 + math.cos(t/5) * 15)
        else:
            # Complex Lissajous figure for more varied movement
            self.y = int(120 + math.sin(t/14) * 45 + math.cos(t/9) * 25)
            self.x = int(45 + math.sin(t/11) * 20)
        
        if self.recoil > 0: self.recoil -= 1

    def draw(self, is_night):
        d = self.display; sx = self.x - (0 if self.aim_up else self.recoil); sy = self.y + (self.recoil if self.aim_up else 0)

        # Rocket flare flickering effect
        flare_radius = random.randint(3, 6)
        flare_offset = random.randint(15, 18)
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