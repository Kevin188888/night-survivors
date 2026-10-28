# Night Survivors — design (CDT501 Lecture 9)

A tiny game in the "survivors" style: you only walk, your weapons attack by themselves,
enemies come from every side, you grow stronger every level. Names, numbers and pictures are our own.

## Goal
- Survive until **2:00** on NORMAL (1:30 on EASY, 2:20 on HARD): then the game shows VICTORY.
- Hero HP reaches 0: GAME OVER.
- Click or tap the end screen to play again.

## Screen and controls
- Window 500 x 600. The camera follows the hero.
- The floor is one tile repeated forever: the map has no edges.
- Computer: the hero walks toward the mouse pointer and keeps walking as long as the pointer
  is more than 12 px away from him, even when the mouse does not move.
- Phone: the hero walks toward the finger while it touches the screen and stops when it is lifted.
- Click or tap a card to choose it. P pauses.

## Hero
| Speed | HP | Hit radius | Gem magnet radius |
|---|---|---|---|
| 200 px/s | 100 | 12 px | 80 px |

## Weapons (start with Spark Wand; at most 3 weapons; levels 1–5)
| Weapon | What it does | Level 1 | Each extra level |
|---|---|---|---|
| Spark Wand | fires a ring of sparks (speed 1000 px/s) that keeps turning at 180 deg/s, so it covers all 360 degrees | 10 damage, every 0.8 s, 8 sparks | +3 damage, 0.08 s faster; +1 spark at levels 3 and 5 |
| Spin Blades | blades circle the hero at 60 px, one turn every 1.5 s; each blade hits an enemy at most every 0.5 s | 2 blades, 8 damage | +3 damage; +1 blade at levels 2 and 4 |
| Holy Ring | hurts every enemy inside a circle around the hero, every 0.5 s | 5 damage, radius 50 px | +2 damage, +10 px radius |

## Passive items (levels 1–5)
| Item | Each level |
|---|---|
| Swift Boots | +10% walking speed |
| Big Heart | +20 max HP and heal 20 |
| Magnet | +30 px gem magnet radius |

## Enemies
| Enemy | HP | Speed | Damage | XP | Picture |
|---|---|---|---|---|---|
| Bat | 8 | 100 | 5 | 1 | bat.png |
| Slime | 30 | 55 | 8 | 2 | slime.png |
| Ghost | 15 | 230 (faster than you) | 6 | 2 | ghost.png |
| Boss: Demon | 800 | 85 | 20 | 0 | demon.png, drawn twice as big |

An enemy that touches the hero hurts him at most once every 0.5 s.

## How enemies appear (the map is endless, so enemies come to you)
- Every 1 s: if fewer enemies are alive than the **minimum** for this time, spawn new ones
  (at most 8 per second) until the minimum is reached.
- New enemies appear at a random point on a circle 380 px from the hero, just outside the screen.
- Any normal enemy more than 700 px from the hero is removed. New ones will come.
- The boss is never removed: if it is more than 600 px away, move it back to the 380 px circle.
- Never more than 120 enemies alive (140 on HARD).

| From | Enemy types | Minimum alive |
|---|---|---|
| 0:00 | Bat | 12 |
| 0:15 | Bat | 20 |
| 0:30 | Bat, Slime | 28 |
| 0:45 | Slime, Ghost | 36 |
| 1:00 | Bat, Ghost | 45 |
| 1:15 | Bat, Slime, Ghost | 55 |
| 1:30 | the boss appears once; Bat, Slime | 55 |
| 1:45 | Bat | 75 |

## Difficulty modes
- The game starts on a picker with three buttons: EASY, NORMAL, HARD. Click, tap or press 1, 2 or 3.
- All three are the same game. `data/difficulties.json` only holds the numbers that differ from
  NORMAL, and the program lays them over `data/game.json` before the rules start.
  NORMAL changes nothing, so it is exactly the table above.
- EASY: 1:30, 150 HP, a much thinner crowd (6 alive at the start, 24 at the end), weaker Bats
  and a 400 HP boss at 1:15.
- HARD: 2:20, the same first 1:15 as NORMAL but with the boss 15 s early (1:15) at 1000 HP,
  and after that the crowd keeps growing (66, 80, 95 alive) instead of resting at 55.
  Enemy damage and Ghost HP are left alone on purpose: a test bot showed that
  +3 HP on a Ghost already makes the 0:45-1:15 swarm unplayable.
- The end screen keeps the best run per mode (time, kills, level) in `data/records.json`.
  In a browser that file cannot be written, so the record is simply skipped.

## XP and level-up
- Every dead enemy drops a gem worth its XP. Gems inside the magnet radius fly to the hero (300 px/s).
- XP needed for the next level: 5 at level 1, then 3 more each level (5, 8, 11, 14, ...).
- Level-up: the game pauses and shows 3 random cards. A card is a new weapon (if fewer than 3),
  +1 level for a weapon you have, or a passive item. Never offer something already at level 5.
  If nothing is left, offer "Heal 30 HP".

## What the screen shows
- Top left: HP bar (red), XP bar (blue) and "Lv 3".
- Top right: the timer, for example "0:45 / 2:00".
- Bottom: what you have, for example "Spark 2  Blades 1  Boots 1".
- Level-up: 3 big cards, each with a name, the new level and one line of text.
- End: VICTORY or GAME OVER, with time, kills and level.

## Build steps (build one step at a time, only when asked)
1. **Core:** hero and controls, camera and repeating floor, Bats with the spawning rules,
   contact damage, Spark Wand, HP, GAME OVER and play again. Coloured shapes, no pictures yet.
2. **Pictures:** make_assets.py makes 3x bigger copies of raw_art/ with Pillow (no blurring),
   plus two bright crystal gems coloured from raw_art/gem.png: blue for XP 1, pink for XP 2.
   main.py draws them.
3. **Growth:** gems, XP, level-up cards, all weapons and passive items.
4. **Waves:** the whole table above, Slime, Ghost, the boss, VICTORY at 2:00, the timer.
5. **Sound and feel:** make_sounds.py (standard library only) makes short sounds for hits,
   gems, level-up, getting hurt and the end; damage numbers, a flash when an enemy dies,
   a small shake when the hero is hurt.
6. **Balance and difficulty:** data/difficulties.json with EASY / NORMAL / HARD as number
   overrides, a mode picker at the start, and a best-run record per mode. No new rules in
   rules.py except merging the overrides.

## Changes we made while building
The numbers above already include the changes we actually made, so the tables match the game.
What we changed from the first draft, and why:
- Window 390 x 700 → **500 x 600**: 390 px wide left no room for the bars and the card text.
- Hero speed 120 → **200 px/s** and magnet 60 → **80 px**: at 120 the hero could not outrun anything
  and gathering felt random.
- Ghost speed 135 → **230 px/s**: it was only faster than the old 120 px/s hero. The design is
  "the Ghost chases you down", so it had to move above the new hero speed.
- Spark Wand "1 spark at the nearest enemy, 400 px/s" → **8 sparks in a ring that turns at 180 deg/s,
  1000 px/s**: a single homing shot left the whole screen behind you safe. The turning ring covers
  360 degrees, which is what makes walking away from the crowd work.
- Boss HP: NORMAL keeps 800, EASY 400, HARD 1000. A maxed three-weapon build does about
  126 damage per second spread over the crowd, so 800 HP is only burned off if you are already
  strong and the area around the boss is clear.
