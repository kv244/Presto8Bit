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

# ---------------------------------------------------------------------------
# Entity classes
# ---------------------------------------------------------------------------

class Alien:
    __slots__ = ('p0', 'p1', 'p2', 't', 'speed', 'active', 'x', 'y', 'target',
                 'is_boss', 'move_speed')

    def __init__(self):
        self.active = False
        self.t = 0; self.speed = 1
        self.x = 0; self.y = 0
        self.p0 = (0, 0); self.p1 = (0, 0); self.p2 = (0, 0)
        self.target = None
        self.is_boss = False
        self.move_speed = 1.8

    def reset(self, p0, p1, p2, speed, target=None, is_boss=False, move_speed=1.8):
        self.p0 = p0; self.p1 = p1; self.p2 = p2
        self.t = 0; self.speed = speed
        self.x = p0[0]; self.y = p0[1]
        self.target = target
        self.is_boss = is_boss
        self.move_speed = move_speed
        self.active = True

    def update(self):
        if self.target:
            self.t += self.speed
            if self.t > 400:
                self.active = False
            else:
                dx = self.target.x - self.x
                dy = self.target.y - self.y
                ms = self.move_speed
                self.x += ms if dx > 0 else -ms
                self.y += ms if dy > 0 else -ms
        else:
            self.t += self.speed
            if self.t > 256:
                self.active = False
            else:
                self.x = get_bezier_point(self.t, self.p0[0], self.p1[0], self.p2[0])
                self.y = get_bezier_point(self.t, self.p0[1], self.p1[1], self.p2[1])

    def draw(self, display, body_pen, glow_pen):
        cx = int(self.x); cy = int(self.y)
        display.set_pen(glow_pen)
        for x1, y, x2 in ALIEN_LINES:
            display.line(cx + x1 + 1, cy + y + 1, cx + x2 + 1, cy + y + 1)
        display.set_pen(body_pen)
        for x1, y, x2 in ALIEN_LINES:
            display.line(cx + x1, cy + y, cx + x2, cy + y)


class Laser:
    __slots__ = ('x', 'y', 'active')

    def __init__(self):
        self.active = False
        self.x = 0; self.y = 0

    def reset(self, x, y):
        self.x = x; self.y = y
        self.active = True

    def update(self):
        self.x += 12
        if self.x > 340:
            self.active = False

    def draw(self, display, pen):
        display.set_pen(pen)
        display.line(self.x, self.y, self.x - 20, self.y)


class EnemyLaser:
    """Alien projectile — travels leftward toward the ship."""
    __slots__ = ('x', 'y', 'active')

    def __init__(self):
        self.active = False
        self.x = 0; self.y = 0

    def reset(self, x, y):
        self.x = x; self.y = y
        self.active = True

    def update(self):
        self.x -= 10          # moves left
        if self.x < -20:
            self.active = False

    def draw(self, display, pen):
        display.set_pen(pen)
        display.line(self.x, self.y, self.x + 16, self.y)  # tail points right


class Particle:
    __slots__ = ('x', 'y', 'vx', 'vy', 'life', 'active', 'is_water')

    def __init__(self):
        self.active = False
        self.x = 0; self.y = 0
        self.vx = 0.0; self.vy = 0.0
        self.life = 0
        self.is_water = False

    def reset(self, x, y, is_water=False):
        self.x = x; self.y = y
        self.is_water = is_water
        if is_water:
            self.vx = random.uniform(-1.0, 1.0)
            self.vy = random.uniform(-2.5, -0.5)
            self.life = random.randint(5, 10)
        else:
            self.vx = random.uniform(-2, 2)
            self.vy = random.uniform(-2, 2)
            self.life = 10
        self.active = True

    def update(self):
        self.x += self.vx
        self.y += self.vy
        if self.is_water:
            self.vy += 0.3
        self.life -= 1
        if self.life <= 0:
            self.active = False

    def draw(self, display, pen, water_pen=None):
        display.set_pen(water_pen if self.is_water and water_pen else pen)
        display.pixel(int(self.x), int(self.y))


# ---------------------------------------------------------------------------
# Object pools — pre-allocated, no heap churn after startup
# ---------------------------------------------------------------------------

class Pool:
    """Fixed-size object pool. get() recycles an inactive slot; never allocates."""
    def __init__(self, factory, size):
        self._pool = [factory() for _ in range(size)]
        self._size = size

    def get(self):
        for obj in self._pool:
            if not obj.active:
                return obj
        return None  # pool exhausted - caller should skip

    def active_objects(self):
        """Iterate only active objects without creating a copy list."""
        return self._pool  # caller checks .active


# Pool sizes: sized generously for worst-case bursts
ALIEN_POOL        = Pool(Alien,        30)
LASER_POOL        = Pool(Laser,        20)
PARTICLE_POOL     = Pool(Particle,    120)
ENEMY_LASER_POOL  = Pool(EnemyLaser,   30)