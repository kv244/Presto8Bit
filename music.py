# music.py
# Frame-based melody sequencer — no threading or timers required.
# Call player.advance() once per game frame; the sequencer steps through
# the note list automatically. At 50fps (20ms/frame):
#   4 frames =  80ms  (very short)
#   8 frames = 160ms  (eighth note @ ~90 BPM)
#  16 frames = 320ms  (quarter note @ ~90 BPM)
#  25 frames = 500ms  (half note)

# ---------------------------------------------------------------------------
# Note frequencies (Hz)
# ---------------------------------------------------------------------------
_B3  = 247
_C4  = 262; _D4  = 294; _E4  = 330; _F4  = 349; _G4  = 392; _A4  = 440; _B4  = 494
_C5  = 523; _D5  = 587; _E5  = 659; _F5  = 698; _G5  = 784; _A5  = 880; _B5  = 988
_REST = 0

# ---------------------------------------------------------------------------
# Melodies — tuples of (frequency_hz, duration_frames)
# ---------------------------------------------------------------------------

# Heroic fanfare loop for the intro screen
INTRO = (
    (_C5,  6), (_REST, 2),
    (_C5,  6), (_REST, 2),
    (_G5, 10), (_REST, 3),
    (_E5,  6), (_REST, 2),
    (_E5,  6), (_REST, 2),
    (_C5, 10), (_REST, 3),
    (_F5,  6), (_REST, 2),
    (_G5,  6), (_REST, 2),
    (_A5,  6), (_REST, 2),
    (_G5, 14), (_REST, 4),
    (_E5,  6), (_REST, 2),
    (_D5,  6), (_REST, 2),
    (_C5, 20), (_REST, 8),
)

# Mournful descending phrase for the game-over screen
GAME_OVER = (
    (_G4, 10), (_REST, 2),
    (_E4, 10), (_REST, 2),
    (_D4,  8), (_REST, 2),
    (_C4, 16), (_REST, 6),
    (_E4,  8), (_REST, 2),
    (_D4,  8), (_REST, 2),
    (_B3, 12), (_REST, 4),
    (_C4, 24), (_REST, 8),
)


# ---------------------------------------------------------------------------
class Player:
    __slots__ = ('_buzzer', '_melody', '_idx', '_frames_left', '_loop')

    def __init__(self, buzzer):
        self._buzzer = buzzer
        self._melody = None
        self._idx = 0
        self._frames_left = 0
        self._loop = False

    def play(self, melody, loop=False):
        self._melody = melody
        self._idx = 0
        self._frames_left = 0
        self._loop = loop
        self._next()

    def stop(self):
        self._melody = None
        self._buzzer.set_tone(0)

    @property
    def active(self):
        return self._melody is not None

    def _next(self):
        if self._melody is None:
            return
        if self._idx >= len(self._melody):
            if self._loop:
                self._idx = 0
            else:
                self._melody = None
                self._buzzer.set_tone(0)
                return
        freq, dur = self._melody[self._idx]
        self._buzzer.set_tone(freq)
        self._frames_left = dur
        self._idx += 1

    def advance(self):
        """Call exactly once per game frame to step the sequencer."""
        if self._melody is None:
            return
        self._frames_left -= 1
        if self._frames_left <= 0:
            self._next()
