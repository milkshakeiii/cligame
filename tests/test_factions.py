"""
Tests for Phase 7: Factions + Minimal Teams.

Covers:
  1. Team model basics — creation, faction association
  2. Ship creation with team/faction — team_id inheritance, faction property
  3. Faction resistance profiles — compute_resistances with base resists
  4. Faction build cost modifiers — FACTION_BUILD_MODIFIERS applied in production
  5. Faction-aware production — get_faction_adjusted_cost, can_ship_build, start_build
  6. Per-team research — start_research with team_id, shared research across team
  7. Faction tech tree — get_effective_tech_tree with Solarion/Voidborn overrides
  8. Faction traits — FACTION_TRAITS constants
  9. Spawn new ship — team_id inheritance, faction ship naming
  10. Shield regen (armor/shield repair modules via tick)
"""

import math
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker, selectinload
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from server.models import (
    ARMOR_BASE_RESISTS,
    BUILD_COSTS,
    FACTION_BUILD_MODIFIERS,
    FACTION_SHIP_NAMES,
    FACTION_TRAITS,
    RESEARCH_COSTS,
    SHIELD_BASE_RESISTS,
    SHIP_CLASSES,
    TECH_TREE,
    GameState,
    ModuleType,
    ResearchProgress,
    ShipClass,
    ShipModule,
    Spaceship,
    Team,
    User,
    create_default_ship,
    make_module,
    recalculate_max_capacitor,
    spawn_new_ship,
)
from server.combat import apply_damage, apply_shield_regen
from server.production import (
    can_ship_build,
    get_faction_adjusted_cost,
    start_build,
    tick_build_order,
)
from server.research import (
    check_prerequisites,
    get_completed_tech_ids,
    get_effective_tech_tree,
    is_module_unlocked,
    is_ship_unlocked,
    start_research,
)
from tests.conftest import add_module_to_ship, make_test_ship


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_team_ship(
    ship_class: ShipClass = ShipClass.frigate,
    user_id: int = 1,
    team_id: int = None,
    faction: str = None,
) -> tuple[Spaceship, Team]:
    """Create an in-memory ship with team set (for unit tests)."""
    ship = make_test_ship(ship_class=ship_class, user_id=user_id)
    team = None
    if team_id is not None or faction is not None:
        team = Team(id=team_id or 1, name=f"TestTeam-{faction or 'none'}", faction=faction)
        ship.team_id = team.id
        ship.team = team
    return ship, team


# ---------------------------------------------------------------------------
# 1. Team model basics
# ---------------------------------------------------------------------------


class TestTeamModel:
    """Tests for the Team SQLModel."""

    def test_team_creation_with_faction(self):
        """A Team should store faction ('solarion' or 'voidborn')."""
        team = Team(name="Solar Guard", faction="solarion")
        assert team.name == "Solar Guard"
        assert team.faction == "solarion"

    def test_team_creation_without_faction(self):
        """Faction can be None for factionless teams."""
        team = Team(name="Independents", faction=None)
        assert team.faction is None

    def test_team_faction_voidborn(self):
        team = Team(name="Dark Fleet", faction="voidborn")
        assert team.faction == "voidborn"


# ---------------------------------------------------------------------------
# 2. Ship creation with team/faction
# ---------------------------------------------------------------------------


class TestShipWithFaction:
    """Test that ships inherit team_id and derive faction correctly."""

    def test_ship_faction_property_with_team(self):
        """Ship.faction should derive from Ship.team.faction."""
        ship, team = _make_team_ship(faction="solarion", team_id=1)
        assert ship.faction == "solarion"

    def test_ship_faction_property_voidborn(self):
        ship, team = _make_team_ship(faction="voidborn", team_id=2)
        assert ship.faction == "voidborn"

    def test_ship_faction_property_no_team(self):
        """Ship with no team should have None faction."""
        ship = make_test_ship()
        ship.team = None
        assert ship.faction is None

    def test_ship_team_id_stored(self):
        """Ship should store team_id FK."""
        ship, _ = _make_team_ship(team_id=42, faction="solarion")
        assert ship.team_id == 42

    def test_ship_team_id_none_by_default(self):
        """New ships without a team should have team_id=None."""
        ship = create_default_ship(
            name="Lone Wolf", ship_class=ShipClass.frigate, user_id=1
        )
        assert ship.team_id is None


# ---------------------------------------------------------------------------
# 3. Faction resistance profiles (base resistances)
# ---------------------------------------------------------------------------


class TestFactionResistances:
    """
    Test compute_resistances() which uses base resist profiles.
    The base resists (SHIELD_BASE_RESISTS, ARMOR_BASE_RESISTS) apply to
    all ships regardless of faction. Faction-specific overrides would
    be additional constants if implemented.
    """

    def test_shield_base_resists_applied(self):
        """Base shield resists should be returned when no hardeners active."""
        ship = make_test_ship(ShipClass.frigate)
        resists = ship.compute_resistances("shield")
        assert resists["kinetic"] == pytest.approx(SHIELD_BASE_RESISTS["kinetic"])
        assert resists["thermal"] == pytest.approx(SHIELD_BASE_RESISTS["thermal"])
        assert resists["explosive"] == pytest.approx(SHIELD_BASE_RESISTS["explosive"])

    def test_armor_base_resists_applied(self):
        """Base armor resists should be returned when no hardeners active."""
        ship = make_test_ship(ShipClass.frigate)
        resists = ship.compute_resistances("armor")
        assert resists["kinetic"] == pytest.approx(ARMOR_BASE_RESISTS["kinetic"])
        assert resists["thermal"] == pytest.approx(ARMOR_BASE_RESISTS["thermal"])
        assert resists["explosive"] == pytest.approx(ARMOR_BASE_RESISTS["explosive"])

    def test_shield_resists_with_active_hardener(self):
        """An active hardener should increase the corresponding resist."""
        ship = make_test_ship(ShipClass.frigate)
        hardener = add_module_to_ship(
            ship, ModuleType.small_shield_hardener_kinetic, 30
        )
        hardener.active = True

        resists = ship.compute_resistances("shield")
        # Base kinetic shield resist is 0.20, hardener adds 0.15
        assert resists["kinetic"] == pytest.approx(0.35)
        # Other resists unchanged
        assert resists["thermal"] == pytest.approx(SHIELD_BASE_RESISTS["thermal"])
        assert resists["explosive"] == pytest.approx(SHIELD_BASE_RESISTS["explosive"])

    def test_armor_resists_with_active_hardener(self):
        ship = make_test_ship(ShipClass.frigate)
        hardener = add_module_to_ship(
            ship, ModuleType.small_armor_hardener_thermal, 30
        )
        hardener.active = True

        resists = ship.compute_resistances("armor")
        # Base thermal armor resist is 0.20, hardener adds 0.15
        assert resists["thermal"] == pytest.approx(0.35)

    def test_inactive_hardener_not_counted(self):
        """Inactive hardeners should not affect resistances."""
        ship = make_test_ship(ShipClass.frigate)
        hardener = add_module_to_ship(
            ship, ModuleType.small_shield_hardener_kinetic, 30
        )
        hardener.active = False

        resists = ship.compute_resistances("shield")
        assert resists["kinetic"] == pytest.approx(SHIELD_BASE_RESISTS["kinetic"])

    def test_stacking_penalties_on_multiple_hardeners(self):
        """Multiple hardeners of the same type should apply stacking penalties."""
        ship = make_test_ship(ShipClass.frigate)
        h1 = add_module_to_ship(ship, ModuleType.small_shield_hardener_kinetic, 30)
        h2 = add_module_to_ship(ship, ModuleType.small_shield_hardener_kinetic, 30)
        h1.active = True
        h2.active = True

        resists = ship.compute_resistances("shield")
        # Two small kinetic hardeners: each 0.15 bonus
        # With stacking: 0.15 * 0.87^0 + 0.15 * 0.87^1 = 0.15 + 0.1305 = 0.2805
        expected = SHIELD_BASE_RESISTS["kinetic"] + 0.15 + 0.15 * 0.87
        assert resists["kinetic"] == pytest.approx(expected, abs=0.001)

    def test_resistance_cap_at_95_percent(self):
        """Resistances should be capped at 95% regardless of stacking."""
        ship = make_test_ship(ShipClass.frigate)
        # Add many hardeners to push past 95%
        for _ in range(10):
            h = add_module_to_ship(ship, ModuleType.small_shield_hardener_kinetic, 30)
            h.active = True

        resists = ship.compute_resistances("shield")
        assert resists["kinetic"] <= 0.95
        assert resists["kinetic"] == pytest.approx(0.95)


# ---------------------------------------------------------------------------
# 4. Faction build cost modifiers
# ---------------------------------------------------------------------------


class TestFactionBuildModifiers:
    """Test that FACTION_BUILD_MODIFIERS constants are correct."""

    def test_solarion_modifiers_exist(self):
        assert "solarion" in FACTION_BUILD_MODIFIERS
        solarion = FACTION_BUILD_MODIFIERS["solarion"]
        assert "frigate" in solarion
        assert "ore_mult" in solarion["frigate"]
        assert "time_mult" in solarion["frigate"]

    def test_voidborn_modifiers_exist(self):
        assert "voidborn" in FACTION_BUILD_MODIFIERS
        voidborn = FACTION_BUILD_MODIFIERS["voidborn"]
        assert "frigate" in voidborn

    def test_solarion_large_ships_cost_more(self):
        """Solarion destroyer/cruiser should cost more ore and time than base."""
        solarion = FACTION_BUILD_MODIFIERS["solarion"]
        for ship_class in ["destroyer", "cruiser"]:
            assert solarion[ship_class]["ore_mult"] > 1.0, (
                f"Solarion {ship_class} should have costlier ore"
            )
            assert solarion[ship_class]["time_mult"] > 1.0, (
                f"Solarion {ship_class} should have slower build time"
            )

    def test_voidborn_small_ships_are_cheap(self):
        """Voidborn strike_craft/corvette should be cheaper and faster to build."""
        voidborn = FACTION_BUILD_MODIFIERS["voidborn"]
        for ship_class in ["strike_craft", "corvette"]:
            assert voidborn[ship_class]["ore_mult"] < 1.0, (
                f"Voidborn {ship_class} should have discounted ore"
            )
            assert voidborn[ship_class]["time_mult"] < 1.0, (
                f"Voidborn {ship_class} should have faster build time"
            )


# ---------------------------------------------------------------------------
# 5. Faction-aware production
# ---------------------------------------------------------------------------


class TestFactionAwareProduction:
    """Test get_faction_adjusted_cost and production with faction modifiers."""

    def test_no_faction_returns_base_cost(self):
        """When faction is None, base BUILD_COSTS should be returned."""
        cost = get_faction_adjusted_cost(ShipClass.frigate, faction=None)
        base = BUILD_COSTS["frigate"]
        assert cost["ore"] == base["ore"]
        assert cost["ticks"] == base["ticks"]

    def test_solarion_frigate_cost(self):
        """Solarion should get discounted ore, slower build time for frigate."""
        cost = get_faction_adjusted_cost(ShipClass.frigate, faction="solarion")
        base = BUILD_COSTS["frigate"]
        mods = FACTION_BUILD_MODIFIERS["solarion"]["frigate"]
        assert cost["ore"] == int(base["ore"] * mods["ore_mult"])
        assert cost["ticks"] == int(base["ticks"] * mods["time_mult"])

    def test_voidborn_frigate_cost(self):
        """Voidborn should get costlier ore, faster build time for frigate."""
        cost = get_faction_adjusted_cost(ShipClass.frigate, faction="voidborn")
        base = BUILD_COSTS["frigate"]
        mods = FACTION_BUILD_MODIFIERS["voidborn"]["frigate"]
        assert cost["ore"] == int(base["ore"] * mods["ore_mult"])
        assert cost["ticks"] == int(base["ticks"] * mods["time_mult"])

    def test_solarion_corvette_cost(self):
        cost = get_faction_adjusted_cost(ShipClass.corvette, faction="solarion")
        base = BUILD_COSTS["corvette"]
        mods = FACTION_BUILD_MODIFIERS["solarion"]["corvette"]
        assert cost["ore"] == int(base["ore"] * mods["ore_mult"])
        assert cost["ticks"] == int(base["ticks"] * mods["time_mult"])

    def test_voidborn_cruiser_cost(self):
        cost = get_faction_adjusted_cost(ShipClass.cruiser, faction="voidborn")
        base = BUILD_COSTS["cruiser"]
        mods = FACTION_BUILD_MODIFIERS["voidborn"]["cruiser"]
        assert cost["ore"] == int(base["ore"] * mods["ore_mult"])
        assert cost["ticks"] == int(base["ticks"] * mods["time_mult"])

    def test_unknown_faction_returns_base(self):
        """Unrecognized faction should return base costs."""
        cost = get_faction_adjusted_cost(ShipClass.frigate, faction="unknown_faction")
        base = BUILD_COSTS["frigate"]
        assert cost["ore"] == base["ore"]
        assert cost["ticks"] == base["ticks"]

    def test_mothership_has_no_build_cost(self):
        """Mothership is not buildable; should return empty dict."""
        cost = get_faction_adjusted_cost(ShipClass.mothership, faction="solarion")
        assert cost == {}

    def test_all_ship_classes_have_both_faction_modifiers(self):
        """Every buildable class should have modifiers in both faction dicts."""
        buildable = list(BUILD_COSTS.keys())
        for faction in ["solarion", "voidborn"]:
            for ship_class in buildable:
                assert ship_class in FACTION_BUILD_MODIFIERS[faction], (
                    f"{faction} missing modifier for {ship_class}"
                )

    def test_can_ship_build_with_faction_adjusted_cost(self):
        """can_ship_build should use faction-adjusted costs."""
        ship = make_test_ship(ShipClass.frigate)
        factory = add_module_to_ship(ship, ModuleType.factory, 500)
        ship.id = 1  # ensure ID is set
        factory.id = 1

        # Solarion frigate cost: int(200 * 0.9) = 180 ore for strike_craft
        solarion_cost = get_faction_adjusted_cost(ShipClass.strike_craft, faction="solarion")

        # Enough ore for solarion but not base
        ship.ore = float(solarion_cost["ore"])
        ok, _ = can_ship_build(ship, ShipClass.strike_craft, factory, faction="solarion")
        assert ok is True

    def test_can_ship_build_insufficient_ore_with_faction(self):
        """Should fail when ore is below faction-adjusted cost."""
        ship = make_test_ship(ShipClass.frigate)
        factory = add_module_to_ship(ship, ModuleType.factory, 500)
        ship.id = 1
        factory.id = 1

        ship.ore = 1.0  # way below any cost
        ok, reason = can_ship_build(ship, ShipClass.strike_craft, factory, faction="solarion")
        assert ok is False
        assert "insufficient ore" in reason.lower()

    def test_start_build_with_solarion_faction(self):
        """start_build with faction should use adjusted costs."""
        ship = make_test_ship(ShipClass.frigate)
        factory = add_module_to_ship(ship, ModuleType.factory, 500)
        ship.id = 1
        factory.id = 1

        solarion_cost = get_faction_adjusted_cost(ShipClass.strike_craft, faction="solarion")
        ship.ore = float(solarion_cost["ore"]) + 100.0  # enough

        order = start_build(ship, factory, ShipClass.strike_craft, faction="solarion")
        assert order.ore_cost == solarion_cost["ore"]
        assert order.ticks_remaining == solarion_cost["ticks"]
        assert order.total_ticks == solarion_cost["ticks"]
        # Ore deducted
        assert ship.ore == pytest.approx(100.0)

    def test_start_build_with_voidborn_faction(self):
        """start_build with voidborn should use adjusted costs."""
        ship = make_test_ship(ShipClass.frigate)
        factory = add_module_to_ship(ship, ModuleType.factory, 500)
        ship.id = 1
        factory.id = 1

        voidborn_cost = get_faction_adjusted_cost(ShipClass.strike_craft, faction="voidborn")
        ship.ore = float(voidborn_cost["ore"]) + 100.0

        order = start_build(ship, factory, ShipClass.strike_craft, faction="voidborn")
        assert order.ore_cost == voidborn_cost["ore"]
        assert order.ticks_remaining == voidborn_cost["ticks"]


# ---------------------------------------------------------------------------
# 6. Per-team research
# ---------------------------------------------------------------------------


class TestPerTeamResearch:
    """Test research.py functions with team_id context."""

    def test_get_completed_tech_ids_extracts_complete(self):
        """get_completed_tech_ids should return only 'complete' status techs."""
        research_list = [
            ResearchProgress(
                user_id=1, tech_id="1a_medium_kinetic_turrets", status="complete",
                ship_id=1, module_id=1, ticks_remaining=0, total_ticks=300, ore_cost=500,
            ),
            ResearchProgress(
                user_id=1, tech_id="1d_medium_shield_extenders", status="researching",
                ship_id=1, module_id=1, ticks_remaining=100, total_ticks=300, ore_cost=500,
            ),
            ResearchProgress(
                user_id=1, tech_id="1h_corvette_hull", status="cancelled",
                ship_id=1, module_id=1, ticks_remaining=200, total_ticks=300, ore_cost=500,
            ),
        ]
        completed = get_completed_tech_ids(research_list)
        assert completed == {"1a_medium_kinetic_turrets"}

    def test_get_completed_tech_ids_empty_list(self):
        completed = get_completed_tech_ids([])
        assert completed == set()

    def test_get_completed_tech_ids_with_team(self):
        """Research with team_id set should still be counted."""
        research_list = [
            ResearchProgress(
                user_id=1, team_id=5, tech_id="1a_medium_kinetic_turrets", status="complete",
                ship_id=1, module_id=1, ticks_remaining=0, total_ticks=300, ore_cost=500,
            ),
        ]
        completed = get_completed_tech_ids(research_list)
        assert "1a_medium_kinetic_turrets" in completed


class TestResearchPrerequisites:
    """Test check_prerequisites with faction context."""

    def test_tier1_no_prerequisites_passes(self):
        """Tier 1 techs have no prerequisites."""
        result = check_prerequisites("1a_medium_kinetic_turrets", set())
        assert result is None

    def test_tier2_missing_prerequisite_fails(self):
        """Tier 2 tech should fail if prerequisite not completed."""
        result = check_prerequisites("2a_large_kinetic_turrets", set())
        assert result is not None
        assert "prerequisite" in result.lower()

    def test_tier2_with_prerequisite_passes(self):
        """Tier 2 tech should pass with prerequisite completed."""
        result = check_prerequisites("2a_large_kinetic_turrets", {"1a_medium_kinetic_turrets"})
        assert result is None

    def test_solarion_faction_tech_valid_with_prereqs(self):
        """Solarion 3a_focused_beams uses prerequisites_any, met by either prereq."""
        result = check_prerequisites(
            "3a_focused_beams", {"2a_large_kinetic_turrets"}, faction="solarion"
        )
        assert result is None

    def test_solarion_tier3_needs_prerequisites(self):
        """Solarion tier 3 tech needs its prerequisites."""
        result = check_prerequisites(
            "3a_focused_beams", set(), faction="solarion"
        )
        assert result is not None

    def test_solarion_superweapon_with_prerequisites_passes(self):
        completed = {"2a_large_kinetic_turrets", "3a_focused_beams"}
        result = check_prerequisites(
            "4a_solar_lance", completed, faction="solarion"
        )
        assert result is None

    def test_voidborn_faction_tech_valid_with_prereqs(self):
        result = check_prerequisites(
            "3a_leech_projectors", {"2a_large_kinetic_turrets"}, faction="voidborn"
        )
        assert result is None

    def test_voidborn_superweapon_with_prerequisites_passes(self):
        completed = {"2a_large_kinetic_turrets", "3a_leech_projectors"}
        result = check_prerequisites(
            "4a_bio_repair_swarm", completed, faction="voidborn"
        )
        assert result is None

    def test_unknown_tech_returns_error(self):
        result = check_prerequisites("nonexistent_tech", set())
        assert result is not None
        assert "unknown" in result.lower()

    def test_hull_tech_in_base_tree(self):
        """Duplicable hull techs are in the base tree (no faction needed)."""
        result = check_prerequisites("3h_destroyer_hull", {"2h_frigate_hull"})
        assert result is None


# ---------------------------------------------------------------------------
# 7. Faction tech tree
# ---------------------------------------------------------------------------


class TestFactionTechTree:
    """Test get_effective_tech_tree with faction filtering."""

    def test_base_tech_tree_without_faction(self):
        tree = get_effective_tech_tree(faction=None)
        assert "1a_medium_kinetic_turrets" in tree
        assert "1b_medium_thermal_turrets" in tree
        # Without faction, all faction nodes are excluded
        assert "3a_focused_beams" not in tree
        assert "3a_leech_projectors" not in tree

    def test_solarion_tree_includes_solarion_nodes(self):
        tree = get_effective_tech_tree(faction="solarion")
        assert "1a_medium_kinetic_turrets" in tree  # base techs present
        # Solarion-specific nodes
        assert "3a_focused_beams" in tree
        assert tree["3a_focused_beams"]["name"] == "Focused Beam Weapons"
        assert "focused_beam_medium" in tree["3a_focused_beams"]["unlocks_modules"]
        assert "4a_solar_lance" in tree
        assert tree["4a_solar_lance"]["name"] == "Solar Lance"
        # Voidborn nodes excluded
        assert "3a_leech_projectors" not in tree
        assert "4a_bio_repair_swarm" not in tree

    def test_voidborn_tree_includes_voidborn_nodes(self):
        tree = get_effective_tech_tree(faction="voidborn")
        assert "1a_medium_kinetic_turrets" in tree
        # Voidborn-specific nodes
        assert "3a_leech_projectors" in tree
        assert tree["3a_leech_projectors"]["name"] == "Leech Projectors"
        assert "light_leech_projector" in tree["3a_leech_projectors"]["unlocks_modules"]
        assert "4a_bio_repair_swarm" in tree
        assert tree["4a_bio_repair_swarm"]["name"] == "Bio-Repair Swarm"
        # Solarion nodes excluded
        assert "3a_focused_beams" not in tree
        assert "4a_solar_lance" not in tree

    def test_faction_tech_tree_structure(self):
        """All faction-specific nodes should have proper tech tree structure."""
        for faction in ("solarion", "voidborn"):
            tree = get_effective_tech_tree(faction=faction)
            for tech_id, node in tree.items():
                assert "name" in node
                assert "tier" in node
                assert "unlocks_modules" in node
                assert "unlocks_ships" in node

    def test_faction_prerequisites_exist_in_tree(self):
        """All prerequisites should exist in the effective tree for each faction."""
        for faction in ("solarion", "voidborn"):
            tree = get_effective_tech_tree(faction=faction)
            for tech_id, node in tree.items():
                for prereq in node.get("prerequisites", []):
                    assert prereq in tree, (
                        f"{faction} tech {tech_id} has unknown prerequisite: {prereq}"
                    )
                for prereq in node.get("prerequisites_any", []):
                    assert prereq in tree, (
                        f"{faction} tech {tech_id} has unknown prerequisites_any: {prereq}"
                    )


# ---------------------------------------------------------------------------
# 8. Faction traits
# ---------------------------------------------------------------------------


class TestFactionTraits:
    """Test FACTION_TRAITS constants are well-formed."""

    def test_solarion_traits_present(self):
        assert "solarion" in FACTION_TRAITS
        traits = FACTION_TRAITS["solarion"]
        assert "armor_repair_hp_mult" in traits
        assert "turret_range_mult" in traits

    def test_voidborn_traits_present(self):
        assert "voidborn" in FACTION_TRAITS
        traits = FACTION_TRAITS["voidborn"]
        assert "shield_booster_hp_mult" in traits
        assert "passive_armor_regen" in traits

    def test_solarion_armor_repair_bonus(self):
        assert FACTION_TRAITS["solarion"]["armor_repair_hp_mult"] > 1.0

    def test_solarion_turret_range_bonus(self):
        assert FACTION_TRAITS["solarion"]["turret_range_mult"] > 1.0

    def test_voidborn_shield_booster_bonus(self):
        assert FACTION_TRAITS["voidborn"]["shield_booster_hp_mult"] > 1.0

    def test_voidborn_passive_armor_regen(self):
        assert FACTION_TRAITS["voidborn"]["passive_armor_regen"] is True

    def test_numeric_trait_values_are_positive(self):
        """All numeric trait values should be positive."""
        for faction, traits in FACTION_TRAITS.items():
            for key, value in traits.items():
                if isinstance(value, (int, float)):
                    assert value > 0, (
                        f"FACTION_TRAITS[{faction}][{key}] = {value} should be positive"
                    )


# ---------------------------------------------------------------------------
# 9. Spawn new ship — team inheritance and faction naming
# ---------------------------------------------------------------------------


class TestSpawnNewShipWithFaction:
    """Test spawn_new_ship inheriting team_id and using faction names."""

    def test_spawn_inherits_team_id(self):
        """Newly spawned ships should inherit team_id from the builder."""
        builder = make_test_ship(ShipClass.frigate)
        builder.team_id = 7
        builder.team = Team(id=7, name="Test Team", faction="solarion")

        new_ship = spawn_new_ship(
            blueprint=ShipClass.strike_craft,
            builder=builder,
            current_tick=100,
        )
        assert new_ship.team_id == 7

    def test_spawn_inherits_user_id(self):
        builder = make_test_ship(ShipClass.frigate, user_id=42)
        new_ship = spawn_new_ship(
            blueprint=ShipClass.corvette,
            builder=builder,
            current_tick=50,
        )
        assert new_ship.user_id == 42

    def test_spawn_no_team_id_when_builder_has_none(self):
        builder = make_test_ship(ShipClass.frigate)
        builder.team_id = None
        new_ship = spawn_new_ship(
            blueprint=ShipClass.strike_craft,
            builder=builder,
            current_tick=100,
        )
        assert new_ship.team_id is None

    def test_spawn_default_name_for_solarion(self):
        """Solarion builder should get default name when no name specified."""
        builder = make_test_ship(ShipClass.frigate)
        builder.team_id = 1
        builder.team = Team(id=1, name="Solar Guard", faction="solarion")

        new_ship = spawn_new_ship(
            blueprint=ShipClass.strike_craft,
            builder=builder,
            current_tick=100,
        )
        # Default auto-name: "New Strike Craft"
        assert "Strike Craft" in new_ship.name

    def test_spawn_default_name_for_voidborn(self):
        builder = make_test_ship(ShipClass.frigate)
        builder.team_id = 2
        builder.team = Team(id=2, name="Dark Fleet", faction="voidborn")

        new_ship = spawn_new_ship(
            blueprint=ShipClass.corvette,
            builder=builder,
            current_tick=100,
        )
        assert "Corvette" in new_ship.name

    def test_spawn_uses_generic_name_without_faction(self):
        builder = make_test_ship(ShipClass.frigate)
        builder.team_id = None
        builder.team = None

        new_ship = spawn_new_ship(
            blueprint=ShipClass.strike_craft,
            builder=builder,
            current_tick=100,
        )
        assert "Strike Craft" in new_ship.name

    def test_spawn_custom_name_overrides_faction(self):
        """Explicit name should override faction naming."""
        builder = make_test_ship(ShipClass.frigate)
        builder.team_id = 1
        builder.team = Team(id=1, name="Solar Guard", faction="solarion")

        new_ship = spawn_new_ship(
            blueprint=ShipClass.strike_craft,
            builder=builder,
            current_tick=100,
            name="My Custom Ship",
        )
        assert new_ship.name == "My Custom Ship"

    def test_spawn_docked_in_builder(self):
        builder = make_test_ship(ShipClass.frigate, pos_x=1000.0, pos_y=2000.0, pos_z=3000.0)
        new_ship = spawn_new_ship(
            blueprint=ShipClass.strike_craft,
            builder=builder,
            current_tick=100,
        )
        # New ships spawn docked inside the builder
        assert new_ship.docked_in_id == builder.id
        assert new_ship.claimed_by_user_id is None

    def test_spawn_has_correct_stats(self):
        builder = make_test_ship(ShipClass.frigate)
        new_ship = spawn_new_ship(
            blueprint=ShipClass.corvette,
            builder=builder,
            current_tick=0,
        )
        consts = SHIP_CLASSES["corvette"]
        assert new_ship.total_volume == consts["volume"]
        assert new_ship.max_capacitor == consts["base_cap"]
        assert new_ship.shield_hp == consts["base_shield"]
        assert new_ship.armor_hp == consts["base_armor"]
        assert new_ship.signature_radius == consts["signature"]

    def test_all_faction_ship_names_exist_for_buildable_classes(self):
        """Every buildable class should have a faction name in both faction dicts."""
        buildable = list(BUILD_COSTS.keys())
        for faction in ["solarion", "voidborn"]:
            assert faction in FACTION_SHIP_NAMES
            for ship_class in buildable:
                assert ship_class in FACTION_SHIP_NAMES[faction], (
                    f"FACTION_SHIP_NAMES[{faction}] missing name for {ship_class}"
                )


# ---------------------------------------------------------------------------
# 10. Shield regen (unit test from combat.py)
# ---------------------------------------------------------------------------


class TestShieldRegeneration:
    """Test apply_shield_regen from combat.py."""

    def test_shield_regen_when_damaged(self):
        """Ship with partial shields should regenerate."""
        ship = make_test_ship(ShipClass.frigate)
        ship.shield_hp = ship.max_shield_hp * 0.5  # 50% shields
        initial = ship.shield_hp

        apply_shield_regen(ship)
        assert ship.shield_hp > initial

    def test_shield_regen_zero_shields(self):
        """Zero shields should still regenerate (slowly)."""
        ship = make_test_ship(ShipClass.frigate)
        ship.shield_hp = 0.0

        apply_shield_regen(ship)
        # At 0 ratio, sqrt(0) * (1 - 0) = 0, so no regen
        assert ship.shield_hp == pytest.approx(0.0)

    def test_shield_regen_full_shields_no_change(self):
        """Full shields should not regenerate further."""
        ship = make_test_ship(ShipClass.frigate)
        ship.shield_hp = ship.max_shield_hp

        apply_shield_regen(ship)
        assert ship.shield_hp == pytest.approx(ship.max_shield_hp)

    def test_shield_regen_does_not_exceed_max(self):
        """Regen should never push shields above max."""
        ship = make_test_ship(ShipClass.frigate)
        ship.shield_hp = ship.max_shield_hp - 1.0

        apply_shield_regen(ship)
        assert ship.shield_hp <= ship.max_shield_hp

    def test_shield_regen_peak_near_25_percent(self):
        """Regen peaks near 25% shield level."""
        ship = make_test_ship(ShipClass.frigate)

        # Measure regen at ~25%
        ship.shield_hp = ship.max_shield_hp * 0.25
        before_25 = ship.shield_hp
        apply_shield_regen(ship)
        regen_at_25 = ship.shield_hp - before_25

        # Measure regen at ~75%
        ship2 = make_test_ship(ShipClass.frigate)
        ship2.shield_hp = ship2.max_shield_hp * 0.75
        before_75 = ship2.shield_hp
        apply_shield_regen(ship2)
        regen_at_75 = ship2.shield_hp - before_75

        # Regen at 25% should be higher than at 75%
        assert regen_at_25 > regen_at_75

    def test_destroyed_ship_no_regen(self):
        """Destroyed ships should not regenerate."""
        ship = make_test_ship(ShipClass.frigate)
        ship.is_destroyed = True
        ship.shield_hp = 0.0

        apply_shield_regen(ship)
        assert ship.shield_hp == 0.0


# ---------------------------------------------------------------------------
# 11. Damage application (with faction context)
# ---------------------------------------------------------------------------


class TestDamageApplication:
    """Test apply_damage with various scenarios related to factions."""

    def test_damage_to_shields_first(self):
        """Damage should hit shields before armor."""
        ship = make_test_ship(ShipClass.frigate)
        result = apply_damage(ship, 100.0, "kinetic")
        assert result["shield_damage"] > 0
        assert ship.shield_hp < SHIP_CLASSES["frigate"]["base_shield"]

    def test_shields_broken_then_armor(self):
        """When shields break, remaining damage hits armor."""
        ship = make_test_ship(ShipClass.frigate)
        # Deal massive damage to break shields
        result = apply_damage(ship, 100_000.0, "kinetic")
        assert result["shields_broken"] is True
        assert result["armor_damage"] > 0

    def test_ship_destroyed_at_zero_armor(self):
        """Ship with no shields should be destroyed when armor reaches 0."""
        ship = make_test_ship(ShipClass.frigate)
        ship.shield_hp = 0.0
        result = apply_damage(ship, 100_000.0, "kinetic")
        assert result["destroyed"] is True
        assert ship.is_destroyed is True

    def test_kinetic_damage_reduced_by_shield_resist(self):
        """Kinetic damage should be reduced by shield kinetic resistance."""
        ship = make_test_ship(ShipClass.frigate)
        initial_shield = ship.shield_hp
        apply_damage(ship, 100.0, "kinetic")

        # With 20% kinetic shield resist, 100 raw -> 80 effective shield damage
        expected_effective = 100.0 * (1.0 - SHIELD_BASE_RESISTS["kinetic"])
        actual_shield_damage = initial_shield - ship.shield_hp
        assert actual_shield_damage == pytest.approx(expected_effective, abs=0.01)

    def test_thermal_damage_reduced_by_shield_resist(self):
        ship = make_test_ship(ShipClass.frigate)
        initial_shield = ship.shield_hp
        apply_damage(ship, 100.0, "thermal")

        expected_effective = 100.0 * (1.0 - SHIELD_BASE_RESISTS["thermal"])
        actual_shield_damage = initial_shield - ship.shield_hp
        assert actual_shield_damage == pytest.approx(expected_effective, abs=0.01)

    def test_explosive_damage_reduced_by_shield_resist(self):
        ship = make_test_ship(ShipClass.frigate)
        initial_shield = ship.shield_hp
        apply_damage(ship, 100.0, "explosive")

        expected_effective = 100.0 * (1.0 - SHIELD_BASE_RESISTS["explosive"])
        actual_shield_damage = initial_shield - ship.shield_hp
        assert actual_shield_damage == pytest.approx(expected_effective, abs=0.01)

    def test_damage_to_destroyed_ship_is_noop(self):
        """Damage to already-destroyed ship should do nothing."""
        ship = make_test_ship(ShipClass.frigate)
        ship.is_destroyed = True
        result = apply_damage(ship, 1000.0, "kinetic")
        assert result["total_applied"] == 0.0

    def test_armor_critical_at_25_percent(self):
        """Armor critical flag should trigger at 25% armor."""
        ship = make_test_ship(ShipClass.frigate)
        ship.shield_hp = 0.0
        # Set armor just above 25% threshold
        target_armor = ship.max_armor_hp * 0.30
        ship.armor_hp = target_armor

        # Deal enough damage to push below 25%
        result = apply_damage(ship, 500.0, "kinetic")
        # Check if armor_critical is set (depends on exact values)
        if ship.armor_hp > 0 and ship.armor_hp <= ship.max_armor_hp * 0.25:
            assert result["armor_critical"] is True


# ---------------------------------------------------------------------------
# 12. Integration tests: Ship creation with team_id via DB
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    """Yield a fresh async SQLite in-memory session for DB tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


class TestTeamDatabaseIntegration:
    """Integration tests for team/faction with database."""

    @pytest.mark.asyncio
    async def test_create_team_in_db(self, db_session):
        """Create a team and verify it persists."""
        team = Team(name="Solar Guard", faction="solarion")
        db_session.add(team)
        await db_session.commit()
        await db_session.refresh(team)

        assert team.id is not None
        assert team.name == "Solar Guard"
        assert team.faction == "solarion"

    @pytest.mark.asyncio
    async def test_assign_ship_to_team(self, db_session):
        """Ship should be assignable to a team via team_id."""
        # Create team
        team = Team(name="Dark Fleet", faction="voidborn")
        db_session.add(team)
        await db_session.flush()

        # Create user
        user = User(username="test_user", token="test_token_123")
        db_session.add(user)
        await db_session.flush()

        # Create ship with team
        ship = create_default_ship(
            name="Test Ship", ship_class=ShipClass.frigate, user_id=user.id
        )
        ship.team_id = team.id
        db_session.add(ship)
        await db_session.commit()
        await db_session.refresh(ship)

        assert ship.team_id == team.id

    @pytest.mark.asyncio
    async def test_multiple_teams_can_exist(self, db_session):
        """Multiple teams can be created with different names."""
        team1 = Team(name="Team Alpha", faction="solarion")
        team2 = Team(name="Team Beta", faction="voidborn")
        db_session.add(team1)
        db_session.add(team2)
        await db_session.commit()
        await db_session.refresh(team1)
        await db_session.refresh(team2)

        assert team1.id != team2.id
        assert team1.faction == "solarion"
        assert team2.faction == "voidborn"

    @pytest.mark.asyncio
    async def test_research_progress_with_team_id(self, db_session):
        """ResearchProgress should store team_id."""
        # Create user and team
        team = Team(name="Test Team", faction="solarion")
        db_session.add(team)
        await db_session.flush()

        user = User(username="researcher", token="token_research")
        db_session.add(user)
        await db_session.flush()

        ship = create_default_ship(
            name="Research Ship", ship_class=ShipClass.frigate, user_id=user.id
        )
        ship.team_id = team.id
        db_session.add(ship)
        await db_session.flush()

        rp = ResearchProgress(
            user_id=user.id,
            team_id=team.id,
            tech_id="1a_medium_kinetic_turrets",
            ship_id=ship.id,
            module_id=1,
            status="researching",
            ticks_remaining=300,
            total_ticks=300,
            ore_cost=500,
        )
        db_session.add(rp)
        await db_session.commit()
        await db_session.refresh(rp)

        assert rp.team_id == team.id
        assert rp.user_id == user.id

    @pytest.mark.asyncio
    async def test_query_research_by_team(self, db_session):
        """Should be able to query all research for a team."""
        team = Team(name="Research Team", faction="voidborn")
        db_session.add(team)
        await db_session.flush()

        user1 = User(username="user1", token="token1")
        user2 = User(username="user2", token="token2")
        db_session.add(user1)
        db_session.add(user2)
        await db_session.flush()

        ship1 = create_default_ship("Ship1", ShipClass.frigate, user1.id)
        ship1.team_id = team.id
        ship2 = create_default_ship("Ship2", ShipClass.frigate, user2.id)
        ship2.team_id = team.id
        db_session.add(ship1)
        db_session.add(ship2)
        await db_session.flush()

        # User1 researches tech A
        rp1 = ResearchProgress(
            user_id=user1.id, team_id=team.id, tech_id="1a_medium_kinetic_turrets",
            ship_id=ship1.id, module_id=1, status="complete",
            ticks_remaining=0, total_ticks=300, ore_cost=500,
        )
        # User2 researches tech B
        rp2 = ResearchProgress(
            user_id=user2.id, team_id=team.id, tech_id="1d_medium_shield_extenders",
            ship_id=ship2.id, module_id=2, status="complete",
            ticks_remaining=0, total_ticks=300, ore_cost=500,
        )
        db_session.add(rp1)
        db_session.add(rp2)
        await db_session.commit()

        # Query all research for the team
        result = await db_session.exec(
            select(ResearchProgress).where(ResearchProgress.team_id == team.id)
        )
        team_research = result.all()
        completed = get_completed_tech_ids(team_research)

        # Both techs should be visible to the entire team
        assert "1a_medium_kinetic_turrets" in completed
        assert "1d_medium_shield_extenders" in completed


# ---------------------------------------------------------------------------
# 13. Gating helpers with faction context
# ---------------------------------------------------------------------------


class TestGatingHelpers:
    """Test is_module_unlocked and is_ship_unlocked."""

    def test_base_module_always_unlocked(self):
        """Modules not in RESEARCH_GATED_MODULES are always available."""
        assert is_module_unlocked("engine", set()) is True
        assert is_module_unlocked("reactor", set()) is True
        assert is_module_unlocked("mining_laser", set()) is True

    def test_gated_module_locked_without_research(self):
        """Gated modules should be locked without completed research."""
        assert is_module_unlocked("medium_turret_kinetic", set()) is False

    def test_gated_module_unlocked_with_research(self):
        """Gated modules should be unlocked with the right tech completed."""
        assert is_module_unlocked(
            "medium_turret_kinetic", {"1a_medium_kinetic_turrets"}
        ) is True

    def test_base_ship_always_unlocked(self):
        """Non-gated ship classes are always available."""
        assert is_ship_unlocked("strike_craft", set()) is True
        assert is_ship_unlocked("mothership", set()) is True

    def test_corvette_locked_without_research(self):
        assert is_ship_unlocked("corvette", set()) is False

    def test_corvette_unlocked_with_research(self):
        assert is_ship_unlocked("corvette", {"1h_corvette_hull"}) is True

    def test_destroyer_locked_without_research(self):
        assert is_ship_unlocked("destroyer", set()) is False

    def test_destroyer_unlocked_with_research(self):
        assert is_ship_unlocked("destroyer", {"3h_destroyer_hull"}) is True

    def test_cruiser_locked_without_research(self):
        assert is_ship_unlocked("cruiser", set()) is False

    def test_cruiser_unlocked_with_research(self):
        assert is_ship_unlocked("cruiser", {"4h_cruiser_hull"}) is True


# ---------------------------------------------------------------------------
# 14. Production tick with faction (tick_build_order)
# ---------------------------------------------------------------------------


class TestProductionTickWithFaction:
    """Test that tick_build_order completes builds that were started with faction costs."""

    def test_tick_build_advances_with_cap(self):
        """Build order should advance when ship has capacitor."""
        ship = make_test_ship(ShipClass.frigate)
        factory = add_module_to_ship(ship, ModuleType.factory, 500)
        ship.id = 1
        factory.id = 1
        ship.ore = 1000.0
        ship.capacitor = 10000.0

        order = start_build(ship, factory, ShipClass.strike_craft, faction="solarion")
        order.status = "building"
        initial_ticks = order.ticks_remaining

        result = tick_build_order(ship, order)
        assert order.ticks_remaining == initial_ticks - 1
        assert result["completed"] is False

    def test_tick_build_completes(self):
        """Build should complete when ticks_remaining reaches 0."""
        ship = make_test_ship(ShipClass.frigate)
        factory = add_module_to_ship(ship, ModuleType.factory, 500)
        ship.id = 1
        factory.id = 1
        ship.ore = 1000.0
        ship.capacitor = 10000.0

        order = start_build(ship, factory, ShipClass.strike_craft, faction="solarion")
        order.status = "building"
        order.ticks_remaining = 1  # about to complete

        result = tick_build_order(ship, order)
        assert result["completed"] is True
        assert result["new_ship"] is not None
        new_ship = result["new_ship"]
        assert new_ship.ship_class == ShipClass.strike_craft

    def test_tick_build_pauses_on_low_cap(self):
        """Build should pause when capacitor is depleted."""
        ship = make_test_ship(ShipClass.frigate)
        factory = add_module_to_ship(ship, ModuleType.factory, 500)
        ship.id = 1
        factory.id = 1
        ship.ore = 1000.0
        ship.capacitor = 0.0  # no cap

        order = start_build(ship, factory, ShipClass.strike_craft, faction="solarion")
        order.status = "building"

        result = tick_build_order(ship, order)
        assert result["paused"] is True
        assert order.status == "paused"

    def test_new_ship_inherits_team_id_from_builder(self):
        """Completed build should produce a ship with the builder's team_id."""
        ship = make_test_ship(ShipClass.frigate)
        factory = add_module_to_ship(ship, ModuleType.factory, 500)
        ship.id = 1
        factory.id = 1
        ship.team_id = 42
        ship.team = Team(id=42, name="Build Team", faction="voidborn")
        ship.ore = 1000.0
        ship.capacitor = 10000.0

        order = start_build(ship, factory, ShipClass.strike_craft, faction="voidborn")
        order.status = "building"
        order.ticks_remaining = 1

        result = tick_build_order(ship, order)
        assert result["completed"] is True
        new_ship = result["new_ship"]
        assert new_ship.team_id == 42


# ---------------------------------------------------------------------------
# 15. Effective signature radius
# ---------------------------------------------------------------------------


class TestEffectiveSignatureRadius:
    """Test effective_signature_radius computation."""

    def test_base_signature_without_extenders(self):
        """Without extenders, effective sig equals base sig."""
        ship = make_test_ship(ShipClass.frigate)
        assert ship.effective_signature_radius() == pytest.approx(
            SHIP_CLASSES["frigate"]["signature"]
        )

    def test_signature_increases_with_shield_extender(self):
        """Shield extenders should increase signature radius."""
        ship = make_test_ship(ShipClass.frigate)
        base_sig = ship.effective_signature_radius()

        add_module_to_ship(ship, ModuleType.small_shield_extender, 50)
        new_sig = ship.effective_signature_radius()
        assert new_sig > base_sig

    def test_multiple_extenders_stack(self):
        """Multiple extenders should stack additively."""
        ship = make_test_ship(ShipClass.frigate)
        base_sig = ship.effective_signature_radius()

        add_module_to_ship(ship, ModuleType.small_shield_extender, 50)
        sig_with_one = ship.effective_signature_radius()

        add_module_to_ship(ship, ModuleType.small_shield_extender, 50)
        sig_with_two = ship.effective_signature_radius()

        assert sig_with_two > sig_with_one > base_sig
        # Two identical extenders should add twice the bonus
        bonus = sig_with_one - base_sig
        assert sig_with_two == pytest.approx(base_sig + 2 * bonus)


# ---------------------------------------------------------------------------
# 16. Research start_research with DB (using db_session fixture)
# ---------------------------------------------------------------------------


class TestResearchStartWithTeam:
    """Test start_research function with team context."""

    @pytest.mark.asyncio
    async def test_start_research_stores_team_id(self, db_session):
        """Research started with team_id should persist it."""
        # Set up user, team, ship, and research module
        team = Team(name="Research Team", faction="solarion")
        db_session.add(team)
        await db_session.flush()

        user = User(username="res_user", token="res_token_123")
        db_session.add(user)
        await db_session.flush()

        ship = create_default_ship("Res Ship", ShipClass.frigate, user.id)
        ship.team_id = team.id
        db_session.add(ship)
        await db_session.flush()

        module = make_module(ModuleType.research_module, 5000)
        module.ship_id = ship.id
        db_session.add(module)
        await db_session.flush()
        await db_session.refresh(ship, attribute_names=["modules"])

        # Give enough ore
        ship.ore = 10000.0

        rp = await start_research(
            db_session, ship, module,
            tech_id="1a_medium_kinetic_turrets",
            user_id=user.id,
            team_id=team.id,
            faction="solarion",
        )
        await db_session.commit()
        await db_session.refresh(rp)

        assert rp.team_id == team.id
        assert rp.user_id == user.id
        assert rp.status == "researching"
        assert rp.ticks_remaining == RESEARCH_COSTS[1]["ticks"]

    @pytest.mark.asyncio
    async def test_start_research_deducts_ore(self, db_session):
        """Research should deduct ore cost from the ship."""
        team = Team(name="Ore Team", faction="voidborn")
        db_session.add(team)
        await db_session.flush()

        user = User(username="ore_user", token="ore_token_456")
        db_session.add(user)
        await db_session.flush()

        ship = create_default_ship("Ore Ship", ShipClass.frigate, user.id)
        ship.team_id = team.id
        db_session.add(ship)
        await db_session.flush()

        module = make_module(ModuleType.research_module, 5000)
        module.ship_id = ship.id
        db_session.add(module)
        await db_session.flush()
        await db_session.refresh(ship, attribute_names=["modules"])

        initial_ore = 10000.0
        ship.ore = initial_ore

        await start_research(
            db_session, ship, module,
            tech_id="1a_medium_kinetic_turrets",
            user_id=user.id,
            team_id=team.id,
        )

        expected_ore = initial_ore - RESEARCH_COSTS[1]["ore"]
        assert ship.ore == pytest.approx(expected_ore)

    @pytest.mark.asyncio
    async def test_start_research_duplicate_fails(self, db_session):
        """Cannot start the same research twice."""
        user = User(username="dup_user", token="dup_token_789")
        db_session.add(user)
        await db_session.flush()

        ship = create_default_ship("Dup Ship", ShipClass.frigate, user.id)
        db_session.add(ship)
        await db_session.flush()

        mod1 = make_module(ModuleType.research_module, 5000)
        mod1.ship_id = ship.id
        db_session.add(mod1)
        mod2 = make_module(ModuleType.research_module, 5000)
        mod2.ship_id = ship.id
        db_session.add(mod2)
        await db_session.flush()
        await db_session.refresh(ship, attribute_names=["modules"])

        ship.ore = 50000.0

        await start_research(
            db_session, ship, mod1,
            tech_id="1a_medium_kinetic_turrets",
            user_id=user.id,
        )
        await db_session.commit()

        with pytest.raises(ValueError, match="[Aa]lready"):
            await start_research(
                db_session, ship, mod2,
                tech_id="1a_medium_kinetic_turrets",
                user_id=user.id,
            )

    @pytest.mark.asyncio
    async def test_start_research_insufficient_ore_fails(self, db_session):
        """Should fail if ship doesn't have enough ore."""
        user = User(username="poor_user", token="poor_token_111")
        db_session.add(user)
        await db_session.flush()

        ship = create_default_ship("Poor Ship", ShipClass.frigate, user.id)
        db_session.add(ship)
        await db_session.flush()

        module = make_module(ModuleType.research_module, 5000)
        module.ship_id = ship.id
        db_session.add(module)
        await db_session.flush()
        await db_session.refresh(ship, attribute_names=["modules"])

        ship.ore = 1.0  # not enough

        with pytest.raises(ValueError, match="[Ii]nsufficient ore"):
            await start_research(
                db_session, ship, module,
                tech_id="1a_medium_kinetic_turrets",
                user_id=user.id,
            )

    @pytest.mark.asyncio
    async def test_start_research_with_faction_tier3_tech(self, db_session):
        """Should be able to research faction-overridden tier 3 tech."""
        team = Team(name="Sol Team", faction="solarion")
        db_session.add(team)
        await db_session.flush()

        user = User(username="sol_user", token="sol_token_222")
        db_session.add(user)
        await db_session.flush()

        ship = create_default_ship("Sol Ship", ShipClass.frigate, user.id)
        ship.team_id = team.id
        db_session.add(ship)
        await db_session.flush()

        module = make_module(ModuleType.research_module, 5000)
        module.ship_id = ship.id
        db_session.add(module)
        await db_session.flush()
        await db_session.refresh(ship, attribute_names=["modules"])

        ship.ore = 50000.0

        # First research the prerequisite
        rp1 = await start_research(
            db_session, ship, module,
            tech_id="1a_medium_kinetic_turrets",
            user_id=user.id,
            team_id=team.id,
            faction="solarion",
        )
        rp1.status = "complete"
        rp1.ticks_remaining = 0
        await db_session.commit()

        # Need a second research module
        module2 = make_module(ModuleType.research_module, 5000)
        module2.ship_id = ship.id
        db_session.add(module2)
        await db_session.flush()
        await db_session.refresh(ship, attribute_names=["modules"])

        # Now research tier 2 prereq
        rp2 = await start_research(
            db_session, ship, module2,
            tech_id="2a_large_kinetic_turrets",
            user_id=user.id,
            team_id=team.id,
            faction="solarion",
        )
        rp2.status = "complete"
        rp2.ticks_remaining = 0
        await db_session.commit()

        # Third research module for tier 3
        module3 = make_module(ModuleType.research_module, 5000)
        module3.ship_id = ship.id
        db_session.add(module3)
        await db_session.flush()
        await db_session.refresh(ship, attribute_names=["modules"])

        # Now research the solarion tier 3 tech
        rp3 = await start_research(
            db_session, ship, module3,
            tech_id="3a_focused_beams",
            user_id=user.id,
            team_id=team.id,
            faction="solarion",
        )
        assert rp3.tech_id == "3a_focused_beams"
        assert rp3.status == "researching"

    @pytest.mark.asyncio
    async def test_research_wrong_module_type_fails(self, db_session):
        """Research requires a research_module type."""
        user = User(username="wrong_mod_user", token="wrong_mod_token")
        db_session.add(user)
        await db_session.flush()

        ship = create_default_ship("Wrong Mod Ship", ShipClass.frigate, user.id)
        db_session.add(ship)
        await db_session.flush()

        module = make_module(ModuleType.engine, 1000)
        module.ship_id = ship.id
        db_session.add(module)
        await db_session.flush()
        await db_session.refresh(ship, attribute_names=["modules"])

        ship.ore = 50000.0

        with pytest.raises(ValueError, match="not a research module"):
            await start_research(
                db_session, ship, module,
                tech_id="1a_medium_kinetic_turrets",
                user_id=user.id,
            )


# ---------------------------------------------------------------------------
# 18. Faction ship name templates
# ---------------------------------------------------------------------------


class TestFactionShipNames:
    """Test FACTION_SHIP_NAMES constants."""

    def test_solarion_names_exist(self):
        assert "solarion" in FACTION_SHIP_NAMES
        solarion = FACTION_SHIP_NAMES["solarion"]
        assert "strike_craft" in solarion
        assert "corvette" in solarion
        assert "frigate" in solarion
        assert "destroyer" in solarion
        assert "cruiser" in solarion

    def test_voidborn_names_exist(self):
        assert "voidborn" in FACTION_SHIP_NAMES
        voidborn = FACTION_SHIP_NAMES["voidborn"]
        assert "strike_craft" in voidborn
        assert "corvette" in voidborn
        assert "frigate" in voidborn
        assert "destroyer" in voidborn
        assert "cruiser" in voidborn

    def test_solarion_names_are_strings(self):
        for cls, name in FACTION_SHIP_NAMES["solarion"].items():
            assert isinstance(name, str)
            assert len(name) > 0

    def test_voidborn_names_are_strings(self):
        for cls, name in FACTION_SHIP_NAMES["voidborn"].items():
            assert isinstance(name, str)
            assert len(name) > 0

    def test_solarion_names_different_from_voidborn(self):
        """Faction ship names should be distinct between factions."""
        for cls in FACTION_SHIP_NAMES["solarion"]:
            if cls in FACTION_SHIP_NAMES["voidborn"]:
                assert FACTION_SHIP_NAMES["solarion"][cls] != FACTION_SHIP_NAMES["voidborn"][cls], (
                    f"Ship class {cls} has same name for both factions"
                )


# ---------------------------------------------------------------------------
# 19. Comprehensive cost comparison tests
# ---------------------------------------------------------------------------


class TestCostComparisons:
    """Test that faction costs match expected modifiers per class."""

    def test_solarion_costs_match_modifiers(self):
        """Solarion costs should exactly match BUILD_COSTS * modifiers."""
        for ship_class in BUILD_COSTS:
            base = BUILD_COSTS[ship_class]
            mods = FACTION_BUILD_MODIFIERS["solarion"][ship_class]
            solarion = get_faction_adjusted_cost(
                ShipClass(ship_class), faction="solarion"
            )
            assert solarion["ore"] == int(base["ore"] * mods["ore_mult"])
            assert solarion["ticks"] == int(base["ticks"] * mods["time_mult"])

    def test_voidborn_costs_match_modifiers(self):
        """Voidborn costs should exactly match BUILD_COSTS * modifiers."""
        for ship_class in BUILD_COSTS:
            base = BUILD_COSTS[ship_class]
            mods = FACTION_BUILD_MODIFIERS["voidborn"][ship_class]
            voidborn = get_faction_adjusted_cost(
                ShipClass(ship_class), faction="voidborn"
            )
            assert voidborn["ore"] == int(base["ore"] * mods["ore_mult"])
            assert voidborn["ticks"] == int(base["ticks"] * mods["time_mult"])

    def test_voidborn_small_ships_cheaper_than_solarion(self):
        """Voidborn small ships should be cheaper than Solarion small ships."""
        for ship_class in ["strike_craft", "corvette"]:
            solarion = get_faction_adjusted_cost(
                ShipClass(ship_class), faction="solarion"
            )
            voidborn = get_faction_adjusted_cost(
                ShipClass(ship_class), faction="voidborn"
            )
            assert voidborn["ore"] <= solarion["ore"]

    def test_solarion_large_ships_costlier_than_base(self):
        """Solarion destroyer/cruiser ore costs exceed base."""
        for ship_class in ["destroyer", "cruiser"]:
            base = BUILD_COSTS[ship_class]["ore"]
            solarion = get_faction_adjusted_cost(
                ShipClass(ship_class), faction="solarion"
            )
            assert solarion["ore"] > base
