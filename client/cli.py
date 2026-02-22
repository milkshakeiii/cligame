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

app.add_typer(ship_app, name="ship")
app.add_typer(order_app, name="order")
app.add_typer(mine_app, name="mine")
app.add_typer(module_app, name="module")
app.add_typer(target_app, name="target")
app.add_typer(weapon_app, name="weapon")


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
    name: str = typer.Argument(..., help="Name for the new ship."),
    ship_class: str = typer.Option(
        "frigate",
        "--class",
        "-c",
        help="Ship class: strike_craft, corvette, frigate, destroyer, cruiser, mothership.",
    ),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Create (spawn) a new ship with no modules installed."""
    client = _client()
    data = _handle(client.create_ship, name, ship_class)
    if json:
        import json as _json
        print(_json.dumps(data, indent=2))
    else:
        display.print_success(
            f"Ship '{data['name']}' (#{data['id']}) created — class: {data['ship_class']}"
        )


@ship_app.command("info")
def ship_info(
    ship_id: int = typer.Argument(..., help="Ship ID."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Show full ship details, modules, and active orders."""
    client = _client()
    data = _handle(client.get_ship, ship_id)
    display.display_ship_info(data, json)


@ship_app.command("modules")
def ship_modules(
    ship_id: int = typer.Argument(..., help="Ship ID."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """List installed modules on a ship."""
    client = _client()
    modules = _handle(client.list_modules, ship_id)
    display.display_modules(modules, json)


# ---------------------------------------------------------------------------
# Movement order commands
# ---------------------------------------------------------------------------


@order_app.command("approach")
def order_approach(
    ship_id: int = typer.Argument(..., help="Ship ID to issue the order to."),
    target: Optional[int] = typer.Option(
        None, "--target", "-t",
        help="Target ship ID (sets target_ship_id). Mutually exclusive with --object and --point.",
    ),
    obj: Optional[int] = typer.Option(
        None, "--object", "-o",
        help="Target celestial object ID, e.g. asteroid or station (sets target_object_id). Mutually exclusive with --target and --point.",
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

      --target <ship_id>     Approach a ship by its ID.
      --object <object_id>   Approach a celestial object (asteroid, station, …) by ID.
      --point 'X Y Z'        Approach a fixed coordinate in space.
    """
    payload: dict = {"order_type": "approach"}

    provided = sum(v is not None for v in (target, obj, point))
    if provided != 1:
        display.print_error(
            "Provide exactly one of --target <ship_id>, --object <object_id>, or --point 'X Y Z'."
        )
        raise typer.Exit(code=1)

    if target is not None:
        payload["target_ship_id"] = target
    elif obj is not None:
        payload["target_object_id"] = obj
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

    client = _client()
    data = _handle(client.create_order, ship_id, payload)
    display.display_order(data, json)


@order_app.command("orbit")
def order_orbit(
    ship_id: int = typer.Argument(..., help="Ship ID."),
    target: Optional[int] = typer.Option(
        None, "--target", "-t",
        help="Target ship ID (sets target_ship_id). Mutually exclusive with --object.",
    ),
    obj: Optional[int] = typer.Option(
        None, "--object", "-o",
        help="Target celestial object ID, e.g. asteroid or station (sets target_object_id). Mutually exclusive with --target.",
    ),
    radius: float = typer.Option(..., "--radius", "-r", help="Orbit radius in metres."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """
    Order a ship to orbit a target at a given radius.

    Exactly one targeting option must be supplied:

      --target <ship_id>     Orbit a ship by its ID.
      --object <object_id>   Orbit a celestial object (asteroid, station, …) by ID.
    """
    provided = sum(v is not None for v in (target, obj))
    if provided != 1:
        display.print_error(
            "Provide exactly one of --target <ship_id> or --object <object_id>."
        )
        raise typer.Exit(code=1)

    payload: dict = {"order_type": "orbit", "orbit_radius": radius}
    if target is not None:
        payload["target_ship_id"] = target
    else:
        payload["target_object_id"] = obj

    client = _client()
    data = _handle(client.create_order, ship_id, payload)
    display.display_order(data, json)


@order_app.command("keep-distance")
def order_keep_distance(
    ship_id: int = typer.Argument(..., help="Ship ID."),
    target: Optional[int] = typer.Option(
        None, "--target", "-t",
        help="Target ship ID (sets target_ship_id). Mutually exclusive with --object.",
    ),
    obj: Optional[int] = typer.Option(
        None, "--object", "-o",
        help="Target celestial object ID, e.g. asteroid or station (sets target_object_id). Mutually exclusive with --target.",
    ),
    distance: float = typer.Option(..., "--distance", "-d", help="Distance to maintain in metres."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """
    Order a ship to keep a fixed distance from a target.

    Exactly one targeting option must be supplied:

      --target <ship_id>     Keep distance from a ship by its ID.
      --object <object_id>   Keep distance from a celestial object (asteroid, station, …) by ID.
    """
    provided = sum(v is not None for v in (target, obj))
    if provided != 1:
        display.print_error(
            "Provide exactly one of --target <ship_id> or --object <object_id>."
        )
        raise typer.Exit(code=1)

    payload: dict = {"order_type": "keep_distance", "desired_distance": distance}
    if target is not None:
        payload["target_ship_id"] = target
    else:
        payload["target_object_id"] = obj

    client = _client()
    data = _handle(client.create_order, ship_id, payload)
    display.display_order(data, json)


@order_app.command("dock")
def order_dock(
    ship_id: int = typer.Argument(..., help="Ship ID to dock."),
    target: int = typer.Option(..., "--target", "-t", help="Target ship ID to dock into."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Order a ship to dock with another ship that has a docking bay."""
    client = _client()
    data = _handle(client.dock_ship, ship_id, target)
    display.display_order(data, json)


@order_app.command("stop")
def order_stop(
    ship_id: int = typer.Argument(..., help="Ship ID."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Order a ship to decelerate to a full stop."""
    payload = {"order_type": "stop"}
    client = _client()
    data = _handle(client.create_order, ship_id, payload)
    display.display_order(data, json)


@order_app.command("cancel")
def order_cancel(
    ship_id: int = typer.Argument(..., help="Ship ID."),
    order_id: int = typer.Argument(..., help="Order ID to cancel."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Cancel a specific movement order."""
    client = _client()
    data = _handle(client.cancel_order, ship_id, order_id)
    display.display_order_cancel(data, json)


# ---------------------------------------------------------------------------
# Mining commands
# ---------------------------------------------------------------------------


@mine_app.command("start")
def mine_start(
    ship_id: int = typer.Argument(..., help="Ship ID."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Activate all mining lasers on a ship."""
    client = _client()
    modules = _handle(client.list_modules, ship_id)
    lasers = [m for m in modules if m["module_type"] == "mining_laser"]
    if not lasers:
        display.print_error("Ship has no mining laser modules installed.")
        raise typer.Exit(code=1)

    results = []
    for laser in lasers:
        result = _handle(client.activate_module, ship_id, laser["id"])
        if result:
            results.append(result)

    payload = {"lasers": results, "action": "start"}
    display.display_mine_action(payload, json, action="start")


@mine_app.command("stop")
def mine_stop(
    ship_id: int = typer.Argument(..., help="Ship ID."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Deactivate all mining lasers on a ship."""
    client = _client()
    modules = _handle(client.list_modules, ship_id)
    lasers = [m for m in modules if m["module_type"] == "mining_laser"]
    if not lasers:
        display.print_error("Ship has no mining laser modules installed.")
        raise typer.Exit(code=1)

    results = []
    for laser in lasers:
        result = _handle(client.deactivate_module, ship_id, laser["id"])
        if result:
            results.append(result)

    payload = {"lasers": results, "action": "stop"}
    display.display_mine_action(payload, json, action="stop")


# ---------------------------------------------------------------------------
# Transfer command (top-level, not under mine)
# ---------------------------------------------------------------------------


@app.command()
def transfer(
    ship_id: int = typer.Argument(..., help="Source ship ID."),
    target: int = typer.Option(..., "--target", "-t", help="Target ship ID to transfer ore to."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Transfer ore from a ship to another ship (target must have a drop-off module)."""
    client = _client()
    data = _handle(client.transfer_ore, ship_id, target)
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
            "Ship ID to build on, OR the word 'status' followed by a ship ID "
            "to view the build queue."
        ),
    ),
    ship_id_for_status: Optional[int] = typer.Argument(
        None,
        help="Ship ID when using 'build status <ship_id>'.",
    ),
    blueprint: Optional[str] = typer.Option(
        None, "--blueprint", "-b",
        help="Ship class to build: strike_craft, corvette, frigate, destroyer, cruiser.",
    ),
    factory_module_id: Optional[int] = typer.Option(
        None, "--factory", "-f", help="Specific factory module ID (optional)."
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
        data = _handle(client.get_build_queue, ship_id_for_status)
        display.display_build_queue(data, json)
        return

    # Normal: first arg is the ship_id
    try:
        ship_id = int(ship_id_or_status)
    except ValueError:
        display.print_error(
            f"Expected a ship ID or 'status', got: {ship_id_or_status!r}"
        )
        raise typer.Exit(code=1)

    if blueprint is None:
        # No blueprint — show status
        data = _handle(client.get_build_queue, ship_id)
        display.display_build_queue(data, json)
    else:
        data = _handle(client.queue_build, ship_id, blueprint, factory_module_id)
        display.display_build_order(data, json)


# ---------------------------------------------------------------------------
# Scanning commands
# ---------------------------------------------------------------------------


@app.command()
def scan(
    ship_id: int = typer.Argument(..., help="Ship ID with an active scanner module."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Trigger an active scan cycle (requires active scanner module)."""
    client = _client()
    data = _handle(client.scan, ship_id)
    display.display_scan_results(data, json)


@app.command()
def nearby(
    ship_id: int = typer.Argument(..., help="Ship ID."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Show nearby objects using default visibility (no scanner required)."""
    client = _client()
    contacts = _handle(client.nearby, ship_id)
    display.display_nearby(contacts, json)


# ---------------------------------------------------------------------------
# Module management commands
# ---------------------------------------------------------------------------


@module_app.command("install")
def module_install(
    ship_id: int = typer.Argument(..., help="Ship ID."),
    module_type: str = typer.Argument(
        ...,
        help=(
            "Module type: engine, reactor, cargo_bay, docking_bay, dropoff, "
            "factory, mining_laser, scanner, passive_detector."
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
    data = _handle(client.install_module, ship_id, module_type, volume)
    display.display_module(data, json, action="Module installed")


@module_app.command("uninstall")
def module_uninstall(
    ship_id: int = typer.Argument(..., help="Ship ID."),
    module_id: int = typer.Argument(..., help="Module ID to remove."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Uninstall (remove) a module from a ship."""
    client = _client()
    _handle(client.uninstall_module, ship_id, module_id)
    display.display_module_uninstall(json)


@module_app.command("activate")
def module_activate(
    ship_id: int = typer.Argument(..., help="Ship ID."),
    module_id: int = typer.Argument(..., help="Module ID to activate."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Activate a module (e.g. scanner, mining laser, passive detector)."""
    client = _client()
    data = _handle(client.activate_module, ship_id, module_id)
    display.display_module(data, json, action="Module activated")


@module_app.command("deactivate")
def module_deactivate(
    ship_id: int = typer.Argument(..., help="Ship ID."),
    module_id: int = typer.Argument(..., help="Module ID to deactivate."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Deactivate an active module."""
    client = _client()
    data = _handle(client.deactivate_module, ship_id, module_id)
    display.display_module(data, json, action="Module deactivated")


# ---------------------------------------------------------------------------
# Target lock commands
# ---------------------------------------------------------------------------


@target_app.command("lock")
def target_lock(
    ship_id: int = typer.Argument(..., help="Ship ID."),
    target: int = typer.Option(..., "--target", "-t", help="Target ship ID to lock."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Begin locking a target ship. Lock time depends on scan resolution and target signature."""
    client = _client()
    data = _handle(client.lock_target, ship_id, target)
    display.display_lock(data, json)


@target_app.command("unlock")
def target_unlock(
    ship_id: int = typer.Argument(..., help="Ship ID."),
    target: int = typer.Option(..., "--target", "-t", help="Target ship ID to unlock."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Release a target lock and remove associated weapon assignments."""
    client = _client()
    _handle(client.unlock_target, ship_id, target)
    if json:
        import json as _json
        print(_json.dumps({"status": "unlocked", "target_ship_id": target}))
    else:
        display.print_success(f"Lock on Ship #{target} released.")


@target_app.command("list")
def target_list(
    ship_id: int = typer.Argument(..., help="Ship ID."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """List all active target locks on a ship."""
    client = _client()
    locks = _handle(client.list_locks, ship_id)
    display.display_locks(locks, json)


# ---------------------------------------------------------------------------
# Weapon commands
# ---------------------------------------------------------------------------


@weapon_app.command("assign")
def weapon_assign(
    ship_id: int = typer.Argument(..., help="Ship ID."),
    module_id: int = typer.Argument(..., help="Weapon module ID to assign."),
    target: int = typer.Option(..., "--target", "-t", help="Target ship ID (must be locked)."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Assign a weapon module to a locked target and activate it."""
    client = _client()
    data = _handle(client.assign_weapon, ship_id, module_id, target)
    display.display_weapon_assign(data, json)


@weapon_app.command("fire-all")
def weapon_fire_all(
    ship_id: int = typer.Argument(..., help="Ship ID."),
    target: int = typer.Option(..., "--target", "-t", help="Target ship ID (must be locked)."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Assign all weapon modules to a locked target and activate them."""
    client = _client()
    data = _handle(client.fire_all_weapons, ship_id, target)
    display.display_weapon_assignments(data, json)


@weapon_app.command("hold")
def weapon_hold(
    ship_id: int = typer.Argument(..., help="Ship ID."),
    json: bool = typer.Option(False, "--json", help="Output raw JSON.", is_flag=True),
):
    """Deactivate all weapons and clear weapon assignments (cease fire)."""
    client = _client()
    _handle(client.hold_fire, ship_id)
    if json:
        import json as _json
        print(_json.dumps({"status": "holding_fire"}))
    else:
        display.print_success("All weapons deactivated. Holding fire.")


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
