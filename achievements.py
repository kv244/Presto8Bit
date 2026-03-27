try:
    import ujson as json
except ImportError:
    import json

_ACHIEVEMENTS = {
    'first_blood':      'First Blood',
    'cloud_buster':     'Cloud Buster',
    'village_guardian': 'Village Guardian',
    'boss_slayer':      'Boss Slayer',
    'nuke_em':          'Nuke Em',
    'centurion':        'Centurion',
    'legendary':        'Legendary',
    'night_owl':        'Night Owl',
    'untouchable':      'Untouchable',
}

_FILE = 'achievements.json'
TOTAL = len(_ACHIEVEMENTS)


def load():
    """Load unlocked achievements from disk. Returns a set of unlocked keys."""
    try:
        with open(_FILE, 'r') as f:
            data = json.loads(f.read())
        return set(data.get('unlocked', []))
    except:
        return set()


def save(unlocked):
    """Persist the current unlocked set to disk."""
    try:
        with open(_FILE, 'w') as f:
            f.write(json.dumps({'unlocked': list(unlocked)}))
    except:
        pass


def unlock(key, unlocked):
    """Unlock an achievement. Returns display name if newly unlocked, else None."""
    if key not in unlocked:
        unlocked.add(key)
        save(unlocked)
        return _ACHIEVEMENTS.get(key, key)
    return None
