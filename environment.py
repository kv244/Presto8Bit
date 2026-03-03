# Dan Dare: Modular Environment
# Optimized for high-performance memory management on RP2350
import random, math, time
from utils import get_asm_pen

class Environment:
    def __init__(self, display):
        self.display = display
        self.fractal_bg = [random.randint(70, 140) for _ in range(30)]
        self.fractal_fg = [random.randint(30, 70) for _ in range(20)]
        self.stars = [(random.randint(0, 320), random.randint(0, 240)) for _ in range(20)]
        # Clouds: [x, y, speed, rgb_tuple, health]
        self.clouds = [[
            random.randint(0, 320), random.randint(20, 50), random.uniform(0.2, 0.4),
            (random.randint(140, 180), random.randint(190, 230), 255), 3
        ] for _ in range(5)]
        # Houses: [x, width, height, health]
        self.houses = [[random.randint(0, 319), random.randint(10, 25), random.randint(15, 40), random.randint(3, 7)] for _ in range(12)]
        
        self._cloud_x_buf = [0] * 5  # Pre-allocated buffer to avoid per-frame list churn

        self.DAY_SKY    = (245, 245, 250)
        self.SUNSET_SKY = (255, 100, 50)
        self.NIGHT_SKY  = (5, 5, 25)

        self.trans    = 0
        self.is_night = False
        self.sky_p    = 0

        # Pre-cache static pens that would otherwise be recreated every draw
        d = display
        self.pen_star   = d.create_pen(255, 255, 255)
        self.pen_moon   = d.create_pen(180, 160, 100)
        self.pen_sun_o  = d.create_pen(255, 140, 0)
        self.pen_sun_i  = d.create_pen(255, 200, 0)
        # Cloud pens — one per cloud (randomised at init, unchanging)
        self.cloud_pens = [d.create_pen(*c[3]) for c in self.clouds]
        # Window pens
        self.pen_win_day   = d.create_pen(160, 200, 250)
        self.pen_win_night = d.create_pen(255, 255, 150)

        # Pen cache for interpolated pens; invalidated when trans changes
        self._last_trans   = -1.0
        self._pen_bg       = 0
        self._pen_fg       = 0
        self._pen_house    = 0

    def update(self, cycle_timer, PHASE_LEN):
        # Rebuild interpolated pens only when trans actually changes
        # (quantise to 2 decimal places — 100 distinct values vs 50 fps = ~2s between rebuilds)
        tr = int(self.trans * 100)
        
        if cycle_timer < PHASE_LEN:
            new_trans, new_night = 0.0, False
            if tr != self._last_trans:
                self.sky_p = self.display.create_pen(*self.DAY_SKY)
        elif cycle_timer < PHASE_LEN * 2:
            lt = (cycle_timer - PHASE_LEN) / PHASE_LEN
            new_trans, new_night = lt, lt > 0.5
            if tr != self._last_trans:
                self.sky_p = (get_asm_pen(self.display, self.DAY_SKY, self.SUNSET_SKY, lt)
                              if lt < 0.5
                              else get_asm_pen(self.display, self.SUNSET_SKY, self.NIGHT_SKY, (lt-0.5)*2))
        elif cycle_timer < PHASE_LEN * 3:
            new_trans, new_night = 1.0, True
            if tr != self._last_trans:
                self.sky_p = self.display.create_pen(*self.NIGHT_SKY)
        else:
            lt = (cycle_timer - PHASE_LEN * 3) / PHASE_LEN
            new_trans, new_night = 1.0 - lt, lt < 0.5
            if tr != self._last_trans:
                self.sky_p = get_asm_pen(self.display, self.NIGHT_SKY, self.DAY_SKY, lt)
        
        self.trans, self.is_night = new_trans, new_night

        if tr != self._last_trans:
            self._last_trans = tr
            d = self.display
            self._pen_bg    = get_asm_pen(d, (180, 210, 255), (20, 15, 30),  self.trans)
            self._pen_fg    = get_asm_pen(d, (120, 160, 200), (5, 5, 15),    self.trans)
            self._pen_house = get_asm_pen(d, (90, 110, 130),  (10, 10, 15),  self.trans)

        # Respawn houses if they were destroyed by rain
        if len(self.houses) < 12 and random.random() > 0.99:
            # Spawn a new house "behind" the scrolling horizon
            scroll = (cycle_timer * 2) % 320
            # Put it at a position that will scroll in from the right
            new_x = (scroll + 320 + random.randint(0, 50)) % 320
            self.houses.append([new_x, random.randint(10, 25), random.randint(15, 40), random.randint(3, 7)])

        # Respawn clouds if they were destroyed
        if len(self.clouds) < 5 and random.random() > 0.995:
            self.clouds.append([
                random.randint(0, 320), random.randint(20, 50), random.uniform(0.2, 0.4),
                (random.randint(140, 180), random.randint(190, 230), 255), 3
            ])
            # Regenerate pens to match count (simple for now)
            new_c = self.clouds[-1]
            self.cloud_pens.append(self.display.create_pen(*new_c[3]))

    def draw_layer0(self, t):
        d = self.display
        d.set_layer(0)
        d.set_pen(self.sky_p)
        d.clear()

        # Celestial bodies
        if self.is_night:
            d.set_pen(self.pen_star)
            for s in self.stars:
                d.pixel((s[0] - t//2) % 320, s[1])
            d.set_pen(self.pen_moon)
            sx = int((320*0.7 - t*0.2) % 320)
            d.circle(sx, 50, 12)
        else:
            sun_y = 40 + int(self.trans * 70)
            sx = int((320 * 0.8 - t * 0.1) % 320)
            d.set_pen(self.pen_sun_o); d.circle(sx, sun_y, 26)
            d.set_pen(self.pen_sun_i); d.circle(sx, sun_y, 18)

        # Clouds (use cached per-cloud pens)
        for idx, c in enumerate(self.clouds):
            d.set_pen(self.cloud_pens[idx])
            cx = int((c[0] - t * c[2]) % 340) - 20
            cy = c[1]
            d.circle(cx, cy, 8)
            d.circle(cx + 8, cy - 4, 10)
            d.circle(cx + 16, cy, 8)

        # BG Ridge
        d.set_pen(self._pen_bg)
        step = 320 / (len(self.fractal_bg) - 1)
        for i in range(len(self.fractal_bg) - 1):
            x = (i * step - (t % 320))
            for ox in [0, 320]:
                px1 = int(x+ox);     py1 = 240 - self.fractal_bg[i]
                px2 = int(x+ox+step+1); py2 = 240 - self.fractal_bg[i+1]
                d.triangle(px1, py1, px2, py2, px1, 240)
                d.triangle(px2, py2, px2, 240, px1, 240)

        # FG Ridge (Parallax)
        d.set_pen(self._pen_fg)
        step_fg = 320 / (len(self.fractal_fg) - 1)
        for i in range(len(self.fractal_fg) - 1):
            x = (i * step_fg - ((t * 2) % 320))
            for ox in [0, 320]:
                px1 = int(x+ox);        py1 = 240 - self.fractal_fg[i]
                px2 = int(x+ox+step_fg+1); py2 = 240 - self.fractal_fg[i+1]
                d.triangle(px1, py1, px2, py2, px1, 240)
                d.triangle(px2, py2, px2, 240, px1, 240)

        # Ground Features (Houses)
        win_pen = self.pen_win_night if self.is_night else self.pen_win_day
        for h in self.houses:
            for ox in [0, 320]:
                hx = int(h[0] - ((t * 2) % 320) + ox)
                if -40 < hx < 340:
                    d.set_pen(self._pen_house)
                    d.rectangle(hx, 240 - h[2], h[1], h[2])
                    if h[1] >= 12 and h[2] >= 15:
                        d.set_pen(win_pen)
                        d.rectangle(hx + 3, 240 - h[2] + 4, 4, 5)
                        if h[1] >= 20:
                            d.rectangle(hx + 12, 240 - h[2] + 4, 4, 5)

    def check_house_damage(self, x, y, t):
        """Checks if a point (x, y) hit any house, accounting for scroll."""
        scroll = (t * 2) % 320
        # Iterate backwards to safely remove items while iterating
        for i in range(len(self.houses) - 1, -1, -1):
            h = self.houses[i]
            for ox in [-320, 0, 320]: # Check all wrap-around instances
                hx = h[0] - scroll + ox
                if hx < x < hx + h[1] and 240 - h[2] < y < 240:
                    h[3] -= 1 # damage health
                    if h[3] <= 0:
                        self.houses.pop(i)
                    return True
        return False

    def get_all_cloud_x(self, t):
        """Returns the number of clouds and populates their screen X into internal buffer."""
        # Using the list as a buffer to avoid per-frame allocation
        count = len(self.clouds)
        for i in range(count):
            c = self.clouds[i]
            # Ensure we don't return more than 5 (our usual max)
            if i >= 5: break
            self._cloud_x_buf[i] = int((c[0] - t * c[2]) % 340) - 20
        return count

    def get_nearest_cloud_x(self, ship_x, t):
        """Returns the X coordinate of the cloud horizontally closest to ship_x."""
        if not self.clouds: return None
        best_x = None
        min_dist = 9999
        for c in self.clouds:
            cx = int((c[0] - t * c[2]) % 340) - 20
            dist = abs(cx - ship_x)
            if dist < min_dist:
                min_dist = dist
                best_x = cx
        return best_x

    def check_cloud_damage(self, x, y, t):
        """Checks if a point (x, y) hit any cloud."""
        for i in range(len(self.clouds) - 1, -1, -1):
            c = self.clouds[i]
            cx = int((c[0] - t * c[2]) % 340) - 20
            cy = c[1]
            
            # Rough bounding box for the cloud cluster
            if cx - 10 < x < cx + 25 and cy - 10 < y < cy + 10:
                c[4] -= 1 # damage health
                if c[4] <= 0:
                    self.clouds.pop(i)
                    self.cloud_pens.pop(i)
                    return 2 # KILLED
                return 1 # HIT
        return 0 # MISS

    def get_celestial_coords(self, t):
        """Returns the current screen (x, y) for the sun or moon."""
        if self.is_night:
            mx = int((320 * 0.7 - t * 0.2) % 320)
            my = 50
            return (mx, my)
        else:
            sx = int((320 * 0.8 - t * 0.1) % 320)
            sy = 40 + int(self.trans * 70)
            return (sx, sy)

    def check_celestial_damage(self, x, y, t):
        """Checks if a point (x, y) hit the sun or moon."""
        if self.is_night:
            mx = int((320 * 0.7 - t * 0.2) % 320)
            my = 50
            dx = x - mx; dy = y - my
            return (dx*dx + dy*dy) < 144
        else:
            sx = int((320 * 0.8 - t * 0.1) % 320)
            sy = 40 + int(self.trans * 70)
            dx = x - sx; dy = y - sy
            return (dx*dx + dy*dy) < 676
        return False

import gc; gc.collect()