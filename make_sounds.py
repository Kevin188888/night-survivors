"""Makes the game sounds. Run this on your computer:  python make_sounds.py

Only Python's standard library is used here (math, random, wave). Every sound is a
short mono 16-bit .wav file in sounds/. main.py only loads these finished files,
it never imports this script, so the game still works in a web browser.
"""

import math
import random
import wave
from array import array
from pathlib import Path

RATE = 44100          # samples per second
OUT = Path(__file__).parent / "sounds"
TOP = 0.9             # nothing is allowed to be louder than this (1.0 would clip)


def count(seconds: float) -> int:
    return int(round(seconds * RATE))


def shape(values: list[float], attack: float = 0.004, hold: float = 0.0) -> list[float]:
    """Fade in, hold, fade out. Without this the first and last sample click."""
    total = len(values)
    in_samples = max(1, count(attack))
    hold_samples = count(hold)
    tail = total - in_samples - hold_samples
    out = []
    for index, value in enumerate(values):
        if index < in_samples:
            fade = index / in_samples
        elif index < in_samples + hold_samples:
            fade = 1.0
        elif tail <= 0:
            fade = 1.0
        else:
            left = (total - index) / tail
            fade = left ** 1.6
        out.append(value * fade)
    return out


def tone(seconds: float, from_hz: float, to_hz: float, volume: float = 1.0,
         harmonics: tuple[tuple[float, float], ...] = ((1.0, 1.0),),
         decay: float = 1.0, attack: float = 0.004, hold: float = 0.0) -> list[float]:
    """One note. The pitch slides from from_hz to to_hz, overtones add colour."""
    total = count(seconds)
    phase = 0.0
    values = []
    for index in range(total):
        progress = index / total
        hz = from_hz + (to_hz - from_hz) * progress
        phase += math.tau * hz / RATE
        value = sum(math.sin(phase * times) * weight for times, weight in harmonics)
        values.append(value * volume * (1 - progress) ** decay)
    return shape(values, attack, hold)


def noise(seconds: float, volume: float = 1.0, seed: int = 0, roughness: float = 6.0,
          decay: float = 1.5, attack: float = 0.001) -> list[float]:
    """Random samples smoothed a little, so it lands as a thud instead of a hiss."""
    rng = random.Random(seed)
    total = count(seconds)
    values = []
    slow = 0.0
    for index in range(total):
        raw = rng.uniform(-1, 1)
        slow += (raw - slow) / roughness
        mixed = (raw + slow * roughness) / (1 + roughness)
        values.append(mixed * volume * (1 - index / total) ** decay)
    return shape(values, attack)


def mix(*tracks: list[float]) -> list[float]:
    """Put notes on top of each other (the same moment in time)."""
    longest = max(len(track) for track in tracks)
    out = [0.0] * longest
    for track in tracks:
        for index, value in enumerate(track):
            out[index] += value
    return out


def delayed(track: list[float], start_seconds: float) -> list[float]:
    """Move a note later in time, so sounds can play one after another."""
    start = count(start_seconds)
    out = [0.0] * (start + len(track))
    for index, value in enumerate(track):
        out[start + index] = value
    return out


def limit(values: list[float]) -> list[float]:
    """Bring the loudest point back to TOP so nothing distorts."""
    peak = max((abs(value) for value in values), default=0.0)
    if peak <= TOP or peak == 0:
        return values
    return [value * TOP / peak for value in values]


def hit() -> list[float]:
    """A spark touching an enemy: a short, bright tick."""
    return mix(
        tone(0.07, 1400, 620, 0.55, ((1.0, 1.0), (2.0, 0.35)), decay=2.2),
        noise(0.03, 0.25, seed=1, roughness=2),
    )


def gem() -> list[float]:
    """A gem flying into the hero: a rising two-note ping."""
    return mix(
        tone(0.07, 880, 880, 0.5, decay=1.4),
        delayed(tone(0.13, 1320, 1320, 0.45, decay=1.8), 0.06),
    )


def level_up() -> list[float]:
    """Four notes climbing a chord, with a thin shimmer above them."""
    parts = [delayed(tone(0.17, hz, hz, 0.36,
                          ((1.0, 1.0), (2.0, 0.4), (3.0, 0.2)), decay=1.2), step * 0.075)
             for step, hz in enumerate((523, 659, 784, 1047))]
    parts.append(tone(0.5, 2093, 2093, 0.09, decay=2.5))
    return mix(*parts)


def hurt() -> list[float]:
    """The hero is hurt: a low thud that falls in pitch."""
    return mix(
        tone(0.22, 210, 70, 0.7, ((1.0, 1.0), (2.0, 0.3)), decay=1.2),
        noise(0.12, 0.5, seed=3, roughness=8, decay=1.5),
    )


def end() -> list[float]:
    """The run is over: three notes falling away together."""
    parts = [tone(0.9, hz, hz * 0.55, 0.32, ((1.0, 1.0), (1.5, 0.25)), decay=1.4)
             for hz in (392, 330, 262)]
    parts.append(noise(0.35, 0.35, seed=7, roughness=14, decay=2))
    return mix(*parts)


SOUNDS = {"hit": hit, "gem": gem, "level_up": level_up, "hurt": hurt, "end": end}


def save(name: str, values: list[float]) -> None:
    frames = array("h", (int(round(value * 32767)) for value in limit(values)))
    path = OUT / f"{name}.wav"
    with wave.open(str(path), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(frames.itemsize)
        file.setframerate(RATE)
        file.writeframes(frames.tobytes())
    print(f"{name}.wav: {len(values) / RATE * 1000:.0f} ms, "
          f"{len(values) * frames.itemsize / 1024:.0f} kB")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, build in SOUNDS.items():
        save(name, build())
    print(f"wrote {len(SOUNDS)} files to {OUT}")


if __name__ == "__main__":
    main()
