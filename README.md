# Night Survivors — Core, Pictures, Growth, Waves, Sound and feel, Difficulty modes

**Play in the browser: <https://kevin188888.github.io/night-survivors/>** (the `gh-pages`
branch holds the built web version; the source is on `main`). The page loads Python and
pygame-ce as WebAssembly, so it needs a few seconds and a click to start with sound.

Run `python make_assets.py` and `python make_sounds.py` once to build `assets/` and
`sounds/`, then run `python main.py` from this folder.
Requires `pygame-ce` and `Pillow` (only for `make_assets.py`).

The game opens on a difficulty screen: click, tap or press **1**, **2** or **3** to choose
EASY, NORMAL or HARD. Move the mouse away from the hero to walk in that direction. Keep it near the
hero to stop. On a touchscreen, hold and move one finger; lift it to stop.
Your weapons fire automatically. Press **P** to pause or resume, **R** to go back to the
difficulty screen, and **Esc** to close. Click or tap the end screen to play again.

Survive **2:00** on NORMAL to win (1:30 on EASY, 2:20 on HARD). The top-right timer shows
how far you have got.

This is Steps 1 to 6 of GAME.md — the whole design.

1. **Core** — hero, camera, endless tiled floor, Bats, contact damage, Spark Wand, HP, game over.
2. **Pictures** — `make_assets.py` writes crisp 3x copies (48x48) of every file in
   `raw_art/`, plus `gem_blue.png` (XP 1) and `gem_pink.png` (XP 2) recoloured from
   `gem.png`; it never touches `raw_art/`. `main.py` only loads the finished files and
   never imports Pillow.
3. **Growth** — dead enemies drop gems, gems inside the magnet radius fly to you and give
   XP, and each level-up freezes the game and shows three cards to click or tap. All three
   weapons and all three passive items work, each up to level 5, with at most three weapons.
4. **Waves** — the whole spawning table runs: Bats from the start, Slimes from 0:30, Ghosts
   from 0:45, and the Demon boss once from 1:30. The boss is never removed by distance: if
   it falls more than 600 px behind it is carried back to the 380 px circle. Reaching 2:00
   shows VICTORY instead of GAME OVER.
5. **Sound and feel** — `make_sounds.py` (standard library only) writes five short clips into
   `sounds/`: `hit`, `gem`, `level_up`, `hurt` and `end`. Every step of `rules.py` also writes
   down what happened (a hit with its damage, a death with the size of the enemy, a gem,
   getting hurt, a level-up, the end) in `game.events`, and `main.py` reads that list once per
   frame: it plays the clips and draws the damage numbers floating up, a white ring where an
   enemy died, and a short camera shake when the hero is hurt. `main.py` never imports
   `wave` or `make_sounds`, so the browser build still works.
6. **Difficulty modes** — `data/difficulties.json` holds EASY, NORMAL and HARD as numbers only.
   `rules.load_config("hard")` reads `game.json` and lays that mode's numbers over it (a dict
   merges key by key, a list such as the spawning table is replaced whole), so NORMAL is
   `game.json` unchanged and a new mode needs no code at all. `main.py` shows the picker, keeps
   the best run of each mode (win, then time, then kills) in `data/records.json`, and skips the
   write quietly when the file system is not available in a browser.

## How the three modes were balanced

Measured, not guessed. A throwaway bot ran the rules with no window: it walks away from the
middle of the crowd, takes a gem only when nothing stands near it, and picks a heal when its HP
drops below half. That is roughly an average player. Twelve runs per mode gave:

| Mode | Runs won | Median run | Level | Kills |
|---|---|---|---|---|
| EASY | 12 / 12 | 1:30 (full) | 8 | 134 |
| NORMAL | 6 / 12 | 1:37 | 12 | 236 |
| HARD | 2 / 12 | 1:25 | 12 | 204 |

Two findings from that work are worth knowing before you retune anything:

- **HARD is NORMAL for its first 1:15.** The first version of HARD also raised every enemy's
  damage by 1 and the Ghost's HP from 15 to 18. That looked harmless and made the mode
  unplayable: the median run fell from 1:25 to 1:05 and the win rate went to zero. A Ghost at
  18 HP needs one more spark than at 15, so the 0:45-1:15 swarm is cleared slower, snowballs,
  and the hero is cornered. HARD now differs only in the boss (1000 HP, 15 s early), the
  crowd after 1:15 (66, 80, 95 alive) and 20 extra seconds on the clock.
- **The Demon is never killed in any mode**, by the bot or by the numbers. A maxed three-weapon
  build does about 126 damage per second *in total*, and the ring spreads that over the whole
  crowd, so 800 HP is out of reach while Bats are still touching you. Dropping the boss to
  roughly 300 HP, or giving it XP, would make it a target instead of an obstacle.

The Spark Wand fires eight sparks in a ring that keeps turning, so the shots sweep the
whole 360 degrees; the number of sparks and the turn rate are both in `data/game.json`.

All design numbers — including the card names and text, the sound volume and every
effect length — are stored in `data/game.json`, and the differences between the three
difficulties in `data/difficulties.json`, so retuning never needs a code change.
`rules.py` advances the game by a fixed
1/60-second step and does not import pygame. `main.py` handles the screen, sound and
mouse/touch events using an async loop.

Run the rule tests with `python -m unittest`.

## Rebuilding the browser version

`python -m pygbag --build --disable-sound-format-error main.py` writes `build/web/`.
Then two small fixes are needed in `build/web/index.html`, because pygbag 0.9.3 points at a
CDN file that no longer exists: download `browserfs.min.js` from
`https://pygame-web.github.io/archives/0.9/browserfs.min.js` into that folder and change the
`<script src=...>` line to `browserfs.min.js`. Copy the folder to the `gh-pages` branch to
publish it. `data/records.json` is packed into the bundle, so move it away before building if
you do not want your own best runs online.
