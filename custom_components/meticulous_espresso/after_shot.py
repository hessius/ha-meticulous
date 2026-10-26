"""After-shot retract: a per-shot measure of piston friction.

Right after every shot the machine pulls the piston up at full drive (-100 %)
with the pressure back at 0 bar. Because the drive level is the same every
time, extra load (seal friction) shows up directly as more motor current and a
slightly lower speed. Analysed over ~500 shots, the median current of the
steady part of this move drops sharply after greasing/descaling and creeps up
in between, with a shot-to-shot noise of only ~0.035 A.

The same summary is used for the live Socket.IO stream (coordinator) and for
importing older shots from the machine's own shot history (history_import).
"""

from __future__ import annotations

from collections.abc import Iterable
from math import isfinite
from statistics import median

# A sample is (position mm, speed mm/s, drive %, current A, pressure bar).
Sample = tuple[float, float, float, float, float]

AFTER_SHOT_MIN_DRIVE = 99.0  # |drive %|: the move runs at full drive
AFTER_SHOT_MIN_SPEED = 8.0  # |mm/s|: steady part only (not the pressure release)
AFTER_SHOT_MAX_PRESSURE = 0.1  # bar
AFTER_SHOT_WINDOW = (35.0, 55.0)  # piston position (mm) covered by nearly every shot
AFTER_SHOT_MIN_SAMPLES = 5

# Machine states before "Retracting" that mean the retract is the pre-shot one
PRE_SHOT_STATES = {
    None,
    "",
    "unknown",
    "idle",
    "click to start",
    "heating",
    "preheating",
    "starting...",
    "boot",
    "home",
    "purge",
    "finished",
}


def is_after_shot_retract(state: str | None, previous_state: str | None) -> bool:
    """Identify a retract that follows an observed profile stage."""
    return (
        state is not None
        and state.strip().casefold() == "retracting"
        and previous_state is not None
        and previous_state.replace("_", " ").strip().casefold() not in PRE_SHOT_STATES
    )


def summarise(samples: Iterable[Sample]) -> tuple[float, float] | None:
    """Return (median current A, median speed mm/s) of the steady full-drive part, or None."""
    lo, hi = AFTER_SHOT_WINDOW
    steady = [
        s
        for s in samples
        if all(isfinite(value) for value in s)
        and s[2] <= -AFTER_SHOT_MIN_DRIVE
        and s[1] <= -AFTER_SHOT_MIN_SPEED
        and abs(s[4]) < AFTER_SHOT_MAX_PRESSURE
        and lo <= s[0] <= hi
    ]
    if len(steady) < AFTER_SHOT_MIN_SAMPLES:
        return None
    return (
        round(median(abs(s[3]) for s in steady), 3),
        round(median(abs(s[1]) for s in steady), 2),
    )
