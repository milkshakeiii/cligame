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
    """Return the stored token, or None if the file doesn't exist."""
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

    def create_ship(self, name: str, ship_class: str) -> dict:
        """POST /api/ships"""
        return self._request(
            "POST", "/api/ships", json_body={"name": name, "ship_class": ship_class}
        )

    def get_ship(self, ship_id: int) -> dict:
        """GET /api/ships/{ship_id}"""
        return self._request("GET", f"/api/ships/{ship_id}")

    def list_modules(self, ship_id: int) -> list:
        """GET /api/ships/{ship_id}/modules"""
        return self._request("GET", f"/api/ships/{ship_id}/modules")

    def install_module(self, ship_id: int, module_type: str, volume: int = 0) -> dict:
        """POST /api/ships/{ship_id}/modules"""
        return self._request(
            "POST",
            f"/api/ships/{ship_id}/modules",
            json_body={"module_type": module_type, "volume": volume},
        )

    def uninstall_module(self, ship_id: int, module_id: int) -> None:
        """DELETE /api/ships/{ship_id}/modules/{module_id}"""
        self._request("DELETE", f"/api/ships/{ship_id}/modules/{module_id}")

    def activate_module(self, ship_id: int, module_id: int) -> dict:
        """POST /api/ships/{ship_id}/modules/{module_id}/activate"""
        return self._request("POST", f"/api/ships/{ship_id}/modules/{module_id}/activate")

    def deactivate_module(self, ship_id: int, module_id: int) -> dict:
        """POST /api/ships/{ship_id}/modules/{module_id}/deactivate"""
        return self._request("POST", f"/api/ships/{ship_id}/modules/{module_id}/deactivate")

    # ------------------------------------------------------------------
    # Movement orders
    # ------------------------------------------------------------------

    def create_order(self, ship_id: int, payload: dict) -> dict:
        """POST /api/ships/{ship_id}/orders"""
        return self._request("POST", f"/api/ships/{ship_id}/orders", json_body=payload)

    def cancel_order(self, ship_id: int, order_id: int) -> dict:
        """POST /api/ships/{ship_id}/orders/{order_id}/cancel"""
        return self._request("POST", f"/api/ships/{ship_id}/orders/{order_id}/cancel")

    def dock_ship(self, ship_id: int, target_ship_id: int) -> dict:
        """POST /api/ships/{ship_id}/dock"""
        return self._request(
            "POST",
            f"/api/ships/{ship_id}/dock",
            json_body={"target_ship_id": target_ship_id},
        )

    # ------------------------------------------------------------------
    # Mining & resources
    # ------------------------------------------------------------------

    def transfer_ore(self, ship_id: int, target_ship_id: int) -> dict:
        """POST /api/ships/{ship_id}/transfer"""
        return self._request(
            "POST",
            f"/api/ships/{ship_id}/transfer",
            json_body={"target_ship_id": target_ship_id},
        )

    # ------------------------------------------------------------------
    # Production
    # ------------------------------------------------------------------

    def queue_build(
        self,
        ship_id: int,
        blueprint: str,
        factory_module_id: Optional[int] = None,
    ) -> dict:
        """POST /api/ships/{ship_id}/build"""
        body: dict = {"blueprint": blueprint}
        if factory_module_id is not None:
            body["factory_module_id"] = factory_module_id
        return self._request("POST", f"/api/ships/{ship_id}/build", json_body=body)

    def get_build_queue(self, ship_id: int) -> dict:
        """GET /api/ships/{ship_id}/build"""
        return self._request("GET", f"/api/ships/{ship_id}/build")

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def scan(self, ship_id: int) -> dict:
        """POST /api/ships/{ship_id}/scan"""
        return self._request("POST", f"/api/ships/{ship_id}/scan")

    def nearby(self, ship_id: int) -> list:
        """GET /api/nearby?ship_id={ship_id}"""
        return self._request("GET", "/api/nearby", params={"ship_id": ship_id})

    def subscribe_alerts(
        self,
        ship_id: int,
        min_range_km: Optional[float] = None,
        event_types: Optional[list[str]] = None,
    ) -> dict:
        """POST /api/alerts"""
        body: dict = {"ship_id": ship_id}
        if min_range_km is not None:
            body["min_range_km"] = min_range_km
        if event_types is not None:
            body["event_types"] = event_types
        return self._request("POST", "/api/alerts", json_body=body)


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
