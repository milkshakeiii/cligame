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
        pos = f"({s['pos_x']:.0f}, {s['pos_y']:.0f}, {s['pos_z']:.0f})"
        speed = _speed_vec(s["vel_x"], s["vel_y"], s["vel_z"])
        ore = f"{s['ore']:.0f}/{s['cargo_capacity']:.0f}"
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

    t = Table(box=box.SIMPLE_HEAVY, title="Ships", show_lines=False)
    t.add_column("ID", style="dim", justify="right")
    t.add_column("Name", style="bold")
    t.add_column("Class")
    t.add_column("Position")
    t.add_column("Speed")
    t.add_column("Ore / Cargo")
    t.add_column("Cap %")
    t.add_column("Vol Used")

    for s in ships:
        pos = f"({s['pos_x']:.0f}, {s['pos_y']:.0f}, {s['pos_z']:.0f})"
        speed = _speed_vec(s["vel_x"], s["vel_y"], s["vel_z"])
        ore = f"{s['ore']:.0f}/{s['cargo_capacity']:.0f}"
        pct = (s["capacitor"] / s["max_capacitor"] * 100) if s["max_capacitor"] else 0
        cap_str = f"{pct:.0f}%"
        vol = f"{s['used_volume']}/{s['total_volume']}"
        t.add_row(
            str(s["id"]),
            s["name"],
            s["ship_class"],
            pos,
            speed,
            ore,
            cap_str,
            vol,
        )

    console.print(t)


def display_ship_info(data: dict, json_mode: bool) -> None:
    if json_mode:
        _json_out(data)
        return

    # Header panel
    docked = data.get("docked_in_id")
    docked_str = f"  Docked in ship #{docked}\n" if docked else ""
    header = (
        f"[bold]{data['name']}[/bold]  —  [cyan]{data['ship_class'].upper()}[/cyan]  "
        f"(ID #{data['id']})\n"
        f"{docked_str}"
        f"  Position   : ({data['pos_x']:.1f}, {data['pos_y']:.1f}, {data['pos_z']:.1f}) m\n"
        f"  Velocity   : ({data['vel_x']:.1f}, {data['vel_y']:.1f}, {data['vel_z']:.1f}) m/s"
        f"  →  {_speed_vec(data['vel_x'], data['vel_y'], data['vel_z'])}\n"
        f"  Max Speed  : {data['max_speed']:.1f} m/s   "
        f"Acceleration: {data['acceleration']:.2f} m/s²\n"
        f"  Ore        : {data['ore']:.0f} / {data['cargo_capacity']:.0f} m³\n"
        f"  Capacitor  : {_cap_bar(data['capacitor'], data['max_capacitor'])}  "
        f"({data['capacitor']:.0f}/{data['max_capacitor']:.0f})\n"
        f"  Volume     : {data['used_volume']} / {data['total_volume']} m³   "
        f"Sig. Radius: {data['signature_radius']:.0f} m"
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
        cap_str = f"{cap:.0f}" if cap else "—"

        details_parts: list[str] = []
        if m.get("mining_yield", 0) > 0:
            details_parts.append(f"yield={m['mining_yield']:.0f} ore, range={m.get('mining_range', 0):.0f} m")
        if m.get("scan_range", 0) > 0:
            details_parts.append(f"scan={_fmt_dist(m['scan_range'])}")
        if m.get("detection_range", 0) > 0:
            details_parts.append(f"detect={_fmt_dist(m['detection_range'])}")
        if m.get("factory_max_class"):
            details_parts.append(f"builds≤{m['factory_max_class']}")
        if m.get("module_type") == "mining_laser" and m.get("active"):
            details_parts.append("active - mines nearest asteroid within 500m range")

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
            _fmt_dist(c["distance"]),
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
# Generic error / success helpers
# ---------------------------------------------------------------------------


def print_error(msg: str) -> None:
    err_console.print(f"[bold red]Error:[/bold red] {msg}")


def print_success(msg: str) -> None:
    console.print(f"[green]{msg}[/green]")
