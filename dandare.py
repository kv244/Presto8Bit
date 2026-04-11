# ICON joystick
# NAME Dan Dare
# DESC Parallax pilot of the future
#
# --- CHANGE LOG ---
# v2  2026-04-11  Three new gameplay systems added:
#
#   1. GENETIC ALGORITHM (enemies)
#      - New module: genetics.py  (gene pool, breed, record_fitness)
#      - Each alien carries a 6-gene genome: speed, move_speed, hp,
#        fire_rate_mul, proj_speed, spread_scale
#      - On death the genome + fitness (survival_frames + direct_hits×100)
#        is recorded in an 8-slot gene pool (tournament selection)
#      - 60 % of new spawns are bred via single-point crossover + 20 % /
#        gene mutation; first-generation aliens use random defaults
#      - Integrated in: spawn_alien(), _update_collisions()
#
#   2. FRACTAL BULLET SPREADS (player + enemies)
#      - Pre-computed golden-ratio (φ=0.618) angle trees at module load
#      - Hero 7-way: depth-2 binary tree ≈ ±6.9°/±18°/±29.1° + centre
#      - Standard 3-way / enemy 3-way: ±15° symmetric fractal subset
#      - Cloud-eraser X offsets: same φ-tree scaled to ±45 px (was uniform)
#      - All spreads use a 2-D rotation matrix so the pattern follows the
#        tracked target direction rather than being axis-aligned
#      - Integrated in: _handle_firing() hero/standard/enemy branches
#
#   3. ENEMY DEFECTION (ally system)
#      - Non-boss enemies have a 0.02 % / frame chance to defect (≈ rare)
#      - Defected alien: is_ally=True, drawn in cyan, max 6 concurrent
#      - Allies home toward the nearest non-ally enemy alien each frame
#      - Allies fire a 3-way fractal spread toward that enemy (new method
#        _handle_ally_fire())
#      - Ally body-collision with an enemy kills the enemy (+15 score)
#      - Ally lasers (EnemyLaser.is_ally=True) are drawn in cyan and only
#        damage non-ally aliens
#      - Integrated in: _update_collisions(), _handle_ally_fire(), draw()

from presto import Presto, Buzzer
from machine import Pin
import time, random, gc, micropython, math, sys

import gc
gc.collect()

# Force reload of local modules on soft-reboot to pick up disk changes
for mod in ['utils', 'entities', 'environment', 'ship']:
    if mod in sys.modules:
        del sys.modules[mod]
gc.collect()

print("Checking local modules...")
print("-> Loading utils...")
gc.collect()
print(f"   [RAM] {gc.mem_free()} bytes free.")
from utils import fast_dimmer
import achievements as _ach
import music as _music
print("   [OK] Utils loaded.")
print("-> Loading entities...")
gc.collect()
print(f"   [RAM] {gc.mem_free()} bytes free.")
from entities import ALIEN_POOL, LASER_POOL, PARTICLE_POOL, ENEMY_LASER_POOL
print("   [OK] Entities loaded.")
print("-> Loading genetics...")
gc.collect()
import genetics as _genetics
print("   [OK] Genetics loaded.")
import chaos as _chaos
print("   [OK] Chaos theory loaded.")
print("-> Loading environment...")
gc.collect()
print(f"   [RAM] {gc.mem_free()} bytes free.")
from environment import Environment
print("   [OK] Environment loaded.")
print("-> Loading ship...")
gc.collect()
print(f"   [RAM] {gc.mem_free()} bytes free.")
from ship import Ship
print("   [OK] Ship loaded.")
print("Local modules reloaded.")

# ---------------------------------------------------------------------------
# Fractal bullet-spread geometry — golden-ratio (φ=0.618) self-similar subdivision
# Each spread is a depth-2 binary tree: outer=base×(1+φ), mid=base, inner=base×(1-φ)
# Pre-computed as (cos, sin) tuples so no trig during gameplay.
# ---------------------------------------------------------------------------
_FS  = 18.0   # base angular spread in degrees (tune here to adjust fan width)
_FX  = 28     # base X-offset for cloud fire (pixels)
_PHI = 0.618  # golden ratio

def _fa(deg):
    import math as _m
    r = deg * _m.pi / 180.0
    return (_m.cos(r), _m.sin(r))

# Hero 7-way spread (depth-2 binary tree, angles in degrees from horizontal):
#   ≈ (-29.1°, -18°, -6.9°, 0°, +6.9°, +18°, +29.1°)
_HERO_SPREAD = (
    _fa(-_FS * (1 + _PHI)),
    _fa(-_FS),
    _fa(-_FS * (1 - _PHI)),
    _fa(0.0),
    _fa( _FS * (1 - _PHI)),
    _fa( _FS),
    _fa( _FS * (1 + _PHI)),
)

# 3-way spread used by: enemy fire, ally fire, standard player mode danger
_ENEMY_SPREAD = (_fa(-15.0), _fa(0.0), _fa(15.0))

# Single centre shot — standard player mode when not in danger
_STD_SINGLE = (_fa(0.0),)

# Cloud-eraser X offsets (hero 7-way, level-2 fractal spacing, ±45 outer):
#   -45, -28, -10, 0, +10, +28, +45
_CLOUD_OFFSETS = (
    -int(_FX * (1 + _PHI)),
    -_FX,
    -int(_FX * (1 - _PHI)),
    0,
    int(_FX * (1 - _PHI)),
    _FX,
    int(_FX * (1 + _PHI)),
)

# Cloud-eraser X offsets (standard 3-way, level-1 nodes only):
#   -28, 0, +28
_CLOUD_OFFSETS_3 = (-_FX, 0, _FX)

del _fa, _PHI, _FS, _FX
gc.collect()

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

def _rain_spawn(cloud_count, cloud_buf):
    if cloud_count == 0: return
    for i in range(_RAIN_MAX):
        if not _rain_live[i]:
            # Pick a random cloud and spawn rain near its center
            cx = cloud_buf[random.randint(0, cloud_count - 1)]
            _rain_x[i]   = cx + random.randint(-15, 15)
            _rain_y[i]   = 0
            _rain_spd[i] = random.randint(8, 12)
            _rain_live[i] = True
            return


class Game:
    __slots__ = ('presto', 'display', 'buzzer', 'joypad', 'env', 'ship', 'ship_vx', 'ship_vy',
                 'score', 'game_over', 't', 'PHASE_LEN', 'pause_timer', 'time_check_counter',
                 'last_hour_checked', 'impact_timer', 'explode_timer', 'boss_active',
                 'boss_next_threshold', 'boss_defeat_timer', 'nuke_used', 'nuke_anim_timer',
                 'cloud_revert_timer', 'pen_shadow', 'pen_hud', 'pen_rain', 'pen_laser',
                 'pen_up_laser', 'pen_particle', 'pen_water', 'pen_alien_body',
                 'pen_alien_glow', 'pen_halo', 'pen_black', 'pen_boss_border',
                 'pen_boss_hud', 'pen_boss_shadow', 'pen_boss_alien_body',
                 'pen_boss_alien_glow', 'pen_enemy_laser', 'pen_night_dim', 'high_score',
                 '_gc_countdown', 'pen_ally_body', 'pen_ally_glow',
                 '_score_str', '_hi_str', '_last_score_drawn', '_last_hi_drawn', 'in_intro',
                 'achievements', 'ach_notify_timer', 'ach_notify_text', 'pen_ach',
                 '_aliens_killed', '_clouds_destroyed', '_untouchable',
                 '_music', 'chaos_twins', 'chaos_tracker', '_lambda_str', 'chaos_wave_active')

    def __init__(self, presto=None):
        # 1. Hardware & Engine Setup (persistent)
        if presto is None:
            micropython.kbd_intr(-1)
            try:
                self.presto = Presto(full_res=False, layers=2)
            finally:
                micropython.kbd_intr(3)
        else:
            self.presto = presto
            
        self.display = self.presto.display
        self.buzzer  = Buzzer(Pin(43))
        self._music  = _music.Player(self.buzzer)

        # Optional QWIIC joypad (QwSTPad) — graceful fallback to autopilot
        try:
            from machine import I2C as _I2C
            from qwstpad import QwSTPad as _QwSTPad, DEFAULT_ADDRESS as _JP_ADDR
            _i2c = _I2C(0, scl=41, sda=40)
            self.joypad = _QwSTPad(_i2c, _JP_ADDR, show_address=False)
            print("Joypad: connected")
        except Exception as _e:
            self.joypad = None
            print(f"Joypad: not available ({_e})")

        # 4. Pre-cache pens (avoids heap allocation every frame)
        d = self.display
        self.pen_shadow    = d.create_pen(30, 0, 50)
        self.pen_hud       = d.create_pen(255, 30, 180)
        self.pen_rain      = d.create_pen(80, 80, 90)
        self.pen_laser     = d.create_pen(0, 255, 255)
        self.pen_up_laser  = d.create_pen(255, 255, 100) # Golden-yellow for clouds
        self.pen_particle  = d.create_pen(255, 150, 0)
        self.pen_water     = d.create_pen(160, 210, 255)
        self.pen_alien_body= d.create_pen(50, 200, 50)
        self.pen_alien_glow= d.create_pen(100, 255, 100)
        self.pen_halo      = d.create_pen(60, 90, 120)
        self.pen_black     = 0
        # Boss-specific pens
        self.pen_boss_border = d.create_pen(220, 0, 0)
        self.pen_boss_hud    = d.create_pen(255, 60, 0)
        self.pen_boss_shadow = d.create_pen(80, 0, 0)
        self.pen_boss_alien_body = d.create_pen(220, 30, 30)
        self.pen_boss_alien_glow = d.create_pen(255, 80, 80)
        self.pen_enemy_laser     = d.create_pen(255, 80, 0)  # red-orange bolt
        self.pen_night_dim       = d.create_pen(0, 5, 20)    # static night dimmer
        
        # High score persistence
        try:
            with open("highscore.txt", "r") as f:
                self.high_score = int(f.read())
        except:
            self.high_score = 0

        # Achievements (persistent across resets)
        self.achievements = _ach.load()
        self.ach_notify_timer = 0
        self.ach_notify_text = ''
        self.pen_ach = d.create_pen(255, 215, 0)  # gold notification text

        # Ally pens — cyan tones distinguish defected aliens from enemies
        self.pen_ally_body = d.create_pen(0, 210, 220)
        self.pen_ally_glow = d.create_pen(80, 255, 255)
        
        # Chaos Logic
        self.chaos_twins = (None, None)
        self.chaos_tracker = _chaos.LyapunovTracker("Chaos Wave")
        self._lambda_str = ""
        self.chaos_wave_active = False

        # Cache HUD strings to avoid per-frame heap churn
        self._score_str = ""
        self._hi_str    = ""
        self._last_score_drawn = -1
        self._last_hi_drawn    = -1
        
        self.in_intro = True
        self.reset()
        self._music.play(_music.INTRO, loop=True)


    def reset(self):
        if hasattr(self, '_music'):
            self._music.stop()
        # Free old subsystem memory before allocating new ones
        gc.collect()
        # 2. Subsystems
        ALIEN_POOL.clear()
        LASER_POOL.clear()
        ENEMY_LASER_POOL.clear()
        PARTICLE_POOL.clear()
        _genetics.reset_pool()
        for i in range(_RAIN_MAX): _rain_live[i] = False

        self.env  = Environment(self.display)
        self.ship = Ship(self.display)
        
        # Initial visual positions to prevent early draw errors
        self.ship_vx = self.ship.x
        self.ship_vy = self.ship.y

        # 3. State
        self.score     = 550
        self.game_over = False
        self.t         = 0
        self.PHASE_LEN = 1000
        self.pause_timer       = 0
        self.time_check_counter = 0
        self.last_hour_checked = time.localtime()[3]

        self.impact_timer  = 0
        self.explode_timer = 0

        self.boss_active        = False
        self.boss_next_threshold = self.score + 500
        self.boss_defeat_timer  = 0
        
        self.nuke_used = False
        self.nuke_anim_timer = 0
        self.cloud_revert_timer = 0
        self._gc_countdown = 0
        # Per-game achievement counters (achievements themselves persist)
        self._aliens_killed = 0
        self._clouds_destroyed = 0
        self._untouchable = True
        self.ach_notify_timer = 0
        # Chaos reset
        self.chaos_twins = (None, None)
        self.chaos_wave_active = False
        self._lambda_str = ""

    # -----------------------------------------------------------------------
    def _unlock_ach(self, key):
        name = _ach.unlock(key, self.achievements)
        if name is not None:
            # Only show notification if none is currently displayed
            if self.ach_notify_timer == 0:
                self.ach_notify_text = f'ACHIEVEMENT: {name}!'
                self.ach_notify_timer = 150  # ~3 seconds at 50fps

    # -----------------------------------------------------------------------
    # Spawn helpers — use pools, never append()
    # -----------------------------------------------------------------------
    def spawn_alien(self):
        if self.boss_active:
            return  # suppress normal spawning during boss fight
        a = ALIEN_POOL.get()
        if a is None:
            return
        sy = random.randint(40, 160)
        tx = -50 if random.random() > 0.3 else 370
        is_seeker = self.ship if random.random() > 0.85 else None

        # Elite alien chance: 15% chance (drawn in red like a mini-boss)
        is_elite = random.random() > 0.85
        # 50% of elites that aren't already seekers become seekers — they hunt the ship
        if is_elite and is_seeker is None and random.random() > 0.5:
            is_seeker = self.ship

        # Genetic algorithm — breed() writes a child genome into a.genome in-place.
        # Returns True if the gene pool had ≥2 parents, False on first generation.
        bred = _genetics.breed(a.genome)
        if bred:
            spd       = a.genome[0]
            move_spd  = a.genome[1]
            hp_val    = max(1, int(a.genome[2]))
            fire_mul  = a.genome[3]
            proj_spd  = a.genome[4]
            spr_scale = a.genome[5]
            if is_elite:
                hp_val = max(2, hp_val)
        else:
            # First-generation defaults with random speed variation
            spd = float(random.randint(2, 5))
            move_spd  = 1.8
            hp_val    = 2 if is_elite else 1
            fire_mul  = 1.0
            proj_spd  = 10.0
            spr_scale = 1.0
            # Mirror defaults into genome so fitness can be recorded on death
            a.genome[0] = spd;  a.genome[1] = move_spd; a.genome[2] = float(hp_val)
            a.genome[3] = fire_mul; a.genome[4] = proj_spd; a.genome[5] = spr_scale

        a.reset(
            340, sy,
            random.randint(0, 320), random.randint(0, 240),
            tx, sy + random.randint(-80, 80),
            spd,
            is_seeker,
            is_boss=is_elite,
            move_speed=move_spd,
            hp=hp_val,
            fire_rate_mul=fire_mul,
            proj_speed=proj_spd,
            spread_scale=spr_scale,
            a_type=0
        )

    def spawn_boss_swarm(self):
        """Spawn 16 boss aliens in a perfect contracting ring centered at screenspace center."""
        self.score += 500  # Extra life points for the boss fight
        self.ship.x = 160  # Center for visibility
        cx, cy = 160, 120
        radius = 120
        count  = 16
        for i in range(count):
            a = ALIEN_POOL.get()
            if a is None:
                break
            angle = (2 * math.pi * i) / count
            sx = int(cx + math.cos(angle) * radius)
            sy = int(cy + math.sin(angle) * radius)
            # Store ring offset in p1x/p1y — Alien.update() uses these to maintain
            # angular formation during contraction (see ring_scale logic there).
            a.reset(
                sx, sy,
                float(sx - cx), float(sy - cy),  # p1x, p1y = ring offset
                0, 0,
                speed=1,
                target=self.ship,
                is_boss=True,
                move_speed=3.8,
                hp=4,
                a_type=0
            )

    def fire_laser(self, x, y, vx=12, vy=0, is_up=False):
        l = LASER_POOL.get()
        if l is not None:
            l.reset(x, y, vx, vy, is_up)

    @micropython.native
    def get_nearest_alien(self, sx, sy):
        best_a = None
        min_d2 = 999999.0
        # Cache alien pool locally for faster iteration
        for a in ALIEN_POOL._pool:
            if a.active:
                dx = a.x - sx
                dy = a.y - sy
                d2 = dx*dx + dy*dy
                if d2 < min_d2:
                    min_d2 = d2
                    best_a = a
        return best_a

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
    @micropython.native
    def _handle_input(self, t, danger, trouble):
        """Read joypad, set ship aim/mode flags, run ship.update().
        Returns (joypad_active, jp_fire_right, jp_super_fire)."""
        ship = self.ship; joypad = self.joypad
        joypad_active = False; jp_fire = False; jp_super = False

        if joypad is not None:
            try:
                _btn = joypad.read_buttons()
                joypad_active = True
                if _btn['L']: ship.x -= 4
                if _btn['R']: ship.x += 4
                if _btn['U']: ship.y -= 4
                if _btn['D']: ship.y += 4
                ship.aim_up = _btn['X'] or _btn['Y'] or danger
                jp_fire  = _btn['A'] or _btn['+']
                jp_super = _btn['B'] or _btn['-']
            except Exception:
                joypad_active = False

        if not joypad_active:
            if self.boss_active:
                # During boss fight keep firing horizontally — only rotate up for nuke opportunity
                ship.aim_up = self.score < 40 and not self.nuke_used
            else:
                ship.aim_up = trouble or danger

        ship.boss_mode  = self.boss_active
        ship.nuke_ready = danger
        ship.update(t)
        self.ship_vx = ship.x + ship.ox
        self.ship_vy = ship.y + ship.oy
        return joypad_active, jp_fire, jp_super

    # -----------------------------------------------------------------------
    def _update_autopilot(self, joypad_active, danger, trouble, is_horde, ship_x, ship_y, near_a):
        """Autonomous ship movement when no joypad is active."""
        if joypad_active:
            return
        ship = self.ship
        if ship.aim_up:
            tx = ship.x
            if danger:
                tx, _ = self.env.get_celestial_coords(self.t)
            elif trouble:
                tx = self.env.get_nearest_cloud_x(ship.x, self.t)
            if tx is not None and abs(ship.x - tx) > 3:
                ship.x += 4 if ship.x < tx else -4
        else:
            home_x = 160 if self.boss_active or is_horde else 45
            if near_a and (self.boss_active or is_horde):
                adx = ship_x - near_a.x; ady = ship_y - near_a.y
                dist_sq = adx*adx + ady*ady
                if dist_sq < 4225:  # 65px danger radius — evasion
                    dist = math.sqrt(dist_sq)
                    if dist > 0:
                        vx = (adx / dist) * 6; vy = (ady / dist) * 5
                        if (ship.x <= 20 or ship.x >= 300) and abs(vx) > 1:
                            ship.y += 5 if ady > 0 else -5
                        if (ship.y <= 40 or ship.y >= 200) and abs(vy) > 1:
                            ship.x += 6 if adx > 0 else -6
                        ship.x += vx; ship.y += vy
                else:
                    if abs(ship.x - home_x) > 2:
                        ship.x += 2 if ship.x < home_x else -2
                    # Drift y toward nearest alien (1px/frame) for better firing angle
                    if abs(ship.y - near_a.y) > 5:
                        ship.y += 1 if ship.y < near_a.y else -1
            else:
                if abs(ship.x - home_x) > 2:
                    ship.x += 2 if ship.x < home_x else -2
                # Drift y toward nearest alien (1px/frame) for better firing angle
                if near_a and abs(ship.y - near_a.y) > 5:
                    ship.y += 1 if ship.y < near_a.y else -1
        ship.x = max(20, min(300, ship.x))
        ship.y = max(40, min(200, ship.y))

    def _handle_spawning(self, alien_pool):
        """Alien/rain spawning and boss fight lifecycle."""
        if not self.boss_active:
            # Chaos Wave Trigger: every 400 points
            if self.score > 0 and self.score % 400 == 0 and not self.chaos_wave_active:
                self.chaos_wave_active = True
                # Alternates between Lorenz (1) and Rossler (2)
                a_type = 1 if (self.score // 400) % 2 == 1 else 2
                label = "Lorenz Wave" if a_type == 1 else "Rossler Wave"
                self.chaos_tracker = _chaos.LyapunovTracker(label)
                a1, a2 = _chaos.spawn_chaos_twins(ALIEN_POOL, a_type, 160, 120)
                if a1:
                    self.chaos_twins = (a1, a2)
                    self.chaos_tracker.start(a1, a2)

            if self.chaos_wave_active:
                # Check if chaotic aliens are still around
                still_chaos = False
                for a in alien_pool:
                    if a.active and a.a_type > 0:
                        still_chaos = True; break
                if not still_chaos:
                    self.chaos_wave_active = False
                    self.chaos_twins = (None, None)
                    self._lambda_str = ""

            threshold = max(0.70, 0.94 - ((self.score - 300) * 0.0004)) if self.score > 300 else 0.94
            if random.random() > threshold:
                self.spawn_alien()

        cloud_count = self.env.get_all_cloud_x(self.t)
        if random.random() < cloud_count * 0.16:
            _rain_spawn(cloud_count, self.env._cloud_x_buf)

        if not self.boss_active and self.score >= self.boss_next_threshold and self.boss_defeat_timer == 0:
            self.boss_active = True
            self.spawn_boss_swarm()

        if self.boss_active:
            if not any(a.active and a.is_boss for a in alien_pool):
                self.boss_active = False
                self.score += 50
                self.boss_next_threshold = self.score + 1000
                self.boss_defeat_timer = 180
                self._unlock_ach('boss_slayer')
                gc.collect()

        if self.boss_defeat_timer > 0:
            self.boss_defeat_timer -= 1

    # -----------------------------------------------------------------------
    def _set_ambient_tone(self):
        """Buzzer tone when not firing, driven by active event timers."""
        b = self.buzzer
        if   self.nuke_anim_timer > 0: b.set_tone(random.randint(50, 150))
        elif self.impact_timer > 0:    b.set_tone(random.randint(50, 250))
        elif self.explode_timer > 0:   b.set_tone(random.randint(2000, 3000))
        else:                          b.set_tone(0)

    @micropython.native
    def _compute_fire(self, fire_threshold, joypad_active, jp_btn, target_a, triggered_by_halo):
        """Returns (should_fire, firing_up, firing_side) given mode-specific inputs."""
        ship = self.ship
        if joypad_active:
            firing_up   = ship.aim_up and jp_btn and ship.fire_cooldown == 0
            firing_side = not ship.aim_up and jp_btn and ship.fire_cooldown == 0
            should_fire = firing_up or firing_side
        else:
            should_fire = (random.random() > fire_threshold or triggered_by_halo or (target_a and not ship.aim_up)) and ship.fire_cooldown == 0
            firing_up   = should_fire and ship.aim_up
            firing_side = should_fire and not ship.aim_up
        return should_fire, firing_up, firing_side

    @micropython.native
    def _handle_firing(self, ship_x, ship_y, alien_count, is_horde,
                        joypad_active, jp_fire, jp_super, danger, near_a):
        """Player firing (hero + standard modes) and alien return fire."""
        ship = self.ship; env = self.env; buzzer = self.buzzer

        # Night halo intrusion — auto-fire trigger
        triggered_by_halo = False
        if env.is_night:
            for a in ALIEN_POOL.active_objects():
                adx = a.x - ship_x; ady = a.y - ship_y
                if adx*adx + ady*ady < 1764:
                    triggered_by_halo = True; break

        house_count       = env.house_count
        is_danger         = self.score <= 50
        fire_rate_penalty = (12 - house_count) * 0.015
        miss_factor       = (12 - house_count) * 0.35

        if self.boss_active or is_horde or (joypad_active and jp_super):
            # ---- HERO MODE ----
            fire_threshold = max(0.20, 0.60 - alien_count * 0.02 + fire_rate_penalty)
            if ship.aim_up: fire_threshold = 0.15
            target_a = near_a
            should_fire, firing_up, firing_side = self._compute_fire(
                fire_threshold, joypad_active, jp_fire or jp_super, target_a, triggered_by_halo)
            if (ship.aim_up or alien_count > 0) and should_fire:
                sx, sy = ship_x, ship_y
                if firing_up:
                    cx, cy = env.get_celestial_coords(self.t)
                    # Hero 7-way cloud fire — fractal golden-ratio X offsets
                    for xi in _CLOUD_OFFSETS:
                        self.fire_laser(sx + xi, sy - 10, vx=0, vy=-12, is_up=True)
                    if danger:
                        vx = float(cx - sx) * -12.0 / (cy - sy) if cy != sy else 0
                        self.fire_laser(sx, sy - 10, vx=vx, vy=-12, is_up=True)
                else:
                    dv = (random.random() - 0.5) * miss_factor
                    # Compute base fire direction — track nearest alien, clamp to ±60°
                    cvx, cvy = 14.0, dv
                    if target_a:
                        tdx = target_a.x - ship_x; tdy = target_a.y - ship_y
                        ca = math.atan2(tdy, tdx)
                        ca = max(-1.0472, min(1.0472, ca))
                        cvx = 14.0 * math.cos(ca); cvy = 14.0 * math.sin(ca)
                    # Hero 7-way fractal spread — rotate base direction by each
                    # pre-computed golden-ratio angle (depth-2 binary tree)
                    for cs in _HERO_SPREAD:
                        rvx = cs[0] * cvx - cs[1] * cvy
                        rvy = cs[1] * cvx + cs[0] * cvy
                        self.fire_laser(sx + 10, sy, vx=rvx, vy=rvy)
                ship.recoil = 5
                ship.fire_cooldown = 2 if not firing_up else 3
                buzzer.set_tone(1800)
            else:
                self._set_ambient_tone()
        else:
            # ---- STANDARD MODE ----
            base_threshold = 0.75 if is_danger else 0.90
            fire_threshold = max(0.50, base_threshold - alien_count * 0.02 + fire_rate_penalty)
            if ship.aim_up: fire_threshold = 0.40
            target_a = near_a
            should_fire, firing_up, firing_side = self._compute_fire(
                fire_threshold, joypad_active, jp_fire, target_a, triggered_by_halo)
            if (ship.aim_up or alien_count > 0) and should_fire:
                ship.fire_cooldown = 4
                dv = (random.random() - 0.5) * miss_factor
                if firing_up:
                    sx, sy = ship_x, ship_y
                    # Standard 3-way cloud fire — fractal level-1 X offsets (-28, 0, +28)
                    for xi in _CLOUD_OFFSETS_3:
                        self.fire_laser(sx + xi, sy - 10, vx=0, vy=-12, is_up=True)
                    if danger:
                        cx, cy = env.get_celestial_coords(self.t)
                        vxd = float(cx - sx) * -12.0 / (cy - sy) if cy != sy else 0
                        self.fire_laser(sx, sy - 10, vx=vxd, vy=-12, is_up=True)
                else:
                    vx0 = 12.0; vy0 = dv
                    if target_a:
                        tdx = target_a.x - ship_x; tdy = target_a.y - ship_y
                        angle = math.atan2(tdy, tdx)
                        limit = 1.0472
                        angle = max(-limit, min(limit, angle))
                        vx0 = 12.0 * math.cos(angle); vy0 = 12.0 * math.sin(angle)
                    # 3-way fractal spread in danger, single centre shot otherwise
                    spread = _ENEMY_SPREAD if is_danger else _STD_SINGLE
                    for cs in spread:
                        rvx = cs[0] * vx0 - cs[1] * vy0
                        rvy = cs[1] * vx0 + cs[0] * vy0
                        self.fire_laser(ship_x + 10, ship_y, vx=rvx, vy=rvy)
                ship.recoil = 5
                buzzer.set_tone(1500 if is_danger else 1200)
            else:
                self._set_ambient_tone()

        # Alien return fire — enemies only; allies fire via _handle_ally_fire()
        # Each non-boss fires a 3-way fractal spread toward the ship;
        # bosses keep single aimed shots to limit pool pressure.
        for a in ALIEN_POOL.active_objects():
            if a.is_ally: continue
            prob = 0.12 if a.is_boss else 0.005
            prob = prob * a.fire_rate_mul          # genetic trait modulates rate
            if a.target:
                dx = a.x - ship_x; dy = a.y - ship_y
                prob = prob * (3.0 if dx*dx + dy*dy < 22500 else 1.5)
            if random.random() < prob:
                if a.is_boss:
                    el = ENEMY_LASER_POOL.get()
                    if el is not None:
                        el.reset(int(a.x) - 8, int(a.y),
                                 vx=-a.proj_speed, vy=0, is_ally=False)
                else:
                    # 3-way fractal spread — rotate toward-ship vector by fractal angles
                    tdx = ship_x - a.x; tdy = ship_y - a.y
                    if tdx*tdx + tdy*tdy > 1.0:
                        fa  = math.atan2(tdy, tdx)
                        cfa = math.cos(fa); sfa = math.sin(fa)
                        spd = a.proj_speed
                        for cs in _ENEMY_SPREAD:
                            rvx = spd * (cs[0] * cfa - cs[1] * sfa)
                            rvy = spd * (cs[0] * sfa + cs[1] * cfa)
                            el  = ENEMY_LASER_POOL.get()
                            if el is not None:
                                el.reset(int(a.x), int(a.y),
                                         vx=rvx, vy=rvy, is_ally=False)

    # -----------------------------------------------------------------------
    def _handle_ally_fire(self):
        """Allies fire a 3-way fractal spread toward their current nearest enemy."""
        for a in ALIEN_POOL.active_objects():
            if not a.is_ally: continue
            if a.target is None: continue
            if random.random() > 0.12 * a.fire_rate_mul: continue
            ax = a.x; ay = a.y
            tdx = a.target.x - ax; tdy = a.target.y - ay
            dist2 = tdx*tdx + tdy*tdy
            if dist2 < 1.0: continue
            fa  = math.atan2(tdy, tdx)
            cfa = math.cos(fa); sfa = math.sin(fa)
            spd = a.proj_speed
            for cs in _ENEMY_SPREAD:
                rvx = spd * (cs[0] * cfa - cs[1] * sfa)
                rvy = spd * (cs[0] * sfa + cs[1] * cfa)
                el  = ENEMY_LASER_POOL.get()
                if el is not None:
                    el.reset(int(ax), int(ay), vx=rvx, vy=rvy, is_ally=True)

    # -----------------------------------------------------------------------
    # v2 (2026-04-11): removed @micropython.native to support ally branching,
    # genetics fitness recording, and defection logic.
    def _update_collisions(self, ship_x, ship_y, alien_pool, laser_pool,
                           enemy_laser_pool, env, t, near_a=None):
        """Rain, enemy laser, player laser, and alien collision resolution.

        near_a — nearest non-ally enemy alien (passed from update()).
        Used to credit direct_hits when an enemy laser reaches the ship.
        """
        # ---- Rain ----
        for i in range(_RAIN_MAX):
            if _rain_live[i]:
                _rain_y[i] += _rain_spd[i]
                dx = _rain_x[i] - ship_x; dy = _rain_y[i] - ship_y
                if dx*dx + dy*dy < 144:
                    self.score = max(0, self.score - 1)
                    _rain_live[i] = False
                    self.spawn_particles(_rain_x[i], _rain_y[i], 2, is_water=True)
                    continue
                if env.check_house_damage(_rain_x[i], _rain_y[i], t):
                    _rain_live[i] = False
                    self.spawn_particles(_rain_x[i], _rain_y[i], 4, is_water=True)
                    continue
                if _rain_y[i] > 240:
                    self.spawn_particles(_rain_x[i], 240, random.randint(2, 4), is_water=True)
                    _rain_live[i] = False

        # ---- Enemy and ally lasers ----
        for el in enemy_laser_pool:
            if not el.active: continue
            el.update()
            if not el.active: continue
            if el.is_ally:
                # Ally laser — hits non-ally enemies only
                for a in alien_pool:
                    if not a.active or a.is_ally: continue
                    dx = el.x - a.x; dy = el.y - a.y
                    if dx*dx + dy*dy < 144:
                        a.hp -= 1
                        if a.hp <= 0:
                            _genetics.record_fitness(a.genome, a.survival_frames, a.direct_hits)
                            self.score += 15
                            a.active = False
                            self.spawn_particles(a.x, a.y, 8)
                        el.active = False; break
            else:
                # Enemy laser — hits ship
                dx = el.x - ship_x; dy = el.y - ship_y
                if dx*dx + dy*dy < 225:
                    self.score = max(0, self.score - max(5, self.score // 10))
                    self.impact_timer = 10
                    self.spawn_particles(ship_x, ship_y, 6)
                    el.active = False
                    # Approximate damage credit to the nearest active enemy alien
                    if near_a is not None and not near_a.is_ally:
                        near_a.direct_hits = near_a.direct_hits + 1
                    if self.score <= 0:
                        self.game_over = True; self.pause_timer = 150
                        self._music.play(_music.GAME_OVER)

        # ---- Player lasers ----
        for l in laser_pool:
            if not l.active: continue
            l.update()
            if not l.active: continue
            lx = l.x; ly = l.y
            if l.is_up:
                res = env.check_cloud_damage(lx, ly, t)
                if res:
                    self.score += 10; self.explode_timer = 2
                    self.spawn_particles(lx, ly, 4, is_water=True)
                    if res == 2:
                        self.cloud_revert_timer = 100
                        self._clouds_destroyed += 1
                        if self._clouds_destroyed >= 10:
                            self._unlock_ach('cloud_buster')
                    l.active = False; continue
                if (self.score < 40 or env.house_count < 6) and not self.nuke_used:
                    if env.check_celestial_damage(lx, ly, t):
                        self.score += 100; self.nuke_used = True; self.nuke_anim_timer = 60
                        self._unlock_ach('nuke_em')
                        for a in alien_pool: a.active = False
                        for el in enemy_laser_pool: el.active = False
                        env.clear_clouds()
                        l.active = False; continue
            for a in alien_pool:
                if not a.active: continue
                if a.is_ally: continue  # allies are never hit by player lasers
                dx = lx - a.x; dy = ly - a.y
                if dx*dx + dy*dy < 144:
                    self.score += 10; self.explode_timer = 5
                    self.spawn_particles(a.x, a.y, 8)
                    a.hp -= 1
                    if a.hp <= 0:
                        _genetics.record_fitness(a.genome, a.survival_frames, a.direct_hits)
                        self.score += 20 if a.is_boss else 10
                        a.active = False
                        self._aliens_killed += 1
                        if self._aliens_killed == 1:
                            self._unlock_ach('first_blood')
                    l.active = False; break

        # ---- Alien movement + defection + collision ----
        # Count current allies so we can cap defection at 6 concurrent allies.
        ally_count = 0
        for x in alien_pool:
            if x.active and x.is_ally:
                ally_count += 1

        for a in alien_pool:
            if not a.active: continue

            # Defection: non-boss enemy may randomly switch sides (~0.4 % per second)
            if not a.is_ally and not a.is_boss and ally_count < 6:
                if random.random() < 0.0002:
                    a.is_ally  = True
                    a.target   = None   # retargeted each frame below
                    ally_count += 1

            # Ally: retarget to nearest non-ally enemy each frame for homing
            if a.is_ally:
                a.target = None
                best_d2  = 999999.0
                for b in alien_pool:
                    if b.active and not b.is_ally:
                        dx2 = b.x - a.x; dy2 = b.y - a.y
                        d2  = dx2*dx2 + dy2*dy2
                        if d2 < best_d2:
                            best_d2 = d2; a.target = b

            a.update()
            if not a.active:
                # Alien timed-out naturally — record fitness for non-allies
                if not a.is_ally:
                    _genetics.record_fitness(a.genome, a.survival_frames, a.direct_hits)
                continue

            if a.is_ally:
                # Ally body-collision with an enemy alien — ram attack
                if a.target is not None:
                    dx = a.x - a.target.x; dy = a.y - a.target.y
                    if dx*dx + dy*dy < 100:
                        _genetics.record_fitness(a.target.genome,
                                                 a.target.survival_frames,
                                                 a.target.direct_hits)
                        self.score += 15
                        self.spawn_particles(a.target.x, a.target.y, 8)
                        a.target.active = False
                        a.active        = False   # ally consumed in collision
                continue   # allies never collide with the ship

            # Non-ally: ship collision
            dx = ship_x - a.x; dy = ship_y - a.y
            if dx*dx + dy*dy < 100:
                self.score -= 150 if self.boss_active else 50
                a.direct_hits += 1   # body-slam counts as damage dealt
                _genetics.record_fitness(a.genome, a.survival_frames, a.direct_hits)
                self._untouchable = False; self.impact_timer = 15
                self.spawn_particles(ship_x, ship_y, 20)
                a.active = False
                if self.score <= 0:
                    self.score = 0; self.game_over = True; self.pause_timer = 150
                    self._music.play(_music.GAME_OVER)

    # -----------------------------------------------------------------------
    @micropython.native
    def update(self):
        self.t = self.t + 1
        t = self.t
        alien_pool       = ALIEN_POOL._pool
        laser_pool       = LASER_POOL._pool
        enemy_laser_pool = ENEMY_LASER_POOL._pool

        # Throttled RTC check — only call time.localtime() rarely
        self.time_check_counter = self.time_check_counter + 1
        if self.time_check_counter > 500:
            self.time_check_counter = 0
            now = time.localtime()
            if now[3] != self.last_hour_checked and now[4] == 0:
                self.pause_timer = 250
                self.score += 100
                self.last_hour_checked = now[3]
                if self.env.is_night:
                    self._unlock_ach('night_owl')
                if self.score > self.high_score:
                    self.high_score = self.score
                    with open("highscore.txt", "w") as f:
                        f.write(str(self.score))

        if self.in_intro:
            presto = self.presto; joypad = self.joypad
            presto.touch.poll()
            if presto.touch.state:
                self.in_intro = False; self._music.stop()
                self._update_leds(); return
            if joypad:
                try:
                    for b in joypad.read_buttons().values():
                        if b: self.in_intro = False; self._music.stop()
                        self._update_leds(); return
                except: pass
            self._update_leds(); return

        if self.pause_timer > 0:
            self._update_leds(); return

        # Decrement global timers
        if self.cloud_revert_timer > 0: self.cloud_revert_timer -= 1
        if self.impact_timer > 0:       self.impact_timer -= 1
        if self.explode_timer > 0:      self.explode_timer -= 1
        if self.nuke_anim_timer > 0:    self.nuke_anim_timer -= 1

        self.env.update(t % (self.PHASE_LEN * 4), self.PHASE_LEN)
        trouble = self.env.house_count < 6 and self.env.cloud_count > 0 and self.cloud_revert_timer == 0
        danger  = (self.score < 40 or self.env.house_count < 6) and not self.nuke_used

        joypad_active, jp_fire, jp_super = self._handle_input(t, danger, trouble)
        ship_x, ship_y = self.ship_vx, self.ship_vy

        # Count active enemy aliens + find nearest non-ally for targeting.
        # Allies are excluded from alien_count and near_a so they don't
        # inflate horde thresholds or attract the player's auto-aim.
        alien_count = 0; near_a = None; min_d2 = 999999.0
        for a in alien_pool:
            if a.active and not a.is_ally:
                alien_count += 1
                dx = a.x - ship_x; dy = a.y - ship_y
                d2 = dx*dx + dy*dy
                if d2 < min_d2: min_d2 = d2; near_a = a
        is_horde = alien_count > 10

        self._update_autopilot(joypad_active, danger, trouble, is_horde, ship_x, ship_y, near_a)
        self._handle_spawning(alien_pool)
        
        # Lyapunov / Chaos Tracking
        if self.chaos_wave_active and self.chaos_twins[0]:
            l_val = self.chaos_tracker.update(self.chaos_twins[0], self.chaos_twins[1])
            if l_val is not None:
                self._lambda_str = f"LAMBDA: {l_val:.3f}"
                if t % 60 == 0: self.chaos_tracker.log_result(l_val)
        
        # Chaos Trails
        for a in alien_pool:
            if a.active and a.a_type > 0 and t % 3 == 0:
                p = PARTICLE_POOL.get()
                if p: p.reset(a.x, a.y, False)
        
        self._handle_firing(ship_x, ship_y, alien_count, is_horde, joypad_active, jp_fire, jp_super, danger, near_a)
        self._handle_ally_fire()
        self._update_collisions(ship_x, ship_y, alien_pool, laser_pool, enemy_laser_pool, self.env, t, near_a)

        for p in PARTICLE_POOL._pool:
            if p.active: p.update()

        # Budgeted GC
        self._gc_countdown -= 1
        if self._gc_countdown <= 0:
            free = gc.mem_free()
            if free < 20000:
                gc.collect(); self._gc_countdown = 60
            else:
                self._gc_countdown = 300

        # Achievement score milestones
        s = self.score
        if s >= 500 and self._untouchable:  self._unlock_ach('untouchable')
        if s >= 1000:
            self._unlock_ach('centurion')
            if self.env.house_count == 12:  self._unlock_ach('village_guardian')
        if s >= 2000:                        self._unlock_ach('legendary')
        if self.ach_notify_timer > 0:        self.ach_notify_timer -= 1
        self._update_leds()

    # -----------------------------------------------------------------------
    def _update_leds(self):
        """Drive the 7 ambient LEDs to reflect game state (priority order)."""
        p = self.presto
        t = self.t

        if self.game_over and self.pause_timer > 0:
            # 1. SHIP DESTROYED: hard red flash alternating with off
            on = (t // 4) % 2 == 0
            v = 255 if on else 0
            for i in range(7):
                p.set_led_rgb(i, v, 0, 0)

        elif self.nuke_anim_timer > 0:
            # 2. NUKE FIRED: white flash with slow fade (timer: 60→0)
            bri = min(255, self.nuke_anim_timer * 2)
            for i in range(7):
                p.set_led_rgb(i, bri, bri, bri)

        elif self.impact_timer > 0:
            # 3. SHIP HIT: orange flash with smoother fade (timer: 15→0)
            bri = min(255, self.impact_timer * 10)
            for i in range(7):
                p.set_led_rgb(i, bri, bri // 3, 0)

        elif self.boss_active:
            # 4. BOSS FIGHT: red wave + per-LED sine flicker
            for i in range(7):
                wave = max(0, 180 - ((t + i * 8) % 40) * 5)
                flicker = int(abs(math.sin((t + i * 31) * 0.18)) * 60)
                bri = min(255, wave + flicker)
                p.set_led_rgb(i, bri, 0, 0)

        elif self.explode_timer > 0:
            # 5. EXPLOSION: brief orange burst
            bri = min(255, self.explode_timer * 40)
            for i in range(7):
                p.set_led_rgb(i, bri, bri // 4, 0)

        elif self.pause_timer > 0:
            # 6. HOURLY VICTORY: warm gold pulse
            brightness = min(255, self.pause_timer)
            flash = (t // 6) % 2 == 0
            r = brightness if flash else brightness // 3
            g = brightness // 2 if flash else brightness // 8
            for i in range(7):
                p.set_led_rgb(i, r, g, 0)

        elif self.env.is_night:
            # 7. NIGHT STARFIELD: each LED twinkles independently
            for i in range(7):
                phase = (t + i * 17) % 31
                if phase < 4:
                    bri = (4 - phase) * 60
                    p.set_led_rgb(i, bri, bri, bri)
                else:
                    p.set_led_rgb(i, 0, 0, 0)

        else:
            # 8. DAYTIME: score-based ambient glow (green=safe → red=danger)
            s = self.score
            if s >= 300:
                r, g, b = 0, 50, 20       # safe: subtle green
            elif s <= 100:
                r, g, b = 50, 0, 0        # danger: red warning
            else:
                frac = (s - 100) / 200    # 0.0=danger, 1.0=safe
                r = int(50 * (1.0 - frac))
                g = int(50 * frac)
                b = int(10 * frac)
            # Slow gentle pulse (no allocations)
            pulse = t % 60
            mul = 1 + (pulse if pulse < 30 else 60 - pulse) // 15  # 1..3
            for i in range(7):
                p.set_led_rgb(i, min(255, r * mul), min(255, g * mul), min(255, b * mul))

    # -----------------------------------------------------------------------
    @micropython.native
    def draw(self):
        d = self.display; env = self.env; ship = self.ship; t = self.t
        ship_vx, ship_vy = self.ship_vx, self.ship_vy

        # Layer 0 (Background)
        env.draw_layer0(t)

        # Layer 1 (Entities)
        d.set_layer(1)
        d.set_pen(self.pen_black)
        d.clear()

        # Night-time: spotlight + dimming (tracks visual ship position)
        if env.is_night:
            fast_dimmer(d, self.pen_night_dim)
            d.set_pen(self.pen_halo)
            d.circle(int(ship_vx), int(ship_vy), 42)
            d.set_pen(self.pen_black)
            d.circle(int(ship_vx), int(ship_vy), 40)

        # Rain
        d.set_pen(self.pen_rain)
        for i in range(_RAIN_MAX):
            if _rain_live[i]:
                ry = _rain_y[i]
                d.line(_rain_x[i], ry, _rain_x[i], ry + _rain_spd[i])

        # Lasers
        for l in LASER_POOL._pool:
            if l.active:
                l.draw(d, self.pen_up_laser if l.is_up else self.pen_laser)

        # Enemy/ally lasers — ally shots drawn in cyan to distinguish them
        for el in ENEMY_LASER_POOL._pool:
            if el.active:
                el.draw(d, self.pen_ally_glow if el.is_ally else self.pen_enemy_laser)

        # Particles
        for p in PARTICLE_POOL._pool:
            if p.active:
                p.draw(d, self.pen_particle, self.pen_water)

        # Aliens: allies cyan, bosses red, normals green
        for a in ALIEN_POOL._pool:
            if a.active:
                if a.is_ally:
                    a.draw(d, self.pen_ally_body,       self.pen_ally_glow)
                elif a.is_boss:
                    a.draw(d, self.pen_boss_alien_body, self.pen_boss_alien_glow)
                else:
                    a.draw(d, self.pen_alien_body,      self.pen_alien_glow)

        ship.draw(env.is_night, t)

        # HUD - Only regenerate strings when score changes
        if self.score != self._last_score_drawn:
            self._score_str = f"SCORE: {self.score}"
            self._last_score_drawn = self.score
        if self.high_score != self._last_hi_drawn:
            self._hi_str = f"HI: {self.high_score}"
            self._last_hi_drawn = self.high_score
            
        self.draw_hud(self._score_str, 5, 5, 2)
        self.draw_hud(self._hi_str, 240, 5, 2)
        
        if self.chaos_wave_active and self._lambda_str:
            self.draw_hud(self._lambda_str, 5, 25, 1)

        if self.boss_active or self.boss_defeat_timer > 0:
            self._draw_boss_overlay(d)

        if self.pause_timer > 0:
            if self.game_over:
                self.draw_hud("GAME OVER", 90, 100, 3)
            else:
                self.draw_hud("HOURLY VICTORY!", 70, 100, 2)

        if self.in_intro:
            self._draw_intro_screen(d)

        # Achievement: persistent count (bottom-right HUD)
        ach_str = f'{len(self.achievements)}/{_ach.TOTAL}'
        d.set_pen(self.pen_shadow)
        d.text(ach_str, 297, 232, 320, 1)
        d.set_pen(self.pen_ach)
        d.text(ach_str, 295, 230, 320, 1)

        # Achievement: unlock notification banner (3-second fade)
        if self.ach_notify_timer > 0:
            d.set_pen(self.pen_shadow)
            d.text(self.ach_notify_text, 12, 222, 310, 1)
            d.set_pen(self.pen_ach)
            d.text(self.ach_notify_text, 10, 220, 310, 1)

        self.presto.update()

    def _draw_boss_overlay(self, d):
        """Boss fight and boss-defeated overlays."""
        if self.boss_active:
            if (self.t // 15) % 2 == 0:
                d.set_pen(self.pen_boss_border)
                d.line(0, 0,   319, 0)
                d.line(0, 239, 319, 239)
                d.line(0, 0,   0,   239)
                d.line(319, 0, 319, 239)
            d.set_pen(self.pen_boss_shadow)
            d.text("BOSS FIGHT!", 87, 27, 320, 2)
            d.set_pen(self.pen_boss_hud)
            d.text("BOSS FIGHT!", 85, 25, 320, 2)
            boss_left = sum(1 for a in ALIEN_POOL.active_objects() if a.is_boss)
            d.set_pen(self.pen_boss_shadow)
            d.text(f"x{boss_left}", 162, 47, 320, 2)
            d.set_pen(self.pen_boss_hud)
            d.text(f"x{boss_left}", 160, 45, 320, 2)
        if self.boss_defeat_timer > 0:
            d.set_pen(self.pen_boss_shadow)
            d.text("BOSS DEFEATED! +50", 47, 107, 320, 2)
            d.set_pen(self.pen_boss_hud)
            d.text("BOSS DEFEATED! +50", 45, 105, 320, 2)

    def _draw_intro_screen(self, d):
        """Full intro/title screen overlay."""
        fast_dimmer(d, self.pen_boss_shadow)
        d.set_pen(self.pen_hud)
        d.text("DAN DARE: PROCTOR OF THE VILLAGE", 10, 20, 320, 2)
        d.set_pen(self.pen_alien_glow)
        d.text("MISSION: Protect houses from Acid Rain & Aliens", 10, 45, 300, 2)
        d.set_pen(self.pen_up_laser)
        if self.joypad:
            d.text("JOYPAD DETECTED - MANUAL MODE:", 10, 75, 300, 2)
            d.set_pen(self.pen_water)
            d.text("D-PAD : Move Ship", 20, 95, 300, 1)
            d.text("A / + : Standard Fire", 20, 110, 300, 1)
            d.text("B / - : SUPER FIRE (7-WAY)", 20, 125, 300, 1)
            d.text("X / Y : AIM UP (Clear Clouds)", 20, 140, 300, 1)
        else:
            d.text("NO JOYPAD - AUTOPILOT ACTIVE", 10, 75, 300, 2)
            d.set_pen(self.pen_water)
            d.text("Ship will defend the village automatically.", 20, 95, 300, 1)
        d.set_pen(self.pen_particle)
        d.text("PRO-TIPS:", 10, 165, 300, 2)
        d.set_pen(self.pen_water)
        d.text("- Shoot CLOUDS to stop toxic rain", 20, 185, 300, 1)
        d.text("- Shoot SUN/MOON for NUKE screen-wipe", 20, 200, 300, 1)
        d.text("- Alien +10 pts | Hit -50 pts", 20, 215, 300, 1)
        d.set_pen(self.pen_boss_hud)
        if (self.t // 15) % 2 == 0:
            d.text("TOUCH SCREEN OR PRESS BUTTON TO START", 15, 227, 300, 1)

    # -----------------------------------------------------------------------
    def run(self):
        while True:
            self.update()
            self.draw()
            self._music.advance()
            if self.pause_timer > 0:
                self.pause_timer -= 1
                if self.pause_timer == 0 and self.game_over:
                    self.reset()   # Soft restart, no hardware re-init
            time.sleep(0.02)


game = Game()
game.run()