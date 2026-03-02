"""
SpaceGameClient — httpx wrapper for all backend API calls.

- Reads the base URL from the SPACEGAME_URL env var (default: http://localhost:8000).
- Loads the auth token from ~/.spacegame_token automatically.
- Raises a clean SystemExit on auth / connection errors so callers don't need
  to handle httpx internals.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOKEN_FILE = Path.home() / ".spacegame_token"
DEFAULT_BASE_URL = "http://localhost:8000"


# ---------------------------------------------------------------------------
# Helper: token persistence
# ---------------------------------------------------------------------------


def save_token(token: str) -> None:
    """Write the auth token to disk."""
    TOKEN_FILE.write_text(token)
    TOKEN_FILE.chmod(0o600)


def load_token() -> Optional[str]:
    """Return the stored token, or None if the file doesn't exist.

    Checks the SPACEGAME_TOKEN environment variable first, then falls
    back to the on-disk token file.
    """
    env_token = os.environ.get("SPACEGAME_TOKEN")
    if env_token:
        return env_token
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip() or None
    return None


def delete_token() -> None:
    """Remove the stored token (logout)."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()


# ---------------------------------------------------------------------------
# Client class
# ---------------------------------------------------------------------------


class SpaceGameClient:
    """
    Thin httpx wrapper for the Space Game API.

    All methods return the parsed JSON response dict/list.
    On HTTP error responses, they raise ``SpaceGameError``.
    On connection errors, they raise ``SystemExit`` with a user-friendly message.
    """

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        self.base_url = (base_url or os.environ.get("SPACEGAME_URL", DEFAULT_BASE_URL)).rstrip("/")
        self._token = token or load_token()

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json_body: Optional[Any] = None,
        require_auth: bool = True,
    ) -> Any:
        if require_auth and not self._token:
            raise SpaceGameError("Not logged in. Run: spacegame login <username>")

        url = f"{self.base_url}{path}"
        try:
            response = httpx.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json_body,
                timeout=30.0,
            )
        except httpx.ConnectError:
            raise SystemExit(
                f"Cannot connect to server at {self.base_url}\n"
                "Is the server running? Set SPACEGAME_URL if the address differs."
            )
        except httpx.TimeoutException:
            raise SystemExit(f"Request timed out connecting to {self.base_url}")

        if not response.is_success:
            detail = _extract_detail(response)
            raise SpaceGameError(f"[{response.status_code}] {detail}")

        # 204 No Content
        if response.status_code == 204 or not response.content:
            return None

        return response.json()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def register(self, username: str, password: Optional[str] = None) -> dict:
        """POST /api/auth/register — create account and get token."""
        body: dict = {"username": username}
        if password is not None:
            body["password"] = password
        return self._request(
            "POST",
            "/api/auth/register",
            json_body=body,
            require_auth=False,
        )

    def login(self, username: str, password: Optional[str] = None) -> dict:
        """POST /api/auth/login — get token for existing account."""
        body: dict = {"username": username}
        if password is not None:
            body["password"] = password
        return self._request(
            "POST",
            "/api/auth/login",
            json_body=body,
            require_auth=False,
        )

    def me(self) -> dict:
        """GET /api/auth/me — return current user info (id, username)."""
        return self._request("GET", "/api/auth/me")

    # ------------------------------------------------------------------
    # Game state & events
    # ------------------------------------------------------------------

    def game_status(self) -> dict:
        """GET /api/game/status"""
        return self._request("GET", "/api/game/status", require_auth=False)

    def get_events(
        self,
        since_tick: int = 0,
        limit: int = 100,
        ship_id: Optional[int] = None,
        types: Optional[str] = None,
    ) -> list:
        """GET /api/events"""
        params: dict = {"since_tick": since_tick, "limit": limit}
        if ship_id is not None:
            params["ship_id"] = ship_id
        if types is not None:
            params["types"] = types
        return self._request("GET", "/api/events", params=params)

    # ------------------------------------------------------------------
    # Ships
    # ------------------------------------------------------------------

    def list_ships(self) -> list:
        """GET /api/ships"""
        return self._request("GET", "/api/ships")

    def create_ship(self, name: Optional[str], ship_class: str) -> dict:
        """Create a new ship (command)."""
        payload: dict = {"ship_class": ship_class}
        if name is not None:
            payload["name"] = name
        return self.send_command("create_ship", **payload)

    def rename_ship(self, ship_id: int, new_name: str) -> dict:
        """Rename a ship (command)."""
        return self.send_command("rename_ship", ship_id=ship_id, name=new_name)

    def get_ship(self, ship_id: int) -> dict:
        """GET /api/ships/{ship_id}"""
        return self._request("GET", f"/api/ships/{ship_id}")

    def list_modules(self, ship_id: int) -> list:
        """GET /api/ships/{ship_id}/modules"""
        return self._request("GET", f"/api/ships/{ship_id}/modules")

    def install_module(self, ship_id: int, module_type: str, volume: int = 0) -> dict:
        """Install a module on a ship (command)."""
        return self.send_command("install_module", ship_id=ship_id, module_type=module_type, volume=volume)

    def uninstall_module(self, ship_id: int, module_id: int) -> dict:
        """Uninstall a module from a ship (command)."""
        return self.send_command("uninstall_module", ship_id=ship_id, module_id=module_id)

    def activate_module(self, ship_id: int, module_id: int) -> dict:
        """Activate a module (command)."""
        return self.send_command("activate_module", ship_id=ship_id, module_id=module_id)

    def deactivate_module(self, ship_id: int, module_id: int) -> dict:
        """Deactivate a module (command)."""
        return self.send_command("deactivate_module", ship_id=ship_id, module_id=module_id)

    # ------------------------------------------------------------------
    # Movement orders
    # ------------------------------------------------------------------

    def create_order(self, ship_id: int, payload: dict) -> dict:
        """Create a movement order (command). Extracts order_type from payload."""
        order_type = payload.get("order_type", "")
        if order_type == "stop":
            return self.send_command("stop", ship_id=ship_id)
        # Forward the full payload as command payload for move
        return self.send_command("move", ship_id=ship_id, **payload)

    def cancel_order(self, ship_id: int, order_id: int) -> dict:
        """Cancel a movement order (command)."""
        return self.send_command("cancel_order", ship_id=ship_id, order_id=order_id)

    def dock_ship(self, ship_id: int, target_ship_id: int) -> dict:
        """Dock a ship (command)."""
        return self.send_command("dock", ship_id=ship_id, target_ship_id=target_ship_id)

    # ------------------------------------------------------------------
    # Mining & resources
    # ------------------------------------------------------------------

    def transfer_ore(self, ship_id: int, target_ship_id: int) -> dict:
        """Transfer ore to another ship (command)."""
        return self.send_command("transfer_ore", ship_id=ship_id, target_ship_id=target_ship_id)

    # ------------------------------------------------------------------
    # Production
    # ------------------------------------------------------------------

    def queue_build(
        self,
        ship_id: int,
        blueprint: str,
        factory_module_id: Optional[int] = None,
    ) -> dict:
        """Queue a build order (command)."""
        payload: dict = {"blueprint": blueprint}
        if factory_module_id is not None:
            payload["factory_module_id"] = factory_module_id
        return self.send_command("build", ship_id=ship_id, **payload)

    def get_build_queue(self, ship_id: int) -> dict:
        """GET /api/ships/{ship_id}/build"""
        return self._request("GET", f"/api/ships/{ship_id}/build")

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def scan(self, ship_id: int) -> dict:
        """Trigger an active scan (command)."""
        return self.send_command("scan", ship_id=ship_id)

    def nearby(self, ship_id: int) -> list:
        """GET /api/nearby?ship_id={ship_id}"""
        return self._request("GET", "/api/nearby", params={"ship_id": ship_id})

    # ------------------------------------------------------------------
    # Combat (Phase 4)
    # ------------------------------------------------------------------

    def lock_target(self, ship_id: int, target_ship_id: int) -> dict:
        """Lock a target (command)."""
        return self.send_command("lock_target", ship_id=ship_id, target_ship_id=target_ship_id)

    def unlock_target(self, ship_id: int, target_id: int) -> dict:
        """Unlock a target (command)."""
        return self.send_command("unlock_target", ship_id=ship_id, target_ship_id=target_id)

    def list_locks(self, ship_id: int) -> list:
        """GET /api/ships/{ship_id}/locks"""
        return self._request("GET", f"/api/ships/{ship_id}/locks")

    def assign_weapon(self, ship_id: int, module_id: int, target_ship_id: int) -> dict:
        """Assign a weapon to a target (command)."""
        return self.send_command("assign_weapon", ship_id=ship_id, module_id=module_id, target_ship_id=target_ship_id)

    def fire_all_weapons(self, ship_id: int, target_ship_id: int) -> dict:
        """Fire all weapons at a target (command)."""
        return self.send_command("fire_all", ship_id=ship_id, target_ship_id=target_ship_id)

    def hold_fire(self, ship_id: int) -> dict:
        """Hold fire on all weapons (command)."""
        return self.send_command("hold_fire", ship_id=ship_id)

    # ------------------------------------------------------------------
    # Research (Phase 5)
    # ------------------------------------------------------------------

    def start_research(
        self,
        ship_id: int,
        tech_id: str,
        module_id: Optional[int] = None,
    ) -> dict:
        """Start researching a technology (command)."""
        payload: dict = {"tech_id": tech_id}
        if module_id is not None:
            payload["module_id"] = module_id
        return self.send_command("start_research", ship_id=ship_id, **payload)

    def cancel_research(
        self,
        ship_id: int,
        module_id: Optional[int] = None,
    ) -> dict:
        """Cancel active research (command)."""
        payload: dict = {}
        if module_id is not None:
            payload["module_id"] = module_id
        return self.send_command("cancel_research", ship_id=ship_id, **payload)

    def research_status(self, ship_id: int) -> list:
        """GET /api/ships/{ship_id}/research/status"""
        return self._request("GET", f"/api/ships/{ship_id}/research/status")

    def tech_tree(self) -> list:
        """GET /api/research/tech-tree"""
        return self._request("GET", "/api/research/tech-tree")

    # ------------------------------------------------------------------
    # Loadout (claim/reship)
    # ------------------------------------------------------------------

    def claim_ship(
        self,
        ship_id: Optional[int] = None,
        modules: Optional[list[dict]] = None,
        ship_class: Optional[str] = None,
    ) -> dict:
        """Claim an unclaimed hull with modules (command).

        Either ``ship_id`` (existing hull) or ``ship_class`` (auto-create a
        free hull) must be provided.
        """
        kwargs: dict[str, Any] = {"modules": modules or []}
        if ship_class is not None:
            kwargs["ship_class"] = ship_class
        return self.send_command("claim_ship", ship_id=ship_id, **kwargs)

    def reship(self, ship_id: int) -> dict:
        """Dock and reship — strip modules, get partial point refund (command)."""
        return self.send_command("reship", ship_id=ship_id)

    def board_ship(self, ship_id: int) -> dict:
        """Board an unpiloted eject-allowed ship (command)."""
        return self.send_command("board_ship", ship_id=ship_id)

    def eject(self, ship_id: int) -> dict:
        """Eject from an eject-allowed ship (command)."""
        return self.send_command("eject", ship_id=ship_id)

    def get_loadout_costs(self) -> dict:
        """GET /api/loadout/costs — hull and module point costs."""
        return self._request("GET", "/api/loadout/costs")

    # ------------------------------------------------------------------
    # Teams (Phase 7)
    # ------------------------------------------------------------------

    def create_team(self, name: str, faction: str) -> dict:
        """POST /api/teams — create a new team."""
        return self._request("POST", "/api/teams", json_body={"name": name, "faction": faction})

    def join_team(self, team_id: int) -> dict:
        """POST /api/teams/{team_id}/join — join an existing team."""
        return self._request("POST", f"/api/teams/{team_id}/join")

    def get_team(self, team_id: int) -> dict:
        """GET /api/teams/{team_id} — get team info."""
        return self._request("GET", f"/api/teams/{team_id}")

    def list_teams(self) -> list:
        """GET /api/teams — list all teams."""
        return self._request("GET", "/api/teams")

    def get_team_research(self, team_id: int) -> list:
        """GET /api/teams/{team_id}/research — team research status."""
        return self._request("GET", f"/api/teams/{team_id}/research")

    # ------------------------------------------------------------------
    # Leech debuffs (Phase 7)
    # ------------------------------------------------------------------

    def get_ship_leeches(self, ship_id: int) -> list:
        """GET /api/ships/{ship_id}/leeches — active leech debuffs on a ship."""
        return self._request("GET", f"/api/ships/{ship_id}/leeches")

    # ------------------------------------------------------------------
    # Matches (Phase 8)
    # ------------------------------------------------------------------

    def create_match(self, name: str, faction: str) -> dict:
        """POST /api/matches — create a new match."""
        return self._request("POST", "/api/matches", json_body={"name": name, "faction": faction})

    def list_matches(self, status: Optional[str] = None) -> list:
        """GET /api/matches — list matches."""
        params: dict = {}
        if status is not None:
            params["status_filter"] = status
        return self._request("GET", "/api/matches", params=params)

    def get_match(self, match_id: int) -> dict:
        """GET /api/matches/{match_id} — match details."""
        return self._request("GET", f"/api/matches/{match_id}")

    def join_match(self, match_id: int, faction: str) -> dict:
        """POST /api/matches/{match_id}/join — join as team2."""
        return self._request("POST", f"/api/matches/{match_id}/join", json_body={"faction": faction})

    def start_match(self, match_id: int) -> dict:
        """Start a match (command)."""
        return self.send_command("start_match", match_id=match_id)

    def surrender_match(self, match_id: int) -> dict:
        """Cast a surrender vote (command)."""
        return self.send_command("surrender", match_id=match_id)

    # ------------------------------------------------------------------
    # Commands & View (Intent-based CQS)
    # ------------------------------------------------------------------

    def send_command(self, command_type: str, ship_id: Optional[int] = None, **payload) -> dict:
        """POST /api/commands — enqueue a command for tick-loop processing."""
        body: dict = {"type": command_type, "payload": payload}
        if ship_id is not None:
            body["ship_id"] = ship_id
        return self._request("POST", "/api/commands", json_body=body)

    def get_view(self, ship_id: Optional[int] = None, since_tick: Optional[int] = None) -> dict:
        """GET /api/view — player's complete world state snapshot."""
        params: dict = {}
        if ship_id is not None:
            params["ship_id"] = ship_id
        if since_tick is not None:
            params["since_tick"] = since_tick
        return self._request("GET", "/api/view", params=params)

    def list_commands(self, status: Optional[str] = None, limit: int = 50) -> list:
        """GET /api/commands — list player's commands."""
        params: dict = {"limit": limit}
        if status is not None:
            params["status"] = status
        return self._request("GET", "/api/commands", params=params)



# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------


class SpaceGameError(Exception):
    """Raised when the server returns an error response."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_detail(response: httpx.Response) -> str:
    """Pull a human-readable error message from an httpx response."""
    try:
        data = response.json()
        if isinstance(data, dict):
            return str(data.get("detail", response.text))
    except Exception:
        pass
    return response.text or f"HTTP {response.status_code}"
