# chaos.py — v1  2026-04-11
# Chaos theory integration for Presto8Bit.
import math, random, time

# Attractor Presets
LORENZ_S = 10.0; LORENZ_R = 28.0; LORENZ_B = 2.666
ROSS_A = 0.2; ROSS_B = 0.2; ROSS_C = 5.7

class LyapunovTracker:
    """Tracks distance between two chaotic trajectories to estimate divergence."""
    def __init__(self, label):
        self.label = label
        self.d0 = 0.0
        self.dt = 0.0
        self.frames = 0
        self.active = False

    def start(self, a1, a2):
        dx = a1.ax - a2.ax; dy = a1.ay - a2.ay; dz = a1.az - a2.az
        self.d0 = math.sqrt(dx*dx + dy*dy + dz*dz)
        if self.d0 == 0: self.d0 = 1e-6 # Avoid div zero
        self.frames = 0
        self.active = True

    def update(self, a1, a2):
        if not self.active or not a1.active or not a2.active:
            self.active = False; return None
        
        self.frames += 1
        dx = a1.ax - a2.ax; dy = a1.ay - a2.ay; dz = a1.az - a2.az
        self.dt = math.sqrt(dx*dx + dy*dy + dz*dz)
        
        # λ ≈ ln(d_t / d_0) / t
        # We use frames as a proxy for time t.
        if self.dt > 0:
            return math.log(self.dt / self.d0) / self.frames
        return 0.0

    def log_result(self, lambda_val):
        try:
            with open("chaos_log.txt", "a") as f:
                f.write(f"{time.localtime()[3:6]} | {self.label} | Lambda: {lambda_val:.4f}\n")
        except: pass

def spawn_chaos_twins(pool, a_type, x_off, y_off, epsilon=0.001):
    """Spawns two aliens with nearly identical initial conditions."""
    a1 = pool.get()
    a2 = pool.get()
    if a1 is None or a2 is None: return None, None
    
    # Random initial state
    ix = random.uniform(-1.0, 1.0); iy = random.uniform(-1.0, 1.0); iz = random.uniform(0.0, 20.0)
    
    if a_type == 1: # Lorenz
        p = (LORENZ_S, LORENZ_R, LORENZ_B)
        scale = 3.5
    else: # Rossler
        p = (ROSS_A, ROSS_B, ROSS_C)
        scale = 10.0
        
    a1.reset(x_off, y_off, 0, 0, 0, 0, speed=1, 
             a_type=a_type, ax=ix, ay=iy, az=iz, 
             ap1=p[0], ap2=p[1], ap3=p[2], a_scale=scale)
    
    a2.reset(x_off, y_off, 0, 0, 0, 0, speed=1, 
             a_type=a_type, ax=ix + epsilon, ay=iy, az=iz, 
             ap1=p[0], ap2=p[1], ap3=p[2], a_scale=scale)
    
    return a1, a2
