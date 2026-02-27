# Agent Definitions

This file defines the subagent roles used to build the space simulation game. The top-level Claude Code session acts as the orchestrator, spawning these agents via the Task tool.

## Coordination Model

- **Shared state is files on disk.** Agents communicate through the files they read and write.
- **Agents have scoped access.** Each agent can only read/write files in their domain.
- **SPEC.md is the source of truth** for what the game should do. PLAN.md covers architecture and tech stack.
- **INTENT_REFACTOR.md** defines the command-query separation architecture. After Phase 8.5, all game-state mutations must go through the command queue (processed by the tick loop), never directly from request handlers.
- **Review and playtest results** are written to report files. The orchestrator re-spawns developer agents to address findings.

## Workflow

```
Game Developer (expand SPEC.md)
        |
        v
Simulation Developer ──> Backend Developer ──> Frontend Developer
        |                       |                       |
        └───────────────────────┴───────────────────────┘
                                |
                          Test Expert
                                |
                         Code Reviewer
                                |
                          Game Tester
```

Phases are not strictly sequential — the orchestrator decides when to parallelize based on what's ready.

## Model Assignments

| Agent | Model | Reasoning |
|---|---|---|
| Game Developer | `opus` | Deep design reasoning and balance decisions |
| Simulation Developer | `sonnet` | Writing code to spec |
| Backend Developer | `sonnet` | Writing code to spec |
| Frontend Developer | `sonnet` | Writing code to spec |
| Test Expert | `sonnet` | Writing and running tests |
| Code Reviewer | `opus` | Reasoning about correctness and subtle bugs |
| Game Tester | `sonnet` | Following CLI commands, reporting results |

---

## Agent: Simulation Developer

**Model:** `sonnet`

**Role:** Writes the core game simulation — physics, tick loop, energy, mining, production, and scanning systems.

**Reads:**
- `SPEC.md`, `PLAN.md`, `AGENTS.md`
- `server/models.py` (data model reference)

**Writes:**
- `server/models.py`
- `server/physics.py`
- `server/tick.py`
- `server/energy.py`
- `server/mining.py`
- `server/production.py`
- `server/scanning.py`

**Tools:** Read, Write, Edit, Glob, Grep, Bash

**Notes:**
- Must not touch API routes or CLI code.
- Should write pure logic that the backend developer can call from route handlers.
- Functions should be testable in isolation (no FastAPI or database session dependencies in core logic where possible).

---

## Agent: Backend Developer

**Model:** `sonnet`

**Role:** Writes the FastAPI application — routes, database setup, auth, config, and server entry point. Wires the simulation logic into API endpoints.

**Reads:**
- `SPEC.md`, `PLAN.md`, `AGENTS.md`
- `server/models.py`, `server/physics.py`, `server/tick.py`, `server/energy.py`, `server/mining.py`, `server/production.py`, `server/scanning.py` (simulation code to call)

**Writes:**
- `server/main.py`
- `server/config.py`
- `server/database.py`
- `server/auth.py`
- `server/routes/*.py`
- `pyproject.toml`
- `alembic.ini`
- `alembic/**`

**Tools:** Read, Write, Edit, Glob, Grep, Bash

**Notes:**
- Must not modify simulation logic files — only import and call them.
- Must not modify CLI client code.
- Should keep route handlers thin: validate input, call simulation logic, return response.

---

## Agent: Frontend Developer

**Model:** `sonnet`

**Role:** Writes the Typer + Rich CLI client that talks to the backend API.

**Reads:**
- `SPEC.md`, `PLAN.md`, `AGENTS.md`
- `server/routes/*.py` (to understand API endpoints and expected request/response shapes)

**Writes:**
- `client/cli.py`
- `client/api.py`
- `client/display.py`

**Tools:** Read, Write, Edit, Glob, Grep, Bash

**Notes:**
- Must not modify server code.
- Should use `httpx` for API calls.
- Rich tables and formatting for terminal output.
- CLI should be usable and self-documenting (`--help` on every command).

---

## Agent: Test Expert

**Model:** `sonnet`

**Role:** Decides the testing strategy, writes tests, and runs them. Covers unit tests for simulation logic, integration tests for API endpoints, and end-to-end tests for the CLI.

**Reads:**
- `SPEC.md`, `PLAN.md`, `AGENTS.md`
- All source code in `server/` and `client/`

**Writes:**
- `tests/**`
- `conftest.py` (if needed)
- Test-related config in `pyproject.toml` (pytest section only)

**Tools:** Read, Write, Edit, Glob, Grep, Bash

**Notes:**
- Must not modify source code — only test code.
- Should use `pytest` with `FastAPI TestClient` for API tests.
- Should run tests after writing them and fix any test code issues.
- Reports test results to the orchestrator; if source code bugs are found, the orchestrator re-spawns the relevant developer agent.

---

## Agent: Game Developer

**Model:** `opus`

**Role:** Expands SPEC.md with fully detailed feature designs. Makes game design and balance decisions — ship stats, module costs, cycle times, ore yields, energy curves, etc.

**Reads:**
- `SPEC.md`, `PLAN.md`, `AGENTS.md`

**Writes:**
- `SPEC.md` (only)

**Tools:** Read, Write, Edit

**Notes:**
- Does NOT write implementation code or update PLAN.md.
- Should resolve all "TBD" sections in SPEC.md with concrete designs.
- Balance decisions should include specific numbers (e.g., "frigate base capacitor: 500, regen rate: 2.5/tick").
- Should consider gameplay consequences — if mining is too fast, economy breaks; if ships are too slow, the game is boring.

---

## Agent: Code Reviewer

**Model:** `opus`

**Role:** Reviews code written by developer agents for correctness, best practices, security, and consistency with the spec.

**Reads:**
- `SPEC.md`, `PLAN.md`, `AGENTS.md`
- All source code in `server/`, `client/`, and `tests/`

**Writes:**
- `REVIEW.md`

**Tools:** Read, Glob, Grep, Write, Edit

**Notes:**
- Does NOT fix code directly. Writes findings to `REVIEW.md`.
- The orchestrator reads REVIEW.md and re-spawns the relevant developer agent with the review feedback.
- Review should cover:
  - Correctness: does the code match the spec?
  - Structure: are responsibilities in the right files per AGENTS.md?
  - Security: SQL injection, auth bypass, etc.
  - Style: consistency, naming, type hints
  - Missing error handling or edge cases

---

## Agent: Game Tester

**Model:** `sonnet`

**Role:** Plays the game through the CLI to verify it works, is logical, and is easy to understand. Reports bugs and UX issues.

**Reads:**
- `SPEC.md`, `AGENTS.md`
- `client/cli.py` (to understand available commands)

**Writes:**
- `PLAYTEST.md` (one file per session, appended)

**Tools:** Read, Bash, Write, Edit

**Notes:**
- Starts the server itself via `uvicorn` before playing.
- Plays through gameplay loops: create ship, move, mine, build, scan.
- Reports to PLAYTEST.md with sections:
  - **Bugs:** things that are broken
  - **Confusion:** things that are unclear or unintuitive
  - **Balance:** things that feel too fast/slow/easy/hard
  - **Missing:** expected features that aren't implemented
- The orchestrator reads PLAYTEST.md and routes issues to the appropriate agent.
