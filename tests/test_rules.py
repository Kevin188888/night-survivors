"""Tests for the rules: Core (Step 1), growth (Step 3), waves (Step 4), the reports
the screen uses for sound and feel (Step 5) and the difficulty modes (Step 6).

The sounds and the pictures themselves are not tested, only what rules.py writes down.
Every expected number comes from data/game.json or data/difficulties.json.
"""

import copy
import math
import unittest

from rules import Enemy, Event, Game, Gem, items_only, load_config, load_modes, merge, mode_numbers


class RuleTestBase(unittest.TestCase):
    seed = 7

    def setUp(self):
        self.config = load_config()
        self.game = Game(copy.deepcopy(self.config), seed=self.seed)

    def advance(self, seconds, offset=None):
        for _ in range(round(seconds / self.game.dt)):
            self.game.step(offset)

    def bat(self, x=0, y=0, hp=None, speed=None):
        stats = self.config["enemies"]["bat"]
        return Enemy(x, y, stats["hp"] if hp is None else hp,
                     stats["speed"] if speed is None else speed,
                     stats["damage"], stats["hit_radius"], xp=stats["xp"], kind="bat")

    def no_weapons(self):
        """Take the weapons away so a test sees only what it checks."""
        self.game.hero.weapons.clear()

    def no_spawning(self):
        for stage in self.game.config["spawning"]["stages"]:
            stage["minimum_alive"] = 0

    def first_stage_only(self):
        """Stay in the first row of the spawning table, whatever the time."""
        self.game.config["spawning"]["stages"] = [self.game.config["spawning"]["stages"][0]]

    def still_ring(self):
        """Stop the spark ring from turning, so a shot lands where it was aimed."""
        self.game.config["weapons"]["spark_wand"]["spin_degrees_per_second"] = 0

    def pick(self, kind, item, level=1):
        """Put one card on screen and click it, the way the player does."""
        self.game.choice_queue = [[{"kind": kind, "item": item, "level": level,
                                    "name": "", "text": ""}]]
        self.assertTrue(self.game.choose(0))

    def spark_angles(self, sparks):
        return sorted(round(math.degrees(math.atan2(s.vy, s.vx)) % 360) % 360 for s in sparks)


class CoreRulesTests(RuleTestBase):
    def test_movement_repeats_and_uses_normalized_speed_and_dead_zone(self):
        self.no_weapons()
        self.no_spawning()
        dead_zone = self.config["controls"]["mouse_dead_zone"]
        self.advance(0.5, (dead_zone, 0))
        self.assertEqual((self.game.hero.x, self.game.hero.y), (0, 0))
        self.advance(0.5, (dead_zone * 2, dead_zone * 2))
        self.assertAlmostEqual(math.hypot(self.game.hero.x, self.game.hero.y),
                               self.config["hero"]["speed"] * 0.5)
        before = self.game.hero.x, self.game.hero.y
        self.advance(0.5, None)
        self.assertEqual((self.game.hero.x, self.game.hero.y), before)

    def test_spawning_interval_radius_limit_and_refill(self):
        spawning = self.config["spawning"]
        self.game.config["enemies"]["bat"]["speed"] = 0
        self.no_weapons()
        self.advance(spawning["interval_seconds"] - self.game.dt)
        self.assertEqual(len(self.game.enemies), 0)
        self.game.step()
        first_batch = min(spawning["maximum_per_interval"], spawning["stages"][0]["minimum_alive"])
        self.assertEqual(len(self.game.enemies), first_batch)
        for enemy in self.game.enemies:
            self.assertAlmostEqual(self.game.distance_to(enemy), spawning["radius"])
        self.advance(spawning["interval_seconds"])
        self.assertEqual(len(self.game.enemies), spawning["stages"][0]["minimum_alive"])
        self.game.enemies.pop()
        self.advance(spawning["interval_seconds"])
        self.assertEqual(len(self.game.enemies), spawning["stages"][0]["minimum_alive"])
        self.assertEqual(self.game.kills, 0)

    def test_spawn_cap_and_distant_enemy_removal(self):
        spawning = self.game.config["spawning"]
        self.no_weapons()
        self.first_stage_only()
        self.game.config["enemies"]["bat"]["speed"] = 0
        spawning["stages"][0]["minimum_alive"] = spawning["maximum_alive"] + 1
        for _ in range(math.ceil(spawning["maximum_alive"] / spawning["maximum_per_interval"]) + 1):
            self.advance(spawning["interval_seconds"])
        self.assertEqual(len(self.game.enemies), spawning["maximum_alive"])
        self.game.enemies[0].x = spawning["remove_distance"] + 1
        self.game.enemies[0].y = 0
        self.game.step()
        self.assertEqual(len(self.game.enemies), spawning["maximum_alive"] - 1)
        self.assertEqual(self.game.kills, 0)

    def test_contact_damage_has_a_separate_cooldown_for_each_enemy(self):
        self.no_weapons()
        self.no_spawning()
        damage = self.config["enemies"]["bat"]["damage"]
        self.game.enemies = [self.bat(), self.bat()]
        self.game.step()
        self.assertEqual(self.game.hero.hp, self.config["hero"]["hp"] - damage * 2)
        self.advance(self.config["contact"]["interval_seconds"] - self.game.dt)
        self.assertEqual(self.game.hero.hp, self.config["hero"]["hp"] - damage * 2)
        self.game.step()
        self.assertEqual(self.game.hero.hp, self.config["hero"]["hp"] - damage * 4)

    def test_wand_fires_an_even_ring_towards_the_nearest_bat(self):
        stats = self.config["weapons"]["spark_wand"]
        self.no_spawning()
        self.still_ring()
        count = stats["spark_count"]
        gap = 360 / count
        far = self.bat(300 * math.cos(math.radians(gap / 2)),
                       300 * math.sin(math.radians(gap / 2)))   # between two sparks
        near = self.bat(200, 0)
        self.game.enemies = [far, near]
        self.game.step()
        self.assertEqual(len(self.game.sparks), count)
        self.assertEqual(self.spark_angles(self.game.sparks),
                         [round(gap * i) for i in range(count)])
        for spark in self.game.sparks:
            self.assertAlmostEqual(math.hypot(spark.vx, spark.vy), stats["spark_speed"])
            self.assertEqual(spark.damage, stats["damage"])
        self.assertAlmostEqual(self.game._cooldowns["spark_wand"], stats["interval_seconds"])
        self.advance(stats["interval_seconds"] - self.game.dt)
        self.assertEqual(self.game.kills, 1)
        self.assertIn(far, self.game.enemies)
        self.assertNotIn(near, self.game.enemies)

    def test_the_ring_spins_through_the_whole_circle(self):
        stats = self.config["weapons"]["spark_wand"]
        spin = stats["spin_degrees_per_second"]
        count = stats["spark_count"]
        bat = self.bat(200, 0, hp=1e9, speed=0)  # it cannot die, so the wand keeps shooting at it
        self.no_spawning()
        self.game.enemies = [bat]
        for seconds in (0.0, 0.5, 2.0):
            self.game.elapsed = seconds
            self.game.sparks.clear()
            self.game._shoot(1)
            expected = sorted(round((spin * seconds + 360 * i / count) % 360) for i in range(count))
            self.assertEqual(self.spark_angles(self.game.sparks), expected, f"at {seconds}s")
        self.assertAlmostEqual(360 / spin, 2.0)   # two seconds make one full turn

    def test_fast_spark_cannot_pass_through_a_bat(self):
        self.no_spawning()
        self.still_ring()
        enemy = self.bat(100, 0, speed=0)
        self.game.enemies = [enemy]
        self.game.config["weapons"]["spark_wand"]["spark_speed"] = 200 / self.game.dt
        self.game.step()
        self.assertEqual(self.game.kills, 1)
        self.assertFalse(self.game.enemies)
        # the spark that hit is used up, the rest of the ring keeps flying
        self.assertEqual(len(self.game.sparks), self.config["weapons"]["spark_wand"]["spark_count"] - 1)

    def test_pause_and_game_over_freeze_rules_and_reset_starts_fresh(self):
        self.no_weapons()
        self.no_spawning()
        self.game.toggle_pause()
        self.game.step((100, 0))
        self.assertEqual(self.game.elapsed, 0)
        self.assertEqual(self.game.hero.x, 0)
        self.game.toggle_pause()
        self.game.enemies = [self.bat()]
        self.game.hero.hp = self.config["enemies"]["bat"]["damage"] / 2
        self.game.step()
        self.assertTrue(self.game.game_over)
        self.assertEqual(self.game.hero.hp, 0)
        ended_at = self.game.elapsed
        self.advance(1, (100, 0))
        self.assertEqual(self.game.elapsed, ended_at)
        self.assertEqual(self.game.hero.x, 0)
        self.game.reset()
        self.assertFalse(self.game.game_over)
        self.assertFalse(self.game.paused)
        self.assertEqual(self.game.hero.hp, self.config["hero"]["hp"])
        self.assertEqual(self.game.elapsed, 0)
        self.assertEqual(self.game.kills, 0)
        self.assertEqual(self.game.enemies, [])
        self.assertEqual(self.game.sparks, [])
        self.assertEqual(self.game.gems, [])


class GrowthTests(RuleTestBase):
    seed = 11

    def setUp(self):
        super().setUp()
        self.no_spawning()

    def test_a_dead_enemy_drops_a_gem_worth_its_xp(self):
        # far enough away that the gem is not magnetised, so we can see it land
        self.still_ring()
        self.game.enemies = [self.bat(300, 0, speed=0)]
        self.advance(self.config["weapons"]["spark_wand"]["interval_seconds"] + 0.5)
        self.assertEqual(self.game.kills, 1)
        self.assertEqual(len(self.game.gems), 1)
        self.assertEqual(self.game.gems[0].xp, self.config["enemies"]["bat"]["xp"])
        self.assertAlmostEqual(self.game.distance_to(self.game.gems[0]), 300, delta=1)

    def test_gems_only_fly_in_from_inside_the_magnet_radius(self):
        self.no_weapons()
        reach = self.game.magnet_range()
        near = Gem(reach - 20, 0, 1)
        far = Gem(reach + 60, 0, 1)
        self.game.gems = [near, far]
        start_of_far = far.x
        self.advance(0.5)
        self.assertEqual(self.game.gems, [far])           # the near one was collected
        self.assertEqual(far.x, start_of_far)             # the far one did not move
        self.assertEqual(self.game.hero.xp, near.xp)

    def test_xp_costs_rise_by_the_configured_step(self):
        cost = self.config["xp"]
        self.assertEqual(self.game.xp_needed(), cost["first_level_cost"])
        self.game.gain_xp(cost["first_level_cost"])
        self.assertEqual(self.game.hero.level, 2)
        self.assertEqual(self.game.hero.xp, 0)
        self.assertEqual(self.game.xp_needed(), cost["first_level_cost"] + cost["cost_increase"])

    def test_a_level_up_stops_the_game_until_a_card_is_chosen(self):
        cost = self.config["xp"]
        self.game.gain_xp(cost["first_level_cost"])
        self.assertEqual(len(self.game.current_cards()), cost["card_count"])
        frozen = (self.game.elapsed, self.game.hero.x)
        self.game.step((100, 0))
        self.assertEqual((self.game.elapsed, self.game.hero.x), frozen)
        self.assertTrue(self.game.choose(0))
        self.assertEqual(self.game.current_cards(), [])
        self.game.step((100, 0))
        self.assertGreater(self.game.elapsed, frozen[0])

    def test_two_level_ups_at_once_ask_twice(self):
        cost = self.config["xp"]
        first = cost["first_level_cost"]
        self.game.gain_xp(first + first + cost["cost_increase"])
        self.assertEqual(self.game.hero.level, 3)
        self.assertEqual(len(self.game.choice_queue), 2)
        self.game.choose(0)
        self.assertEqual(len(self.game.choice_queue), 1)
        self.game.choose(0)
        self.assertEqual(self.game.choice_queue, [])

    def test_the_pool_offers_new_weapons_up_to_the_limit_only(self):
        weapons = self.config["weapons"]
        self.assertIn("weapon", [c["kind"] for c in self.game.card_pool()])
        for name in items_only(weapons):
            self.game.hero.weapons[name] = 1
        self.assertEqual(len(self.game.hero.weapons), weapons["maximum_owned"])
        self.assertFalse([c for c in self.game.card_pool()
                          if c["kind"] == "weapon" and c["level"] == 1])

    def test_the_pool_never_offers_something_already_maxed(self):
        for name in items_only(self.config["weapons"]):
            self.game.hero.weapons[name] = self.config["weapons"]["maximum_level"]
        for name in items_only(self.config["passives"]):
            self.game.hero.passives[name] = self.config["passives"]["maximum_level"]
        self.assertEqual(self.game.card_pool(), [])

    def test_nothing_left_offers_a_heal_instead(self):
        for name in items_only(self.config["weapons"]):
            self.game.hero.weapons[name] = self.config["weapons"]["maximum_level"]
        for name in items_only(self.config["passives"]):
            self.game.hero.passives[name] = self.config["passives"]["maximum_level"]
        cards = self.game.make_cards()
        self.assertEqual([c["kind"] for c in cards], ["heal"])
        self.game.hero.hp = 10
        self.game.choice_queue = [cards]
        self.game.choose(0)
        self.assertEqual(self.game.hero.hp, 10 + self.config["xp"]["fallback_heal"])

    def test_choosing_a_weapon_raises_its_level(self):
        self.pick("weapon", "spin_blades")
        self.assertEqual(self.game.hero.weapons["spin_blades"], 1)
        self.pick("weapon", "spark_wand", 2)
        self.assertEqual(self.game.hero.weapons["spark_wand"], 2)

    def test_spark_wand_levels_add_damage_speed_and_sparks(self):
        stats = self.config["weapons"]["spark_wand"]
        one = self.game.spark_wand_stats(1)
        self.assertEqual(one["count"], stats["spark_count"])
        self.assertEqual(one["damage"], stats["damage"])
        self.assertEqual(one["interval"], stats["interval_seconds"])
        level = stats["extra_spark_levels"][-1]
        top = self.game.spark_wand_stats(level)
        self.assertEqual(top["count"], stats["spark_count"] + len(
            [n for n in stats["extra_spark_levels"] if level >= n]))
        self.assertEqual(top["damage"], stats["damage"] + stats["damage_per_level"] * (level - 1))
        self.assertAlmostEqual(
            top["interval"],
            stats["interval_seconds"] + stats["interval_reduction_per_level"] * (level - 1))

    def test_blades_circle_the_hero_and_cut_once_per_pass(self):
        self.no_weapons()
        self.game.hero.weapons["spin_blades"] = 1
        stats = self.config["weapons"]["spin_blades"]
        self.assertEqual(len(self.game.blade_positions()), stats["blade_count"])
        bat = self.bat(stats["orbit_radius"], 0, hp=1e9, speed=0)
        self.game.enemies = [bat]

        def hits():
            return (1e9 - bat.hp) / stats["damage"]

        # one blade reaches the bat every part of a turn
        pass_every = stats["orbit_seconds"] / stats["blade_count"]
        self.advance(pass_every / 2)
        self.assertEqual(hits(), 1)
        self.advance(pass_every)
        self.assertEqual(hits(), 2)

    def test_blades_never_hit_the_same_bat_twice_in_one_pass(self):
        self.no_weapons()
        self.game.hero.weapons["spin_blades"] = 1
        stats = self.config["weapons"]["spin_blades"]
        bat = self.bat(stats["orbit_radius"], 0, hp=1e9, speed=0)
        self.game.enemies = [bat]
        self.advance(0.3)   # the first blade stays next to it for several frames
        self.assertEqual((1e9 - bat.hp) / stats["damage"], 1)

    def test_more_levels_mean_more_blades(self):
        self.no_weapons()
        stats = self.config["weapons"]["spin_blades"]
        for level in range(1, self.config["weapons"]["maximum_level"] + 1):
            self.game.hero.weapons["spin_blades"] = level
            self.assertEqual(self.game.blade_count(level), stats["blade_count"] + len(
                [n for n in stats["extra_blade_levels"] if level >= n]))

    def test_holy_ring_hurts_everything_inside_the_circle_only(self):
        self.no_weapons()
        self.game.hero.weapons["holy_ring"] = 1
        stats = self.config["weapons"]["holy_ring"]
        inside = self.bat(self.game.holy_ring_radius(), 0, hp=1e9, speed=0)
        outside = self.bat(self.game.holy_ring_radius() + 80, 0, hp=1e9, speed=0)
        self.game.enemies = [inside, outside]
        self.game.step()
        self.assertEqual(inside.hp, 1e9 - stats["damage"])
        self.assertEqual(outside.hp, 1e9)
        self.advance(stats["interval_seconds"] - self.game.dt)
        self.assertEqual(inside.hp, 1e9 - stats["damage"])   # one pulse per interval
        self.game.step()
        self.assertEqual(inside.hp, 1e9 - stats["damage"] * 2)

    def test_holy_ring_grows_with_levels(self):
        self.game.hero.weapons["holy_ring"] = 1
        stats = self.config["weapons"]["holy_ring"]
        start = self.game.holy_ring_radius()
        self.game.hero.weapons["holy_ring"] = 3
        self.assertEqual(self.game.holy_ring_radius(), start + 2 * stats["radius_per_level"])

    def test_passives_change_speed_max_hp_and_magnet(self):
        hero = self.config["hero"]
        passives = self.config["passives"]
        self.game.hero.hp = 40
        self.pick("passive", "swift_boots")
        self.assertAlmostEqual(self.game.walk_speed(),
                               hero["speed"] * (1 + passives["swift_boots"]["speed_fraction_per_level"]))
        self.pick("passive", "big_heart")
        self.assertEqual(self.game.hero.max_hp, hero["hp"] + passives["big_heart"]["max_hp_per_level"])
        self.assertEqual(self.game.hero.hp, 40 + passives["big_heart"]["heal_per_level"])
        self.pick("passive", "magnet")
        self.assertEqual(self.game.magnet_range(),
                         hero["magnet_radius"] + passives["magnet"]["radius_per_level"])

    def test_two_levels_of_boots_stack(self):
        self.pick("passive", "swift_boots", 2)
        fraction = self.config["passives"]["swift_boots"]["speed_fraction_per_level"]
        self.assertAlmostEqual(self.game.walk_speed(), self.config["hero"]["speed"] * (1 + 2 * fraction))


class WaveTests(RuleTestBase):
    """Step 4: the whole spawning table, the boss and the two-minute victory."""

    seed = 5

    def setUp(self):
        super().setUp()
        self.no_weapons()
        self.game.hero.max_hp = self.game.hero.hp = 1e9   # nothing can end the run early

    def test_the_table_is_read_by_the_clock(self):
        stages = self.config["spawning"]["stages"]
        self.assertEqual(self.game.stage(0), stages[0])
        self.assertEqual(self.game.stage(stages[1]["from_seconds"] - 0.1), stages[0])
        self.assertEqual(self.game.stage(stages[1]["from_seconds"]), stages[1])
        self.assertEqual(self.game.stage(10_000), stages[-1])

    def test_every_stage_spawns_its_own_kinds_until_the_minimum(self):
        spawning = self.config["spawning"]
        for stage in spawning["stages"]:
            self.game.enemies = []
            self.game.elapsed = stage["from_seconds"]
            self.game._boss_spawned = True          # the boss has its own test below
            for _ in range(round(stage["minimum_alive"] / spawning["maximum_per_interval"]) + 1):
                self.game._spawn_wave()
            kinds = {enemy.kind for enemy in self.game.enemies}
            self.assertEqual(kinds, set(stage["types"]))   # every listed type, and no other
            self.assertEqual(len(self.game.enemies), stage["minimum_alive"])

    def test_the_boss_arrives_with_its_stage_and_only_once(self):
        boss_stage = next(stage for stage in self.config["spawning"]["stages"] if "boss" in stage)
        self.advance(boss_stage["from_seconds"] + 1.5)
        bosses = [enemy for enemy in self.game.enemies if enemy.boss]
        self.assertEqual([enemy.kind for enemy in bosses], [boss_stage["boss"]])
        stats = self.config["enemies"][boss_stage["boss"]]
        self.assertEqual(bosses[0].hp, stats["hp"])
        self.assertEqual(bosses[0].damage, stats["damage"])
        self.advance(20)
        self.assertEqual(len([enemy for enemy in self.game.enemies if enemy.boss]), 1)

    def test_the_boss_is_carried_back_instead_of_removed(self):
        spawning = self.config["spawning"]
        boss = self.game._spawn_at_circle("demon")
        boss.speed = 0
        boss.hp = 400
        stray = self.game._spawn_at_circle("bat")
        stray.speed = 0
        self.game.enemies = [boss, stray]
        boss.x = self.game.hero.x + spawning["boss_return_distance"] + 40
        stray.x = self.game.hero.x + spawning["remove_distance"] + 40
        self.game.step()
        self.assertEqual([enemy.kind for enemy in self.game.enemies], ["demon"])
        self.assertEqual(self.game.enemies[0].hp, 400)          # the same boss, not a fresh one
        self.assertAlmostEqual(self.game.distance_to(self.game.enemies[0]),
                               spawning["radius"], delta=3)

    def test_the_boss_drops_no_gem(self):
        boss = self.game._spawn_at_circle("demon")
        self.game.enemies = [boss]
        boss.hp = 0
        self.game._drop_gems_for_corpses()
        self.assertEqual(self.game.kills, 1)
        self.assertEqual(self.game.gems, [])

    def test_surviving_the_clock_wins_and_freezes_the_run(self):
        victory = self.config["run"]["victory_seconds"]
        self.advance(victory - 1)
        self.assertFalse(self.game.finished)
        self.advance(1.1)
        self.assertTrue(self.game.won)
        self.assertTrue(self.game.finished)
        self.assertFalse(self.game.game_over)                   # he is still on his feet
        ended_at = self.game.elapsed
        self.advance(2, (100, 0))
        self.assertEqual(self.game.elapsed, ended_at)
        self.game.toggle_pause()
        self.assertFalse(self.game.paused)                      # the end screen cannot pause


class FeelEventTests(RuleTestBase):
    """Step 5: what the rules write down, so the screen can play a sound or draw a flash."""

    def kinds(self):
        return [event.kind for event in self.game.events]

    def test_take_events_empties_the_list(self):
        self.no_weapons()
        self.no_spawning()
        self.game.enemies = [self.bat()]
        self.game.step()
        self.assertTrue(self.game.events)
        self.assertTrue(self.game.take_events())
        self.assertEqual(self.game.events, [])

    def test_every_weapon_reports_its_own_hit(self):
        self.no_spawning()
        self.still_ring()
        stats = self.config["weapons"]["spark_wand"]
        enemy = self.bat(120, 0, hp=1e9, speed=0)
        self.game.enemies = [enemy]
        self.advance(stats["interval_seconds"] + 0.05)
        hits = [event for event in self.game.events if event.kind == "hit"]
        self.assertTrue(hits)
        self.assertEqual(hits[0].amount, stats["damage"])          # how much it took off
        self.assertEqual((hits[0].x, hits[0].y), (enemy.x, enemy.y))

        self.game.events.clear()
        self.game.hero.weapons.clear()
        self.game.sparks.clear()                    # no sparks left over from the wand
        self.game.hero.weapons["spin_blades"] = 1
        blades = self.config["weapons"]["spin_blades"]
        enemy.x, enemy.y = blades["orbit_radius"], 0
        self.advance(blades["orbit_seconds"] / blades["blade_count"])
        hits = [event for event in self.game.events if event.kind == "hit"]
        self.assertTrue(hits)
        self.assertEqual({event.amount for event in hits}, {blades["damage"]})

        self.game.events.clear()
        self.game.hero.weapons.clear()
        self.game.hero.weapons["holy_ring"] = 2
        ring = self.config["weapons"]["holy_ring"]
        self.game.step()
        self.assertEqual([event.amount for event in self.game.events if event.kind == "hit"],
                         [ring["damage"] + ring["damage_per_level"]])

    def test_a_dead_enemy_reports_its_size_for_the_flash(self):
        self.no_weapons()
        self.no_spawning()
        first, second = self.bat(200, 0), self.bat(300, 0)
        self.game.enemies = [first, second]
        first.hp, second.hp = 0, 0
        self.game._drop_gems_for_corpses()
        self.assertEqual(self.kinds(), ["kill", "kill"])
        self.assertEqual([event.amount for event in self.game.events],
                         [self.config["enemies"]["bat"]["hit_radius"]] * 2)
        self.assertEqual([event.x for event in self.game.events], [200, 300])

    def test_a_collected_gem_is_reported_at_its_own_spot(self):
        self.no_weapons()
        self.no_spawning()
        bat = self.config["enemies"]["bat"]
        self.game.gems = [Gem(0, 4, bat["xp"])]
        self.game.step()
        self.assertEqual(self.game.events, [Event("gem", 0, 4, bat["xp"])])

    def test_the_level_up_a_gem_buys_is_reported_with_the_new_level(self):
        self.no_weapons()
        self.no_spawning()
        cost = self.config["xp"]
        self.game.gain_xp(cost["first_level_cost"])
        self.assertEqual(self.game.events, [Event("level_up", 0, 0, 2)])
        self.game.hero.xp = 0
        self.game.gain_xp(self.game.xp_needed())
        self.assertEqual(self.game.events[-1], Event("level_up", 0, 0, 3))

    def test_getting_hurt_is_reported_with_the_damage(self):
        self.no_weapons()
        self.no_spawning()
        self.game.enemies = [self.bat()]
        self.game.step()
        hurt = [event for event in self.game.events if event.kind == "hurt"]
        self.assertEqual(len(hurt), 1)
        self.assertEqual(hurt[0].amount, self.config["enemies"]["bat"]["damage"])

    def test_the_end_is_reported_only_once(self):
        self.no_weapons()
        self.no_spawning()
        self.game.enemies = [self.bat()]
        self.game.hero.hp = self.config["enemies"]["bat"]["damage"]
        self.game.step()
        self.assertTrue(self.game.game_over)
        self.assertEqual(self.kinds().count("end"), 1)
        self.assertEqual(self.game.events[-1], Event("end", 0, 0, 0))
        self.game.events.clear()
        self.advance(1)
        self.assertEqual(self.game.events, [])
        self.game.reset()
        self.assertEqual(self.game.events, [])

    def test_surviving_reports_the_end_as_a_win(self):
        self.no_weapons()
        self.no_spawning()
        self.first_stage_only()                 # the boss row is gone, nothing can hurt him
        victory = self.config["run"]["victory_seconds"]
        self.advance(victory - 1)
        self.assertEqual(self.game.events, [])
        self.advance(1.1)
        self.assertEqual(self.kinds(), ["end"])
        self.assertEqual(self.game.events[0].amount, 1.0)


class DifficultyTests(unittest.TestCase):
    """Step 6: a difficulty is only a pile of numbers laid over data/game.json."""

    def setUp(self):
        self.base = load_config()
        self.modes = load_modes()

    def names(self):
        return [mode["name"] for mode in self.modes]

    def test_easy_normal_and_hard_are_offered_in_that_order(self):
        self.assertEqual(self.names(), ["easy", "normal", "hard"])

    def test_every_mode_has_what_the_picker_button_shows(self):
        for mode in self.modes:
            with self.subTest(mode=mode["name"]):
                for key in ("name", "label", "text", "numbers"):
                    self.assertIn(key, mode)
                self.assertTrue(mode["label"] and mode["text"])
                self.assertIsInstance(mode["numbers"], dict)

    def test_merge_lays_one_number_over_a_nested_dict(self):
        merged = merge({"hero": {"hp": 100, "speed": 200}}, {"hero": {"hp": 150}})
        self.assertEqual(merged, {"hero": {"hp": 150, "speed": 200}})

    def test_merge_replaces_a_whole_list_instead_of_adding_to_it(self):
        merged = merge({"spawning": {"stages": [{"a": 1}, {"a": 2}]}},
                       {"spawning": {"stages": [{"a": 3}]}})
        self.assertEqual(merged["spawning"]["stages"], [{"a": 3}])

    def test_merge_leaves_the_config_it_was_handed_alone(self):
        hp = self.base["hero"]["hp"]
        merged = merge(self.base, {"hero": {"hp": hp + 50}})
        merged["hero"]["hp"] = 1
        self.assertEqual(self.base["hero"]["hp"], hp)

    def test_normal_changes_nothing_and_an_unknown_name_does_too(self):
        self.assertEqual(load_config("normal"), self.base)
        self.assertEqual(load_config("something_else"), self.base)

    def test_a_mode_only_writes_numbers_game_json_already_has(self):
        """A spelling mistake in difficulties.json would add a new key instead of changing one."""
        for mode in self.modes:
            with self.subTest(mode=mode["name"]):
                self.check_paths(mode["numbers"], self.base, mode["numbers"])

    def check_paths(self, node, base, numbers):
        for key, value in node.items():
            self.assertIn(key, base, f"{key} is not a number in game.json")
            if isinstance(value, dict):
                self.check_paths(value, base[key], numbers)

    def test_easy_is_a_shorter_run_for_a_hero_with_more_hp(self):
        numbers = mode_numbers("easy")
        easy = load_config("easy")
        self.assertEqual(easy["hero"]["hp"], numbers["hero"]["hp"])
        self.assertGreater(easy["hero"]["hp"], self.base["hero"]["hp"])
        self.assertLess(easy["run"]["victory_seconds"], self.base["run"]["victory_seconds"])

    def test_hard_is_normal_until_the_boss_and_thicker_afterwards(self):
        """The balance we measured: pressing earlier than 1:15 makes the swarm unplayable."""
        hard = {row["from_seconds"]: row["minimum_alive"]
                for row in mode_numbers("hard")["spawning"]["stages"]}
        normal = {row["from_seconds"]: row["minimum_alive"]
                  for row in self.base["spawning"]["stages"]}
        for seconds, minimum in normal.items():
            with self.subTest(seconds=seconds):
                if seconds <= 75:
                    self.assertEqual(hard[seconds], minimum)
                else:
                    self.assertGreaterEqual(hard[seconds], minimum)
        self.assertGreater(max(hard.values()), max(normal.values()))

    def test_every_stage_table_is_sane(self):
        for mode in self.modes:
            stages = mode["numbers"].get("spawning", {}).get("stages")
            if stages is None:
                continue
            with self.subTest(mode=mode["name"]):
                kinds = set(items_only(self.base["enemies"]))
                times = [row["from_seconds"] for row in stages]
                self.assertEqual(times, sorted(set(times)), "a time appears twice")
                self.assertEqual(len([row for row in stages if "boss" in row]), 1)
                for row in stages:
                    self.assertTrue(set(row["types"]) <= kinds)
                    self.assertGreaterEqual(row["minimum_alive"], 0)

    def test_the_merged_numbers_reach_the_rules(self):
        easy = load_config("easy")
        game = Game(copy.deepcopy(easy))
        self.assertEqual(game.hero.max_hp, easy["hero"]["hp"])
        self.assertEqual(game.xp_needed(), easy["xp"]["first_level_cost"])
        game.elapsed = easy["run"]["victory_seconds"]
        self.assertTrue(game.won)


if __name__ == "__main__":
    unittest.main()
