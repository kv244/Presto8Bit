# ICON joystick
# NAME Dan Dare
# DESC Parallax pilot of the future

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
print("   [OK] Utils loaded.")
print("-> Loading entities...")
gc.collect()
print(f"   [RAM] {gc.mem_free()} bytes free.")
from entities import ALIEN_POOL, LASER_POOL, PARTICLE_POOL, ENEMY_LASER_POOL
print("   [OK] Entities loaded.")
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
                 '_gc_countdown', '_cloud_eraser_offsets',
                 '_score_str', '_hi_str', '_last_score_drawn', '_last_hi_drawn')

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

        self._cloud_eraser_offsets = [-45, -30, -15, 0, 15, 30, 45]
        
        # Cache HUD strings to avoid per-frame heap churn
        self._score_str = ""
        self._hi_str    = ""
        self._last_score_drawn = -1
        self._last_hi_drawn    = -1
        
        self.reset()

    def reset(self):
        # Free old subsystem memory before allocating new ones
        gc.collect()
        # 2. Subsystems
        ALIEN_POOL.clear()
        LASER_POOL.clear()
        ENEMY_LASER_POOL.clear()
        PARTICLE_POOL.clear()
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
        
        # Elite alien chance: 15% chance to have 2HP (drawn in red like a mini-boss)
        is_elite = random.random() > 0.85
        a.reset(
            340, sy,
            random.randint(0, 320), random.randint(0, 240),
            tx, sy + random.randint(-80, 80),
            random.randint(2, 5),
            is_seeker,
            is_boss=is_elite,
            hp=2 if is_elite else 1
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
            a.reset(
                sx, sy, 0, 0, 0, 0,
                speed=1,          
                target=self.ship,
                is_boss=True,
                move_speed=3.8,    
                hp=4               
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
    def update(self):
        self.t = self.t + 1
        t = self.t

        # Throttled RTC check — only call time.localtime() rarely
        self.time_check_counter = self.time_check_counter + 1
        if self.time_check_counter > 500:
            self.time_check_counter = 0
            now = time.localtime()
            if now[3] != self.last_hour_checked and now[4] == 0:
                self.pause_timer = 250
                self.score += 100  # Bonus for survival!
                self.last_hour_checked = now[3]
                if self.score > self.high_score:
                    self.high_score = self.score
                    with open("highscore.txt", "w") as f:
                        f.write(str(self.score))

        if self.pause_timer > 0:
            return

        # Decrement all global timers
        if self.cloud_revert_timer > 0: self.cloud_revert_timer -= 1
        if self.impact_timer > 0:        self.impact_timer -= 1
        if self.explode_timer > 0:       self.explode_timer -= 1
        if self.nuke_anim_timer > 0:      self.nuke_anim_timer -= 1

        # Environment & ship
        self.env.update(self.t % (self.PHASE_LEN * 4), self.PHASE_LEN)
        has_clouds = len(self.env.clouds) > 0
        trouble = len(self.env.houses) < 6 and has_clouds and self.cloud_revert_timer == 0
        # CRITICAL: village almost gone OR score low
        is_critical = (self.score < 40 or len(self.env.houses) < 6)
        danger = is_critical and not self.nuke_used

        # ---- JOYPAD INPUT (overrides all autopilot when connected) ----
        joypad_active = False
        joypad_fire_right = False
        joypad_fire_up    = False
        joypad_super_fire = False
        if self.joypad is not None:
            try:
                _btn = self.joypad.read_buttons()
                joypad_active = True
                # Movement: 4 px per frame, clamped below
                if _btn['L']: self.ship.x -= 4
                if _btn['R']: self.ship.x += 4
                if _btn['U']: self.ship.y -= 4
                if _btn['D']: self.ship.y += 4
                
                # Manual Aim Control (X/Y strictly)
                _manual_aim_up_held = _btn['X'] or _btn['Y']
                self.ship.aim_up = _manual_aim_up_held or danger  # danger always forces aim_up
                
                # Fire Mapping
                joypad_fire_right = _btn['A'] or _btn['+']
                joypad_super_fire = _btn['B'] or _btn['-']
                joypad_fire_up    = self.ship.aim_up and (joypad_fire_right or joypad_super_fire)
            except Exception:
                # I2C hiccup — treat as no input this frame
                joypad_active = False

        if not joypad_active:
            # Ship aims up if village is in trouble or in danger
            # Boss fights normally override upward aiming UNLESS it's a critical danger
            if self.boss_active:
                self.ship.aim_up = danger
            else:
                self.ship.aim_up = trouble or danger

        self.ship.boss_mode = self.boss_active
        self.ship.nuke_ready = danger
        self.ship.update(self.t)
        # Visual ship position (for collisions, firing origin AND halo)
        self.ship_vx = self.ship.x + self.ship.ox
        self.ship_vy = self.ship.y + self.ship.oy
        ship_x, ship_y = self.ship_vx, self.ship_vy

        # ESCAPE/EVASION LOGIC: Pre-calculate counts/threats
        alien_count = 0
        for a in ALIEN_POOL._pool:
            if a.active: alien_count += 1
        is_horde = alien_count > 10
        near_a = self.get_nearest_alien(ship_x, ship_y)

        if not joypad_active:
            # ----- AUTOPILOT MOVEMENT -----
            # Autonomous movement while aiming up: Glide under the target
            if self.ship.aim_up:
                tx = self.ship.x
                if danger:
                    tx, _ = self.env.get_celestial_coords(self.t)
                elif trouble:
                    tx = self.env.get_nearest_cloud_x(self.ship.x, self.t)

                if tx is not None:
                    if abs(self.ship.x - tx) > 3:
                        self.ship.x += 4 if self.ship.x < tx else -4
            else:
                # Return to home position (left side, UNLESS in boss fight/horde)
                home_x = 160 if self.boss_active or is_horde else 45
                
                # ESCAPE PROTOCOL: If any alien is too close during swarm, move exactly opposite
                if near_a and (self.boss_active or is_horde):
                    adx, ady = ship_x - near_a.x, ship_y - near_a.y
                    dist_sq = adx*adx + ady*ady
                    if dist_sq < 4225: # Inside 65px: DANGER!
                        dist = math.sqrt(dist_sq)
                        if dist > 0:
                            # High-speed repulsion
                            vx, vy = (adx / dist) * 6, (ady / dist) * 5
                            
                            # ANTI-STUCK: If hitting a boundary, sidestep perpendicular to the threat
                            if (self.ship.x <= 20 or self.ship.x >= 300) and abs(vx) > 1:
                                # If pinned horizontally, burst vertically
                                self.ship.y += 5 if ady > 0 else -5
                            if (self.ship.y <= 40 or self.ship.y >= 200) and abs(vy) > 1:
                                # If pinned vertically, burst horizontally
                                self.ship.x += 6 if adx > 0 else -6
                                
                            self.ship.x += vx
                            self.ship.y += vy
                    else:
                        # No immediate death-spiral, return to home center
                        if abs(self.ship.x - home_x) > 2:
                            self.ship.x += 2 if self.ship.x < home_x else -2
                else:
                    # Regular drift to home
                    if abs(self.ship.x - home_x) > 2:
                        self.ship.x += 2 if self.ship.x < home_x else -2

        # FINAL CLAMP: Move this to the end so evasion isn't choppy
        self.ship.x = max(20, min(300, self.ship.x))
        self.ship.y = max(40, min(200, self.ship.y))

        # Spawning — suppressed during boss fight
        if not self.boss_active:
            spawn_threshold = 0.94
            if self.score > 300:
                spawn_threshold = max(0.70, 0.94 - ((self.score - 300) * 0.0004))
            if random.random() > spawn_threshold:
                self.spawn_alien()
        
        # Rain scales strictly with cloud count
        cloud_count = self.env.get_all_cloud_x(self.t)
        rain_chance = cloud_count * 0.16
        if random.random() < rain_chance:
            _rain_spawn(cloud_count, self.env._cloud_x_buf)

        # Boss fight trigger
        if (not self.boss_active and
                self.score >= self.boss_next_threshold and
                self.boss_defeat_timer == 0):
            self.boss_active = True
            self.spawn_boss_swarm()

        # Boss fight end check
        if self.boss_active:
            boss_alive = False
            for a in ALIEN_POOL._pool:
                if a.active and a.is_boss:
                    boss_alive = True
                    break
            if not boss_alive:
                self.boss_active = False
                self.score += 50                       # bonus for clearing the swarm
                self.boss_next_threshold = self.score + 1000 # Next boss much further away
                self.boss_defeat_timer = 180           # show "BOSS DEFEATED!" for ~3s
                gc.collect()                           # reclaim memory from the boss swarm

        # Boss defeat message countdown
        if self.boss_defeat_timer > 0:
            self.boss_defeat_timer -= 1

        # Firing — rate scales with aliens; and house count affects fire rate/accuracy
        # (alien_count already calculated for evasion above)

        # Halo intrusion check (automated defense fire at night)
        triggered_by_halo = False
        if self.env.is_night:
            for a in ALIEN_POOL.active_objects():
                if a.active:
                    adx = a.x - ship_x; ady = a.y - ship_y
                    if adx*adx + ady*ady < 1764: # 42px radius squared
                        triggered_by_halo = True
                        break

        house_count = len(self.env.houses)
        is_danger   = self.score <= 50
        
        # House-based modifiers: more houses = more/better fire
        fire_rate_penalty = (12 - house_count) * 0.015
        miss_factor = (12 - house_count) * 0.35

        is_horde = alien_count > 10
        if self.boss_active or is_horde or (joypad_active and joypad_super_fire):
            # HERO MODE: high frequency with cooldown if target present
            fire_threshold = max(0.20, 0.60 - alien_count * 0.02 + fire_rate_penalty)
            if self.ship.aim_up: fire_threshold = 0.15

            target_a = self.get_nearest_alien(ship_x, ship_y)
            # Joypad: fire buttons override probabilistic check
            if joypad_active:
                firing_up   = self.ship.aim_up and (joypad_fire_right or joypad_super_fire) and self.ship.fire_cooldown == 0
                firing_side = not self.ship.aim_up and (joypad_fire_right or joypad_super_fire) and self.ship.fire_cooldown == 0
                should_fire = firing_up or firing_side
            else:
                # Automatic fire is gated by the fire_cooldown for sustainability
                should_fire = (random.random() > fire_threshold or triggered_by_halo or (target_a and not self.ship.aim_up))
                should_fire = should_fire and (self.ship.fire_cooldown == 0)
                firing_up   = should_fire and self.ship.aim_up
                firing_side = should_fire and not self.ship.aim_up

            if (self.ship.aim_up or alien_count > 0) and should_fire:
                sx, sy = ship_x, ship_y
                self.ship.fire_cooldown = 3 # Cooldown of 3 frames (~15-20 shots/sec)
                # Each shot gets a small random deflection based on miss_factor
                deflect = lambda: (random.random() - 0.5) * miss_factor
                
                if firing_up:
                    # Cloud Eraser: Massive 7-way fan
                    # If in danger, one laser targets the celestial body (Sun/Moon)
                    cx, cy = self.env.get_celestial_coords(self.t)
                    for offset in self._cloud_eraser_offsets:
                        self.fire_laser(sx + offset, sy - 10, vx=0, vy=-12, is_up=True)
                    if danger:
                        # Seeker laser: targets celestial body X
                        vx = float(cx - sx) * -12.0 / (cy - sy) if cy != sy else 0
                        self.fire_laser(sx, sy - 10, vx=vx, vy=-12, is_up=True)
                else:
                    # MASSIVE FIREPOWER: 7-way spread, overlapping streams
                    deflect_val = (random.random() - 0.5) * miss_factor
                    self.fire_laser(sx + 10, sy,       vx=14, vy=deflect_val)   # centre
                    self.fire_laser(sx + 5,  sy - 12,  vx=13, vy=deflect_val-1) # up
                    self.fire_laser(sx + 5,  sy + 12,  vx=13, vy=deflect_val+1) # down
                    self.fire_laser(sx,      sy - 24,  vx=12, vy=deflect_val-2) # wide up
                    self.fire_laser(sx,      sy + 24,  vx=12, vy=deflect_val+2) # wide down
                    self.fire_laser(sx - 5,  sy - 36,  vx=11, vy=deflect_val-3) # extreme up
                    self.fire_laser(sx - 5,  sy + 36,  vx=11, vy=deflect_val+3) # extreme down
                
                self.ship.recoil = 5
                # Ultra fast cooldown for massive fire
                self.ship.fire_cooldown = 2 if not firing_up else 3
                self.buzzer.set_tone(1800)
            else:
                if self.nuke_anim_timer > 0:
                    self.buzzer.set_tone(random.randint(50, 150))
                elif self.impact_timer > 0:
                    self.buzzer.set_tone(random.randint(50, 250))
                elif self.explode_timer > 0:
                    self.buzzer.set_tone(random.randint(2000, 3000))
                else:
                    self.buzzer.set_tone(0)
        else:
            base_threshold = 0.75 if is_danger else 0.90
            fire_threshold = max(0.50, base_threshold - alien_count * 0.02 + fire_rate_penalty)
            if self.ship.aim_up: fire_threshold = 0.40

            target_a = self.get_nearest_alien(ship_x, ship_y)
            # Joypad: fire buttons override probabilistic check
            if joypad_active:
                firing_up   = self.ship.aim_up and joypad_fire_right and self.ship.fire_cooldown == 0
                firing_side = not self.ship.aim_up and joypad_fire_right and self.ship.fire_cooldown == 0
                should_fire = firing_up or firing_side
            else:
                should_fire = (random.random() > fire_threshold or triggered_by_halo or (target_a and not self.ship.aim_up))
                should_fire = should_fire and (self.ship.fire_cooldown == 0)
                firing_up   = should_fire and self.ship.aim_up
                firing_side = should_fire and not self.ship.aim_up

            if (self.ship.aim_up or alien_count > 0) and should_fire:
                self.ship.fire_cooldown = 4 # slightly slower in regular mode
                deflect_val = (random.random() - 0.5) * miss_factor
                if firing_up:
                    # Fire UP at clouds (Massive 3-way spread + optional seeker)
                    sx, sy = ship_x, ship_y
                    self.fire_laser(sx,      sy - 10, vx=0, vy=-12, is_up=True)
                    self.fire_laser(sx - 15, sy - 5,  vx=0, vy=-12, is_up=True)
                    self.fire_laser(sx + 15, sy - 5,  vx=0, vy=-12, is_up=True)
                    if danger:
                        cx, cy = self.env.get_celestial_coords(self.t)
                        vx = float(cx - sx) * -12.0 / (cy - sy) if cy != sy else 0
                        self.fire_laser(sx, sy - 10, vx=vx, vy=-12, is_up=True)
                else:
                    # Fire RIGHT at aliens with angular aiming (-60 to 60 deg)
                    target_a = self.get_nearest_alien(ship_x, ship_y)
                    vx, vy = 12, deflect_val
                    if target_a:
                        dx = target_a.x - ship_x
                        dy = target_a.y - ship_y
                        angle = math.atan2(dy, dx)
                        # Clamp to -60 to 60 degrees
                        limit = 60 * math.pi / 180
                        angle = max(-limit, min(limit, angle))
                        vx = 12 * math.cos(angle)
                        vy = 12 * math.sin(angle)
                    
                    self.fire_laser(ship_x + 10, ship_y, vx=vx, vy=vy)
                    if is_danger:
                        self.fire_laser(ship_x, ship_y - 15, vx=vx, vy=vy)
                        self.fire_laser(ship_x, ship_y + 15, vx=vx, vy=vy)
                self.ship.recoil = 5
                self.buzzer.set_tone(1500 if is_danger else 1200)
            else:
                if self.nuke_anim_timer > 0:
                    self.buzzer.set_tone(random.randint(50, 150))
                elif self.impact_timer > 0:
                    self.buzzer.set_tone(random.randint(50, 250))
                elif self.explode_timer > 0:
                    self.buzzer.set_tone(random.randint(2000, 3000))
                else:
                    self.buzzer.set_tone(0)

        # All aliens fire back — each active alien has a small frame chance
        for a in ALIEN_POOL.active_objects():
            if a.active:
                # Base probabilities: bosses fire much faster now
                prob = 0.12 if a.is_boss else 0.005
                
                # Homing aliens fire wildly as they approach
                if a.target:
                    dx = a.x - ship_x; dy = a.y - ship_y
                    dist_sq = dx*dx + dy*dy
                    # If within ~150px, triple the fire rate; otherwise 1.5x
                    prob *= 3.0 if dist_sq < 22500 else 1.5
                
                if random.random() < prob:
                    el = ENEMY_LASER_POOL.get()
                    if el is not None:
                        el.reset(int(a.x) - 8, int(a.y))

        # ---- Rain update (index-based, no object allocation) ----
        for i in range(_RAIN_MAX):
            if _rain_live[i]:
                _rain_y[i] += _rain_spd[i]
                
                # Ship collision check (penalty for getting wet!)
                dx = _rain_x[i] - ship_x
                dy = _rain_y[i] - ship_y
                if dx*dx + dy*dy < 144: # ~12px hit radius
                    self.score = max(0, self.score - 1)
                    _rain_live[i] = False
                    self.spawn_particles(_rain_x[i], _rain_y[i], 2, is_water=True)
                    continue
                
                # Check house damage from rain
                if self.env.check_house_damage(_rain_x[i], _rain_y[i], self.t):
                    _rain_live[i] = False
                    self.spawn_particles(_rain_x[i], _rain_y[i], 4, is_water=True)
                    continue

                if _rain_y[i] > 240:
                    self.spawn_particles(_rain_x[i], 240,
                                         random.randint(2, 4), is_water=True)
                    _rain_live[i] = False

        # ---- Enemy laser update + ship collision ----
        for el in ENEMY_LASER_POOL.active_objects():
            if not el.active:
                continue
            el.update()
            if not el.active:
                continue
            dx = el.x - ship_x; dy = el.y - ship_y
            if dx*dx + dy*dy < 225:          # ~15px hit radius
                penalty = max(5, self.score // 10)   # 10% of score, min 5
                self.score = max(0, self.score - penalty)
                self.impact_timer = 10
                self.spawn_particles(ship_x, ship_y, 6)
                el.active = False
                if self.score <= 0:
                    self.game_over = True
                    self.pause_timer = 150

        # ---- Laser update + collision ----
        for l in LASER_POOL.active_objects():
            if not l.active:
                continue
            l.update()
            if not l.active:
                continue
            lx = l.x; ly = l.y

            # Cloud/Celestial check (if firing up)
            if l.is_up:
                res = self.env.check_cloud_damage(lx, ly, self.t)
                if res:
                    self.score += 10 # Score for hitting/destroying cloud
                    self.explode_timer = 2
                    self.spawn_particles(lx, ly, 4, is_water=True)
                    if res == 2:
                        # CLOUD DESTROYED: trigger recovery window
                        self.cloud_revert_timer = 100
                    l.active = False
                    continue
                # NUKE CHECK: Shoot the sun/moon to wipe the screen
                if (self.score < 40 or len(self.env.houses) < 6) and not self.nuke_used:
                    if self.env.check_celestial_damage(lx, ly, self.t):
                        self.score += 100 # Huge bonus for nuclear trigger
                        print("Nuclear")
                        self.nuke_used = True
                        self.nuke_anim_timer = 60
                        # Clear everything
                        for a in ALIEN_POOL.active_objects(): a.active = False
                        for el in ENEMY_LASER_POOL.active_objects(): el.active = False
                        self.env.clouds = []
                        self.env.cloud_pens = []
                        l.active = False
                        continue
            
            for a in ALIEN_POOL.active_objects():
                if not a.active:
                    continue
                dx = lx - a.x; dy = ly - a.y
                if dx*dx + dy*dy < 144:
                    self.score += 10
                    self.explode_timer = 5
                    self.spawn_particles(a.x, a.y, 8)
                    a.hp -= 1
                    if a.hp <= 0:
                        self.score += 20 if a.is_boss else 10 # More points for elites/bosses
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
                penalty = 150 if self.boss_active else 50
                self.score -= penalty
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
    def _update_leds(self):
        """Drive the 7 ambient LEDs to reflect game state."""
        p = self.presto
        t = self.t

        if self.game_over and self.pause_timer > 0:
            # SHIP DESTROYED: hard red flash alternating with off
            on = (t // 4) % 2 == 0
            v = 255 if on else 0
            for i in range(7):
                p.set_led_rgb(i, v, 0, 0)

        elif self.pause_timer > 0:
            # HOURLY VICTORY: warm gold pulse (full brightness, fading)
            # pause_timer counts down from 250; use it to drive brightness
            brightness = min(255, self.pause_timer)
            flash = (t // 6) % 2 == 0
            r = brightness if flash else brightness // 3
            g = brightness // 2 if flash else brightness // 8
            for i in range(7):
                p.set_led_rgb(i, r, g, 0)

        elif self.env.is_night:
            # NIGHT STARFIELD: each LED twinkles independently
            # Uses a simple deterministic formula — no allocations
            for i in range(7):
                # Each LED has a different phase offset so they don't all sync
                phase = (t + i * 17) % 31
                if phase < 4:
                    # Brief bright white twinkle
                    bri = (4 - phase) * 60
                    p.set_led_rgb(i, bri, bri, bri)
                else:
                    p.set_led_rgb(i, 0, 0, 0)

        else:
            # Daytime / boss fight — LEDs off
            for i in range(7):
                p.set_led_rgb(i, 0, 0, 0)

    # -----------------------------------------------------------------------
    def draw(self):
        d = self.display

        # Layer 0 (Background)
        self.env.draw_layer0(self.t)

        # Layer 1 (Entities)
        d.set_layer(1)
        d.set_pen(self.pen_black)
        d.clear()

        # Night-time: spotlight + dimming (tracks visual ship position)
        if self.env.is_night:
            fast_dimmer(d, self.pen_night_dim)
            d.set_pen(self.pen_halo)
            d.circle(int(self.ship_vx), int(self.ship_vy), 42)
            d.set_pen(self.pen_black)
            d.circle(int(self.ship_vx), int(self.ship_vy), 40)

        # Rain
        d.set_pen(self.pen_rain)
        for i in range(_RAIN_MAX):
            if _rain_live[i]:
                ry = _rain_y[i]
                d.line(_rain_x[i], ry, _rain_x[i], ry + _rain_spd[i])

        # Lasers
        for l in LASER_POOL.active_objects():
            if l.active:
                l.draw(d, self.pen_up_laser if l.is_up else self.pen_laser)

        # Enemy lasers
        for el in ENEMY_LASER_POOL.active_objects():
            if el.active:
                el.draw(d, self.pen_enemy_laser)

        # Particles
        for p in PARTICLE_POOL.active_objects():
            if p.active:
                p.draw(d, self.pen_particle, self.pen_water)

        # Aliens (boss aliens drawn in red)
        for a in ALIEN_POOL.active_objects():
            if a.active:
                if a.is_boss:
                    a.draw(d, self.pen_boss_alien_body, self.pen_boss_alien_glow)
                else:
                    a.draw(d, self.pen_alien_body,      self.pen_alien_glow)

        self.ship.draw(self.env.is_night, self.t)

        # HUD - Only regenerate strings when score changes
        if self.score != self._last_score_drawn:
            self._score_str = f"SCORE: {self.score}"
            self._last_score_drawn = self.score
        if self.high_score != self._last_hi_drawn:
            self._hi_str = f"HI: {self.high_score}"
            self._last_hi_drawn = self.high_score
            
        self.draw_hud(self._score_str, 5, 5, 2)
        self.draw_hud(self._hi_str, 240, 5, 2)

        # Boss fight overlays
        if self.boss_active:
            # Flashing red border (flashes every 15 frames)
            if (self.t // 15) % 2 == 0:
                d.set_pen(self.pen_boss_border)
                d.line(0, 0,   319, 0)    # top
                d.line(0, 239, 319, 239)  # bottom
                d.line(0, 0,   0,   239)  # left
                d.line(319, 0, 319, 239)  # right
            # "BOSS FIGHT!" title
            d.set_pen(self.pen_boss_shadow)
            d.text("BOSS FIGHT!", 87, 27, 320, 2)
            d.set_pen(self.pen_boss_hud)
            d.text("BOSS FIGHT!", 85, 25, 320, 2)
            # Remaining boss count
            boss_left = 0
            for a in ALIEN_POOL._pool:
                if a.active and a.is_boss:
                    boss_left += 1
            d.set_pen(self.pen_boss_shadow)
            d.text(f"x{boss_left}", 162, 47, 320, 2)
            d.set_pen(self.pen_boss_hud)
            d.text(f"x{boss_left}", 160, 45, 320, 2)

        if self.boss_defeat_timer > 0:
            d.set_pen(self.pen_boss_shadow)
            d.text("BOSS DEFEATED! +50", 47, 107, 320, 2)
            d.set_pen(self.pen_boss_hud)
            d.text("BOSS DEFEATED! +50", 45, 105, 320, 2)

        if self.pause_timer > 0:
            if self.game_over:
                self.draw_hud("GAME OVER", 90, 100, 3)
            else:
                self.draw_hud("HOURLY VICTORY!", 70, 100, 2)

        self._update_leds()
        self.presto.update()

    # -----------------------------------------------------------------------
    def run(self):
        while True:
            self.update()
            self.draw()
            if self.pause_timer > 0:
                self.pause_timer -= 1
                if self.pause_timer == 0 and self.game_over:
                    self.reset()   # Soft restart, no hardware re-init
            time.sleep(0.02)


game = Game()
game.run()