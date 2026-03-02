"""
Rich formatting helpers for the Space Game CLI.

Each public function accepts a data dict/list and a ``json_mode`` bool.
When json_mode is True it prints raw JSON and returns immediately.
When json_mode is False it renders Rich tables, panels, etc.
"""

from __future__ import annotations

import json
import math
from typing import Any, Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
err_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _json_out(data: Any) -> None:
    """Print data as formatted JSON."""
    print(json.dumps(data, indent=2))


def _fmt_float(v: float, decimals: int = 1) -> str:
    return f"{v:.{decimals}f}"


def _fmt_dist(m: float) -> str:
    """Format distance in metres or km."""
    if m >= 1_000:
        return f"{m / 1_000:.1f} km"
    return f"{m:.0f} m"


def _speed_vec(vx: float, vy: float, vz: float) -> str:
    speed = math.sqrt(vx ** 2 + vy ** 2 + vz ** 2)
    return f"{speed:.1f} m/s"


def _cap_bar(cap: float, max_cap: float, width: int = 20) -> str:
    """ASCII progress bar for capacitor. Uses pipe-delimited borders to avoid Rich markup conflicts."""
    if max_cap <= 0:
        pct = 0.0
    else:
        pct = cap / max_cap
    filled = round(pct * width)
    bar = "#" * filled + "-" * (width - filled)
    # Use | instead of [] to avoid Rich treating this as markup
    return f"|{bar}| {pct * 100:.0f}%"


def _hp_bar(current: float, maximum: float, color: str = "green", width: int = 20) -> str:
    """ASCII bar for shield/armor HP with color."""
    if maximum <= 0:
        pct = 0.0
    else:
        pct = max(0.0, min(1.0, current / maximum))
    filled = round(pct * width)
    bar = "#" * filled + "-" * (width - filled)
    return f"[{color}]|{bar}|[/{color}] {pct * 100:.0f}%"


def _detail_label(level: int) -> str:
    labels = {1: "Contact", 2: "Classification", 3: "Identification", 4: "Detailed"}
    return labels.get(level, f"Level {level}")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def display_login(data: dict, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return
    console.print(
        Panel(
            f"[bold green]Logged in![/bold green]\n"
            f"  Username : [cyan]{data['username']}[/cyan]\n"
            f"  User ID  : {data['user_id']}\n"
            f"  Token saved to [dim]~/.spacegame_token[/dim]",
            title="Login",
            border_style="green",
        )
    )


def display_whoami(data: dict, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return
    # data keys vary depending on what info is available
    if "username" in data:
        console.print(f"[bold]{data['username']}[/bold]  (user_id={data['user_id']})")
    else:
        console.print(
            f"Token  : [dim]{data.get('token_prefix', '?')}[/dim]\n"
            f"Ships  : {data.get('ship_count', '?')}\n"
            f"[dim]{data.get('note', '')}[/dim]"
        )


# ---------------------------------------------------------------------------
# Game status
# ---------------------------------------------------------------------------


def display_status(status_data: dict, ships: list, json_mode: bool) -> None:
    if json_mode:
        _json_out({"game": status_data, "ships": ships})
        return

    tick = status_data.get("current_tick", 0)
    running = status_data.get("running", False)
    interval = status_data.get("tick_interval", 1.0)
    state_str = "[green]RUNNING[/green]" if running else "[red]STOPPED[/red]"

    game_text = (
        f"Tick: [bold cyan]{tick}[/bold cyan]   "
        f"State: {state_str}   "
        f"Interval: {interval}s/tick"
    )
    console.print(Panel(game_text, title="Game State", border_style="blue"))

    if not ships:
        console.print("[dim]No ships found.[/dim]")
        return

    t = Table(box=box.SIMPLE_HEAVY, title="Your Fleet", show_lines=False)
    t.add_column("ID", style="dim", justify="right")
    t.add_column("Name", style="bold")
    t.add_column("Class")
    t.add_column("Position")
    t.add_column("Speed")
    t.add_column("Ore")
    t.add_column("Capacitor")
    t.add_column("Status")

    for s in ships:
        pos = f"({s['pos_x']:.0f}, {s['pos_y']:.0f}, {s['pos_z']:.0f}) m"
        speed = _speed_vec(s["vel_x"], s["vel_y"], s["vel_z"])
        ore = f"{s['ore']:.0f}/{s['cargo_capacity']:.0f} ore"
        cap = _cap_bar(s["capacitor"], s["max_capacitor"])
        docked = s.get("docked_in_id")
        ship_status = f"[dim]Docked in #{docked}[/dim]" if docked else "[green]Active[/green]"
        t.add_row(
            str(s["id"]),
            s["name"],
            s["ship_class"],
            pos,
            speed,
            ore,
            cap,
            ship_status,
        )

    console.print(t)


# ---------------------------------------------------------------------------
# Ships
# ---------------------------------------------------------------------------


def display_ship_list(ships: list, json_mode: bool) -> None:
    if json_mode:
        _json_out(ships)
        return

    if not ships:
        console.print("[dim]No ships found.[/dim]")
        return

    has_faction = any(s.get("faction") for s in ships)

    t = Table(box=box.SIMPLE_HEAVY, title="Ships", show_lines=False)
    t.add_column("ID", style="dim", justify="right")
    t.add_column("Name", style="bold")
    t.add_column("Class")
    if has_faction:
        t.add_column("Faction")
    t.add_column("Position")
    t.add_column("Speed")
    t.add_column("Ore / Cargo")
    t.add_column("Cap %")
    t.add_column("Vol Used")

    for s in ships:
        pos = f"({s['pos_x']:.0f}, {s['pos_y']:.0f}, {s['pos_z']:.0f}) m"
        speed = _speed_vec(s["vel_x"], s["vel_y"], s["vel_z"])
        ore = f"{s['ore']:.0f}/{s['cargo_capacity']:.0f} ore"
        pct = (s["capacitor"] / s["max_capacitor"] * 100) if s["max_capacitor"] else 0
        cap_str = f"{pct:.0f}%"
        vol = f"{s['used_volume']}/{s['total_volume']}"
        row = [
            str(s["id"]),
            s["name"],
            s["ship_class"],
        ]
        if has_faction:
            row.append((s.get("faction") or "none").title())
        row.extend([pos, speed, ore, cap_str, vol])
        t.add_row(*row)

    console.print(t)


def display_ship_info(data: dict, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return

    # Header panel
    docked = data.get("docked_in_id")
    docked_str = f"  Docked in ship #{docked}\n" if docked else ""
    # Combat stats
    shield_hp = data.get("shield_hp", 0)
    max_shield = data.get("max_shield_hp", 0)
    armor_hp = data.get("armor_hp", 0)
    max_armor = data.get("max_armor_hp", 0)
    destroyed = data.get("is_destroyed", False)
    scan_res = data.get("scan_resolution", 0)
    eff_sig = data.get("effective_signature_radius", data.get("signature_radius", 0))

    destroyed_str = "  [bold red]*** DESTROYED ***[/bold red]\n" if destroyed else ""

    faction_str = data.get("faction") or "none"
    team_id = data.get("team_id")
    team_str = f"  Team       : #{team_id}\n" if team_id else ""

    header = (
        f"[bold]{data['name']}[/bold]  —  [cyan]{data['ship_class'].upper()}[/cyan]  "
        f"(ID #{data['id']})\n"
        f"  Faction    : {faction_str.title()}\n"
        f"{team_str}"
        f"{destroyed_str}"
        f"{docked_str}"
        f"  Position   : ({data['pos_x']:.1f}, {data['pos_y']:.1f}, {data['pos_z']:.1f}) m\n"
        f"  Velocity   : ({data['vel_x']:.1f}, {data['vel_y']:.1f}, {data['vel_z']:.1f}) m/s"
        f"  →  {_speed_vec(data['vel_x'], data['vel_y'], data['vel_z'])}\n"
        f"  Max Speed  : {data['max_speed']:.1f} m/s   "
        f"Acceleration: {data['acceleration']:.2f} m/s²\n"
        f"  Ore        : {data['ore']:.0f} / {data['cargo_capacity']:.0f} m³\n"
        f"  Capacitor  : {_cap_bar(data['capacitor'], data['max_capacitor'])}  "
        f"({data['capacitor']:.0f}/{data['max_capacitor']:.0f} GJ)\n"
        f"  Shield     : {_hp_bar(shield_hp, max_shield, 'blue')}  "
        f"({shield_hp:.0f}/{max_shield:.0f} HP)\n"
        f"  Armor      : {_hp_bar(armor_hp, max_armor, 'yellow')}  "
        f"({armor_hp:.0f}/{max_armor:.0f} HP)\n"
        f"  Volume     : {data['used_volume']} / {data['total_volume']} m³   "
        f"Sig. Radius: {eff_sig:.0f} m   "
        f"Scan Res: {scan_res:.0f} mm"
    )
    console.print(Panel(header, title=f"Ship #{data['id']} Detail", border_style="cyan"))

    # Modules
    modules = data.get("modules", [])
    if modules:
        display_modules(modules, json_mode=False, _title="Installed Modules")

    # Active orders
    orders = data.get("active_orders", [])
    if orders:
        _display_orders(orders)


def display_modules(modules: list, json_mode: bool, _title: str = "Modules") -> None:
    if json_mode:
        _json_out(modules)
        return

    if not modules:
        console.print("[dim]No modules installed.[/dim]")
        return

    t = Table(box=box.SIMPLE, title=_title, show_lines=False)
    t.add_column("ID", style="dim", justify="right")
    t.add_column("Type", style="bold")
    t.add_column("Volume", justify="right")
    t.add_column("Active")
    t.add_column("Cap/Cycle", justify="right")
    t.add_column("Cycle Time", justify="right")
    t.add_column("Details")

    for m in modules:
        active_str = "[green]YES[/green]" if m.get("active") else "[red]no[/red]"
        cap = m.get("capacitor_per_cycle", 0)
        cycle = m.get("cycle_time", 0)
        cycle_str = f"{cycle}t" if cycle else "passive"
        cap_str = f"{cap:.0f} GJ" if cap else "—"

        details_parts: list[str] = []
        if (m.get("mining_yield") or 0) > 0:
            details_parts.append(f"yield={m['mining_yield']:.0f} ore, range={m.get('mining_range') or 0:.0f} m")
        if (m.get("scan_range") or 0) > 0:
            details_parts.append(f"scan={_fmt_dist(m['scan_range'])}")
        if (m.get("detection_range") or 0) > 0:
            details_parts.append(f"detect={_fmt_dist(m['detection_range'])}")
        if m.get("factory_max_class"):
            details_parts.append(f"builds≤{m['factory_max_class']}")
        if m.get("module_type") == "mining_laser" and m.get("active"):
            details_parts.append("active - mines nearest asteroid within 500m range")
        # Combat module details
        if (m.get("damage_per_cycle") or 0) > 0:
            details_parts.append(f"dmg={m['damage_per_cycle']:.0f} {m.get('damage_type', '?')}")
        if (m.get("optimal_range") or 0) > 0:
            details_parts.append(f"opt={_fmt_dist(m['optimal_range'])}")
        if (m.get("falloff_range") or 0) > 0:
            details_parts.append(f"fall={_fmt_dist(m['falloff_range'])}")
        if (m.get("tracking_speed") or 0) > 0:
            details_parts.append(f"track={m['tracking_speed']:.4f} rad/s")
        if (m.get("shield_hp_bonus") or 0) > 0:
            details_parts.append(f"+shield={m['shield_hp_bonus']:.0f} HP")
        if (m.get("armor_hp_bonus") or 0) > 0:
            details_parts.append(f"+armor={m['armor_hp_bonus']:.0f} HP")
        if (m.get("shield_repair_per_cycle") or 0) > 0:
            details_parts.append(f"shield rep={m['shield_repair_per_cycle']:.0f} HP/cycle")
        if (m.get("armor_repair_per_cycle") or 0) > 0:
            details_parts.append(f"armor rep={m['armor_repair_per_cycle']:.0f} HP/cycle")

        t.add_row(
            str(m["id"]),
            m["module_type"],
            f"{m['volume']} m³",
            active_str,
            cap_str,
            cycle_str,
            ", ".join(details_parts) if details_parts else "—",
        )

    console.print(t)


def _display_orders(orders: list) -> None:
    if not orders:
        return
    t = Table(box=box.SIMPLE, title="Active Orders", show_lines=False)
    t.add_column("ID", style="dim", justify="right")
    t.add_column("Type", style="bold")
    t.add_column("Status")
    t.add_column("Target")
    t.add_column("Parameters")

    for o in orders:
        target_parts: list[str] = []
        if o.get("target_ship_id") is not None:
            target_parts.append(f"ship #{o['target_ship_id']}")
        if o.get("target_object_id") is not None:
            target_parts.append(f"object #{o['target_object_id']}")
        if o.get("target_x") is not None:
            target_parts.append(
                f"({o['target_x']:.0f}, {o['target_y']:.0f}, {o['target_z']:.0f})"
            )
        params: list[str] = []
        if o.get("orbit_radius", 0) > 0:
            params.append(f"radius={o['orbit_radius']:.0f} m")
        if o.get("desired_distance", 0) > 0:
            params.append(f"distance={o['desired_distance']:.0f} m")

        t.add_row(
            str(o["id"]),
            o["order_type"],
            o["status"],
            ", ".join(target_parts) or "—",
            ", ".join(params) or "—",
        )
    console.print(t)


def display_order(data: dict, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return
    console.print(
        f"[green]Order #{data['id']} created[/green]  "
        f"type=[bold]{data['order_type']}[/bold]  status={data['status']}"
    )


def display_order_cancel(data: dict, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return
    console.print(
        f"[yellow]Order #{data['id']} cancelled[/yellow]  "
        f"type={data['order_type']}"
    )


# ---------------------------------------------------------------------------
# Module install / activate / deactivate
# ---------------------------------------------------------------------------


def display_module(data: dict, json_mode: bool, action: str = "Module") -> None:
    if json_mode:
        _json_out(data)
        return
    active_str = "[green]active[/green]" if data.get("active") else "[dim]inactive[/dim]"
    console.print(
        f"[green]{action}[/green]  "
        f"#{data['id']} [bold]{data['module_type']}[/bold]  {data['volume']} m³  {active_str}"
    )


def display_module_uninstall(json_mode: bool) -> None:
    if json_mode:
        _json_out({"status": "uninstalled"})
        return
    console.print("[green]Module uninstalled.[/green]")


# ---------------------------------------------------------------------------
# Mining
# ---------------------------------------------------------------------------


def display_mine_action(data: dict, json_mode: bool, action: str) -> None:
    """Display result of activating/deactivating mining lasers."""
    if json_mode:
        _json_out(data)
        return

    lasers = data.get("lasers", [])
    count = len(lasers)
    verb = "Activated" if action == "start" else "Deactivated"
    console.print(
        f"[green]{verb} {count} mining laser(s).[/green]"
    )
    for laser in lasers:
        state = "[green]active[/green]" if laser.get("active") else "[dim]inactive[/dim]"
        console.print(f"  Laser #{laser['id']}  {state}")


# ---------------------------------------------------------------------------
# Resources / transfer
# ---------------------------------------------------------------------------


def display_transfer(data: dict, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return
    color = "green" if data.get("transferred", 0) > 0 else "yellow"
    console.print(f"[{color}]{data.get('message', 'Transfer complete')}[/{color}]")
    console.print(
        f"  Transferred : [bold]{data.get('transferred', 0):.0f}[/bold] ore\n"
        f"  Source ore  : {data.get('source_ore', 0):.0f}\n"
        f"  Target ore  : {data.get('target_ore', 0):.0f}\n"
        f"  Complete    : {'yes' if data.get('complete') else 'no'}"
    )


# ---------------------------------------------------------------------------
# Production
# ---------------------------------------------------------------------------


def display_build_order(data: dict, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return
    console.print(
        Panel(
            f"Blueprint    : [bold]{data['blueprint']}[/bold]\n"
            f"Status       : [cyan]{data['status']}[/cyan]\n"
            f"Ore cost     : {data['ore_cost']}\n"
            f"Ticks total  : {data['total_ticks']}\n"
            f"Ticks left   : {data['ticks_remaining']}\n"
            f"Progress     : {data['progress_pct']}%\n"
            f"Factory mod  : #{data['factory_module_id']}",
            title=f"Build Order #{data['id']}",
            border_style="magenta",
        )
    )


def display_build_queue(data: dict, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return

    console.print(f"[bold]Build queue for ship #{data['ship_id']}[/bold]")

    active = data.get("active_build")
    if active:
        _display_build_row_panel(active, label="[cyan]BUILDING[/cyan]")
    else:
        console.print("  [dim]No active build[/dim]")

    queued = data.get("queued", [])
    if queued:
        console.print("  [yellow]Queued:[/yellow]")
        for o in queued:
            _display_build_row_panel(o, label="queued")

    completed = data.get("completed", [])
    if completed:
        t = Table(box=box.SIMPLE, title="Completed Builds", show_lines=False)
        t.add_column("ID", justify="right")
        t.add_column("Blueprint")
        t.add_column("Ore Cost", justify="right")
        for o in completed:
            t.add_row(str(o["id"]), o["blueprint"], str(o["ore_cost"]))
        console.print(t)


def _display_build_row_panel(o: dict, label: str) -> None:
    progress_bar_width = 20
    pct = o.get("progress_pct", 0.0) / 100.0
    filled = round(pct * progress_bar_width)
    bar = "#" * filled + "-" * (progress_bar_width - filled)
    # Use | instead of [] to avoid Rich treating this as markup
    console.print(
        f"  {label}  #{o['id']} [bold]{o['blueprint']}[/bold]  "
        f"|{bar}| {o['progress_pct']}%  "
        f"{o['ticks_remaining']}/{o['total_ticks']} ticks left"
    )


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


def display_scan_results(data: dict, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return

    contacts = data.get("contacts", [])
    tick = data.get("tick", "?")
    msg = data.get("message", "")

    console.print(
        Panel(
            f"Tick [bold cyan]{tick}[/bold cyan]  —  {msg}",
            title="Active Scan Results",
            border_style="blue",
        )
    )
    _display_contacts_table(contacts)


def display_nearby(contacts: list, json_mode: bool) -> None:
    if json_mode:
        _json_out(contacts)
        return

    console.print(Panel(f"{len(contacts)} object(s) in default visibility range", title="Nearby", border_style="blue"))
    _display_contacts_table(contacts)


def _display_contacts_table(contacts: list) -> None:
    if not contacts:
        console.print("[dim]No contacts.[/dim]")
        return

    t = Table(box=box.SIMPLE_HEAVY, show_lines=False)
    t.add_column("Type")
    t.add_column("ID", justify="right")
    t.add_column("Distance")
    t.add_column("Detail")
    t.add_column("Class / Object")
    t.add_column("Name / Info")
    t.add_column("Position")

    for c in contacts:
        class_col = c.get("ship_class") or c.get("object_type") or "?"
        name_parts: list[str] = []
        if c.get("name"):
            name_parts.append(c["name"])
        if c.get("ore_remaining") is not None:
            name_parts.append(f"ore={c['ore_remaining']:.0f}")
        if c.get("capacitor") is not None and c.get("max_capacitor"):
            pct = c["capacitor"] / c["max_capacitor"] * 100
            name_parts.append(f"cap={pct:.0f}%")

        pos = f"({c['pos_x']:.0f}, {c['pos_y']:.0f}, {c['pos_z']:.0f})"

        t.add_row(
            c["type"],
            str(c["id"]),
            _fmt_dist(c["distance"]) if "distance" in c else "—",
            _detail_label(c["detail"]),
            class_col,
            ", ".join(name_parts) or "—",
            pos,
        )

    console.print(t)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


EVENT_COLORS: dict[str, str] = {
    "detection": "yellow",
    "scan_complete": "blue",
    "scan_detected": "magenta",
    "mining": "green",
    "cargo_full": "bold yellow",
    "asteroid_depleted": "red",
    "build_complete": "bold green",
    "build_paused": "yellow",
    "order_complete": "cyan",
    "dock_complete": "cyan",
    "cap_depleted": "bold red",
    "transfer_complete": "green",
    # Research events
    "research_started": "cyan",
    "research_complete": "bold green",
    "research_paused": "yellow",
    # Match events
    "match_started": "bold green",
    "mothership_under_attack": "bold yellow",
    "mothership_critical": "bold red",
    "match_ended": "bold cyan",
    "surrender_vote": "yellow",
    # Combat events
    "target_locked": "bold yellow",
    "target_lost": "yellow",
    "weapon_hit": "bold red",
    "weapon_miss": "dim",
    "missile_launched": "magenta",
    "missile_hit": "bold red",
    "shield_depleted": "bold yellow",
    "ship_destroyed": "bold red",
    "wreck_created": "dim red",
    "kill": "bold green",
}


def display_events(events: list, json_mode: bool) -> None:
    if json_mode:
        _json_out(events)
        return

    if not events:
        console.print("[dim]No new events.[/dim]")
        return

    for e in events:
        _print_event_line(e)


def format_event_line(event: dict, json_mode: bool) -> str:
    """Return a single formatted string for an event (used by 'watch')."""
    if json_mode:
        return json.dumps(event)

    tick = event.get("tick", "?")
    etype = event.get("type", "event").upper()
    ship_part = f"Ship #{event['ship_id']}: " if event.get("ship_id") is not None else ""
    msg = event.get("message", "")
    color = EVENT_COLORS.get(event.get("type", ""), "white")
    return f"[dim][Tick {tick}][/dim] [{color}]{etype}[/{color}] {ship_part}{msg}"


def _print_event_line(event: dict) -> None:
    console.print(format_event_line(event, json_mode=False))


# ---------------------------------------------------------------------------
# Research
# ---------------------------------------------------------------------------


def display_research_progress(data: dict, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return
    pct = data.get("progress_pct", 0.0)
    console.print(
        Panel(
            f"Tech       : [bold]{data.get('tech_name', data.get('tech_id'))}[/bold]\n"
            f"Status     : [cyan]{data.get('status')}[/cyan]\n"
            f"Progress   : {pct}%  ({data.get('ticks_remaining', 0)} ticks remaining)\n"
            f"Ship       : #{data.get('ship_id')}  Module: #{data.get('module_id')}",
            title=f"Research #{data.get('id', '?')}",
            border_style="cyan",
        )
    )


def display_research_list(items: list, json_mode: bool) -> None:
    if json_mode:
        _json_out(items)
        return

    if not items:
        console.print("[dim]No research in progress on this ship.[/dim]")
        return

    t = Table(box=box.SIMPLE, title="Research Progress", show_lines=False)
    t.add_column("ID", style="dim", justify="right")
    t.add_column("Tech", style="bold")
    t.add_column("Status")
    t.add_column("Progress")
    t.add_column("Ticks Left", justify="right")

    for r in items:
        status = r.get("status", "?")
        color = {"researching": "cyan", "paused": "yellow", "complete": "green"}.get(status, "white")
        pct = r.get("progress_pct", 0.0)
        t.add_row(
            str(r.get("id", "?")),
            r.get("tech_name", r.get("tech_id", "?")),
            f"[{color}]{status}[/{color}]",
            f"{pct:.0f}%",
            str(r.get("ticks_remaining", 0)),
        )

    console.print(t)


def display_tech_tree(nodes: list, json_mode: bool) -> None:
    if json_mode:
        _json_out(nodes)
        return

    if not nodes:
        console.print("[dim]No tech tree data.[/dim]")
        return

    t = Table(box=box.SIMPLE_HEAVY, title="Tech Tree", show_lines=True)
    t.add_column("Tier", justify="center")
    t.add_column("Tech ID", style="dim")
    t.add_column("Name", style="bold")
    t.add_column("Status")
    t.add_column("Prerequisites")
    t.add_column("Ore", justify="right")
    t.add_column("Ticks", justify="right")
    t.add_column("Unlocks")

    for n in sorted(nodes, key=lambda x: (x.get("tier", 0), x.get("tech_id", ""))):
        status = n.get("status", "?")
        color_map = {
            "complete": "green",
            "researching": "cyan",
            "available": "yellow",
            "locked": "dim",
        }
        color = color_map.get(status, "white")
        prereqs = ", ".join(n.get("prerequisites", [])) or "—"
        unlocks_parts = n.get("unlocks_modules", []) + n.get("unlocks_ships", [])
        unlocks = ", ".join(unlocks_parts[:3])
        if len(unlocks_parts) > 3:
            unlocks += f" +{len(unlocks_parts) - 3} more"

        t.add_row(
            str(n.get("tier", "?")),
            n.get("tech_id", "?"),
            n.get("name", "?"),
            f"[{color}]{status}[/{color}]",
            prereqs,
            str(n.get("ore_cost", 0)),
            str(n.get("research_ticks", 0)),
            unlocks or "—",
        )

    console.print(t)


# ---------------------------------------------------------------------------
# Loadout: available hulls & cost tables
# ---------------------------------------------------------------------------


def display_available_hulls(hulls: list, points: float) -> None:
    """Rich table of claimable unclaimed hulls."""
    console.print(f"  Points: [bold yellow]{points:.0f}[/bold yellow]")
    if not hulls:
        console.print("  [dim]No unclaimed hulls available.[/dim]")
        return
    t = Table(box=box.SIMPLE_HEAVY, title="Available Hulls", show_lines=False)
    t.add_column("Ship ID", justify="right", style="dim")
    t.add_column("Class", style="bold")
    t.add_column("Docked At", justify="right")
    t.add_column("Hull Cost", justify="right")
    for h in hulls:
        t.add_row(
            str(h["ship_id"]),
            h["ship_class"],
            str(h["docked_at_ship_id"]),
            str(h["hull_point_cost"]),
        )
    console.print(t)


def display_loadout_costs(hull_costs: dict, module_costs: dict) -> None:
    """Rich tables showing hull and module point costs."""
    ht = Table(box=box.SIMPLE_HEAVY, title="Hull Point Costs", show_lines=False)
    ht.add_column("Ship Class", style="bold")
    ht.add_column("Cost", justify="right")
    for cls, cost in sorted(hull_costs.items(), key=lambda x: x[1]):
        ht.add_row(cls, str(cost))
    console.print(ht)

    mt = Table(box=box.SIMPLE_HEAVY, title="Module Point Costs", show_lines=False)
    mt.add_column("Module Type", style="bold")
    mt.add_column("Cost", justify="right")
    for mod, cost in sorted(module_costs.items(), key=lambda x: (x[1], x[0])):
        mt.add_row(mod, str(cost))
    console.print(mt)


# ---------------------------------------------------------------------------
# Combat: target locks
# ---------------------------------------------------------------------------


def display_lock(data: dict, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return
    status = data.get("status", "locking")
    ticks = data.get("ticks_remaining", 0)
    if status == "locked":
        console.print(
            f"[bold green]Lock acquired[/bold green] on Ship #{data['target_ship_id']}"
        )
    else:
        console.print(
            f"[yellow]Locking[/yellow] Ship #{data['target_ship_id']}  "
            f"— {ticks} tick(s) remaining"
        )


def display_locks(locks: list, json_mode: bool) -> None:
    if json_mode:
        _json_out(locks)
        return

    if not locks:
        console.print("[dim]No active target locks.[/dim]")
        return

    t = Table(box=box.SIMPLE, title="Target Locks", show_lines=False)
    t.add_column("Lock ID", style="dim", justify="right")
    t.add_column("Target Ship", justify="right")
    t.add_column("Status")
    t.add_column("Ticks Left", justify="right")

    for l in locks:
        status = l.get("status", "?")
        color = "green" if status == "locked" else "yellow"
        t.add_row(
            str(l["id"]),
            f"#{l['target_ship_id']}",
            f"[{color}]{status}[/{color}]",
            str(l.get("ticks_remaining", 0)),
        )

    console.print(t)


# ---------------------------------------------------------------------------
# Combat: weapons
# ---------------------------------------------------------------------------


def display_weapon_assign(data: dict, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return
    console.print(
        f"[green]Weapon #{data['module_id']} assigned[/green] → Ship #{data['target_ship_id']}"
    )


def display_weapon_assignments(assignments: list, json_mode: bool) -> None:
    if json_mode:
        _json_out(assignments)
        return

    if not assignments:
        console.print("[dim]No weapon modules found on this ship.[/dim]")
        return

    console.print(f"[bold green]{len(assignments)} weapon(s) assigned and active:[/bold green]")
    for a in assignments:
        console.print(f"  Weapon #{a['module_id']} → Ship #{a['target_ship_id']}")


# ---------------------------------------------------------------------------
# Teams (Phase 7)
# ---------------------------------------------------------------------------


def display_teams(data: list, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return
    if not data:
        console.print("[dim]No teams found.[/dim]")
        return
    t = Table(box=box.SIMPLE, title="Teams")
    t.add_column("ID", justify="right")
    t.add_column("Name")
    t.add_column("Faction")
    t.add_column("Members", justify="right")
    for team in data:
        t.add_row(
            str(team["id"]),
            team["name"],
            team.get("faction", "?").title(),
            str(team.get("member_count", "?")),
        )
    console.print(t)


def display_team_info(data: dict, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return

    faction = (data.get("faction") or "?").title()
    members = data.get("members", [])
    member_count = data.get("member_count", len(members))

    header = (
        f"[bold]{data.get('name', '?')}[/bold]  (ID #{data.get('id', '?')})\n"
        f"  Faction    : [cyan]{faction}[/cyan]\n"
        f"  Members    : {member_count}"
    )

    console.print(Panel(header, title=f"Team #{data.get('id', '?')}", border_style="cyan"))

    if members:
        t = Table(box=box.SIMPLE, title="Team Members", show_lines=False)
        t.add_column("User ID", justify="right")
        t.add_column("Username", style="bold")
        for m in members:
            t.add_row(
                str(m.get("id", m.get("user_id", "?"))),
                m.get("username", "?"),
            )
        console.print(t)


def display_team_research(data: list, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return

    if not data:
        console.print("[dim]No team research in progress.[/dim]")
        return

    t = Table(box=box.SIMPLE, title="Team Research Status", show_lines=False)
    t.add_column("ID", style="dim", justify="right")
    t.add_column("Tech", style="bold")
    t.add_column("Status")
    t.add_column("Progress")
    t.add_column("Ticks Left", justify="right")
    t.add_column("Ship", justify="right")

    for r in data:
        status = r.get("status", "?")
        color = {"researching": "cyan", "paused": "yellow", "complete": "green"}.get(status, "white")
        total = r.get("total_ticks", 1) or 1
        remaining = r.get("ticks_remaining", 0)
        pct = r.get("progress_pct", ((total - remaining) / total) * 100.0)
        t.add_row(
            str(r.get("id", "?")),
            r.get("tech_name", r.get("tech_id", "?")),
            f"[{color}]{status}[/{color}]",
            f"{pct:.0f}%",
            str(remaining),
            str(r.get("ship_id", "?")),
        )

    console.print(t)


# ---------------------------------------------------------------------------
# Leech debuffs (Phase 7)
# ---------------------------------------------------------------------------


def display_leeches(data: list, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return
    if not data:
        console.print("[dim]No active leech debuffs.[/dim]")
        return
    t = Table(box=box.SIMPLE, title="Active Leech Debuffs")
    t.add_column("Source Ship", justify="right")
    t.add_column("Type")
    t.add_column("Damage/tick", justify="right")
    t.add_column("Cap Drain/tick", justify="right")
    t.add_column("Ticks Left", justify="right")
    for l in data:
        t.add_row(
            str(l.get("source_ship_id", "?")),
            l.get("leech_type", "?"),
            f"{l.get('damage_per_tick', 0):.1f}",
            f"{l.get('cap_drain_per_tick', 0):.1f}",
            str(l.get("ticks_remaining", 0)),
        )
    console.print(t)


# ---------------------------------------------------------------------------
# Matches (Phase 8)
# ---------------------------------------------------------------------------


def display_matches(data: list, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return
    if not data:
        console.print("[dim]No matches found.[/dim]")
        return
    t = Table(box=box.SIMPLE, title="Matches")
    t.add_column("ID", justify="right")
    t.add_column("Name", style="bold")
    t.add_column("Status")
    t.add_column("Team 1", justify="right")
    t.add_column("Team 2", justify="right")
    t.add_column("Winner", justify="right")
    for m in data:
        status_color = {
            "pending": "yellow",
            "active": "green",
            "completed": "cyan",
            "cancelled": "dim",
        }.get(m.get("status", ""), "white")
        winner = str(m["winner_team_id"]) if m.get("winner_team_id") else "-"
        t.add_row(
            str(m["id"]),
            m["name"],
            f"[{status_color}]{m['status']}[/{status_color}]",
            str(m.get("team1_id") or "-"),
            str(m.get("team2_id") or "-"),
            winner,
        )
    console.print(t)


def display_match_info(data: dict, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return

    status_color = {
        "pending": "yellow",
        "active": "green",
        "completed": "cyan",
        "cancelled": "dim",
    }.get(data.get("status", ""), "white")

    header = (
        f"[bold]{data.get('name', '?')}[/bold]  (Match #{data.get('id', '?')})\n"
        f"  Status     : [{status_color}]{data.get('status', '?')}[/{status_color}]"
    )

    if data.get("started_at_tick") is not None:
        header += f"\n  Started    : Tick {data['started_at_tick']}"
    if data.get("ended_at_tick") is not None:
        header += f"\n  Ended      : Tick {data['ended_at_tick']}"
    if data.get("winner_team_id") is not None:
        header += f"\n  Winner     : Team #{data['winner_team_id']}"

    # Team info
    for label, team_key, ms_key in [
        ("Team 1", "team1", "team1_mothership"),
        ("Team 2", "team2", "team2_mothership"),
    ]:
        team = data.get(team_key)
        if team:
            header += (
                f"\n  {label}      : {team['name']}  "
                f"({team['faction'].title()}, {team['member_count']} player(s))"
            )
            ms = data.get(ms_key)
            if ms:
                shield_bar = _hp_bar(ms["shield_hp"], ms["max_shield_hp"], "blue", 15)
                armor_bar = _hp_bar(ms["armor_hp"], ms["max_armor_hp"], "yellow", 15)
                destroyed = " [bold red]DESTROYED[/bold red]" if ms.get("is_destroyed") else ""
                header += (
                    f"\n    Mothership : {ms['name']}{destroyed}"
                    f"\n      Shield   : {shield_bar}"
                    f"\n      Armor    : {armor_bar}"
                )
        else:
            header += f"\n  {label}      : [dim]Waiting for opponent[/dim]"

    console.print(Panel(header, title=f"Match #{data.get('id', '?')}", border_style="cyan"))


def display_surrender(data: dict, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return
    if data.get("match_ended"):
        console.print(f"[bold red]{data.get('message', 'Match ended by surrender.')}[/bold red]")
    else:
        console.print(
            f"[yellow]{data.get('message', 'Vote recorded.')}[/yellow]  "
            f"({data.get('votes', 0)}/{data.get('needed', 0)} votes needed)"
        )


# ---------------------------------------------------------------------------
# View (Intent-based CQS)
# ---------------------------------------------------------------------------


def display_view(data: dict, json_mode: bool, events_only: bool = False) -> None:
    if json_mode:
        _json_out(data)
        return

    tick = data.get("tick", 0)
    points = data.get("points", 0)
    console.print(Panel(
        f"Tick: [bold cyan]{tick}[/bold cyan]   Points: [bold yellow]{points:.0f}[/bold yellow]",
        title="World View", border_style="blue",
    ))

    # Team info
    team = data.get("team")
    if team:
        console.print(
            f"  Team: [bold]{team['name']}[/bold] (#{team['id']})  "
            f"Faction: [cyan]{team.get('faction', '?').title()}[/cyan]"
        )

    # Match info
    match = data.get("match")
    if match:
        console.print(
            f"  Match: [bold]{match.get('name', '?')}[/bold] (#{match['id']})  "
            f"Status: {match.get('status', '?')}"
        )

    if not events_only:
        # Ships
        ships = data.get("ships", [])
        if ships:
            t = Table(box=box.SIMPLE_HEAVY, title="Your Ships", show_lines=False)
            t.add_column("ID", style="dim", justify="right")
            t.add_column("Name", style="bold")
            t.add_column("Class")
            t.add_column("Position")
            t.add_column("Speed")
            t.add_column("Ore / Cargo")
            t.add_column("Shield")
            t.add_column("Armor")
            t.add_column("Cap %")

            for s in ships:
                pos = f"({s['pos_x']:.0f}, {s['pos_y']:.0f}, {s['pos_z']:.0f})"
                speed = _speed_vec(s["vel_x"], s["vel_y"], s["vel_z"])
                ore = f"{s['ore']:.0f}/{s['cargo_capacity']:.0f}"
                shield_pct = (s["shield_hp"] / s["max_shield_hp"] * 100) if s.get("max_shield_hp") else 0
                armor_pct = (s["armor_hp"] / s["max_armor_hp"] * 100) if s.get("max_armor_hp") else 0
                cap_pct = (s["capacitor"] / s["max_capacitor"] * 100) if s.get("max_capacitor") else 0
                destroyed = " [red]X[/red]" if s.get("is_destroyed") else ""
                t.add_row(
                    str(s["id"]),
                    s["name"] + destroyed,
                    s["ship_class"],
                    pos,
                    speed,
                    ore,
                    f"{shield_pct:.0f}%",
                    f"{armor_pct:.0f}%",
                    f"{cap_pct:.0f}%",
                )
            console.print(t)

        # Available hulls
        hulls = data.get("available_hulls", [])
        if hulls:
            ht = Table(box=box.SIMPLE_HEAVY, title="Available Hulls", show_lines=False)
            ht.add_column("Ship ID", justify="right", style="dim")
            ht.add_column("Class", style="bold")
            ht.add_column("Docked At", justify="right")
            ht.add_column("Hull Cost", justify="right")
            for h in hulls:
                ht.add_row(
                    str(h["ship_id"]), h["ship_class"],
                    str(h["docked_at_ship_id"]), str(h["hull_point_cost"]),
                )
            console.print(ht)

        # Nearby contacts
        nearby = data.get("nearby", [])
        if nearby:
            _display_contacts_table(nearby)

    # Events
    events = data.get("events", [])
    if events:
        console.print(f"\n[bold]Events ({len(events)}):[/bold]")
        for e in events:
            tick_num = e.get("tick", "?")
            etype = e.get("type", "event").upper()
            ship_part = f"Ship #{e['ship_id']}: " if e.get("ship_id") is not None else ""
            msg = e.get("message", "")
            color = EVENT_COLORS.get(e.get("type", ""), "white")
            console.print(f"  [dim][Tick {tick_num}][/dim] [{color}]{etype}[/{color}] {ship_part}{msg}")

    # Pending commands
    commands = data.get("pending_commands", [])
    pending = [c for c in commands if c.get("status") == "pending"]
    if pending:
        console.print(f"\n[yellow]{len(pending)} pending command(s)[/yellow]")


def display_command_queued(data: dict, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return
    cmd_id = data.get("command_id", "?")
    cmd_type = data.get("type", "?")
    console.print(
        f"[green]Command queued[/green]  id={cmd_id}  type=[bold]{cmd_type}[/bold]  "
        f"status={data.get('status', 'pending')}"
    )


# ---------------------------------------------------------------------------
# Generic error / success helpers
# ---------------------------------------------------------------------------


def print_error(msg: str) -> None:
    err_console.print(f"[bold red]Error:[/bold red] {msg}")


def print_success(msg: str) -> None:
    console.print(f"[green]{msg}[/green]")
