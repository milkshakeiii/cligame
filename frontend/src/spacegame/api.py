"""API client for spacegame backend."""

import os
import sys

import requests


class APIError(Exception):
    """Raised when API returns an error."""
    pass


class SpacegameAPI:
    """Client for the spacegame API."""

    def __init__(self, base_url: str = None, token: str = None):
        self.base_url = base_url or os.environ.get("SPACEGAME_URL", "http://localhost:8000/api/")
        self.token = token or os.environ.get("SPACEGAME_TOKEN")

    def _post(self, endpoint: str, data: dict = None) -> dict:
        """Make a POST request to the API."""
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}

        if self.token:
            headers["Authorization"] = f"Token {self.token}"

        try:
            response = requests.post(url, json=data or {}, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError:
            try:
                error_data = response.json()
                error_msg = error_data.get("error", str(response.status_code))
            except Exception:
                error_msg = f"HTTP {response.status_code}"
            raise APIError(error_msg)
        except requests.exceptions.ConnectionError:
            raise APIError(f"Could not connect to API at {self.base_url}")

    def login(self, username: str) -> dict:
        """Login and get auth token."""
        return self._post("login/", {"username": username})
