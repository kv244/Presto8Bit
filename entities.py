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

# Harvest RAM: Delete sprite source strings after conversion
del ALIEN_SPRITE
import gc; gc.collect()

# ---------------------------------------------------------------------------
# Entity classes
# ---------------------------------------------------------------------------

class Alien:
    __slots__ = ('p0x', 'p0y', 'p1x', 'p1y', 'p2x', 'p2y', 't', 'speed', 'active', 'x', 'y', 'target',
                 'is_boss', 'move_speed', 'hp')

    def __init__(self):
        self.active = False
        self.t = 0; self.speed = 1
        self.x = 0; self.y = 0
        self.p0x = 0; self.p0y = 0; self.p1x = 0; self.p1y = 0; self.p2x = 0; self.p2y = 0
        self.target = None
        self.is_boss = False
        self.move_speed = 1.8
        self.hp = 1

    def reset(self, p0x, p0y, p1x, p1y, p2x, p2y, speed, target=None, is_boss=False, move_speed=1.8, hp=1):
        self.p0x = p0x; self.p0y = p0y; self.p1x = p1x; self.p1y = p1y; self.p2x = p2x; self.p2y = p2y
        self.t = 0; self.speed = speed
        self.x = float(p0x); self.y = float(p0y)
        self.target = target
        self.is_boss = is_boss
        self.move_speed = move_speed
        self.active = True
        self.hp = hp

    @micropython.native
    def update(self):
        t = self.t + self.speed
        self.t = t
        target = self.target
        if target:
            if t > 400:
                self.active = False
            else:
                # Cache everything in locals to avoid slow self-lookups
                ax, ay = self.x, self.y
                # Explicitly accessing ship attributes (targets are always ships)
                tx, ty = target.x + target.ox, target.y + target.oy
                dx, dy = tx - ax, ty - ay
                dist = math.sqrt(dx*dx + dy*dy)
                if dist > 0:
                    ms = self.move_speed
                    self.x = ax + (dx / dist) * ms
                    self.y = ay + (dy / dist) * ms
        else:
            if t > 256:
                self.active = False
            else:
                self.x = get_bezier_point(t, self.p0x, self.p1x, self.p2x)
                self.y = get_bezier_point(t, self.p0y, self.p1y, self.p2y)

    def draw(self, display, body_pen, glow_pen):
        cx = int(self.x); cy = int(self.y)
        display.set_pen(glow_pen)
        for x1, y, x2 in ALIEN_LINES:
            display.line(cx + x1 + 1, cy + y + 1, cx + x2 + 1, cy + y + 1)
        display.set_pen(body_pen)
        for x1, y, x2 in ALIEN_LINES:
            display.line(cx + x1, cy + y, cx + x2, cy + y)


class Laser:
    __slots__ = ('x', 'y', 'vx', 'vy', 'active', 'is_up')

    def __init__(self):
        self.active = False
        self.x = 0; self.y = 0

    def reset(self, x, y, vx=12, vy=0, is_up=False):
        self.x = x; self.y = y; self.vx = vx; self.vy = vy
        self.active = True; self.is_up = is_up

    @micropython.native
    def update(self):
        vx, vy = self.vx, self.vy
        nx, ny = self.x + vx, self.y + vy
        self.x, self.y = nx, ny
        if nx > 340 or nx < -20 or ny < -20 or ny > 260:
            self.active = False

    def draw(self, display, pen):
        display.set_pen(pen)
        # Draw tail pointing opposite to velocity vector
        display.line(int(self.x), int(self.y), int(self.x - self.vx * 1.5), int(self.y - self.vy * 1.5))


class EnemyLaser:
    """Alien projectile — travels leftward toward the ship."""
    __slots__ = ('x', 'y', 'vx', 'vy', 'active')

    def __init__(self):
        self.active = False
        self.x = 0; self.y = 0; self.vy = 0

    def reset(self, x, y, vx=-10, vy=0):
        self.x = x; self.y = y; self.vx = vx; self.vy = vy
        self.active = True

    @micropython.native
    def update(self):
        vx, vy = self.vx, self.vy
        nx, ny = self.x + vx, self.y + vy
        self.x, self.y = nx, ny
        if nx < -20 or nx > 340 or ny < -20 or ny > 260:
            self.active = False

    def draw(self, display, pen):
        display.set_pen(pen)
        # Draw tail pointing opposite to velocity vector
        display.line(int(self.x), int(self.y), int(self.x - self.vx * 1.5), int(self.y - self.vy * 1.5))


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

    @micropython.native
    def update(self):
        nx, ny = self.x + self.vx, self.y + self.vy
        self.x, self.y = nx, ny
        is_water = self.is_water
        if is_water:
            self.vy += 0.3
        life = self.life - 1
        self.life = life
        if life <= 0:
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
        """Yield only active objects — no allocation."""
        for obj in self._pool:
            if obj.active:
                yield obj

    def clear(self):
        """Deactivate all objects in the pool."""
        for obj in self._pool:
            obj.active = False


# Pool sizes: tuned for high-performance without heap exhaustion
ALIEN_POOL        = Pool(Alien,        24) # 30 -> 24
LASER_POOL        = Pool(Laser,        64) # Increased for 7-way Super Fire spread
PARTICLE_POOL     = Pool(Particle,     80) # 120 -> 80 (Large RAM saving)
ENEMY_LASER_POOL  = Pool(EnemyLaser,   20)
gc.collect()