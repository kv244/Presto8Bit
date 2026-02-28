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
    def __init__(self, display):
        self.display = display
        self.y = 120; self.recoil = 0; self.x = 45

    def update(self, t):
        # Complex Lissajous figure for more varied movement
        self.y = int(120 + math.sin(t/14) * 45 + math.cos(t/9) * 25)
        self.x = int(45 + math.sin(t/11) * 20)
        if self.recoil > 0: self.recoil -= 1

    def draw(self, is_night):
        d = self.display; sx = self.x - self.recoil
        
        # Rocket flare flickering effect
        flare_radius = random.randint(3, 6)
        flare_offset = random.randint(15, 18)
        d.set_pen(d.create_pen(255, 100, 0) if not is_night else d.create_pen(255, 250, 0))
        d.circle(sx - flare_offset, self.y, flare_radius)
        
        # Hull Sprite Loop
        hull_pen = d.create_pen(20, 20, 20) if not is_night else d.create_pen(230, 240, 255)
        d.set_pen(hull_pen)
        
        for x1, y, x2 in SHIP_LINES:
            d.line(sx + x1, self.y + y, sx + x2, self.y + y)