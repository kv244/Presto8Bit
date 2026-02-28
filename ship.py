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
    __slots__ = ('display', 'x', 'y', 'recoil',
                 'pen_flare_day', 'pen_flare_night',
                 'pen_hull_day', 'pen_hull_night')

    def __init__(self, display):
        self.display = display
        self.y = 120; self.recoil = 0; self.x = 45
        # Pre-cache pens once — no heap alloc during draw
        self.pen_flare_day   = display.create_pen(255, 100, 0)
        self.pen_flare_night = display.create_pen(255, 250, 0)
        self.pen_hull_day    = display.create_pen(20, 20, 20)
        self.pen_hull_night  = display.create_pen(230, 240, 255)

    def update(self, t, boss_mode=False):
        if boss_mode:
            # Eratic, complex evasive maneuvers for boss fight
            self.y = int(120 + math.sin(t/10) * 60 + math.cos(t/6) * 30 + math.sin(t/3) * 10)
            self.x = int(60 + math.sin(t/8) * 35 + math.cos(t/5) * 15)
        else:
            # Complex Lissajous figure for more varied movement
            self.y = int(120 + math.sin(t/14) * 45 + math.cos(t/9) * 25)
            self.x = int(45 + math.sin(t/11) * 20)
        
        if self.recoil > 0: self.recoil -= 1

    def draw(self, is_night):
        d = self.display; sx = self.x - self.recoil

        # Rocket flare flickering effect
        flare_radius = random.randint(3, 6)
        flare_offset = random.randint(15, 18)
        d.set_pen(self.pen_flare_night if is_night else self.pen_flare_day)
        d.circle(sx - flare_offset, self.y, flare_radius)

        # Hull Sprite Loop
        d.set_pen(self.pen_hull_night if is_night else self.pen_hull_day)
        for x1, y, x2 in SHIP_LINES:
            d.line(sx + x1, self.y + y, sx + x2, self.y + y)