# genetics.py — v1  2026-04-11
#
# Genetic algorithm for enemy evolution in Dan Dare (Presto8Bit).
#
# Design constraints (MicroPython / RP2350):
#   - All data structures pre-allocated at module load; no heap after startup
#   - breed() mutates the alien's own genome list in-place (no new lists)
#   - record_fitness() replaces the weakest gene-pool slot in-place
#
# Fitness function: survival_frames + direct_hits * 100
#   survival_frames — how long the alien stayed active (tracked in Alien.update)
#   direct_hits     — body-slams + approximate laser hits credited to the alien
#
# Gene encoding (6 floats per genome):
#   [0] speed        2.0–6.0    Bézier traversal / homing step size
#   [1] move_speed   0.8–4.5    Homing pixels-per-frame
#   [2] hp           1.0–4.0    Hit points (int-cast at spawn)
#   [3] fire_rate    0.5–3.0    Fire probability multiplier
#   [4] proj_speed   6.0–16.0   Projectile speed (px/frame)
#   [5] spread_scale 0.5–2.5    Fractal spread angle scale (reserved for future use)

import random

# ---------------------------------------------------------------------------
# Genetic algorithm — enemy trait evolution
# Fitness function: survival_frames + direct_hits * 100
# ---------------------------------------------------------------------------
# Gene layout (all floats, index constants below):
#   [0] speed        2.0–6.0    Bézier traversal / homing speed
#   [1] move_speed   0.8–4.5    Homing pixels-per-frame
#   [2] hp           1.0–4.0    Hit points (int-cast at spawn)
#   [3] fire_rate    0.5–3.0    Fire probability multiplier
#   [4] proj_speed   6.0–16.0   Projectile speed (px/frame)
#   [5] spread_scale 0.5–2.5    Fractal spread angle multiplier

GENE_COUNT = 6
GENE_MIN   = (2.0,  0.8, 1.0, 0.5,  6.0, 0.5)
GENE_MAX   = (6.0,  4.5, 4.0, 3.0, 16.0, 2.5)

POOL_SIZE  = 8

# Pre-allocated pool — no heap after startup
_genomes  = [[3.0, 1.8, 1.0, 1.0, 10.0, 1.0] for _ in range(POOL_SIZE)]
_fitness  = [-1.0] * POOL_SIZE   # -1.0 = empty slot
_n_filled = [0]                   # number of filled slots (single-element list for mutability)


def reset_pool():
    """Clear gene pool — call on Game.reset()."""
    for i in range(POOL_SIZE):
        _fitness[i] = -1.0
    _n_filled[0] = 0


def breed(out_genome):
    """Breed a child genome into out_genome (6-element list, mutated in-place).

    Uses 60 %-probability tournament-selection crossover + 20 % per-gene mutation.
    Returns True if breeding succeeded, False if pool had fewer than 2 parents
    (caller should populate out_genome with defaults).
    """
    if _n_filled[0] < 2 or random.random() > 0.60:
        return False

    # Tournament selection — two distinct filled slots
    idx1 = -1
    start = random.randint(0, POOL_SIZE - 1)
    for k in range(POOL_SIZE):
        i = (start + k) % POOL_SIZE
        if _fitness[i] >= 0.0:
            idx1 = i; break
    if idx1 < 0:
        return False

    idx2 = -1
    start = random.randint(0, POOL_SIZE - 1)
    for k in range(POOL_SIZE):
        i = (start + k) % POOL_SIZE
        if i != idx1 and _fitness[i] >= 0.0:
            idx2 = i; break
    if idx2 < 0:
        return False

    # Prefer fitter parent as the primary donor
    if _fitness[idx2] > _fitness[idx1]:
        idx1, idx2 = idx2, idx1

    p1 = _genomes[idx1]; p2 = _genomes[idx2]
    pt = random.randint(1, GENE_COUNT - 1)   # single-point crossover

    for i in range(GENE_COUNT):
        out_genome[i] = p1[i] if i < pt else p2[i]

    # Per-gene mutation (20 % chance, ±15 % of range)
    for i in range(GENE_COUNT):
        if random.random() < 0.20:
            lo = GENE_MIN[i]; hi = GENE_MAX[i]
            delta = (hi - lo) * 0.15
            v = out_genome[i] + random.uniform(-delta, delta)
            out_genome[i] = lo if v < lo else (hi if v > hi else v)

    return True


def record_fitness(genome, survival_frames, direct_hits):
    """Record alien fitness into the gene pool.

    Replaces an empty slot, or the weakest slot if pool is full.
    genome must be the alien's 6-element list (never None when called).
    """
    f = float(survival_frames) + float(direct_hits) * 100.0

    worst_i = -1; worst_f = f   # only replace if we beat the worst
    for i in range(POOL_SIZE):
        if _fitness[i] < 0.0:   # empty slot — always take it
            worst_i = i; break
        if _fitness[i] < worst_f:
            worst_f = _fitness[i]; worst_i = i

    if worst_i >= 0:
        g = _genomes[worst_i]
        for i in range(GENE_COUNT):
            g[i] = genome[i]
        _fitness[worst_i] = f
        if _n_filled[0] < POOL_SIZE:
            _n_filled[0] = _n_filled[0] + 1
