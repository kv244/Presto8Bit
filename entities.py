import random, math
from utils import get_bezier_point, lorenz_step, rossler_step

# --- CHANGE LOG ---
# v2.1 2026-04-11 Chaotic attractor integration:
#   - Alien: added slots for attractor state (ax, ay, az), parameters (ap1, ap2, ap3), 
#     motion type (a_type: 0=Bezier, 1=Lorenz, 2=Rossler), and screen mapping (a_scale, a_offx, a_offy).
#   - Alien.update(): added branches for lorenz/rossler numerical integration.
#   - Alien.reset(): added support for chaotic initialization.

class Alien:
    __slots__ = ('p0x', 'p0y', 'p1x', 'p1y', 'p2x', 'p2y', 't', 'speed', 'active', 'x', 'y', 'target',
                 'is_boss', 'move_speed', 'hp',
                 # Genetic algorithm traits (pre-allocated per pool slot)
                 'genome', 'survival_frames', 'direct_hits',
                 'fire_rate_mul', 'proj_speed', 'spread_scale',
                 # Ally system
                 'is_ally',
                 # ox/oy always 0 — lets allies use other Aliens as homing targets
                 'ox', 'oy',
                 # Chaotic Attractor state
                 'a_type',    # 0=Bezier/Homing, 1=Lorenz, 2=Rossler
                 'ax', 'ay', 'az', # Trajectory position in attractor phase space
                 'ap1', 'ap2', 'ap3', # Parameters (sigma/rho/beta or a/b/c)
                 'a_scale',   # Scaling phase space coords to pixels
                 'a_offx', 'a_offy') # World offset for attractor center

    def __init__(self):
        self.active = False
        self.t = 0; self.speed = 1
        self.x = 0; self.y = 0
        self.p0x = 0; self.p0y = 0; self.p1x = 0; self.p1y = 0; self.p2x = 0; self.p2y = 0
        self.target = None
        self.is_boss = False
        self.move_speed = 1.8
        self.hp = 1
        # Genetics — 6-element list allocated once per pool slot, mutated by breed()
        self.genome         = [3.0, 1.8, 1.0, 1.0, 10.0, 1.0]
        self.survival_frames = 0
        self.direct_hits    = 0
        self.fire_rate_mul  = 1.0
        self.proj_speed     = 10.0
        self.spread_scale   = 1.0
        # Ally flag
        self.is_ally = False
        # Always zero — satisfies target.ox / target.oy reads in Alien.update()
        self.ox = 0; self.oy = 0
        # Chaos defaults (0 is standard Bezier mode)
        self.a_type = 0; self.ax = 0.0; self.ay = 0.0; self.az = 0.0
        self.ap1 = 0.0; self.ap2 = 0.0; self.ap3 = 0.0
        self.a_scale = 1.0; self.a_offx = 0.0; self.a_offy = 0.0

    def reset(self, p0x, p0y, p1x, p1y, p2x, p2y, speed, target=None, is_boss=False, move_speed=1.8, hp=1,
              fire_rate_mul=1.0, proj_speed=10.0, spread_scale=1.0, 
              a_type=0, ax=0.0, ay=0.0, az=0.0, ap1=0.0, ap2=0.0, ap3=0.0, a_scale=5.0):
        self.p0x = p0x; self.p0y = p0y; self.p1x = p1x; self.p1y = p1y; self.p2x = p2x; self.p2y = p2y
        self.t = 0; self.speed = speed
        self.x = float(p0x); self.y = float(p0y)
        self.target = target
        self.is_boss = is_boss
        self.move_speed = move_speed
        self.active = True
        self.hp = hp
        self.fire_rate_mul  = fire_rate_mul
        self.proj_speed     = proj_speed
        self.spread_scale   = spread_scale
        self.survival_frames = 0
        self.direct_hits    = 0
        self.is_ally        = False   # defection never carries over across respawns
        # Initialize Chaotic Motion if a_type > 0
        self.a_type = a_type; self.ax = ax; self.ay = ay; self.az = az
        self.ap1 = ap1; self.ap2 = ap2; self.ap3 = ap3
        self.a_scale = a_scale; self.a_offx = float(p0x); self.a_offy = float(p0y)

    @micropython.native
    def update(self):
        self.survival_frames = self.survival_frames + 1
        t = self.t + self.speed
        self.t = t
        
        # MOTION TYPE BRANCHING
        if self.a_type == 1: # LORENZ CHAOS
            # Update internal phase space coords via utils.lorenz_step (Viper)
            self.ax, self.ay, self.az = lorenz_step(self.ax, self.ay, self.az, self.ap1, self.ap2, self.ap3, 0.01)
            # Map phase-space X/Y directly to screen pixels
            self.x = self.a_offx + self.ax * self.a_scale
            self.y = self.a_offy + self.ay * self.a_scale
            if t > 600: self.active = False
        elif self.a_type == 2: # ROSSLER CHAOS
            # Update internal phase space coords via utils.rossler_step (Viper)
            self.ax, self.ay, self.az = rossler_step(self.ax, self.ay, self.az, self.ap1, self.ap2, self.ap3, 0.05)
            # Map phase-space X/Y directly to screen pixels
            self.x = self.a_offx + self.ax * self.a_scale
            self.y = self.a_offy + self.ay * self.a_scale
            if t > 600: self.active = False
        else: # STANDARD (BEZIER OR HOMING)
            target = self.target
            if target:
                if t > 400:
                    self.active = False
                else:
                    ax, ay = self.x, self.y
                    tx, ty = target.x + target.ox, target.y + target.oy
                    if self.is_boss:
                        # Ring formation: p1x/p1y hold the spawn offset from ring centre.
                        # Scale decays 1.0→0 over 160 frames, keeping angular separation
                        # while the ring contracts onto the ship.
                        ring_scale = max(0.0, (160.0 - t) / 160.0)
                        tx += self.p1x * ring_scale
                        ty += self.p1y * ring_scale
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
                    # Quadratic Bezier spline movement
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
    """Alien projectile — enemy fire toward the ship, or ally fire toward enemies."""
    __slots__ = ('x', 'y', 'vx', 'vy', 'active', 'is_ally')

    def __init__(self):
        self.active = False
        self.x = 0; self.y = 0; self.vy = 0
        self.is_ally = False

    def reset(self, x, y, vx=-10, vy=0, is_ally=False):
        self.x = x; self.y = y; self.vx = vx; self.vy = vy
        self.active = True; self.is_ally = is_ally

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
ENEMY_LASER_POOL  = Pool(EnemyLaser,   32)  # 20→32: ally 3-way fractal fire needs headroom
gc.collect()