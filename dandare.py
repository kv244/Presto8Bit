# ICON joystick
# NAME Dan Dare
# DESC Parallax pilot of the future

from presto import Presto, Buzzer
from machine import Pin
import time, random, gc, micropython
from utils import fast_dimmer
from entities import ALIEN_POOL, LASER_POOL, PARTICLE_POOL
from environment import Environment
from ship import Ship

# ---------------------------------------------------------------------------
# Rain is simple enough to stay as pre-allocated plain lists.
# We cap it and recycle slots instead of append/remove.
# ---------------------------------------------------------------------------
_RAIN_MAX = 40
_rain_x    = [0]  * _RAIN_MAX
_rain_y    = [0]  * _RAIN_MAX  # stored as fixed-point *256 to avoid floats
_rain_spd  = [0]  * _RAIN_MAX
_rain_live = [False] * _RAIN_MAX
_rain_len  = [0, _RAIN_MAX]   # [0]=wasted-slot cache hint, [1]=cap

def _rain_spawn():
    for i in range(_RAIN_MAX):
        if not _rain_live[i]:
            _rain_x[i]   = random.randint(0, 320)
            _rain_y[i]   = 0
            _rain_spd[i] = random.randint(8, 12)
            _rain_live[i] = True
            return


class Game:
    def __init__(self):
        # 1. Hardware & Engine Setup
        micropython.kbd_intr(-1)
        try:
            self.presto = Presto(full_res=False, layers=2)
        finally:
            micropython.kbd_intr(3)
        self.display = self.presto.display
        self.buzzer  = Buzzer(Pin(43))

        # 2. Subsystems
        self.env  = Environment(self.display)
        self.ship = Ship(self.display)

        # 3. State
        self.score     = 50
        self.game_over = False
        self.t         = 0
        self.PHASE_LEN = 1000
        self.pause_timer       = 0
        self.time_check_counter = 0
        self.last_hour_checked = time.localtime()[3]

        self.impact_timer  = 0
        self.explode_timer = 0

        # 4. Pre-cache pens (avoids heap allocation every frame)
        d = self.display
        self.pen_shadow    = d.create_pen(30, 0, 50)
        self.pen_hud       = d.create_pen(255, 30, 180)
        self.pen_rain      = d.create_pen(80, 80, 90)
        self.pen_laser     = d.create_pen(0, 255, 255)
        self.pen_particle  = d.create_pen(255, 150, 0)
        self.pen_water     = d.create_pen(160, 210, 255)
        self.pen_alien_body= d.create_pen(50, 200, 50)
        self.pen_alien_glow= d.create_pen(100, 255, 100)
        self.pen_halo      = d.create_pen(60, 90, 120)
        self.pen_black     = 0

        # 5. High Score persistence
        try:
            with open("highscore.txt", "r") as f:
                self.high_score = int(f.read())
        except:
            self.high_score = 0

        # 6. GC budget: collect only when free memory drops below threshold
        self._gc_countdown = 0

    # -----------------------------------------------------------------------
    # Spawn helpers — use pools, never append()
    # -----------------------------------------------------------------------
    def spawn_alien(self):
        a = ALIEN_POOL.get()
        if a is None:
            return  # pool full, skip this spawn
        sy = random.randint(40, 160)
        tx = -50 if random.random() > 0.3 else 370
        is_seeker = self.ship if random.random() > 0.85 else None
        a.reset(
            (340, sy),
            (random.randint(0, 320), random.randint(0, 240)),
            (tx, sy + random.randint(-80, 80)),
            random.randint(2, 5),
            is_seeker
        )

    def fire_laser(self, x, y):
        l = LASER_POOL.get()
        if l is not None:
            l.reset(x, y)

    def spawn_particles(self, x, y, count, is_water=False):
        for _ in range(count):
            p = PARTICLE_POOL.get()
            if p is None:
                break
            p.reset(x, y, is_water)

    # -----------------------------------------------------------------------
    def draw_hud(self, text, x, y, size):
        d = self.display
        d.set_pen(self.pen_shadow)
        d.text(text, x + 2, y + 2, 320, size)
        d.set_pen(self.pen_hud)
        d.text(text, x, y, 320, size)

    # -----------------------------------------------------------------------
    def update(self):
        self.t += 1

        # Throttled RTC check — only call time.localtime() rarely
        self.time_check_counter += 1
        if self.time_check_counter > 500:
            self.time_check_counter = 0
            now = time.localtime()
            if now[3] != self.last_hour_checked and now[4] == 0:
                self.pause_timer = 250
                self.last_hour_checked = now[3]
                if self.score > self.high_score:
                    self.high_score = self.score
                    with open("highscore.txt", "w") as f:
                        f.write(str(self.score))

        if self.pause_timer > 0:
            return

        # Environment & ship
        self.env.update(self.t % (self.PHASE_LEN * 4), self.PHASE_LEN)
        self.ship.update(self.t)

        # Spawning
        spawn_threshold = 0.94
        if self.score > 300:
            spawn_threshold = max(0.70, 0.94 - ((self.score - 300) * 0.0004))
        if random.random() > spawn_threshold:
            self.spawn_alien()
        if random.random() > 0.60:
            _rain_spawn()

        # Firing
        is_danger = self.score <= 50
        fire_threshold = 0.85 if is_danger else 0.96
        if random.random() > fire_threshold:
            self.fire_laser(self.ship.x + 10, self.ship.y)
            if is_danger:
                self.fire_laser(self.ship.x, self.ship.y - 15)
                self.fire_laser(self.ship.x, self.ship.y + 15)
            self.ship.recoil = 5
            self.buzzer.set_tone(1500 if is_danger else 1200)
        else:
            if self.impact_timer > 0:
                self.buzzer.set_tone(random.randint(50, 250))
                self.impact_timer -= 1
            elif self.explode_timer > 0:
                self.buzzer.set_tone(random.randint(2000, 3000))
                self.explode_timer -= 1
            else:
                self.buzzer.set_tone(0)

        # ---- Rain update (index-based, no object allocation) ----
        for i in range(_RAIN_MAX):
            if _rain_live[i]:
                _rain_y[i] += _rain_spd[i]
                if _rain_y[i] > 240:
                    self.spawn_particles(_rain_x[i], 240,
                                         random.randint(2, 4), is_water=True)
                    _rain_live[i] = False

        # ---- Laser update + collision ----
        ship_x = self.ship.x
        ship_y = self.ship.y
        for l in LASER_POOL.active_objects():
            if not l.active:
                continue
            l.update()
            if not l.active:
                continue
            lx = l.x; ly = l.y
            for a in ALIEN_POOL.active_objects():
                if not a.active:
                    continue
                dx = lx - a.x; dy = ly - a.y
                if dx*dx + dy*dy < 144:
                    self.score += 10
                    self.explode_timer = 5
                    self.spawn_particles(a.x, a.y, 8)
                    a.active = False
                    l.active = False
                    break

        # ---- Alien update + ship collision ----
        for a in ALIEN_POOL.active_objects():
            if not a.active:
                continue
            a.update()
            if not a.active:
                continue
            dx = ship_x - a.x; dy = ship_y - a.y
            if dx*dx + dy*dy < 100:
                self.score -= 50
                self.impact_timer = 15
                self.spawn_particles(ship_x, ship_y, 20)
                a.active = False
                if self.score <= 0:
                    self.score = 0
                    self.game_over = True
                    self.pause_timer = 150

        # ---- Particle update ----
        for p in PARTICLE_POOL.active_objects():
            if p.active:
                p.update()

        # ---- Budgeted GC: only collect when needed ----
        self._gc_countdown -= 1
        if self._gc_countdown <= 0:
            free = gc.mem_free()
            if free < 20000:
                gc.collect()
                self._gc_countdown = 60   # after a collect, wait 60 frames
            else:
                self._gc_countdown = 300  # plenty of memory, check again in 300 frames

    # -----------------------------------------------------------------------
    def draw(self):
        d = self.display

        # Layer 0 (Background)
        self.env.draw_layer0(self.t)

        # Layer 1 (Entities)
        d.set_layer(1)
        d.set_pen(self.pen_black)
        d.clear()

        # Night-time: spotlight + dimming
        if self.env.is_night:
            fast_dimmer(d, 0, 5, 20)
            d.set_pen(self.pen_halo)
            d.circle(self.ship.x, self.ship.y, 42)
            d.set_pen(self.pen_black)
            d.circle(self.ship.x, self.ship.y, 40)

        # Rain
        d.set_pen(self.pen_rain)
        for i in range(_RAIN_MAX):
            if _rain_live[i]:
                ry = _rain_y[i]
                d.line(_rain_x[i], ry, _rain_x[i], ry + _rain_spd[i])

        # Lasers
        for l in LASER_POOL.active_objects():
            if l.active:
                l.draw(d, self.pen_laser)

        # Particles
        for p in PARTICLE_POOL.active_objects():
            if p.active:
                p.draw(d, self.pen_particle, self.pen_water)

        # Aliens
        for a in ALIEN_POOL.active_objects():
            if a.active:
                a.draw(d, self.pen_alien_body, self.pen_alien_glow)

        self.ship.draw(self.env.is_night)

        # HUD
        self.draw_hud(f"SCORE: {self.score}", 5, 5, 2)
        self.draw_hud(f"HI: {self.high_score}", 240, 5, 2)

        if self.pause_timer > 0:
            if self.game_over:
                self.draw_hud("GAME OVER", 90, 100, 3)
            else:
                self.draw_hud("HOURLY VICTORY!", 70, 100, 2)

        self.presto.update()

    # -----------------------------------------------------------------------
    def run(self):
        while True:
            self.update()
            self.draw()
            if self.pause_timer > 0:
                self.pause_timer -= 1
                if self.pause_timer == 0 and self.game_over:
                    self.__init__()   # Full restart
            time.sleep(0.02)


game = Game()
game.run()