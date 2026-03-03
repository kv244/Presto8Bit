# sim.py  — headless game runner for AI training
import headless          # must be first — patches sys.modules before any game import
import sys, importlib

# Force-reload game modules so edits are picked up between runs
for mod in ["utils", "entities", "environment", "ship", "dandare"]:
    sys.modules.pop(mod, None)

from dandare import Game

def run_episode(max_frames=50_000, action_fn=None):
    """
    Run one game episode.

    action_fn: if None, the built-in rule-based pilot runs as normal.
               if provided, called each frame as:
                 action_fn(game) -> (move_x, move_y, aim_up, fire)
               and the returned values override the ship's decisions.

    Returns the final score.
    """
    game = Game()

    for frame in range(max_frames):
        if action_fn is not None:
            _apply_action(game, action_fn(game))

        game.update()
        # skip game.draw() entirely — the FakeDisplay absorbs all calls

        if game.game_over:
            break

        if game.pause_timer > 0:
            game.pause_timer -= 1
            if game.pause_timer == 0:
                break   # episode over

    return game.score


def _apply_action(game, action):
    """
    Writes an (aim_up, move_x, move_y, fire) action into game state
    BEFORE update() runs its physics and collision logic.
    """
    move_x, move_y, aim_up, fire = action

    # Override movement
    game.ship.x = max(20, min(300, game.ship.x + move_x))
    game.ship.y = max(40, min(200, game.ship.y + move_y))

    # Override fire mode
    game.ship.aim_up = bool(aim_up)

    # Override firing — bypass the probabilistic threshold entirely
    if fire and game.ship.fire_cooldown == 0:
        sx, sy = game.ship_vx, game.ship_vy
        if aim_up:
            game.fire_laser(sx, sy - 10, vx=0, vy=-12, is_up=True)
        else:
            target = game.get_nearest_alien(sx, sy)
            vx, vy = 12, 0
            if target:
                import math
                dx, dy = target.x - sx, target.y - sy
                a = math.atan2(dy, dx)
                vx = 12 * math.cos(a)
                vy = 12 * math.sin(a)
            game.fire_laser(sx + 10, sy, vx=vx, vy=vy)
        game.ship.recoil = 5
        game.ship.fire_cooldown = 4


# ── example: record rule-based pilot telemetry at 10× speed ─────────────────
if __name__ == "__main__":
    from telemetry import Telemetry
    import time

    N_EPISODES = 20
    tel = Telemetry(path="telemetry.csv")

    for ep in range(N_EPISODES):
        game = Game()
        game._prev_score = game.score
        frame = 0

        t0 = time.time()
        while not game.game_over and frame < 50_000:
            game.update()
            tel.step(game)
            game._prev_score = game.score
            frame += 1
            if game.pause_timer > 0:
                game.pause_timer -= 1
                if game.pause_timer == 0 and game.game_over:
                    break

        tel.on_game_over()
        elapsed = time.time() - t0
        print(f"Episode {ep+1}/{N_EPISODES}  frames={frame}  "
              f"score={game.score}  {elapsed:.1f}s  "
              f"({frame/elapsed:.0f} fps)")

    tel.flush()
    print("Done. telemetry.csv ready for train.py")