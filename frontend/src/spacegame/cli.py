"""Main CLI entry point for spacegame."""

import json
import os
import sys

import click

from .api import SpacegameAPI, APIError


def get_api() -> SpacegameAPI:
    """Get API client."""
    return SpacegameAPI()


def output(data: dict, as_json: bool):
    """Output data as JSON or human-readable."""
    if as_json:
        print(json.dumps(data, indent=2))
    else:
        for key, value in data.items():
            print(f"{key}: {value}")


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Spacegame CLI - a space simulation."""
    pass


@cli.command()
@click.argument("username")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def login(username: str, as_json: bool):
    """Login with a username (creates account if new)."""
    api = get_api()
    try:
        result = api.login(username)
        if as_json:
            output(result, as_json=True)
        else:
            print(f"Logged in as: {result['username']}")
            print(f"Token: {result['token']}")
            print()
            print("Set this environment variable to use other commands:")
            print(f"  export SPACEGAME_TOKEN={result['token']}")
    except APIError as e:
        if as_json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def status(as_json: bool):
    """Show current game status."""
    api = get_api()
    if not api.token:
        msg = "SPACEGAME_TOKEN not set. Run 'spacegame login <username>' first."
        if as_json:
            print(json.dumps({"error": msg}))
        else:
            print(f"Error: {msg}", file=sys.stderr)
        sys.exit(1)

    # Placeholder - will add actual status endpoint later
    if as_json:
        print(json.dumps({"status": "ok", "message": "Status endpoint not yet implemented"}))
    else:
        print("Status: OK")
        print("(Status endpoint not yet implemented)")


def main():
    """Main entry point."""
    try:
        cli()
    except APIError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
