# ICON deployed-code
# NAME Dan Dare
# DESC Parallax pilot of the future

from presto import Presto, Buzzer
from machine import Pin
import time, random, gc
from utils import fast_dimmer
from entities import Alien, Laser, Particle
from environment import Environment
from ship import Ship

class Game:
    def __init__(self):
        # 1. Hardware & Engine Setup
        self.presto = Presto(full_res=False, layers=2)
        self.display = self.presto.display
        self.buzzer = Buzzer(Pin(43))
        
        # 2. Subsystems
        self.env = Environment(self.display)
        self.ship = Ship(self.display)
        
        # 3. State Management
        self.aliens = []
        self.lasers = []
        self.particles = []
        self.rain = []
        
        self.score = 50
        self.game_over = False
        self.t = 0
        self.PHASE_LEN = 1000
        self.pause_timer = 0
        self.time_check_counter = 0
        self.last_hour_checked = time.localtime()[3]
        
        # Load High Score (Persistence)
        try:
            with open("highscore.txt", "r") as f:
                self.high_score = int(f.read())
        except:
            self.high_score = 0

    def spawn_alien(self):
        sy = random.randint(40, 160)
        # Randomize target: Left escape or Right retreat
        tx = -50 if random.random() > 0.3 else 370
        is_seeker = self.ship if random.random() > 0.85 else None
        self.aliens.append(Alien(
            (340, sy), 
            (random.randint(0, 320), random.randint(0, 240)), 
            (tx, sy + random.randint(-80, 80)), 
            random.randint(2, 5),
            is_seeker
        ))

    def draw_hud(self, text, x, y, size, is_night):
        # Drop-Shadow Kernel for daytime/nighttime visibility
        # Shadow: Dark purple
        self.display.set_pen(self.display.create_pen(30, 0, 50))
        self.display.text(text, x + 2, y + 2, 320, size)
        
        # Main text: Vibrant Hot Pink
        self.display.set_pen(self.display.create_pen(255, 30, 180))
        self.display.text(text, x, y, 320, size)

    def update(self):
        self.t += 1
        now = time.localtime()
        
        # Throttled RTC Check for Victory Condition
        self.time_check_counter += 1
        if self.time_check_counter > 500:
            self.time_check_counter = 0
            if now[3] != self.last_hour_checked and now[4] == 0:
                self.pause_timer = 250
                self.last_hour_checked = now[3]
                # Save Persistence
                if self.score > self.high_score:
                    self.high_score = self.score
                    with open("highscore.txt", "w") as f: f.write(str(self.score))

        # Skip logic if paused for Win Screen
        if self.pause_timer > 0:
            return

        # Update Environment and Ship
        self.env.update(self.t % (self.PHASE_LEN * 4), self.PHASE_LEN)
        self.ship.update(self.t)
        
        # Spawning
        spawn_threshold = 0.94
        if self.score > 300:
            # Increase alien spawn chance progressively (up to a max of ~30% per frame)
            spawn_threshold = max(0.70, 0.94 - ((self.score - 300) * 0.0004))
            
        if random.random() > spawn_threshold: self.spawn_alien()
        # Increased frequency of rain dropping by lowering the randomization threshold
        if random.random() > 0.60: self.rain.append([random.randint(0, 320), 0, random.randint(8, 12)])
        
        # Firing Logic
        is_danger = self.score <= 50
        fire_threshold = 0.85 if is_danger else 0.96
        
        if random.random() > fire_threshold:
            self.lasers.append(Laser(self.ship.x + 10, self.ship.y))
            if is_danger:
                # Triple shot firepower!
                self.lasers.append(Laser(self.ship.x, self.ship.y - 15))
                self.lasers.append(Laser(self.ship.x, self.ship.y + 15))
            self.ship.recoil = 5
            self.buzzer.set_tone(1500 if is_danger else 1200)
        else:
            if getattr(self, "impact_timer", 0) > 0:
                self.buzzer.set_tone(random.randint(50, 250)) # Low crunchy impact frequency
                self.impact_timer -= 1
            elif getattr(self, "explode_timer", 0) > 0:
                self.buzzer.set_tone(random.randint(2000, 3000)) # High pitched explosion sound
                self.explode_timer -= 1
            else:
                self.buzzer.set_tone(0)

        # Entity Life Cycles
        for r in self.rain[:]:
            r[1] += r[2]
            if r[1] > 240 and r in self.rain:
                # Add splash effect at the bottom of the screen
                for _ in range(random.randint(2, 4)):
                    self.particles.append(Particle(r[0], 240, is_water=True))
                self.rain.remove(r)

        for l in self.lasers[:]: 
            l.update()
            if not l.active:
                if l in self.lasers: self.lasers.remove(l)
                continue
                
            # Circular Collision Detection
            for a in self.aliens[:]:
                dx = l.x - a.x
                dy = l.y - a.y
                if dx*dx + dy*dy < 144:  # roughly 12^2
                    if a in self.aliens:
                        self.score += 10
                        self.explode_timer = 5 # Short duration high pitch sound
                        self.aliens.remove(a)
                        if l in self.lasers: self.lasers.remove(l)
                        for _ in range(8):
                            self.particles.append(Particle(a.x, a.y))
                    break
                    
        for a in self.aliens[:]:
            a.update()
            if not a.active:
                if a in self.aliens: self.aliens.remove(a)
                continue
                
            dx = self.ship.x - a.x
            dy = self.ship.y - a.y
            if dx*dx + dy*dy < 100:  # Ship collision
                if a in self.aliens:
                    self.score -= 50
                    self.impact_timer = 15 # Set buzzer crunch frames
                    self.aliens.remove(a)
                    for _ in range(20):
                        self.particles.append(Particle(self.ship.x, self.ship.y))
                    if self.score <= 0:
                        self.score = 0
                        self.game_over = True
                        self.pause_timer = 150 # 3 seconds pause

        for p in self.particles[:]:
            p.update()
            if not p.active:
                if p in self.particles: self.particles.remove(p)

    def draw(self):
        d = self.display

        # Layer 0 (Background)
        self.env.draw_layer0(self.t)

        # Layer 1 (Entities)
        d.set_layer(1)
        d.set_pen(0)
        d.clear()
        
        # Ship Spotlight (if night)
        if self.env.is_night:
            # Step 1: Dim the screen with non-transparent dark midnight-blue lines
            fast_dimmer(d, 0, 5, 20)
            
            # Step 2: Draw a soft glowing halo outline ring
            d.set_pen(d.create_pen(60, 90, 120))
            d.circle(self.ship.x, self.ship.y, 42)
            
            # Step 3: Punch a transparent hole through all layer 1 dimming
            d.set_pen(0) 
            d.circle(self.ship.x, self.ship.y, 40)

        # Rain
        d.set_pen(d.create_pen(80, 80, 90))
        for r in self.rain:
            d.line(r[0], int(r[1]), r[0], int(r[1]) + r[2])

        # Lasers
        l_pen = d.create_pen(0, 255, 255)
        for l in self.lasers: l.draw(d, l_pen)

        # Particles
        p_pen = d.create_pen(255, 150, 0)
        w_pen = d.create_pen(160, 210, 255)
        for p in self.particles: p.draw(d, p_pen, w_pen)

        # Aliens
        a_body = d.create_pen(50, 200, 50)
        a_glow = d.create_pen(100, 255, 100)
        for a in self.aliens: a.draw(d, a_body, a_glow)

        self.ship.draw(self.env.is_night)

        # HUD
        self.draw_hud(f"SCORE: {self.score}", 5, 5, 2, self.env.is_night)
        self.draw_hud(f"HI: {self.high_score}", 240, 5, 2, self.env.is_night)

        if self.pause_timer > 0:
            if getattr(self, "game_over", False):
                self.draw_hud("GAME OVER", 90, 100, 3, self.env.is_night)
            else:
                self.draw_hud("HOURLY VICTORY!", 70, 100, 2, self.env.is_night)

        self.presto.update()

    def run(self):
        while True:
            self.update()
            self.draw()
            if self.pause_timer > 0:
                self.pause_timer -= 1
                if self.pause_timer == 0 and getattr(self, "game_over", False):
                    self.__init__() # Restart
            gc.collect()
            time.sleep(0.02)

if __name__ == '__main__':
    game = Game()
    game.run()