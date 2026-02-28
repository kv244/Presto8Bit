import random, math
from utils import get_bezier_point
ALIEN_SPRITE = [
    "    ########       ",
    "   ##########      ",
    "  ## ## ## ##    # ",
    " ### ## ## ## #### ",
    "   # ## ## ## #  # ",
    "################## ",
    "   # ## ## ## #  # ",
    " ### ## ## ## #### ",
    "  ## ## ## ##    # ",
    "   ##########      ",
    "    ########       "
]

ALIEN_LINES = []
for _y, row in enumerate(ALIEN_SPRITE):
    start = -1
    for _x, char in enumerate(row):
        if char == '#' and start == -1:
            start = _x
        elif char != '#' and start != -1:
            ALIEN_LINES.append((start - 9, _y - 5, _x - 1 - 9))
            start = -1
    if start != -1:
        ALIEN_LINES.append((start - 9, _y - 5, len(row) - 1 - 9))

class Alien:
    def __init__(self, p0, p1, p2, speed, target=None):
        self.p0, self.p1, self.p2 = p0, p1, p2
        self.t = 0
        self.speed = speed
        self.active = True
        self.x, self.y = p0[0], p0[1]
        self.target = target

    def update(self):
        if self.target:
            self.t += self.speed
            if self.t > 400: # allow chasers more time to stay alive
                self.active = False
            else:
                dx = self.target.x - self.x
                dy = self.target.y - self.y
                self.x += 1.8 if dx > 0 else -1.8
                self.y += 1.8 if dy > 0 else -1.8
        else:
            self.t += self.speed
            if self.t > 256:
                self.active = False
            else:
                self.x = get_bezier_point(self.t, self.p0[0], self.p1[0], self.p2[0])
                self.y = get_bezier_point(self.t, self.p0[1], self.p1[1], self.p2[1])

    def draw(self, display, body_pen, glow_pen):
        cx = int(self.x)
        cy = int(self.y)
        
        display.set_pen(glow_pen)
        for x1, y, x2 in ALIEN_LINES:
            display.line(cx + x1 + 1, cy + y + 1, cx + x2 + 1, cy + y + 1)
            
        display.set_pen(body_pen)
        for x1, y, x2 in ALIEN_LINES:
            display.line(cx + x1, cy + y, cx + x2, cy + y)

class Laser:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.active = True

    def update(self):
        self.x += 12
        if self.x > 340: self.active = False

    def draw(self, display, pen):
        display.set_pen(pen)
        display.line(self.x, self.y, self.x - 20, self.y)

class Particle:
    def __init__(self, x, y, is_water=False):
        self.x, self.y = x, y
        if is_water:
            self.vx = random.uniform(-1.0, 1.0)
            self.vy = random.uniform(-2.5, -0.5)
            self.life = random.randint(5, 10)
        else:
            self.vx = random.uniform(-2, 2)
            self.vy = random.uniform(-2, 2)
            self.life = 10
        self.active = True
        self.is_water = is_water

    def update(self):
        self.x += self.vx
        self.y += self.vy
        if self.is_water:
            self.vy += 0.3 # gravity pull for water splashes
        self.life -= 1
        if self.life <= 0: self.active = False

    def draw(self, display, pen, water_pen=None):
        display.set_pen(water_pen if self.is_water and water_pen else pen)
        display.pixel(int(self.x), int(self.y))