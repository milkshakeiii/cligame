#!/usr/bin/env python3
"""
Full real-time playtest: Solarion vs Voidborn.

Two httpx clients play both sides of a complete match against the live server.
Logs everything and produces PLAYTEST_REPORT.md at the end.
"""

import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
REPORT_PATH = Path(__file__).resolve().parent.parent / "PLAYTEST_REPORT.md"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("playtest")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Gap:
    category: str  # bug, missing_feature, balance, ux, crash
    severity: str  # critical, high, medium, low
    description: str
    context: str = ""


@dataclass
class Player:
    name: str
    faction: str
    token: str = ""
    user_id: int = 0
    team_id: int = 0
    mothership_id: int = 0
    ships: dict = field(default_factory=dict)  # ship_id -> ship_data
    ore: float = 0.0
    client: httpx.AsyncClient = field(default=None, repr=False)

    def headers(self):
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}


@dataclass
class PlaytestState:
    match_id: int = 0
    current_tick: int = 0
    gaps: list = field(default_factory=list)
    events_log: list = field(default_factory=list)
    command_results: list = field(default_factory=list)
    phase: str = "setup"
    start_time: float = 0.0


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

async def api_post(player: Player, path: str, data: dict = None,
                   expect_status=None, no_auth=False):
    """POST to API, return (status_code, json_body)."""
    try:
        headers = {} if no_auth else player.headers()
        r = await player.client.post(
            f"{BASE}{path}", json=data or {}, headers=headers, timeout=10.0,
        )
        body = r.json() if "json" in r.headers.get("content-type", "") else {}
        if expect_status and r.status_code != expect_status:
            log.warning(f"[{player.name}] POST {path} expected {expect_status}, "
                        f"got {r.status_code}: {body}")
        return r.status_code, body
    except Exception as e:
        log.error(f"[{player.name}] POST {path} failed: {e}")
        return 0, {"error": str(e)}


async def api_get(player: Player, path: str, params: dict = None):
    """GET from API, return (status_code, json_body)."""
    try:
        r = await player.client.get(
            f"{BASE}{path}", headers=player.headers(),
            params=params or {}, timeout=10.0,
        )
        body = r.json() if "json" in r.headers.get("content-type", "") else {}
        return r.status_code, body
    except Exception as e:
        log.error(f"[{player.name}] GET {path} failed: {e}")
        return 0, {"error": str(e)}


async def cmd(player: Player, cmd_type: str, ship_id: int = None,
              payload: dict = None, quiet: bool = False):
    """Send a command and return the response."""
    data = {"type": cmd_type, "payload": payload or {}}
    if ship_id is not None:
        data["ship_id"] = ship_id
    status_code, body = await api_post(player, "/api/commands", data)
    result = {"player": player.name, "type": cmd_type, "ship_id": ship_id,
              "payload": payload, "status": status_code, "response": body}
    if status_code not in (200, 201, 202):
        log.warning(f"[{player.name}] Command {cmd_type} FAILED ({status_code}): {body}")
    elif not quiet:
        log.info(f"[{player.name}] Command {cmd_type} queued (ship={ship_id})")
    return result


async def get_view(player: Player, since_tick: int = None):
    """Get player's world view."""
    params = {}
    if since_tick is not None:
        params["since_tick"] = since_tick
    status_code, body = await api_get(player, "/api/view", params)
    if status_code != 200:
        log.warning(f"[{player.name}] GET /api/view failed ({status_code}): {body}")
    return body


async def get_game_status():
    """Get game tick status (no auth needed)."""
    try:
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/game/status", timeout=5.0)
            return r.json()
    except Exception as e:
        log.error(f"Game status failed: {e}")
        return {}


def get_tick(view: dict) -> int:
    """Extract current tick from a view response."""
    return view.get("tick", 0)


def get_ms(view: dict, ms_id: int) -> dict | None:
    """Find mothership in view."""
    for s in view.get("ships", []):
        if s["id"] == ms_id:
            return s
    return None


def find_modules(ship: dict, module_type: str) -> list:
    """Find modules of a given type on a ship."""
    return [m for m in ship.get("modules", [])
            if m.get("module_type") == module_type]


def find_nearby_asteroids(view: dict) -> list:
    """Find asteroid contacts in nearby list, sorted by distance."""
    asteroids = [c for c in view.get("nearby", [])
                 if c.get("type") == "object" and c.get("object_type") == "asteroid"]
    asteroids.sort(key=lambda c: c.get("distance", float("inf")))
    return asteroids


def find_enemy_ships(view: dict, my_user_id: int) -> list:
    """Find enemy ship contacts in nearby list."""
    return [c for c in view.get("nearby", [])
            if c.get("type") == "ship"
            and c.get("owner_id") is not None
            and c.get("owner_id") != my_user_id]


async def wait_ticks(n: int, label: str = ""):
    """Wait for approximately n ticks (1 tick = 1 second)."""
    if label:
        log.info(f"Waiting {n}s for {label}...")
    await asyncio.sleep(n)


def log_events(view: dict, player: Player, state: PlaytestState,
               interesting_only: bool = True):
    """Log events from a view response."""
    interesting = {"command_rejected", "research_complete", "research_started",
                   "ship_destroyed", "match_ended", "mothership_critical",
                   "mothership_under_attack", "weapon_hit", "weapon_miss",
                   "incoming_damage", "shield_depleted", "armor_critical",
                   "target_locked", "target_lost", "mining", "cargo_full",
                   "cap_depleted", "order_complete"}
    for evt in view.get("events", []):
        state.events_log.append(evt)
        etype = evt.get("type", "")
        if not interesting_only or etype in interesting:
            log.info(f"[{player.name}]   Event t={evt.get('tick','?')}: "
                    f"{etype} — {evt.get('message', '')}")


def log_ship_status(player: Player, ms: dict, tick: int):
    """Log mothership status."""
    log.info(f"[{player.name}] Tick {tick}: ore={ms.get('ore', 0):.0f}, "
            f"shield={ms.get('shield_hp', 0):.0f}/{ms.get('max_shield_hp', 0):.0f}, "
            f"armor={ms.get('armor_hp', 0):.0f}/{ms.get('max_armor_hp', 0):.0f}, "
            f"cap={ms.get('capacitor', 0):.0f}/{ms.get('max_capacitor', 0):.0f}")


# ---------------------------------------------------------------------------
# Phase implementations
# ---------------------------------------------------------------------------

async def phase_setup(p1: Player, p2: Player, state: PlaytestState):
    """Register players, create match, join, start."""
    state.phase = "setup"
    log.info("=" * 60)
    log.info("PHASE: SETUP")
    log.info("=" * 60)

    # Register both players
    for p, uname, faction in [(p1, "solarion_player", "solarion"),
                               (p2, "voidborn_player", "voidborn")]:
        sc, body = await api_post(p, "/api/auth/register",
                                  {"username": uname, "password": "test123"},
                                  no_auth=True)
        if sc == 201:
            p.token, p.user_id = body["token"], body["user_id"]
            log.info(f"[{p.name}] Registered: user_id={p.user_id}")
        elif sc == 409:
            sc, body = await api_post(p, "/api/auth/login",
                                      {"username": uname, "password": "test123"},
                                      no_auth=True)
            if sc != 200:
                state.gaps.append(Gap("crash", "critical", f"Login failed: {body}"))
                return False
            p.token, p.user_id = body["token"], body["user_id"]
            log.info(f"[{p.name}] Logged in: user_id={p.user_id}")
        else:
            state.gaps.append(Gap("crash", "critical", f"Registration failed: {body}"))
            return False

    # P1 creates match
    sc, body = await api_post(p1, "/api/matches",
                              {"name": "Playtest Match", "faction": "solarion"})
    if sc != 201:
        state.gaps.append(Gap("bug", "critical", f"Match creation failed: {body}"))
        return False
    state.match_id = body["id"]
    p1.team_id = body["team1_id"]
    log.info(f"Match created: id={state.match_id}, team1_id={p1.team_id}")

    # P2 joins
    sc, body = await api_post(p2, f"/api/matches/{state.match_id}/join",
                              {"faction": "voidborn"})
    if sc != 200:
        state.gaps.append(Gap("bug", "critical", f"Match join failed: {body}"))
        return False
    p2.team_id = body["team_id"]
    log.info(f"[{p2.name}] Joined match, team_id={p2.team_id}")

    # P1 starts match
    result = await cmd(p1, "start_match", payload={"match_id": state.match_id})
    state.command_results.append(result)
    await wait_ticks(3, "match to start")

    # Verify match started
    sc, body = await api_get(p1, f"/api/matches/{state.match_id}")
    if body.get("status") != "active":
        state.gaps.append(Gap("bug", "critical",
                              f"Match not active: status={body.get('status')}",
                              json.dumps(body, indent=2)))
        return False
    log.info("Match is ACTIVE!")

    # Get initial views to find motherships
    for p in [p1, p2]:
        view = await get_view(p)
        if not view or "ships" not in view:
            state.gaps.append(Gap("bug", "critical",
                                  f"[{p.name}] No ships in view after match start"))
            return False
        state.current_tick = get_tick(view)

        ms = None
        for ship in view.get("ships", []):
            if (ship.get("ship_class") == "mothership"
                    and ship.get("match_id") == state.match_id):
                ms = ship
                break

        if not ms:
            state.gaps.append(Gap("bug", "critical",
                                  f"[{p.name}] No mothership found in view"))
            return False

        p.mothership_id = ms["id"]
        p.ore = ms.get("ore", 0)
        p.ships[ms["id"]] = ms

        log.info(f"[{p.name}] Mothership: id={ms['id']}, ore={p.ore:.0f}, "
                f"pos=({ms.get('pos_x',0):.0f}, {ms.get('pos_y',0):.0f}, "
                f"{ms.get('pos_z',0):.0f})")

        # Log modules
        mod_types = {}
        for m in ms.get("modules", []):
            mt = m.get("module_type", "?")
            mod_types[mt] = mod_types.get(mt, 0) + 1
        log.info(f"[{p.name}] Mothership modules: {mod_types}")

        # Check ore
        if ms.get("ore", 0) != 5000:
            state.gaps.append(Gap("bug", "medium",
                                  f"[{p.name}] Expected 5000 starting ore, got {ms.get('ore')}"))

        # Log nearby asteroids
        asteroids = find_nearby_asteroids(view)
        log.info(f"[{p.name}] Nearby asteroids: {len(asteroids)}")
        for a in asteroids[:5]:
            log.info(f"  Asteroid id={a['id']} dist={a.get('distance',0):.0f}m "
                    f"ore={a.get('ore_remaining', '?')}")

    log.info(f"Setup complete. Match={state.match_id}, Tick={state.current_tick}")
    return True


async def phase_early_game(p1: Player, p2: Player, state: PlaytestState):
    """Ticks 0-600: Move to asteroid, mine ore, install research module, research."""
    state.phase = "early_game"
    log.info("=" * 60)
    log.info("PHASE: EARLY GAME (mining + research)")
    log.info("=" * 60)

    match_start_tick = state.current_tick

    for p in [p1, p2]:
        view = await get_view(p)
        ms = get_ms(view, p.mothership_id)
        if not ms:
            state.gaps.append(Gap("bug", "high", f"[{p.name}] Mothership not in view"))
            continue

        # --- Step 1: Move mothership to nearest asteroid ---
        asteroids = find_nearby_asteroids(view)
        if asteroids:
            closest = asteroids[0]
            dist = closest.get("distance", 0)
            log.info(f"[{p.name}] Moving to nearest asteroid (id={closest['id']}, "
                    f"dist={dist:.0f}m)")
            result = await cmd(p, "move", p.mothership_id,
                               {"order_type": "approach",
                                "target_object_id": closest["id"],
                                "desired_distance": 100.0})
            state.command_results.append(result)
        else:
            state.gaps.append(Gap("bug", "high",
                                  f"[{p.name}] No asteroids visible from mothership"))

        # --- Step 2: Activate scanner and passive detector ---
        for mod in ms.get("modules", []):
            if mod.get("module_type") in ("scanner", "passive_detector"):
                if not mod.get("active"):
                    result = await cmd(p, "activate_module", p.mothership_id,
                                       {"module_id": mod["id"]})
                    state.command_results.append(result)

        # --- Step 3: Activate mining laser ---
        for mod in ms.get("modules", []):
            if mod.get("module_type") == "mining_laser" and not mod.get("active"):
                result = await cmd(p, "activate_module", p.mothership_id,
                                   {"module_id": mod["id"]})
                state.command_results.append(result)

        # --- Step 4: Install missing modules on match mothership ---
        # BUG: MATCH_MOTHERSHIP_LOADOUT is missing engine + research_module
        # Install engine (mandatory — mining requires movement to asteroids)
        has_engine = any(m.get("module_type") == "engine"
                        for m in ms.get("modules", []))
        if not has_engine:
            log.info(f"[{p.name}] Installing engine on mothership (required for movement)")
            result = await cmd(p, "install_module", p.mothership_id,
                               {"module_type": "engine", "volume": 200_000})
            state.command_results.append(result)

        # Install research module (required for tech progression)
        has_research = any(m.get("module_type") == "research_module"
                          for m in ms.get("modules", []))
        if not has_research:
            log.info(f"[{p.name}] Installing research_module on mothership")
            result = await cmd(p, "install_module", p.mothership_id,
                               {"module_type": "research_module", "volume": 5000})
            state.command_results.append(result)

    # Wait for module installs to process, then re-issue movement
    await wait_ticks(5, "module installs")

    # Re-issue movement now that engines are installed
    for p in [p1, p2]:
        view = await get_view(p)
        ms = get_ms(view, p.mothership_id)
        if not ms:
            continue

        # Check speed now
        log.info(f"[{p.name}] Mothership max_speed={ms.get('max_speed', 0):.1f} "
                f"acceleration={ms.get('acceleration', 0):.3f}")

        asteroids = find_nearby_asteroids(view)
        if asteroids:
            closest = asteroids[0]
            log.info(f"[{p.name}] Re-issuing approach to asteroid "
                    f"id={closest['id']} dist={closest.get('distance',0):.0f}m")
            result = await cmd(p, "move", p.mothership_id,
                               {"order_type": "approach",
                                "target_object_id": closest["id"],
                                "desired_distance": 100.0})
            state.command_results.append(result)

    # --- Step 5: Activate research module and start research ---
    for p in [p1, p2]:
        view = await get_view(p)
        ms = get_ms(view, p.mothership_id)
        if not ms:
            continue

        research_mod = next((m for m in ms.get("modules", [])
                            if m.get("module_type") == "research_module"), None)
        if research_mod:
            if not research_mod.get("active"):
                result = await cmd(p, "activate_module", p.mothership_id,
                                   {"module_id": research_mod["id"]})
                state.command_results.append(result)
                await wait_ticks(2, "research module activation")

            result = await cmd(p, "start_research", p.mothership_id,
                               {"tech_id": "1a_medium_weapons",
                                "module_id": research_mod["id"]})
            state.command_results.append(result)
            log.info(f"[{p.name}] Started research: 1a_medium_weapons "
                    "(500 ore, 300 ticks)")
        else:
            state.gaps.append(Gap("bug", "high",
                                  f"[{p.name}] Research module not found after install"))

    # --- Poll during early game ---
    # Wait until ~tick 600 (10 min) or until we have enough ore + research done
    poll_interval = 60
    early_game_end = match_start_tick + 600
    last_poll_tick = state.current_tick

    while True:
        gs = await get_game_status()
        state.current_tick = gs.get("current_tick", 0)

        if state.current_tick >= early_game_end:
            break

        if state.current_tick - last_poll_tick >= poll_interval:
            last_poll_tick = state.current_tick

            for p in [p1, p2]:
                view = await get_view(p, since_tick=state.current_tick - poll_interval)
                ms = get_ms(view, p.mothership_id)
                if ms:
                    p.ore = ms.get("ore", 0)
                    p.ships[ms["id"]] = ms
                    log_ship_status(p, ms, state.current_tick)

                    # Log build orders
                    for bo in ms.get("build_orders", []):
                        log.info(f"[{p.name}]   Build: {bo.get('blueprint')} "
                                f"status={bo.get('status')} "
                                f"remaining={bo.get('ticks_remaining')}")

                # Log events (including mining success/failure)
                log_events(view, p, state)

                # Check pending commands for rejections
                for pc in view.get("pending_commands", []):
                    if pc.get("status") == "rejected":
                        log.warning(f"[{p.name}] REJECTED cmd: {pc.get('type')} — "
                                   f"{pc.get('rejection_reason')}")

        remaining = early_game_end - state.current_tick
        await asyncio.sleep(min(30, max(1, remaining)))

    # End-of-phase status
    for p in [p1, p2]:
        view = await get_view(p)
        ms = get_ms(view, p.mothership_id)
        if ms:
            p.ore = ms.get("ore", 0)
            log.info(f"[{p.name}] End early game: ore={p.ore:.0f}")

    log.info(f"Early game complete at tick {state.current_tick}")
    return True


async def phase_mid_game(p1: Player, p2: Player, state: PlaytestState):
    """Ticks 600-2000: Build fleet, install weapons, move toward enemy."""
    state.phase = "mid_game"
    log.info("=" * 60)
    log.info("PHASE: MID GAME (build fleet + advance)")
    log.info("=" * 60)

    mid_game_end = state.current_tick + 1400  # ~23 min

    # --- Build strike craft ---
    ships_to_build = 4
    for p in [p1, p2]:
        view = await get_view(p)
        ms = get_ms(view, p.mothership_id)
        if not ms:
            continue

        p.ore = ms.get("ore", 0)
        factory_mod = next((m for m in ms.get("modules", [])
                           if m.get("module_type") == "factory"), None)
        if not factory_mod:
            state.gaps.append(Gap("bug", "high",
                                  f"[{p.name}] No factory on mothership"))
            continue

        built = 0
        for i in range(ships_to_build):
            # Voidborn gets 20% discount on strike_craft
            ore_cost = 200 if p.faction == "solarion" else 160
            if p.ore < ore_cost:
                log.warning(f"[{p.name}] Not enough ore for strike_craft #{i+1}: "
                           f"{p.ore:.0f} < {ore_cost}")
                break

            result = await cmd(p, "build", p.mothership_id,
                               {"blueprint": "strike_craft",
                                "factory_module_id": factory_mod["id"]})
            state.command_results.append(result)
            p.ore -= ore_cost
            built += 1

        log.info(f"[{p.name}] Queued {built} strike_craft builds (ore left: {p.ore:.0f})")

    # Start next research if previous completed
    for p in [p1, p2]:
        view = await get_view(p)
        ms = get_ms(view, p.mothership_id)
        if not ms:
            continue
        research_mod = next((m for m in ms.get("modules", [])
                            if m.get("module_type") == "research_module"), None)
        if research_mod:
            result = await cmd(p, "start_research", p.mothership_id,
                               {"tech_id": "1b_medium_defenses",
                                "module_id": research_mod["id"]})
            state.command_results.append(result)
            log.info(f"[{p.name}] Started research: 1b_medium_defenses")

    # --- Poll and manage fleet ---
    poll_interval = 120
    last_poll_tick = state.current_tick
    fleet_moved = {p1.name: False, p2.name: False}

    while True:
        gs = await get_game_status()
        state.current_tick = gs.get("current_tick", 0)

        if state.current_tick >= mid_game_end:
            break

        if state.current_tick - last_poll_tick >= poll_interval:
            last_poll_tick = state.current_tick

            for p in [p1, p2]:
                view = await get_view(p, since_tick=state.current_tick - poll_interval)
                if not view:
                    continue

                all_ships = view.get("ships", [])
                p.ships = {s["id"]: s for s in all_ships}

                ms = p.ships.get(p.mothership_id)
                if ms:
                    p.ore = ms.get("ore", 0)

                # Count non-mothership combat ships
                combat_ships = [s for s in all_ships
                               if s.get("ship_class") != "mothership"
                               and not s.get("is_destroyed", False)]

                log.info(f"[{p.name}] Tick {state.current_tick}: ore={p.ore:.0f}, "
                        f"combat_ships={len(combat_ships)}, total={len(all_ships)}")

                for s in combat_ships:
                    log.info(f"  Ship {s['id']} ({s.get('ship_class')}): "
                            f"pos=({s.get('pos_x',0):.0f},{s.get('pos_y',0):.0f},"
                            f"{s.get('pos_z',0):.0f}) docked_in={s.get('docked_in_id')}")

                # Build orders
                if ms:
                    for bo in ms.get("build_orders", []):
                        log.info(f"  Build: {bo.get('blueprint')} "
                                f"status={bo.get('status')} "
                                f"remaining={bo.get('ticks_remaining')}")

                # Once we have 2+ combat ships, equip and move
                if len(combat_ships) >= 2 and not fleet_moved[p.name]:
                    await equip_and_move_fleet(p, state, combat_ships)
                    fleet_moved[p.name] = True

                log_events(view, p, state)

                # Keep building if we have ore
                if ms and p.ore > 250:
                    factory_mod = next((m for m in ms.get("modules", [])
                                       if m.get("module_type") == "factory"), None)
                    active_builds = [bo for bo in ms.get("build_orders", [])
                                    if bo.get("status") in ("queued", "building")]
                    if factory_mod and len(active_builds) < 2:
                        result = await cmd(p, "build", p.mothership_id,
                                           {"blueprint": "strike_craft",
                                            "factory_module_id": factory_mod["id"]},
                                           quiet=True)
                        state.command_results.append(result)

        remaining = mid_game_end - state.current_tick
        await asyncio.sleep(min(30, max(1, remaining)))

    log.info(f"Mid game complete at tick {state.current_tick}")
    return True


async def equip_and_move_fleet(p: Player, state: PlaytestState,
                                combat_ships: list):
    """Undock ships, install weapons, move toward enemy."""
    log.info(f"[{p.name}] Equipping and moving fleet ({len(combat_ships)} ships)")

    enemy_x = 800_000.0 if p.faction == "solarion" else -800_000.0

    for ship in combat_ships:
        sid = ship["id"]

        # Take manual control (newly built ships are on autopilot)
        if ship.get("autopilot_mode") != "off":
            result = await cmd(p, "assume_control", sid)
            state.command_results.append(result)

        # Undock if needed
        if ship.get("docked_in_id"):
            result = await cmd(p, "undock", sid)
            state.command_results.append(result)

        # Install weapon if none
        has_weapon = any("turret" in m.get("module_type", "") or
                        "missile" in m.get("module_type", "")
                        for m in ship.get("modules", []))
        if not has_weapon:
            result = await cmd(p, "install_module", sid,
                               {"module_type": "small_turret_kinetic"})
            state.command_results.append(result)

    await wait_ticks(5, "undock + equip")

    # Move all toward enemy mothership
    for ship in combat_ships:
        sid = ship["id"]
        result = await cmd(p, "move", sid,
                           {"order_type": "approach",
                            "target_x": enemy_x, "target_y": 0.0, "target_z": 0.0})
        state.command_results.append(result)
        log.info(f"[{p.name}] Ship {sid} moving toward enemy at x={enemy_x:.0f}")

    # Activate weapons
    await wait_ticks(3, "movement orders")
    for ship in combat_ships:
        sid = ship["id"]
        view = await get_view(p)
        updated = next((s for s in view.get("ships", []) if s["id"] == sid), None)
        if updated:
            for mod in updated.get("modules", []):
                mt = mod.get("module_type", "")
                if ("turret" in mt or "missile" in mt) and not mod.get("active"):
                    result = await cmd(p, "activate_module", sid,
                                       {"module_id": mod["id"]}, quiet=True)
                    state.command_results.append(result)


async def phase_late_game(p1: Player, p2: Player, state: PlaytestState):
    """Ticks 2000+: Combat — engage, observe damage, try to destroy mothership."""
    state.phase = "late_game"
    log.info("=" * 60)
    log.info("PHASE: LATE GAME (combat)")
    log.info("=" * 60)

    max_tick = state.current_tick + 2500
    poll_interval = 60
    last_poll_tick = state.current_tick
    match_ended = False
    combat_engaged = {p1.name: False, p2.name: False}

    while not match_ended:
        gs = await get_game_status()
        state.current_tick = gs.get("current_tick", 0)

        if state.current_tick >= max_tick:
            log.warning(f"Reached max tick {max_tick}, ending playtest")
            state.gaps.append(Gap("balance", "high",
                                  "Game did not end within tick limit — "
                                  "may be too slow or stalemate"))
            break

        if state.current_tick - last_poll_tick >= poll_interval:
            last_poll_tick = state.current_tick

            # Check match status
            sc, match_data = await api_get(p1, f"/api/matches/{state.match_id}")
            if match_data.get("status") == "completed":
                log.info(f"MATCH ENDED! Winner team: {match_data.get('winner_team_id')}")
                match_ended = True
                break

            for p in [p1, p2]:
                view = await get_view(p, since_tick=state.current_tick - poll_interval)
                if not view:
                    continue

                all_ships = view.get("ships", [])
                p.ships = {s["id"]: s for s in all_ships}

                ms = p.ships.get(p.mothership_id)
                if ms:
                    p.ore = ms.get("ore", 0)
                    log_ship_status(p, ms, state.current_tick)

                # Find enemies
                enemies = find_enemy_ships(view, p.user_id)
                if enemies:
                    log.info(f"[{p.name}] {len(enemies)} enemy contacts visible")
                    for e in enemies[:3]:
                        log.info(f"  Enemy: id={e['id']} class={e.get('ship_class','?')} "
                                f"dist={e.get('distance',0):.0f}m")

                combat_ships = [s for s in all_ships
                               if s.get("ship_class") != "mothership"
                               and not s.get("is_destroyed", False)]

                # Engage combat
                if enemies and not combat_engaged[p.name]:
                    await engage_combat(p, state, combat_ships, enemies)
                    combat_engaged[p.name] = True
                elif combat_engaged[p.name]:
                    # Keep firing
                    for ship in combat_ships:
                        locks = ship.get("locks", [])
                        if any(l.get("status") == "locked" for l in locks):
                            await cmd(p, "fire_all", ship["id"], quiet=True)

                # Mothership combat
                if ms and enemies:
                    await engage_with_mothership(p, state, ms, enemies)

                log_events(view, p, state)

                # Continue building
                if ms and p.ore > 250:
                    factory_mod = next((m for m in ms.get("modules", [])
                                       if m.get("module_type") == "factory"), None)
                    active_builds = [bo for bo in ms.get("build_orders", [])
                                    if bo.get("status") in ("queued", "building")]
                    if factory_mod and len(active_builds) < 2:
                        result = await cmd(p, "build", p.mothership_id,
                                           {"blueprint": "strike_craft",
                                            "factory_module_id": factory_mod["id"]},
                                           quiet=True)
                        state.command_results.append(result)

        remaining = max_tick - state.current_tick
        await asyncio.sleep(min(30, max(1, remaining)))

    log.info(f"Late game complete at tick {state.current_tick}")
    return match_ended


async def engage_combat(p: Player, state: PlaytestState,
                        combat_ships: list, enemies: list):
    """Lock and fire on enemies."""
    log.info(f"[{p.name}] ENGAGING COMBAT with {len(combat_ships)} ships "
            f"vs {len(enemies)} enemies")

    # Prefer enemy mothership
    target = None
    for e in enemies:
        if e.get("ship_class") == "mothership":
            target = e
            break
    if not target:
        target = enemies[0]

    target_id = target["id"]
    log.info(f"[{p.name}] Primary target: id={target_id}, "
            f"class={target.get('ship_class','?')}, "
            f"dist={target.get('distance',0):.0f}m")

    # Lock + assign weapons on all combat ships
    for ship in combat_ships:
        sid = ship["id"]
        await cmd(p, "lock_target", sid, {"target_ship_id": target_id})
        for mod in ship.get("modules", []):
            mt = mod.get("module_type", "")
            if "turret" in mt or "missile" in mt:
                await cmd(p, "assign_weapon", sid,
                          {"module_id": mod["id"], "target_ship_id": target_id},
                          quiet=True)

    await wait_ticks(15, "target locks to resolve")

    for ship in combat_ships:
        result = await cmd(p, "fire_all", ship["id"])
        state.command_results.append(result)

    # Mothership too
    ms = p.ships.get(p.mothership_id)
    if ms:
        await engage_with_mothership(p, state, ms, enemies)


async def engage_with_mothership(p: Player, state: PlaytestState,
                                  ms: dict, enemies: list):
    """Lock and fire mothership weapons."""
    ms_id = ms["id"]

    # Find best target
    target = None
    for e in enemies:
        if e.get("ship_class") == "mothership":
            target = e
            break
    if not target and enemies:
        target = enemies[0]
    if not target:
        return

    target_id = target["id"]
    existing_locks = ms.get("locks", [])
    has_lock = any(l.get("target_ship_id") == target_id and l.get("status") == "locked"
                   for l in existing_locks)
    is_locking = any(l.get("target_ship_id") == target_id for l in existing_locks)

    if not is_locking:
        await cmd(p, "lock_target", ms_id, {"target_ship_id": target_id}, quiet=True)

    if has_lock:
        weapon_mods = [m for m in ms.get("modules", [])
                      if "turret" in m.get("module_type", "")
                      or "missile" in m.get("module_type", "")]
        wa = ms.get("weapon_assignments", [])
        for mod in weapon_mods:
            if not any(w.get("module_id") == mod["id"] for w in wa):
                await cmd(p, "assign_weapon", ms_id,
                          {"module_id": mod["id"], "target_ship_id": target_id},
                          quiet=True)
            # Activate if not active
            if not mod.get("active"):
                await cmd(p, "activate_module", ms_id,
                          {"module_id": mod["id"]}, quiet=True)

        await cmd(p, "fire_all", ms_id, quiet=True)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(p1: Player, p2: Player, state: PlaytestState):
    """Generate PLAYTEST_REPORT.md."""
    elapsed = time.time() - state.start_time

    bugs = [g for g in state.gaps if g.category == "bug"]
    crashes = [g for g in state.gaps if g.category == "crash"]
    balance = [g for g in state.gaps if g.category == "balance"]
    missing = [g for g in state.gaps if g.category == "missing_feature"]
    ux = [g for g in state.gaps if g.category == "ux"]

    event_counts = {}
    for evt in state.events_log:
        etype = evt.get("type", "unknown")
        event_counts[etype] = event_counts.get(etype, 0) + 1

    rejected = [r for r in state.command_results
                if r.get("status") not in (200, 201, 202)]

    lines = [
        "# Playtest Report: Solarion vs Voidborn",
        "",
        f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Duration:** {elapsed:.0f}s ({elapsed/60:.1f} min)",
        f"**Final tick:** {state.current_tick}",
        f"**Phase reached:** {state.phase}",
        f"**Match ID:** {state.match_id}",
        "",
        "## Summary",
        "",
        f"- Solarion ore at end: {p1.ore:.0f}",
        f"- Voidborn ore at end: {p2.ore:.0f}",
        f"- Total ships (Solarion): "
        f"{len([s for s in p1.ships.values() if not s.get('is_destroyed')])}",
        f"- Total ships (Voidborn): "
        f"{len([s for s in p2.ships.values() if not s.get('is_destroyed')])}",
        f"- Total events logged: {len(state.events_log)}",
        f"- Total commands sent: {len(state.command_results)}",
        f"- Commands rejected/failed: {len(rejected)}",
        "",
        "## Gaps Found",
        "",
    ]

    for label, items in [("Crashes / Critical", crashes), ("Bugs", bugs),
                          ("Balance Issues", balance),
                          ("Missing Features", missing), ("UX Issues", ux)]:
        if items:
            lines.append(f"### {label}")
            for g in items:
                lines.append(f"- **[{g.severity.upper()}]** {g.description}")
                if g.context:
                    lines.append(f"  ```\n  {g.context}\n  ```")
            lines.append("")

    if not state.gaps:
        lines.append("*No gaps found during playtest.*")
        lines.append("")

    lines.extend(["## Rejected / Failed Commands", ""])
    if rejected:
        for r in rejected[:50]:
            lines.append(f"- `{r.get('type')}` (ship={r.get('ship_id')}): "
                        f"status={r.get('status')} — "
                        f"{json.dumps(r.get('response', {}))[:200]}")
    else:
        lines.append("*None*")

    lines.extend(["", "## Event Summary", "",
                   "| Event Type | Count |", "|---|---|"])
    for etype, count in sorted(event_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {etype} | {count} |")

    lines.extend(["", "## Timeline", ""])
    key_types = {"match_started", "research_complete", "research_started",
                 "ship_destroyed", "match_ended", "mothership_critical",
                 "mothership_under_attack", "command_rejected"}
    timeline = [e for e in state.events_log if e.get("type") in key_types]
    for evt in timeline[:80]:
        lines.append(f"- **Tick {evt.get('tick','?')}** [{evt.get('type')}] "
                    f"{evt.get('message', '')}")
    if not timeline:
        lines.append("*No key timeline events captured.*")

    lines.extend(["", "---", "*Generated by tests/playtest.py*"])

    report = "\n".join(lines)
    REPORT_PATH.write_text(report)
    log.info(f"Report written to {REPORT_PATH}")
    return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    state = PlaytestState()
    state.start_time = time.time()

    # Check server is running
    try:
        gs = await get_game_status()
        if not gs:
            log.error("Server not responding. Start it first.")
            sys.exit(1)
        log.info(f"Server running. Tick={gs.get('current_tick', 0)}, "
                f"Running={gs.get('running', False)}")
    except Exception as e:
        log.error(f"Cannot reach server: {e}")
        sys.exit(1)

    async with httpx.AsyncClient() as c1, httpx.AsyncClient() as c2:
        p1 = Player(name="Solarion", faction="solarion", client=c1)
        p2 = Player(name="Voidborn", faction="voidborn", client=c2)

        try:
            if not await phase_setup(p1, p2, state):
                log.error("Setup failed")
                generate_report(p1, p2, state)
                return

            if not await phase_early_game(p1, p2, state):
                log.error("Early game failed")

            if not await phase_mid_game(p1, p2, state):
                log.error("Mid game failed")

            match_ended = await phase_late_game(p1, p2, state)

            if not match_ended:
                log.warning("Match did not end. Forcing surrender.")
                await cmd(p1, "surrender", payload={"match_id": state.match_id})
                await wait_ticks(3, "surrender")

        except KeyboardInterrupt:
            log.info("Interrupted")
        except Exception as e:
            log.error(f"Playtest error: {e}", exc_info=True)
            state.gaps.append(Gap("crash", "critical", f"Unhandled exception: {e}"))
        finally:
            for p in [p1, p2]:
                try:
                    view = await get_view(p)
                    if view:
                        for s in view.get("ships", []):
                            p.ships[s["id"]] = s
                        ms = p.ships.get(p.mothership_id)
                        if ms:
                            p.ore = ms.get("ore", 0)
                except Exception:
                    pass

            generate_report(p1, p2, state)


if __name__ == "__main__":
    asyncio.run(main())
