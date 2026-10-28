"""Night Survivors, Steps 2-6: the screen, the sound and the input.

This file only reads finished files: pictures from assets/, sounds from sounds/.
make_assets.py and make_sounds.py are the scripts that write them.
All the rules live in rules.py.
"""

import asyncio
import json
import math
from pathlib import Path

import pygame

from rules import Game, load_config, load_modes

ASSETS = Path(__file__).parent / "assets"
SOUNDS = Path(__file__).parent / "sounds"
RECORDS = Path(__file__).parent / "data" / "records.json"


INK = (230, 240, 248)
MUTED = (132, 154, 178)
TEAL = (83, 232, 195)
GOLD = (255, 218, 112)
PANEL = (15, 23, 38)
CARD = (28, 41, 62)
CARD_EDGE = (74, 100, 128)
HP_COLOUR = (241, 100, 118)
XP_COLOUR = (96, 156, 255)
RING_COLOUR = (255, 235, 160)


def clock_text(seconds):
    """Seconds as 0:45."""
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def load_records():
    """The best run of each mode, or nothing at all if the file is missing or broken."""
    try:
        with RECORDS.open(encoding="utf-8") as file:
            saved = json.load(file)
    except (OSError, ValueError):
        return {}
    return {name: run for name, run in saved.items() if isinstance(run, dict)}


def save_records(records):
    """Write the records back. A browser build cannot write files, so failing here is normal."""
    try:
        with RECORDS.open("w", encoding="utf-8") as file:
            json.dump(records, file, ensure_ascii=False, indent=2)
            file.write("\n")
        return True
    except OSError:
        return False


def best_line(run):
    """The record for one mode as the text on the buttons and the end screen."""
    if run is None:
        return "no run yet"
    return (f"{clock_text(run['seconds'])}  {run['kills']} defeated  "
            f"Lv {run['level']}  {'won' if run['won'] else 'lost'}")


def score_of(run):
    """What makes one run better than another: winning, then surviving, then killing."""
    return (run["won"], run["seconds"], run["kills"])


class Run:
    """One difficulty, ready to play: its own rules, picture set, sounds and pointer."""

    def __init__(self, screen, mode):
        self.mode = mode
        self.config = load_config(mode["name"])
        self.game = Game(self.config)
        self.controls = Controls(screen.get_size())
        self.view = View(screen, self.config)
        self.sounds = Sounds(self.config)

    def restart(self):
        self.game.reset()
        self.controls.reset()
        self.view.clear_effects()


class Picker:
    """The first screen: three difficulty buttons, click, tap or press 1, 2 or 3."""

    def __init__(self, screen, modes, records):
        self.screen = screen
        self.width, self.height = screen.get_size()
        self.fonts = {size: pygame.font.Font(None, size) for size in (18, 21, 25, 45)}
        self.modes = modes
        self.records = records
        self.rects = []

    def record(self, name, game):
        """Keep the best run of this mode and write it to data/records.json."""
        run = {"seconds": round(game.elapsed, 1), "kills": game.kills,
               "level": game.hero.level, "won": game.won}
        best = self.records.get(name)
        if best is None or score_of(run) > score_of(best):
            self.records[name] = run
            save_records(self.records)

    def mode_at(self, position):
        for index, rect in enumerate(self.rects):
            if rect.collidepoint(position):
                return self.modes[index]
        return None

    def mode_for_key(self, key):
        for index, mode in enumerate(self.modes):
            if key == pygame.K_1 + index:
                return mode
        return None

    def text(self, words, size, color, position, center=False):
        surface = self.fonts[size].render(words, True, color)
        rect = surface.get_rect(center=position) if center else surface.get_rect(topleft=position)
        self.screen.blit(surface, rect)

    def draw(self):
        self.screen.fill(PANEL)
        middle = self.width // 2
        self.text("NIGHT SURVIVORS", 45, GOLD, (middle, 74), True)
        self.text("choose a difficulty", 21, MUTED, (middle, 118), True)
        self.rects = []
        gap, height, top = 18, 96, 168
        for index, mode in enumerate(self.modes):
            rect = pygame.Rect(28, top + index * (height + gap), self.width - 56, height)
            pygame.draw.rect(self.screen, CARD, rect, border_radius=14)
            pygame.draw.rect(self.screen, CARD_EDGE, rect, 1, border_radius=14)
            self.text(f"{index + 1}   {mode['label']}", 25, INK, (rect.x + 18, rect.y + 12))
            self.text(mode["text"], 18, MUTED, (rect.x + 18, rect.y + 48))
            record = self.records.get(mode["name"])
            self.text(f"best  {best_line(record)}" if record else "no run yet", 18, TEAL,
                      (rect.x + 18, rect.y + 70))
            self.rects.append(rect)
        self.text("Click, tap or press 1, 2, 3      Esc: quit", 18, INK,
                  (middle, self.height - 34), True)


class Controls:
    """Remember the pointer between events, and ignore touch-generated mouse events."""

    def __init__(self, size):
        self.width, self.height = size
        self.reset()

    def reset(self):
        self.pointer = (self.width / 2, self.height / 2)
        self.touch_mode = False
        self.finger = None

    def handle(self, event):
        if event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP):
            if event.type == pygame.FINGERDOWN and self.finger is None:
                self.finger = event.finger_id
                self.touch_mode = True
            if event.finger_id == self.finger:
                self.pointer = (event.x * self.width, event.y * self.height)
                if event.type == pygame.FINGERUP:
                    self.finger = None
        elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            if not getattr(event, "touch", False) and self.finger is None:
                self.touch_mode = False
                self.pointer = event.pos

    def offset(self):
        if self.touch_mode and self.finger is None:
            return None
        return self.pointer[0] - self.width / 2, self.pointer[1] - self.height / 2


def load_picture(name, size=None):
    """One picture from assets/, optionally resized with whole pixels (no blurring)."""
    path = ASSETS / name
    if not path.exists():
        raise SystemExit(f"{path} is missing. Run  python make_assets.py  first.")
    picture = pygame.image.load(path).convert_alpha()
    if size is not None and picture.get_width() != size:
        picture = pygame.transform.scale(picture, (size, size))
    return picture


class Sounds:
    """The five short clips from sounds/, played when something happens in the rules.

    A clip is sounds/<name>.ogg if it is there, otherwise sounds/<name>.wav. If the
    computer has no sound device, or make_sounds.py was never run, the game just
    plays silently instead of crashing.
    """

    NAMES = ("hit", "gem", "level_up", "hurt", "end")

    def __init__(self, config):
        self.config = config
        self.clips = {}
        self.since = {name: 0.0 for name in self.NAMES}
        try:
            pygame.mixer.init(frequency=44100, buffer=512)
        except pygame.error:
            print("No sound device. The game plays silently.")
            return
        for name in self.NAMES:
            for extension in (".ogg", ".wav"):
                path = SOUNDS / f"{name}{extension}"
                if path.exists():
                    clip = pygame.mixer.Sound(path)
                    clip.set_volume(config["feel"]["volume"])
                    self.clips[name] = clip
                    break
        if not self.clips:
            print(f"Nothing in {SOUNDS}. Run  python make_sounds.py  once.")

    def play(self, events, seconds):
        """One clip per kind of event per frame, with a small gap so it is not a mess."""
        gaps = {"hit": self.config["feel"]["hit_gap_seconds"],
                "gem": self.config["feel"]["gem_gap_seconds"]}
        for name in self.since:
            self.since[name] += seconds
        for event in events:
            clip = self.clips.get(event.kind)
            if clip is None or self.since[event.kind] < gaps.get(event.kind, 0.0):
                continue
            clip.play()
            self.since[event.kind] = 0.0


class View:
    def __init__(self, screen, config):
        self.screen = screen
        self.config = config
        self.width, self.height = screen.get_size()
        self.fonts = {size: pygame.font.Font(None, size) for size in (18, 21, 25, 30, 45)}
        drawing = config["drawing"]
        self.tile = load_picture("floor.png", drawing["floor_tile_size"])
        self.hero_picture = load_picture("hero.png", drawing["sprite_size"])
        self.pictures = {
            kind: load_picture(stats["picture"], drawing["sprite_size"] * stats.get("draw_scale", 1))
            for kind, stats in config["enemies"].items()
        }
        self.gem_pictures = [load_picture(name, drawing["gem_size"])
                             for name in config["xp"]["gem_pictures"]]
        self.blade_picture = load_picture(config["weapons"]["spin_blades"]["picture"],
                                          drawing["sprite_size"])
        self.card_rects = []
        # Step 5: the small effects that answer what the rules reported.
        self.marks = []        # damage numbers: [x, y, text, age]
        self.flashes = []      # dying enemies:   [x, y, radius, age]
        self.shake_left = 0.0  # seconds of screen shake still to play
        self.shake_time = 0.0
        self.shake_dx = 0.0
        self.shake_dy = 0.0

    # --- the feel: damage numbers, death flashes, screen shake ------------
    def clear_effects(self):
        """A new run starts with a clean screen."""
        self.marks.clear()
        self.flashes.clear()
        self.shake_left = self.shake_dx = self.shake_dy = 0.0

    def feel(self, events, seconds, hero):
        """Take the events of this frame and turn them into short-lived effects."""
        feel = self.config["feel"]
        for event in events:
            if event.kind not in ("hit", "kill", "hurt"):
                continue                      # the sounds already covered level-up, gems, the end
            if event.kind == "hurt":
                self.shake_left = feel["shake_seconds"]
                continue
            x, y = self.at(event.x, event.y, hero)
            if not (-60 <= x <= self.width + 60 and -60 <= y <= self.height + 60):
                continue                      # it happened off screen, so nobody could see it
            if event.kind == "hit":
                self.marks.append([event.x, event.y, f"{event.amount:g}", 0.0, event.amount])
                if len(self.marks) > feel["damage_number_maximum"]:
                    self.marks.pop(0)
            else:
                self.flashes.append([event.x, event.y, event.amount, 0.0])
        for group in (self.marks, self.flashes):
            for effect in group:
                effect[3] += seconds
        self.marks = [mark for mark in self.marks
                      if mark[3] < feel["damage_number_seconds"]]
        self.flashes = [flash for flash in self.flashes
                        if flash[3] < feel["flash_seconds"]]
        self.shake_left = max(0.0, self.shake_left - seconds)
        self.shake_time += seconds
        if self.shake_left:
            strength = feel["shake_pixels"] * self.shake_left / feel["shake_seconds"]
            self.shake_dx = math.sin(self.shake_time * 61) * strength
            self.shake_dy = math.cos(self.shake_time * 47) * strength
        else:
            self.shake_dx = self.shake_dy = 0.0

    def view_centre(self):
        return (round(self.width / 2 + self.shake_dx), round(self.height / 2 + self.shake_dy))

    # --- small helpers ---------------------------------------------------
    def text(self, words, size, color, position, center=False):
        surface = self.fonts[size].render(words, True, color)
        rect = surface.get_rect(center=position) if center else surface.get_rect(topleft=position)
        self.screen.blit(surface, rect)

    def world_position(self, item, hero):
        return self.at(item.x, item.y, hero)

    def at(self, x, y, hero):
        centre = self.view_centre()
        return (round(x - hero.x + centre[0]), round(y - hero.y + centre[1]))

    def blit_centred(self, picture, position):
        self.screen.blit(picture, picture.get_rect(center=position))

    def inventory_line(self, game):
        owned = [f"{self.config['weapons'][name]['short']} {level}"
                 for name, level in game.hero.weapons.items()]
        owned += [f"{self.config['passives'][name]['short']} {level}"
                  for name, level in game.hero.passives.items()]
        return "   ".join(owned)

    def card_at(self, position):
        for index, rect in enumerate(self.card_rects):
            if rect.collidepoint(position):
                return index
        return None

    # --- the world -------------------------------------------------------
    def draw(self, game, controls, summary=""):
        hero = game.hero
        centre = self.view_centre()
        tile_size = self.tile.get_width()
        origin_x = round(centre[0] - hero.x) % tile_size - tile_size
        origin_y = round(centre[1] - hero.y) % tile_size - tile_size
        for x in range(origin_x, self.width, tile_size):
            for y in range(origin_y, self.height, tile_size):
                self.screen.blit(self.tile, (x, y))

        self.draw_holy_ring(game)

        for gem in game.gems:
            picture = self.gem_pictures[min(int(gem.xp) - 1, len(self.gem_pictures) - 1)]
            self.blit_centred(picture, self.world_position(gem, hero))

        for enemy in sorted(game.enemies, key=lambda enemy: enemy.boss):   # the boss on top
            self.blit_centred(self.pictures[enemy.kind], self.world_position(enemy, hero))

        self.draw_flashes(hero)

        for spark in game.sparks:
            x, y = self.world_position(spark, hero)
            speed = math.hypot(spark.vx, spark.vy)
            if speed:
                tail = (round(x - spark.vx / speed * 12), round(y - spark.vy / speed * 12))
                pygame.draw.line(self.screen, (180, 133, 64), tail, (x, y), 3)
            pygame.draw.circle(self.screen, GOLD, (x, y), round(spark.radius))
            pygame.draw.circle(self.screen, (255, 250, 225), (x, y), 2)

        size = self.hero_picture.get_width()
        pygame.draw.ellipse(self.screen, (15, 24, 35),
                            (centre[0] - size // 3, centre[1] + size // 2 - 8,
                             size * 2 // 3, size // 4))
        self.blit_centred(self.hero_picture, centre)
        for blade_x, blade_y in game.blade_positions():
            self.blit_centred(self.blade_picture, self.at(blade_x, blade_y, hero))

        offset = controls.offset()
        if offset and math.hypot(*offset) > game.config["controls"]["mouse_dead_zone"]:
            distance = math.hypot(*offset)
            tip = (round(centre[0] + offset[0] / distance * 22),
                   round(centre[1] + offset[1] / distance * 22))
            pygame.draw.circle(self.screen, TEAL, tip, 3)

        self.draw_marks(hero)
        self.draw_hud(game)
        self.card_rects = []
        if game.finished:
            self.draw_end_screen(game, summary)
        elif game.current_cards():
            self.draw_cards(game)
        elif game.paused:
            self.draw_pause_screen()
        pygame.display.flip()

    def draw_holy_ring(self, game):
        radius = game.holy_ring_radius()
        if not radius:
            return
        box = pygame.Surface((radius * 2 + 12,) * 2, pygame.SRCALPHA)
        centre = (box.get_width() // 2,) * 2
        pygame.draw.circle(box, (*RING_COLOUR, 34), centre, radius, width=7)
        pygame.draw.circle(box, (*RING_COLOUR, 90), centre, radius, width=2)
        self.screen.blit(box, box.get_rect(center=self.view_centre()))

    def draw_flashes(self, hero):
        """A white ring that grows and fades where an enemy just died."""
        feel = self.config["feel"]
        for x, y, radius, age in self.flashes:
            grown = radius + feel["flash_grow_pixels"] * age / feel["flash_seconds"]
            alpha = round(220 * (1 - age / feel["flash_seconds"]))
            box = pygame.Surface((round(grown * 2 + 6),) * 2, pygame.SRCALPHA)
            middle = (box.get_width() // 2,) * 2
            pygame.draw.circle(box, (255, 255, 255, alpha), middle, round(grown), width=3)
            pygame.draw.circle(box, (255, 240, 200, round(alpha * 0.35)), middle,
                               round(grown * 0.6))
            self.screen.blit(box, box.get_rect(center=self.at(x, y, hero)))

    def draw_marks(self, hero):
        """The damage numbers, floating up and fading away."""
        feel = self.config["feel"]
        for x, y, words, age, amount in self.marks:
            progress = age / feel["damage_number_seconds"]
            surface = self.fonts[21].render(words, True, GOLD if amount >= 20 else INK)
            surface.set_alpha(round(255 * (1 - progress)))
            place = self.at(x, y, hero)
            place = (place[0], place[1] - round(progress * feel["damage_number_rise_pixels"]))
            self.screen.blit(surface, surface.get_rect(center=place))

    # --- the screen furniture -------------------------------------------
    def draw_bar(self, label, y, ratio, colour, reading):
        self.text(label, 18, MUTED, (24, y))
        bar = pygame.Rect(49, y, self.width - 180, 12)
        pygame.draw.rect(self.screen, (36, 44, 60), bar, border_radius=6)
        fill = bar.copy()
        fill.width = round(bar.width * max(0.0, min(1.0, ratio)))
        if fill.width:
            pygame.draw.rect(self.screen, colour, fill, border_radius=6)
        self.text(reading, 18, INK, (bar.right + 9, y - 1))

    def draw_hud(self, game):
        hero = game.hero
        pygame.draw.rect(self.screen, PANEL, (12, 14, self.width - 24, 112), border_radius=14)
        self.text("NIGHT SURVIVORS", 25, INK, (24, 22))
        self.text(f"Lv {hero.level}", 25, GOLD, (self.width - 36, 24), True)
        self.draw_bar("HP", 56, hero.hp / hero.max_hp, HP_COLOUR,
                      f"{math.ceil(hero.hp)} / {hero.max_hp:g}")
        self.draw_bar("XP", 78, hero.xp / game.xp_needed(), XP_COLOUR,
                      f"{hero.xp:g} / {game.xp_needed():g}")
        self.text(f"DEFEATED  {game.kills}", 18, MUTED, (24, 100))
        total = self.config["run"]["victory_seconds"]
        self.text(f"{clock_text(game.elapsed)} / {clock_text(total)}", 21, TEAL,
                  (self.width - 80, 98), True)

        pygame.draw.rect(self.screen, PANEL,
                         (12, self.height - 84, self.width - 24, 70), border_radius=14)
        self.text(self.inventory_line(game) or "nothing yet", 21, GOLD, (25, self.height - 72))
        self.text("Mouse to walk / hold a finger   |   P: pause", 18, INK,
                  (25, self.height - 44))

    def shade(self, alpha=210):
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((5, 10, 20, alpha))
        self.screen.blit(overlay, (0, 0))

    def draw_end_screen(self, game, summary):
        self.shade()
        box = pygame.Rect(25, self.height // 2 - 150, self.width - 50, 300)
        pygame.draw.rect(self.screen, CARD, box, border_radius=20)
        pygame.draw.rect(self.screen, CARD_EDGE, box, 1, border_radius=20)
        cx, cy = box.center
        self.text("VICTORY" if game.won else "GAME OVER", 45,
                  GOLD if game.won else INK, (cx, cy - 105), True)
        seconds = int(game.elapsed)
        self.text(f"Survived {seconds // 60}:{seconds % 60:02d}", 25, MUTED, (cx, cy - 58), True)
        self.text(f"{game.kills} defeated  /  Level {game.hero.level}", 21, MUTED, (cx, cy - 30), True)
        if summary:
            self.text(summary, 18, TEAL, (cx, cy + 4), True)
        self.text("R: another difficulty   |   Esc: quit", 18, INK, (cx, cy + 42), True)
        button = pygame.Rect(box.x + 22, box.bottom - 70, box.width - 44, 45)
        pygame.draw.rect(self.screen, TEAL, button, border_radius=10)
        self.text("Click or tap to play again", 25, PANEL, button.center, True)

    def draw_pause_screen(self):
        self.shade()
        box = pygame.Rect(25, self.height // 2 - 70, self.width - 50, 140)
        pygame.draw.rect(self.screen, CARD, box, border_radius=20)
        pygame.draw.rect(self.screen, CARD_EDGE, box, 1, border_radius=20)
        self.text("PAUSED", 45, INK, (box.centerx, box.centery - 22), True)
        self.text("Press P to continue", 21, MUTED, (box.centerx, box.centery + 26), True)

    def draw_cards(self, game):
        """The level-up choice: three cards, click or tap one."""
        self.shade(150)
        cards = game.current_cards()
        self.text("LEVEL UP  -  pick one", 25, GOLD, (self.width // 2, 152), True)
        gap = 14
        room = self.height - 84 - 180 - gap * (len(cards) - 1)
        height = max(60, min(96, room // len(cards)))
        top = 180
        for index, card in enumerate(cards):
            rect = pygame.Rect(28, top + index * (height + gap), self.width - 56, height)
            pygame.draw.rect(self.screen, CARD, rect, border_radius=14)
            pygame.draw.rect(self.screen, CARD_EDGE, rect, 1, border_radius=14)
            self.text(card["name"], 25, INK, (rect.x + 18, rect.y + 12))
            if card["kind"] == "heal":
                self.text("Heal", 21, TEAL, (rect.right - 46, rect.y + 16), True)
            else:
                self.text(f"Lv {card['level']}", 21, TEAL, (rect.right - 40, rect.y + 16), True)
            self.text(card["text"], 18, MUTED, (rect.x + 18, rect.y + 48))
            self.card_rects.append(rect)


async def main():
    pygame.init()
    base = load_config()
    screen = pygame.display.set_mode((base["window"]["width"], base["window"]["height"]))
    pygame.display.set_caption("Night Survivors")
    picker = Picker(screen, load_modes(), load_records())
    clock = pygame.time.Clock()
    run = None                       # nothing chosen yet, so the picker is on screen
    accumulator = 0.0
    running = True
    try:
        while running:
            frame_seconds = min(clock.tick(base["window"]["fps"]) / 1000, 0.25)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif run is None:
                        mode = picker.mode_for_key(event.key)
                        if mode is not None:
                            run = Run(screen, mode)
                            accumulator = 0.0
                    elif event.key == pygame.K_p:
                        run.game.toggle_pause()
                        accumulator = 0.0
                    elif event.key == pygame.K_r:
                        run = None
                else:
                    clicked = (event.type == pygame.MOUSEBUTTONDOWN
                               and event.button == 1 and not getattr(event, "touch", False))
                    tapped = event.type == pygame.FINGERDOWN
                    if clicked or tapped:
                        where = event.pos if clicked else (event.x * picker.width,
                                                           event.y * picker.height)
                        if run is None:
                            mode = picker.mode_at(where)
                            if mode is not None:
                                run = Run(screen, mode)
                                accumulator = 0.0
                        elif run.game.current_cards():
                            choice = run.view.card_at(where)
                            if choice is not None:
                                run.game.choose(choice)
                                accumulator = 0.0
                        elif run.game.finished:
                            run.restart()
                            accumulator = 0.0
                    if run is not None:
                        run.controls.handle(event)

            if run is None:
                picker.draw()
                pygame.display.flip()
            else:
                game, view = run.game, run.view
                if game.paused or game.finished or game.current_cards():
                    accumulator = 0.0
                else:
                    accumulator += frame_seconds
                    while accumulator + 1e-9 >= game.dt:
                        game.step(run.controls.offset())
                        accumulator -= game.dt
                happened = game.take_events()      # everything from the steps of this frame
                run.sounds.play(happened, frame_seconds)
                view.feel(happened, frame_seconds, game.hero)
                if any(event.kind == "end" for event in happened):
                    picker.record(run.mode["name"], game)
                summary = ""
                if game.finished:
                    summary = (f"best on {run.mode['label']}: "
                               f"{best_line(picker.records.get(run.mode['name']))}")
                view.draw(game, run.controls, summary)
            await asyncio.sleep(0)
    finally:
        pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
