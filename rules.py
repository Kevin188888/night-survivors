"""Game rules for Steps 1-5 and the difficulty modes. One step is 1/60 second; no pygame here.

Every step also writes down what happened (a hit, a death, a gem, getting hurt,
a level-up, the end) in self.events, so main.py can answer with a sound or an effect.
The rules never play anything themselves.
"""

import copy
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import random

DATA = Path(__file__).parent / "data"


def merge(base, numbers):
    """base with numbers laid over it: a dict merges key by key, anything else replaces it."""
    out = copy.deepcopy(base)
    for key, value in numbers.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_modes():
    """The difficulty list from data/difficulties.json, in the order the screen shows it."""
    with (DATA / "difficulties.json").open(encoding="utf-8") as file:
        return json.load(file)["modes"]


def mode_numbers(name):
    """The numbers one difficulty changes. An unknown name changes nothing."""
    for mode in load_modes():
        if mode["name"] == name:
            return copy.deepcopy(mode.get("numbers", {}))
    return {}


def load_config(difficulty=None):
    """All the numbers for one run: game.json, with one difficulty laid over it."""
    with (DATA / "game.json").open(encoding="utf-8") as file:
        base = json.load(file)
    return base if difficulty is None else merge(base, mode_numbers(difficulty))


def items_only(section):
    """The real entries of a config section, skipping numbers and _说明 text."""
    return {name: stats for name, stats in section.items() if isinstance(stats, dict)}


@dataclass
class Hero:
    x: float
    y: float
    hp: float
    max_hp: float
    speed: float
    radius: float
    level: int = 1
    xp: float = 0.0
    weapons: dict = field(default_factory=dict)
    passives: dict = field(default_factory=dict)


@dataclass
class Enemy:
    x: float
    y: float
    hp: float
    speed: float
    damage: float
    radius: float
    xp: float = 0.0
    contact_cooldown: float = 0.0
    kind: str = ""
    boss: bool = False
    blade_cooldowns: dict = field(default_factory=dict)


@dataclass
class Spark:
    x: float
    y: float
    vx: float
    vy: float
    damage: float
    radius: float
    remaining_seconds: float


@dataclass
class Gem:
    x: float
    y: float
    xp: float


@dataclass
class Event:
    """Something that just happened, so the screen can answer with a sound or an effect.

    amount means a different thing per kind: the damage for "hit" and "hurt",
    the size of the enemy for "kill", the new level for "level_up".
    """

    kind: str
    x: float = 0.0
    y: float = 0.0
    amount: float = 0.0


def hit_fraction(x, y, next_x, next_y, enemy, radius):
    """Find the first contact along a spark's path (so fast sparks cannot skip bats)."""
    dx, dy = next_x - x, next_y - y
    ox, oy = x - enemy.x, y - enemy.y
    c = ox * ox + oy * oy - (radius + enemy.radius) ** 2
    if c <= 0:
        return 0.0
    a = dx * dx + dy * dy
    if a == 0:
        return None
    b = 2 * (ox * dx + oy * dy)
    discriminant = b * b - 4 * a * c
    if discriminant < 0:
        return None
    fraction = (-b - math.sqrt(discriminant)) / (2 * a)
    return fraction if 0 <= fraction <= 1 else None


class Game:
    def __init__(self, config=None, seed=None):
        self.config = config if config is not None else load_config()
        self.rng = random.Random(seed)
        self.dt = self.config["simulation"]["fixed_step_seconds"]
        self.reset()

    def reset(self):
        stats = self.config["hero"]
        self.hero = Hero(0, 0, stats["hp"], stats["hp"], stats["speed"], stats["hit_radius"])
        self.hero.weapons[self.config["weapons"]["starting_weapon"]] = 1
        self.enemies = []
        self.sparks = []
        self.gems = []
        self.elapsed = 0.0
        self.kills = 0
        self.paused = False
        self.choice_queue = []
        self.events = []
        self._spawn_elapsed = 0.0
        self._boss_spawned = False
        self._end_told = False
        self._cooldowns = {name: 0.0 for name in items_only(self.config["weapons"])}
        self._blade_angle = 0.0

    def _happen(self, kind, x=0.0, y=0.0, amount=0.0):
        self.events.append(Event(kind, x, y, amount))

    def take_events(self):
        """Everything that happened since the last frame; the list is emptied."""
        events, self.events = self.events, []
        return events

    @property
    def game_over(self):
        return self.hero.hp <= 0

    @property
    def won(self):
        return self.elapsed >= self.config["run"]["victory_seconds"]

    @property
    def finished(self):
        """True when the run is over, whatever the reason."""
        return self.game_over or self.won

    def toggle_pause(self):
        if not self.finished and not self.choice_queue:
            self.paused = not self.paused

    # --- what the passive items give -------------------------------------
    def walk_speed(self):
        boots = self.hero.passives.get("swift_boots", 0)
        per_level = self.config["passives"]["swift_boots"]["speed_fraction_per_level"]
        return self.hero.speed * (1 + per_level * boots)

    def magnet_range(self):
        magnet = self.hero.passives.get("magnet", 0)
        per_level = self.config["passives"]["magnet"]["radius_per_level"]
        return self.config["hero"]["magnet_radius"] + per_level * magnet

    # --- XP and level-up cards -------------------------------------------
    def xp_needed(self):
        cost = self.config["xp"]
        return cost["first_level_cost"] + cost["cost_increase"] * (self.hero.level - 1)

    def gain_xp(self, amount):
        self.hero.xp += amount
        while self.hero.xp >= self.xp_needed():
            self.hero.xp -= self.xp_needed()
            self.hero.level += 1
            self._happen("level_up", amount=self.hero.level)
            self.choice_queue.append(self.make_cards())

    def card_pool(self):
        """Everything that can still be offered: nothing at max level."""
        options = []
        weapons = self.config["weapons"]
        for name, stats in items_only(weapons).items():
            owned = self.hero.weapons.get(name, 0)
            if owned >= weapons["maximum_level"]:
                continue
            if owned == 0 and len(self.hero.weapons) >= weapons["maximum_owned"]:
                continue
            options.append({"kind": "weapon", "item": name, "level": owned + 1,
                            "name": stats["name"], "text": stats["text"]})
        passives = self.config["passives"]
        for name, stats in items_only(passives).items():
            owned = self.hero.passives.get(name, 0)
            if owned >= passives["maximum_level"]:
                continue
            options.append({"kind": "passive", "item": name, "level": owned + 1,
                            "name": stats["name"], "text": stats["text"]})
        return options

    def make_cards(self):
        pool = self.card_pool()
        if not pool:
            heal = self.config["xp"]["fallback_heal"]
            return [{"kind": "heal", "item": "", "level": 0, "name": "Heal",
                     "text": f"Recover {heal:g} HP"}]
        return self.rng.sample(pool, min(self.config["xp"]["card_count"], len(pool)))

    def current_cards(self):
        return self.choice_queue[0] if self.choice_queue else []

    def choose(self, index):
        """Take card number index and start the game running again."""
        cards = self.current_cards()
        if not 0 <= index < len(cards):
            return False
        card = cards[index]
        if card["kind"] == "weapon":
            self.hero.weapons[card["item"]] = card["level"]
        elif card["kind"] == "passive":
            self.hero.passives[card["item"]] = card["level"]
            if card["item"] == "big_heart":
                heart = self.config["passives"]["big_heart"]
                self.hero.max_hp += heart["max_hp_per_level"]
                self.hero.hp = min(self.hero.max_hp, self.hero.hp + heart["heal_per_level"])
        else:
            self.hero.hp = min(self.hero.max_hp,
                               self.hero.hp + self.config["xp"]["fallback_heal"])
        self.choice_queue.pop(0)
        return True

    # --- the step ---------------------------------------------------------
    def step(self, pointer_offset=None):
        """Advance one fixed step. The pointer offset is measured from screen centre.

        None means no active touch. A stationary mouse still supplies its offset
        every step, so the hero keeps walking while the camera follows.
        """
        if self.paused or self.finished or self.choice_queue:
            return
        self.elapsed += self.dt
        if pointer_offset is not None:
            dx, dy = pointer_offset
            distance = math.hypot(dx, dy)
            if distance > self.config["controls"]["mouse_dead_zone"]:
                speed = self.walk_speed()
                self.hero.x += dx / distance * speed * self.dt
                self.hero.y += dy / distance * speed * self.dt

        self._move_stray_enemies()
        self._spawn_elapsed += self.dt
        interval = self.config["spawning"]["interval_seconds"]
        while self._spawn_elapsed + 1e-9 >= interval:
            self._spawn_elapsed -= interval
            self._spawn_wave()

        for enemy in self.enemies:
            distance = self.distance_to(enemy)
            if distance:
                travel = min(enemy.speed * self.dt, distance)
                enemy.x += (self.hero.x - enemy.x) / distance * travel
                enemy.y += (self.hero.y - enemy.y) / distance * travel
            enemy.contact_cooldown = max(0, enemy.contact_cooldown - self.dt)
            for blade in enemy.blade_cooldowns:
                enemy.blade_cooldowns[blade] = max(0, enemy.blade_cooldowns[blade] - self.dt)

        self._update_weapons()
        self._move_sparks()
        self._drop_gems_for_corpses()
        self._update_gems()

        for enemy in self.enemies:
            if self.distance_to(enemy) <= self.hero.radius + enemy.radius:
                if enemy.contact_cooldown <= 1e-9:
                    self.hero.hp = max(0, self.hero.hp - enemy.damage)
                    enemy.contact_cooldown = self.config["contact"]["interval_seconds"]
                    self._happen("hurt", self.hero.x, self.hero.y, enemy.damage)
                    if self.game_over:
                        break

        if self.finished and not self._end_told:
            self._end_told = True
            self._happen("end", amount=1.0 if self.won else 0.0)

    def distance_to(self, item):
        return math.hypot(item.x - self.hero.x, item.y - self.hero.y)

    # --- spawning -----------------------------------------------------------
    def stage(self, at_seconds=None):
        """The row of the spawning table that is in force right now."""
        stages = self.config["spawning"]["stages"]
        now = self.elapsed if at_seconds is None else at_seconds
        current = stages[0]
        for stage in stages:
            if stage["from_seconds"] <= now:
                current = stage
        return current

    def _spawn_at_circle(self, kind):
        """One enemy of that kind, on the circle just outside the screen."""
        stats = self.config["enemies"][kind]
        settings = self.config["spawning"]
        angle = self.rng.uniform(0, math.tau)
        return Enemy(
            self.hero.x + math.cos(angle) * settings["radius"],
            self.hero.y + math.sin(angle) * settings["radius"],
            stats["hp"], stats["speed"], stats["damage"], stats["hit_radius"],
            xp=stats["xp"], kind=kind, boss=stats.get("boss", False),
        )

    def _spawn_wave(self):
        settings = self.config["spawning"]
        stage = self.stage()
        if stage.get("boss") and not self._boss_spawned:
            self._boss_spawned = True
            self.enemies.append(self._spawn_at_circle(stage["boss"]))
        count = max(0, min(stage["minimum_alive"] - len(self.enemies),
                           settings["maximum_per_interval"],
                           settings["maximum_alive"] - len(self.enemies)))
        for _ in range(count):
            kind = self.rng.choice(stage["types"])
            self.enemies.append(self._spawn_at_circle(kind))

    def _move_stray_enemies(self):
        """Normal enemies far away are removed; the boss is only carried back."""
        settings = self.config["spawning"]
        kept = []
        for enemy in self.enemies:
            distance = self.distance_to(enemy)
            if enemy.boss:
                if distance > settings["boss_return_distance"]:
                    boss = self._spawn_at_circle(enemy.kind)
                    boss.hp = enemy.hp
                    kept.append(boss)
                else:
                    kept.append(enemy)
            elif distance <= settings["remove_distance"]:
                kept.append(enemy)
        self.enemies = kept

    # --- weapons ----------------------------------------------------------
    def _update_weapons(self):
        for name, level in self.hero.weapons.items():
            if name == "spin_blades":
                self._spin_blades(level)
                continue
            self._cooldowns[name] = max(0.0, self._cooldowns[name] - self.dt)
            if self._cooldowns[name] > 1e-9:
                continue
            if name == "spark_wand":
                self._shoot(level)
            elif name == "holy_ring":
                self._holy_ring(level)

    def spark_wand_stats(self, level):
        stats = self.config["weapons"]["spark_wand"]
        extra = level - 1
        return {
            "damage": stats["damage"] + stats["damage_per_level"] * extra,
            "interval": stats["interval_seconds"] + stats["interval_reduction_per_level"] * extra,
            "count": stats["spark_count"] + len([n for n in stats["extra_spark_levels"] if level >= n]),
        }

    def _shoot(self, level):
        if not self.enemies:
            return
        stats = self.config["weapons"]["spark_wand"]
        wand = self.spark_wand_stats(level)
        nearest = min(self.enemies, key=self.distance_to)
        # One spark starts on the nearest enemy and the whole ring keeps turning,
        # so the shots sweep all 360 degrees as time passes.
        aim = math.atan2(nearest.y - self.hero.y, nearest.x - self.hero.x)
        base = aim + math.radians(stats["spin_degrees_per_second"]) * self.elapsed
        for index in range(wand["count"]):
            angle = base + math.tau * index / wand["count"]
            self.sparks.append(Spark(
                self.hero.x, self.hero.y,
                math.cos(angle) * stats["spark_speed"], math.sin(angle) * stats["spark_speed"],
                wand["damage"], stats["hit_radius"], stats["lifetime_seconds"],
            ))
        self._cooldowns["spark_wand"] = wand["interval"]

    def blade_count(self, level):
        stats = self.config["weapons"]["spin_blades"]
        return stats["blade_count"] + len([n for n in stats["extra_blade_levels"] if level >= n])

    def blade_positions(self):
        """Where the blades are right now, so the rules and the screen agree."""
        level = self.hero.weapons.get("spin_blades", 0)
        if not level:
            return []
        stats = self.config["weapons"]["spin_blades"]
        count = self.blade_count(level)
        return [(self.hero.x + math.cos(self._blade_angle + math.tau * i / count) * stats["orbit_radius"],
                 self.hero.y + math.sin(self._blade_angle + math.tau * i / count) * stats["orbit_radius"])
                for i in range(count)]

    def _spin_blades(self, level):
        stats = self.config["weapons"]["spin_blades"]
        self._blade_angle = (self._blade_angle + math.tau * self.dt / stats["orbit_seconds"]) % math.tau
        damage = stats["damage"] + stats["damage_per_level"] * (level - 1)
        for index, (blade_x, blade_y) in enumerate(self.blade_positions()):
            for enemy in self.enemies:
                if enemy.blade_cooldowns.get(index, 0) > 1e-9:
                    continue
                if math.hypot(enemy.x - blade_x, enemy.y - blade_y) <= stats["hit_radius"] + enemy.radius:
                    enemy.blade_cooldowns[index] = stats["hit_interval_seconds"]
                    self._damage(enemy, damage)

    def _damage(self, enemy, amount):
        """A weapon landed: take the HP and write down what happened."""
        enemy.hp -= amount
        self._happen("hit", enemy.x, enemy.y, amount)

    def holy_ring_radius(self):
        level = self.hero.weapons.get("holy_ring", 0)
        if not level:
            return 0
        stats = self.config["weapons"]["holy_ring"]
        return stats["radius"] + stats["radius_per_level"] * (level - 1)

    def _holy_ring(self, level):
        stats = self.config["weapons"]["holy_ring"]
        radius = self.holy_ring_radius()
        damage = stats["damage"] + stats["damage_per_level"] * (level - 1)
        for enemy in self.enemies:
            if self.distance_to(enemy) <= radius + enemy.radius:
                self._damage(enemy, damage)
        self._cooldowns["holy_ring"] = stats["interval_seconds"]

    def _move_sparks(self):
        remaining = []
        for spark in self.sparks:
            spark.remaining_seconds -= self.dt
            if spark.remaining_seconds <= 0:
                continue
            next_x = spark.x + spark.vx * self.dt
            next_y = spark.y + spark.vy * self.dt
            target, first_hit = None, math.inf
            for enemy in self.enemies:
                fraction = hit_fraction(spark.x, spark.y, next_x, next_y, enemy, spark.radius)
                if fraction is not None and fraction < first_hit:
                    target, first_hit = enemy, fraction
            if target is None:
                spark.x, spark.y = next_x, next_y
                remaining.append(spark)
            else:
                self._damage(target, spark.damage)
        self.sparks = remaining

    def _drop_gems_for_corpses(self):
        alive = []
        for enemy in self.enemies:
            if enemy.hp > 0:
                alive.append(enemy)
            else:
                self.kills += 1
                self._happen("kill", enemy.x, enemy.y, enemy.radius)
                if enemy.xp:
                    self.gems.append(Gem(enemy.x, enemy.y, enemy.xp))
        self.enemies = alive

    # --- gems -------------------------------------------------------------
    def _update_gems(self):
        reach = self.magnet_range()
        speed = self.config["xp"]["gem_speed"]
        collected = 0.0
        left = []
        for gem in self.gems:
            distance = self.distance_to(gem)
            if distance <= self.hero.radius:
                collected += gem.xp
                self._happen("gem", gem.x, gem.y, gem.xp)
                continue
            if distance <= reach:
                travel = min(speed * self.dt, distance)
                gem.x += (self.hero.x - gem.x) / distance * travel
                gem.y += (self.hero.y - gem.y) / distance * travel
            left.append(gem)
        self.gems = left
        if collected:
            self.gain_xp(collected)
