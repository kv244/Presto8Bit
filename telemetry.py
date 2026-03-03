# telemetry.py  –  Dan Dare AI training telemetry
# Drop this file next to dandare.py on the Presto SD card.
#
# WHAT IT CAPTURES
# ────────────────
# Every frame records the observation vector the model will see,
# the action the rule-based pilot actually took, and the reward
# earned.  Replay this CSV offline to train via imitation learning
# or as an offline RL dataset (CQL / BCQ).
#
# INTEGRATION (in dandare.py)
# ────────────────────────────
#   from telemetry import Telemetry
#   # inside Game.__init__:
#   self.tel = Telemetry()
#   self._prev_score = self.score
#   # at the END of Game.update(), after all collision logic:
#   self.tel.step(self)
#   self._prev_score = self.score          # keep for next frame's reward

import gc

# ── CSV header ──────────────────────────────────────────────────────────────
# Observation columns
_OBS = [
    # Ship (all coordinates normalised to [0,1] range)
    "ship_x",           # ship.x / 320
    "ship_y",           # ship.y / 240
    "ship_vx",          # visual x (includes oscillation) / 320
    "ship_vy",          # visual y / 240
    "aim_up",           # 1 = shooting clouds/celestial, 0 = shooting aliens
    "fire_cd",          # fire_cooldown / 10  (proxy for "can fire now")
    # Nearest alien threat
    "near_ax",          # nearest alien x / 320  (-1 if none)
    "near_ay",          # nearest alien y / 240  (-1 if none)
    "near_rel_x",       # (alien.x - ship_vx) / 320  (signed direction)
    "near_rel_y",       # (alien.y - ship_vy) / 240
    "near_dist",        # sqrt distance / 320  (0..~1.4)
    "near_is_boss",     # 1 if elite/boss alien
    "near_is_homing",   # 1 if alien is locked onto ship
    "alien_count",      # active aliens / 24
    "boss_wave",        # 1 during boss swarm fight
    # Nearest enemy laser threat
    "elaser_rx",        # (elaser.x - ship_vx) / 320  (-1 if none)
    "elaser_ry",        # (elaser.y - ship_vy) / 240
    "elaser_dist",      # distance / 320  (-1 if none)
    # Cloud / rain context  (drive the "shoot clouds?" decision)
    "cloud_count",      # len(clouds) / 5
    "nearest_cloud_rx", # (nearest_cloud_x - ship_vx) / 320  (signed)
    "rain_density",     # active rain drops / 40
    "house_count",      # len(houses) / 12
    "cloud_revert",     # cloud_revert_timer > 0  (shooting clouds is currently hurting)
    # Celestial / nuke context
    "celestial_rx",     # (cel_x - ship_vx) / 320
    "celestial_ry",     # (cel_y - ship_vy) / 240
    "nuke_ready",       # ship.nuke_ready flag
    "nuke_used",        # nuke already consumed this game
    # Environment
    "is_night",         # 1 at night (halo defence active)
    "day_trans",        # env.trans [0..1]
    "score_norm",       # score / 2000  (capped)
    "is_critical",      # score < 40 or houses < 6
]

# Action columns  (what the rule-based pilot actually did this frame)
_ACT = [
    "act_move_x",       # ship.x delta this frame  (raw pixels, –6..+6)
    "act_move_y",       # ship.y delta this frame
    "act_aim_up",       # 1 = chose cloud/celestial targeting
    "act_fired",        # 1 = at least one laser spawned this frame
]

# Outcome columns
_OUT = [
    "reward",           # score delta this frame (can be negative)
    "game_over",        # 1 on terminal frame
]

HEADER = ",".join(_OBS + _ACT + _OUT) + "\n"


class Telemetry:
    """
    Collects one row per game-frame.  Flushes to SD every FLUSH_EVERY frames
    to avoid filling MicroPython heap.

    Usage
    -----
    tel = Telemetry()
    # at end of Game.update():
    tel.step(game_instance)
    """

    FLUSH_EVERY = 300   # ~6 seconds at 50 fps;  reduce if RAM is tight

    def __init__(self, path="/sd/telemetry.csv"):
        self._path = path
        self._buf  = []
        self._prev_score = None
        self._prev_ship_x = None
        self._prev_ship_y = None
        self._prev_lasers_active = 0
        self._episode = 0

        # Write header (overwrite each new game launch so we don't
        # accumulate stale headers mid-file during development).
        try:
            with open(path, "w") as f:
                f.write(HEADER)
        except OSError:
            pass  # SD not mounted — silently degrade

    # ── helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _nearest_elaser(ship_vx, ship_vy, pool):
        best_d2 = 1e9
        best = None
        for el in pool._pool:
            if el.active:
                dx = el.x - ship_vx
                dy = el.y - ship_vy
                d2 = dx * dx + dy * dy
                if d2 < best_d2:
                    best_d2 = d2
                    best = el
        return best, best_d2

    @staticmethod
    def _rain_count():
        from dandare import _rain_live  # import at call-time to avoid circular
        return sum(1 for v in _rain_live if v)

    # ── main entry point ────────────────────────────────────────────────────

    def step(self, game):
        """Call once per frame, at the END of Game.update()."""
        from entities import ALIEN_POOL, LASER_POOL, ENEMY_LASER_POOL  # local import

        # ── score delta (reward) ────────────────────────────────────────────
        if self._prev_score is None:
            self._prev_score = game.score
        reward = game.score - self._prev_score
        self._prev_score = game.score

        # ── ship position delta (action: move) ──────────────────────────────
        if self._prev_ship_x is None:
            self._prev_ship_x = game.ship.x
            self._prev_ship_y = game.ship.y
        act_move_x = game.ship.x - self._prev_ship_x
        act_move_y = game.ship.y - self._prev_ship_y
        self._prev_ship_x = game.ship.x
        self._prev_ship_y = game.ship.y

        # ── did the ship actually fire this frame? ───────────────────────────
        lasers_now = sum(1 for l in LASER_POOL._pool if l.active)
        act_fired  = 1 if lasers_now > self._prev_lasers_active else 0
        self._prev_lasers_active = lasers_now

        # ── cache frequently-used values ────────────────────────────────────
        svx = game.ship_vx
        svy = game.ship_vy

        # ── nearest alien ───────────────────────────────────────────────────
        near_a = game.get_nearest_alien(svx, svy)
        if near_a:
            na_rx  = (near_a.x - svx) / 320.0
            na_ry  = (near_a.y - svy) / 240.0
            na_d   = (na_rx * na_rx + na_ry * na_ry) ** 0.5
            na_x   = near_a.x / 320.0
            na_y   = near_a.y / 240.0
            na_boss   = 1 if near_a.is_boss else 0
            na_homing = 1 if near_a.target is not None else 0
        else:
            na_rx = na_ry = na_d = 0.0
            na_x  = na_y  = -1.0
            na_boss = na_homing = 0

        # ── alien count ─────────────────────────────────────────────────────
        alien_count = sum(1 for a in ALIEN_POOL._pool if a.active)

        # ── nearest enemy laser ─────────────────────────────────────────────
        best_el, _ = self._nearest_elaser(svx, svy, ENEMY_LASER_POOL)
        if best_el:
            el_rx   = (best_el.x - svx) / 320.0
            el_ry   = (best_el.y - svy) / 240.0
            el_dist = (el_rx * el_rx + el_ry * el_ry) ** 0.5
        else:
            el_rx = el_ry = el_dist = -1.0

        # ── cloud context ────────────────────────────────────────────────────
        cloud_count  = len(game.env.clouds) / 5.0
        ncx          = game.env.get_nearest_cloud_x(svx, game.t)
        nc_rx        = ((ncx - svx) / 320.0) if ncx is not None else 0.0
        rain_density = self._rain_count() / 40.0

        # ── celestial ───────────────────────────────────────────────────────
        cel_x, cel_y = game.env.get_celestial_coords(game.t)
        cel_rx = (cel_x - svx) / 320.0
        cel_ry = (cel_y - svy) / 240.0

        # ── assemble row ─────────────────────────────────────────────────────
        def f(v): return "{:.4f}".format(v)

        row = (
            # Observation
            f(game.ship.x / 320.0),
            f(game.ship.y / 240.0),
            f(svx / 320.0),
            f(svy / 240.0),
            "1" if game.ship.aim_up else "0",
            f(min(game.ship.fire_cooldown, 10) / 10.0),
            f(na_x), f(na_y), f(na_rx), f(na_ry), f(na_d),
            str(na_boss), str(na_homing),
            f(min(alien_count, 24) / 24.0),
            "1" if game.boss_active else "0",
            f(el_rx), f(el_ry), f(el_dist),
            f(cloud_count),
            f(nc_rx),
            f(rain_density),
            f(len(game.env.houses) / 12.0),
            "1" if game.cloud_revert_timer > 0 else "0",
            f(cel_rx), f(cel_ry),
            "1" if game.ship.nuke_ready else "0",
            "1" if game.nuke_used else "0",
            "1" if game.env.is_night else "0",
            f(game.env.trans),
            f(min(game.score, 2000) / 2000.0),
            "1" if (game.score < 40 or len(game.env.houses) < 6) else "0",
            # Actions
            f(act_move_x), f(act_move_y),
            "1" if game.ship.aim_up else "0",
            str(act_fired),
            # Outcome
            str(reward),
            "1" if game.game_over else "0",
        )

        self._buf.append(",".join(row))

        if len(self._buf) >= self.FLUSH_EVERY:
            self.flush()

    # ── flush ────────────────────────────────────────────────────────────────

    def flush(self):
        if not self._buf:
            return
        try:
            with open(self._path, "a") as f:
                f.write("\n".join(self._buf) + "\n")
        except OSError:
            pass  # SD write failed — don't crash the game
        self._buf.clear()
        gc.collect()

    def on_game_over(self):
        """Call when game_over triggers to flush any remaining buffer."""
        self.flush()
        self._prev_score  = None
        self._prev_ship_x = None
        self._prev_ship_y = None
        self._prev_lasers_active = 0
        self._episode += 1