"""
Space Game CLI — Typer entry point.

Usage:
    spacegame <command> [options]

All commands support --json to receive machine-readable output.
This is essential for LLM playability.
"""

from __future__ import annotations

import sys
import time
from typing import Optional

import typer

from client.api import SpaceGameClient, SpaceGameError, save_token, load_token
from client import display

# ---------------------------------------------------------------------------
# App definitions
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="spacegame",
    help="Space simulation game CLI. All commands support --json for machine-readable output.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
ship_app = typer.Typer(help="Ship management commands.", no_args_is_help=True)
order_app = typer.Typer(help="Movement order commands.", no_args_is_help=True)
mine_app = typer.Typer(help="Mining laser commands.", no_args_is_help=True)
module_app = typer.Typer(help="Module management commands.", no_args_is_help=True)
target_app = typer.Typer(help="Target lock commands.", no_args_is_help=True)
weapon_app = typer.Typer(help="Weapon commands.", no_args_is_help=True)
research_app = typer.Typer(help="Research / tech tree commands.", no_args_is_help=True)
command_app = typer.Typer(help="Autopilot / command authority commands.", no_args_is_help=True)
team_app = typer.Typer(help="Team management commands.", no_args_is_help=True)

app.add_typer(ship_app, name="ship")
app.add_typer(order_app, name="order")
app.add_typer(mine_app, name="mine")
app.add_typer(module_app, name="module")
app.add_typer(target_app, name="target")
app.add_typer(weapon_app, name="weapon")
app.add_typer(research_app, name="research")
app.add_typer(command_app, name="command")
app.add_typer(team_app, name="team")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client() -> SpaceGameClient:
    """Return an authenticated API client."""
    return SpaceGameClient()


def _handle(fn, *args, **kwargs):
    """
    Call fn(*args, **kwargs), catching SpaceGameError and printing cleanly.
    Returns the result or raises SystemExit on error.
    """
    try:
        return fn(*args, **kwargs)
    except SpaceGameError as exc:
        display.print_error(str(exc))
        raise typer.Exit(code=1)


def _normalize(s: str) -> str:
    """Lowercase, strip whitespace, collapse spaces, remove underscores."""
    import re
    return re.sub(r"[\s_]+", "", s.strip().lower())


def _name_match(items: list[dict], query: str, name_key: str = "name") -> list[dict]:
    """
    Match items by name: exact (case-insensitive, ignoring spaces/underscores),
    then substring.  Returns list of matches.
    """
    nq = _normalize(query)

    # Exact match (normalized)
    exact = [i for i in items if i.get(name_key) and _normalize(i[name_key]) == nq]
    if exact:
        return exact

    # Substring match (normalized)
    return [i for i in items if i.get(name_key) and nq in _normalize(i[name_key])]


def _resolve_ship(client: SpaceGameClient, name: str) -> int:
    """
    Resolve a ship name to a numeric ship ID.
    Matches by name (case-insensitive, spaces/underscores ignored).
    """
    ships = _handle(client.list_ships)
    matches = _name_match(ships, name)

    if len(matches) == 1:
        return matches[0]["id"]
    if len(matches) > 1:
        names = ", ".join(f"{s['name']}" for s in matches)
        display.print_error(f"Ambiguous ship name '{name}': {names}")
        raise typer.Exit(code=1)

    display.print_error(f"No ship found matching '{name}'.")
    raise typer.Exit(code=1)


def _resolve_object(client: SpaceGameClient, ship_id: int, name: str) -> int:
    """
    Resolve a celestial object name to a numeric object ID.
    Tries nearby (passive detector) and scan (active scanner).
    Canonical name is always '{Type} {id}' — e.g. 'Asteroid 29'.
    Accepts 'asteroid29', 'Asteroid 29', 'asteroid 29', etc.
    """
    seen_ids: set[int] = set()
    objects: list[dict] = []

    # Try nearby first (passive, no scanner needed)
    try:
        nearby = client.nearby(ship_id)
        for c in nearby:
            if c.get("type") == "object" and c["id"] not in seen_ids:
                objects.append(c)
                seen_ids.add(c["id"])
    except SpaceGameError:
        pass

    # Also try scan (active scanner, longer range) — even if nearby found some
    try:
        scan_data = client.scan(ship_id)
        for c in scan_data.get("contacts", []):
            if c.get("type") == "object" and c["id"] not in seen_ids:
                objects.append(c)
                seen_ids.add(c["id"])
    except SpaceGameError:
        pass

    if not objects:
        display.print_error(
            "No objects detected. Activate scanner or passive detector first."
        )
        raise typer.Exit(code=1)

    # Canonical name is always '{Type} {id}' (e.g. 'Asteroid 29')
    for obj in objects:
        obj["name"] = f"{(obj.get('object_type') or 'Object').title()} {obj['id']}"

    matches = _name_match(objects, name)

    if len(matches) == 1:
        return matches[0]["id"]
    if len(matches) > 1:
        names = ", ".join(f"{o['name']}" for o in matches)
        display.print_error(f"Ambiguous object name '{name}': {names}")
        raise typer.Exit(code=1)

    display.print_error(f"No object found matching '{name}'. Run 'scan' to see nearby objects.")
    raise typer.Exit(code=1)


def _resolve_module(client: SpaceGameClient, ship_id: int, name: str) -> int:
    """
    Resolve a module type name to a numeric module ID.

    Accepts:
      - Type name: 'scanner', 'mining_laser', 'factory'
      - Indexed type: 'mining_laser2' → second mining laser
      - Type with spaces: 'mining laser' → same as 'mining_laser'

    When multiple modules of the same type exist and no index is given,
    uses the first one.
    """
    import re

    modules = _handle(client.list_modules, ship_id)

    # Parse optional trailing index: "mining_laser2" → ("mining_laser", 2)
    m = re.match(r"^(.+?)(\d+)$", _normalize(name))
    if m:
        type_query = m.group(1)
        index = int(m.group(2))
    else:
        type_query = _normalize(name)
        index = 1  # default to first

    # Match by module_type (normalized)
    typed = [mod for mod in modules if _normalize(mod["module_type"]) == type_query]

    if not typed:
        # Try substring match on module_type
        typed = [mod for mod in modules if type_query in _normalize(mod["module_type"])]

    if not typed:
        available = sorted(set(mod["module_type"] for mod in modules))
        display.print_error(
            f"No module matching '{name}'. Available types: {', '.join(available)}"
        )
        raise typer.Exit(code=1)

    if index < 1 or index > len(typed):
        display.print_error(
            f"Module index {index} out of range. Ship has {len(typed)} '{typed[0]['module_type']}' module(s)."
        )
        raise typer.Exit(code=1)

    return typed[index - 1]["id"]


# ---------------------------------------------------------------------------
# Auth commands
# ---------------------------------------------------------------------------


@app.command()
def register(
    username: str = typer.Argument(..., help="Username for the new account."),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Password (prompted if omitted)."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """
    Register a new account and save the auth token to ~/.spacegame_token.

    You will be prompted for a password if --password is not provided.
    """
    if password is None:
        password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    client = SpaceGameClient()
    try:
        data = client.register(username, password=password)
    except SpaceGameError as exc:
        display.print_error(str(exc))
        raise typer.Exit(code=1)

    save_token(data["token"])
    display.display_login(data, json)


@app.command()
def login(
    username: str = typer.Argument(..., help="Your username."),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Password (prompted if omitted)."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """
    Login and save the auth token to ~/.spacegame_token.

    You will be prompted for a password if --password is not provided.
    """
    if password is None:
        password = typer.prompt("Password", hide_input=True)
    client = SpaceGameClient()
    try:
        data = client.login(username, password=password)
    except SpaceGameError as exc:
        display.print_error(str(exc))
        raise typer.Exit(code=1)

    save_token(data["token"])
    display.display_login(data, json)


@app.command()
def whoami(
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Show the currently logged-in user (calls GET /api/auth/me)."""
    token = load_token()
    if not token:
        display.print_error("Not logged in. Run: spacegame login <username>")
        raise typer.Exit(code=1)

    client = _client()
    data = _handle(client.me)
    display.display_whoami(data, json)


# ---------------------------------------------------------------------------
# Game status
# ---------------------------------------------------------------------------


@app.command()
def status(
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Show game state and your ships overview."""
    client = _client()
    game_data = _handle(client.game_status)
    ships = _handle(client.list_ships)
    display.display_status(game_data, ships, json)


# ---------------------------------------------------------------------------
# Ship commands
# ---------------------------------------------------------------------------


@ship_app.command("list")
def ship_list(
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """List all your ships."""
    client = _client()
    ships = _handle(client.list_ships)
    display.display_ship_list(ships, json)


@ship_app.command("create")
def ship_create(
    name: Optional[str] = typer.Argument(None, help="Name for the new ship (auto-generated if omitted)."),
    ship_class: str = typer.Option(
        "frigate",
        "--class",
        "-c",
        help="Ship class: strike_craft, corvette, frigate, destroyer, cruiser, mothership.",
    ),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Create (spawn) a new ship. Name is auto-generated if omitted."""
    client = _client()
    data = _handle(client.create_ship, name, ship_class)
    if json:
        import json as _json
        print(_json.dumps(data, indent=2))
    else:
        display.print_success(
            f"Ship '{data['name']}' (#{data['id']}) created — class: {data['ship_class']}"
        )


@ship_app.command("rename")
def ship_rename(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    new_name: str = typer.Argument(..., help="New name for the ship."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Rename a ship."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    data = _handle(client.rename_ship, resolved, new_name)
    if json:
        import json as _json
        print(_json.dumps(data, indent=2))
    else:
        display.print_success(f"Ship #{data['id']} renamed to '{data['name']}'.")


@ship_app.command("info")
def ship_info(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Show full ship details, modules, and active orders."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    data = _handle(client.get_ship, resolved)
    display.display_ship_info(data, json)


@ship_app.command("modules")
def ship_modules(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """List installed modules on a ship."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    modules = _handle(client.list_modules, resolved)
    display.display_modules(modules, json)


@ship_app.command("leeches")
def ship_leeches(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Show active leech debuffs on a ship."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    data = _handle(client.get_ship_leeches, resolved)
    if json:
        import json as _json
        print(_json.dumps(data, indent=2))
    else:
        display.display_leeches(data, json)


# ---------------------------------------------------------------------------
# Movement order commands
# ---------------------------------------------------------------------------


@order_app.command("approach")
def order_approach(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    target: Optional[str] = typer.Option(
        None, "--target", "-t",
        help="Target ship ID or name. Mutually exclusive with --object and --point.",
    ),
    obj: Optional[str] = typer.Option(
        None, "--object", "-o",
        help="Target object name, e.g. 'asteroid1'. Mutually exclusive with --target and --point.",
    ),
    point: Optional[str] = typer.Option(
        None, "--point", "-p",
        help="Target coordinates as 'X Y Z' (quote the argument: --point '100 200 0'). Mutually exclusive with --target and --object.",
    ),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """
    Order a ship to approach a target.

    Exactly one targeting option must be supplied:

      --target <name>     Approach a ship by name.
      --object <name>     Approach a celestial object (e.g. 'asteroid1').
      --point 'X Y Z'    Approach a fixed coordinate in space.
    """
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    payload: dict = {"order_type": "approach"}

    provided = sum(v is not None for v in (target, obj, point))
    if provided != 1:
        display.print_error(
            "Provide exactly one of --target <name>, --object <name>, or --point 'X Y Z'."
        )
        raise typer.Exit(code=1)

    if target is not None:
        payload["target_ship_id"] = _resolve_ship(client, target)
    elif obj is not None:
        payload["target_object_id"] = _resolve_object(client, resolved, obj)
    else:
        # point
        try:
            parts = point.split()  # type: ignore[union-attr]
            if len(parts) != 3:
                raise ValueError
            payload["target_x"] = float(parts[0])
            payload["target_y"] = float(parts[1])
            payload["target_z"] = float(parts[2])
        except ValueError:
            display.print_error("--point must be three numbers: --point '100 200 0'")
            raise typer.Exit(code=1)

    data = _handle(client.create_order, resolved, payload)
    display.display_order(data, json)


@order_app.command("orbit")
def order_orbit(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    target: Optional[str] = typer.Option(
        None, "--target", "-t",
        help="Target ship ID or name. Mutually exclusive with --object.",
    ),
    obj: Optional[str] = typer.Option(
        None, "--object", "-o",
        help="Target object name, e.g. 'asteroid1'. Mutually exclusive with --target.",
    ),
    radius: float = typer.Option(..., "--radius", "-r", help="Orbit radius in metres."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """
    Order a ship to orbit a target at a given radius.

    Exactly one targeting option must be supplied:

      --target <name>     Orbit a ship by name.
      --object <name>     Orbit a celestial object (e.g. 'asteroid1').
    """
    client = _client()
    resolved = _resolve_ship(client, ship_id)

    provided = sum(v is not None for v in (target, obj))
    if provided != 1:
        display.print_error(
            "Provide exactly one of --target <name> or --object <name>."
        )
        raise typer.Exit(code=1)

    payload: dict = {"order_type": "orbit", "orbit_radius": radius}
    if target is not None:
        payload["target_ship_id"] = _resolve_ship(client, target)
    else:
        payload["target_object_id"] = _resolve_object(client, resolved, obj)

    data = _handle(client.create_order, resolved, payload)
    display.display_order(data, json)


@order_app.command("keep-distance")
def order_keep_distance(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    target: Optional[str] = typer.Option(
        None, "--target", "-t",
        help="Target ship ID or name. Mutually exclusive with --object.",
    ),
    obj: Optional[str] = typer.Option(
        None, "--object", "-o",
        help="Target object name, e.g. 'asteroid1'. Mutually exclusive with --target.",
    ),
    distance: float = typer.Option(..., "--distance", "-d", help="Distance to maintain in metres."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """
    Order a ship to keep a fixed distance from a target.

    Exactly one targeting option must be supplied:

      --target <name>     Keep distance from a ship by name.
      --object <name>     Keep distance from a celestial object (e.g. 'asteroid1').
    """
    client = _client()
    resolved = _resolve_ship(client, ship_id)

    provided = sum(v is not None for v in (target, obj))
    if provided != 1:
        display.print_error(
            "Provide exactly one of --target <name> or --object <name>."
        )
        raise typer.Exit(code=1)

    payload: dict = {"order_type": "keep_distance", "desired_distance": distance}
    if target is not None:
        payload["target_ship_id"] = _resolve_ship(client, target)
    else:
        payload["target_object_id"] = _resolve_object(client, resolved, obj)

    data = _handle(client.create_order, resolved, payload)
    display.display_order(data, json)


@order_app.command("dock")
def order_dock(
    ship_id: str = typer.Argument(..., help="Ship ID or name to dock."),
    target: str = typer.Option(..., "--target", "-t", help="Target ship ID or name to dock into."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Order a ship to dock with another ship that has a docking bay."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    resolved_target = _resolve_ship(client, target)
    data = _handle(client.dock_ship, resolved, resolved_target)
    display.display_order(data, json)


@order_app.command("stop")
def order_stop(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Order a ship to decelerate to a full stop."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    payload = {"order_type": "stop"}
    data = _handle(client.create_order, resolved, payload)
    display.display_order(data, json)


@order_app.command("cancel")
def order_cancel(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    order_id: int = typer.Argument(..., help="Order ID to cancel."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Cancel a specific movement order."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    data = _handle(client.cancel_order, resolved, order_id)
    display.display_order_cancel(data, json)


# ---------------------------------------------------------------------------
# Mining commands
# ---------------------------------------------------------------------------


@mine_app.command("start")
def mine_start(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Activate all mining lasers on a ship."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    modules = _handle(client.list_modules, resolved)
    lasers = [m for m in modules if m["module_type"] == "mining_laser"]
    if not lasers:
        display.print_error("Ship has no mining laser modules installed.")
        raise typer.Exit(code=1)

    results = []
    for laser in lasers:
        result = _handle(client.activate_module, resolved, laser["id"])
        if result:
            results.append(result)

    payload = {"lasers": results, "action": "start"}
    display.display_mine_action(payload, json, action="start")


@mine_app.command("stop")
def mine_stop(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Deactivate all mining lasers on a ship."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    modules = _handle(client.list_modules, resolved)
    lasers = [m for m in modules if m["module_type"] == "mining_laser"]
    if not lasers:
        display.print_error("Ship has no mining laser modules installed.")
        raise typer.Exit(code=1)

    results = []
    for laser in lasers:
        result = _handle(client.deactivate_module, resolved, laser["id"])
        if result:
            results.append(result)

    payload = {"lasers": results, "action": "stop"}
    display.display_mine_action(payload, json, action="stop")


# ---------------------------------------------------------------------------
# Transfer command (top-level, not under mine)
# ---------------------------------------------------------------------------


@app.command()
def transfer(
    ship_id: str = typer.Argument(..., help="Source ship ID or name."),
    target: str = typer.Option(..., "--target", "-t", help="Target ship ID or name to transfer ore to."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Transfer ore from a ship to another ship (target must have a drop-off module)."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    resolved_target = _resolve_ship(client, target)
    data = _handle(client.transfer_ore, resolved, resolved_target)
    display.display_transfer(data, json)


# ---------------------------------------------------------------------------
# Build commands
# ---------------------------------------------------------------------------
# Provides:
#   spacegame build <ship_id> --blueprint scout   — queue a build
#   spacegame build status <ship_id>              — show build queue
#
# The "status" keyword is detected as the first positional argument so we
# can distinguish between the two forms in a single top-level command.


@app.command("build")
def build_cmd(
    ship_id_or_status: str = typer.Argument(
        ...,
        help=(
            "Ship ID/name to build on, OR the word 'status' followed by a ship ID "
            "to view the build queue."
        ),
    ),
    ship_id_for_status: Optional[str] = typer.Argument(
        None,
        help="Ship ID or name when using 'build status <ship>'.",
    ),
    blueprint: Optional[str] = typer.Option(
        None, "--blueprint", "-b",
        help="Ship class to build: strike_craft, corvette, frigate, destroyer, cruiser.",
    ),
    factory_module: Optional[str] = typer.Option(
        None, "--factory", "-f", help="Factory module name (e.g. 'factory', 'factory2'). Optional."
    ),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """
    Queue a build order or show build queue status.

    Queue a build:
        spacegame build <ship_id> --blueprint strike_craft

    Show build queue:
        spacegame build status <ship_id>
        spacegame build <ship_id>          (no --blueprint also shows queue)
    """
    client = _client()

    # Handle "spacegame build status <ship_id>"
    if ship_id_or_status.lower() == "status":
        if ship_id_for_status is None:
            display.print_error("Usage: spacegame build status <ship_id>")
            raise typer.Exit(code=1)
        resolved = _resolve_ship(client, ship_id_for_status)
        data = _handle(client.get_build_queue, resolved)
        display.display_build_queue(data, json)
        return

    # Normal: first arg is the ship_id
    resolved = _resolve_ship(client, ship_id_or_status)

    if blueprint is None:
        # No blueprint — show status
        data = _handle(client.get_build_queue, resolved)
        display.display_build_queue(data, json)
    else:
        factory_module_id = _resolve_module(client, resolved, factory_module) if factory_module else None
        data = _handle(client.queue_build, resolved, blueprint, factory_module_id)
        display.display_build_order(data, json)


# ---------------------------------------------------------------------------
# Scanning commands
# ---------------------------------------------------------------------------


@app.command()
def scan(
    ship_id: str = typer.Argument(..., help="Ship ID or name with an active scanner module."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Trigger an active scan cycle (requires active scanner module)."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    data = _handle(client.scan, resolved)
    display.display_scan_results(data, json)


@app.command()
def nearby(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Show nearby objects using default visibility (no scanner required)."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    contacts = _handle(client.nearby, resolved)
    display.display_nearby(contacts, json)


# ---------------------------------------------------------------------------
# Module management commands
# ---------------------------------------------------------------------------


@module_app.command("install")
def module_install(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    module_type: str = typer.Argument(
        ...,
        help=(
            "Module type. Categories: "
            "base (engine, reactor, cargo_bay, docking_bay, dropoff, factory, mining_laser, scanner, passive_detector), "
            "turrets (small/medium/large_turret_kinetic/thermal), "
            "missiles (light/heavy_missile_launcher, torpedo_launcher), "
            "shields (small/medium/large_shield_extender/booster/hardener_kinetic/thermal/explosive), "
            "armor (small/medium/large_armor_plate/repairer/hardener_kinetic/thermal/explosive), "
            "research (research_module, strip_miner, enhanced_docking_bay, fortress), "
            "Solarion (focused_beam_medium/large, reactive_armor_membrane_medium/large, "
            "armor_repair_nexus_medium/large, solar_lance), "
            "Voidborn (light/heavy_leech_projector, phase_shield_amplifier_medium/large, "
            "small/medium_stealth_field, bio_repair_swarm), "
            "shared (shield_purge)."
        ),
    ),
    volume: int = typer.Option(
        0, "--volume", "-v",
        help="Volume in m³ (required for variable-size modules: engine, reactor, cargo_bay, docking_bay, factory).",
    ),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Install a module on a ship."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    data = _handle(client.install_module, resolved, module_type, volume)
    display.display_module(data, json, action="Module installed")


@module_app.command("uninstall")
def module_uninstall(
    ship_id: str = typer.Argument(..., help="Ship name."),
    module: str = typer.Argument(..., help="Module type name (e.g. 'scanner', 'mining_laser2')."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Uninstall (remove) a module from a ship."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    module_id = _resolve_module(client, resolved, module)
    _handle(client.uninstall_module, resolved, module_id)
    display.display_module_uninstall(json)


@module_app.command("activate")
def module_activate(
    ship_id: str = typer.Argument(..., help="Ship name."),
    module: str = typer.Argument(..., help="Module type name (e.g. 'scanner', 'mining_laser2')."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Activate a module (e.g. scanner, mining laser, passive detector)."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    module_id = _resolve_module(client, resolved, module)
    data = _handle(client.activate_module, resolved, module_id)
    display.display_module(data, json, action="Module activated")


@module_app.command("deactivate")
def module_deactivate(
    ship_id: str = typer.Argument(..., help="Ship name."),
    module: str = typer.Argument(..., help="Module type name (e.g. 'scanner', 'mining_laser2')."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Deactivate an active module."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    module_id = _resolve_module(client, resolved, module)
    data = _handle(client.deactivate_module, resolved, module_id)
    display.display_module(data, json, action="Module deactivated")


# ---------------------------------------------------------------------------
# Target lock commands
# ---------------------------------------------------------------------------


@target_app.command("lock")
def target_lock(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    target: str = typer.Option(..., "--target", "-t", help="Target ship ID or name to lock."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Begin locking a target ship. Lock time depends on scan resolution and target signature."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    resolved_target = _resolve_ship(client, target)
    data = _handle(client.lock_target, resolved, resolved_target)
    display.display_lock(data, json)


@target_app.command("unlock")
def target_unlock(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    target: str = typer.Option(..., "--target", "-t", help="Target ship ID or name to unlock."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Release a target lock and remove associated weapon assignments."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    resolved_target = _resolve_ship(client, target)
    _handle(client.unlock_target, resolved, resolved_target)
    if json:
        import json as _json
        print(_json.dumps({"status": "unlocked", "target_ship_id": resolved_target}))
    else:
        display.print_success(f"Lock on Ship #{resolved_target} released.")


@target_app.command("list")
def target_list(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """List all active target locks on a ship."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    locks = _handle(client.list_locks, resolved)
    display.display_locks(locks, json)


# ---------------------------------------------------------------------------
# Weapon commands
# ---------------------------------------------------------------------------


@weapon_app.command("assign")
def weapon_assign(
    ship_id: str = typer.Argument(..., help="Ship name."),
    module: str = typer.Argument(..., help="Weapon module name (e.g. 'small_turret_kinetic1')."),
    target: str = typer.Option(..., "--target", "-t", help="Target ship name (must be locked)."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Assign a weapon module to a locked target and activate it."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    module_id = _resolve_module(client, resolved, module)
    resolved_target = _resolve_ship(client, target)
    data = _handle(client.assign_weapon, resolved, module_id, resolved_target)
    display.display_weapon_assign(data, json)


@weapon_app.command("fire-all")
def weapon_fire_all(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    target: str = typer.Option(..., "--target", "-t", help="Target ship ID or name (must be locked)."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Assign all weapon modules to a locked target and activate them."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    resolved_target = _resolve_ship(client, target)
    data = _handle(client.fire_all_weapons, resolved, resolved_target)
    display.display_weapon_assignments(data, json)


@weapon_app.command("hold")
def weapon_hold(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Deactivate all weapons and clear weapon assignments (cease fire)."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    _handle(client.hold_fire, resolved)
    if json:
        import json as _json
        print(_json.dumps({"status": "holding_fire"}))
    else:
        display.print_success("All weapons deactivated. Holding fire.")


# ---------------------------------------------------------------------------
# Research commands
# ---------------------------------------------------------------------------


@research_app.command("start")
def research_start(
    ship_id: str = typer.Argument(..., help="Ship name with a research module."),
    tech_id: str = typer.Argument(..., help="Tech ID to research (e.g. '1a_medium_weapons')."),
    module: Optional[str] = typer.Option(
        None, "--module", "-m", help="Research module name (e.g. 'research_module'). Optional."
    ),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Start researching a technology. Ore is consumed immediately."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    module_id = _resolve_module(client, resolved, module) if module else None
    data = _handle(client.start_research, resolved, tech_id, module_id)
    display.display_research_progress(data, json)


@research_app.command("cancel")
def research_cancel(
    ship_id: str = typer.Argument(..., help="Ship name."),
    module: Optional[str] = typer.Option(
        None, "--module", "-m", help="Cancel only research on this module."
    ),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Cancel active research on a ship. Ore is not refunded."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    module_id = _resolve_module(client, resolved, module) if module else None
    _handle(client.cancel_research, resolved, module_id)
    if json:
        import json as _json
        print(_json.dumps({"status": "cancelled"}))
    else:
        display.print_success("Research cancelled.")


@research_app.command("status")
def research_status_cmd(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Show research progress on a ship."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    data = _handle(client.research_status, resolved)
    display.display_research_list(data, json)


@research_app.command("tree")
def research_tree(
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Show the full tech tree with research status."""
    client = _client()
    data = _handle(client.tech_tree)
    display.display_tech_tree(data, json)


# ---------------------------------------------------------------------------
# Autopilot / command authority commands
# ---------------------------------------------------------------------------


@command_app.command("assume")
def command_assume(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Take manual control of an autopiloted ship."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    data = _handle(client.assume_command, resolved)
    if json:
        import json as _json
        print(_json.dumps(data, indent=2))
    else:
        display.print_success(
            f"Command assumed for Ship #{resolved}. Autopilot disengaged."
        )


@command_app.command("release")
def command_release(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p",
        help="Autopilot profile: mining, scout, combat_aggressive, combat_defensive, escort, patrol.",
    ),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Release a ship to autopilot control."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    data = _handle(client.release_command, resolved, profile)
    if json:
        import json as _json
        print(_json.dumps(data, indent=2))
    else:
        ap_profile = data.get("autopilot_profile", profile or "default")
        display.print_success(
            f"Ship #{resolved} released to autopilot (profile: {ap_profile})."
        )


@command_app.command("profile")
def command_profile(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    profile: str = typer.Argument(
        ...,
        help="Autopilot profile: mining, scout, combat_aggressive, combat_defensive, escort, patrol.",
    ),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Change the autopilot profile for a ship."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    data = _handle(client.set_autopilot_profile, resolved, profile)
    if json:
        import json as _json
        print(_json.dumps(data, indent=2))
    else:
        new_profile = data.get("profile", profile)
        display.print_success(
            f"Ship #{resolved} autopilot profile set to '{new_profile}'."
        )


@command_app.command("tick")
def command_tick(
    ship_id: str = typer.Argument(..., help="Ship ID or name."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Show aggregated autopilot state for a ship."""
    client = _client()
    resolved = _resolve_ship(client, ship_id)
    data = _handle(client.autopilot_tick, resolved)
    display.display_autopilot_tick(data, json)


# ---------------------------------------------------------------------------
# Team commands
# ---------------------------------------------------------------------------


@team_app.command("create")
def team_create(
    name: str = typer.Argument(..., help="Team name."),
    faction: str = typer.Option(..., "--faction", "-f", help="Faction: solarion or voidborn."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Create a new team."""
    client = _client()
    data = _handle(client.create_team, name, faction)
    if json:
        import json as _json
        print(_json.dumps(data, indent=2))
    else:
        display.print_success(f"Team '{data['name']}' created (faction: {data['faction']}, ID #{data['id']})")


@team_app.command("join")
def team_join(
    team_id: int = typer.Argument(..., help="Team ID to join."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Join an existing team."""
    client = _client()
    data = _handle(client.join_team, team_id)
    if json:
        import json as _json
        print(_json.dumps(data, indent=2))
    else:
        display.print_success(f"Joined team #{team_id}")


@team_app.command("list")
def team_list(
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """List all teams."""
    client = _client()
    data = _handle(client.list_teams)
    if json:
        import json as _json
        print(_json.dumps(data, indent=2))
    else:
        display.display_teams(data, json)


@team_app.command("info")
def team_info(
    team_id: int = typer.Argument(..., help="Team ID."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Show team details."""
    client = _client()
    data = _handle(client.get_team, team_id)
    if json:
        import json as _json
        print(_json.dumps(data, indent=2))
    else:
        display.display_team_info(data, json)


@team_app.command("research")
def team_research(
    team_id: int = typer.Argument(..., help="Team ID."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Show team research status."""
    client = _client()
    data = _handle(client.get_team_research, team_id)
    if json:
        import json as _json
        print(_json.dumps(data, indent=2))
    else:
        display.display_team_research(data, json)


# ---------------------------------------------------------------------------
# Events command
# ---------------------------------------------------------------------------


@app.command()
def events(
    since: int = typer.Option(0, "--since", help="Return events after this tick number."),
    types: Optional[str] = typer.Option(
        None, "--types",
        help="Comma-separated event types to filter: detection,mining,build_complete,etc.",
    ),
    ship: Optional[int] = typer.Option(None, "--ship", help="Filter to a specific ship ID."),
    limit: int = typer.Option(100, "--limit", "-n", help="Maximum number of events to return."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """
    Poll the event log for new events.

    Use --since TICK to get only events after the last tick you've seen.
    Combine with --types and --ship for fine-grained filtering.
    """
    client = _client()
    data = _handle(client.get_events, since_tick=since, limit=limit, ship_id=ship, types=types)
    display.display_events(data, json)


# ---------------------------------------------------------------------------
# Watch command (blocking long-poll)
# ---------------------------------------------------------------------------


@app.command()
def watch(
    ship: Optional[int] = typer.Option(None, "--ship", help="Filter events to a specific ship ID."),
    types: Optional[str] = typer.Option(
        None, "--types",
        help="Comma-separated event types: detection,mining,build_complete,order_complete,etc.",
    ),
    poll_interval: float = typer.Option(
        2.0, "--interval", "-i", help="Polling interval in seconds (default: 2)."
    ),
    json: bool = typer.Option(False, "--json", help="Output one JSON object per line.", is_flag=True),
):
    """
    Watch for new events in real time (long-running, blocking).

    Polls the event log every INTERVAL seconds and prints new events to stdout
    as they arrive.  Press Ctrl+C to stop.

    Designed to be run as a background process by an LLM agent:

        spacegame watch &

    Without --json, prints human-readable lines:

        [Tick 1042] DETECTION Ship #1: Unknown contact at (1204, -532, 89), range 28.4 km

    With --json, prints one JSON object per line (newline-delimited JSON):

        {"tick": 1042, "type": "detection", "ship_id": 1, "message": "..."}
    """
    client = _client()
    last_tick = 0

    if not json:
        display.console.print(
            "[dim]Watching for events. Press Ctrl+C to stop.[/dim]"
        )

    try:
        while True:
            try:
                new_events = client.get_events(
                    since_tick=last_tick, limit=200, ship_id=ship, types=types
                )
            except SpaceGameError as exc:
                display.print_error(str(exc))
                time.sleep(poll_interval)
                continue

            for event in new_events:
                line = display.format_event_line(event, json)
                if json:
                    # Raw JSON line to stdout — use print for clean output
                    print(line, flush=True)
                else:
                    display.console.print(line)
                    # Also flush so background processes see output immediately
                    sys.stdout.flush()

                tick = event.get("tick", 0)
                if tick > last_tick:
                    last_tick = tick

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        if not json:
            display.console.print("\n[dim]Watch stopped.[/dim]")
        raise SystemExit(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
