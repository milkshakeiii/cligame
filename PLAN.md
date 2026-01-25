# Space Simulation Engine - Implementation Plan

## Overview
Add a tick-based 3D space simulation with velocity physics and background processing. Users can command ships to approach, orbit, or keep distance from targets.

## Models (`backend/api/models.py`)

**GameState** - Singleton tracking current tick, running state, tick interval

**Spaceship** - Player ships with:
- Position (pos_x, pos_y, pos_z)
- Velocity (vel_x, vel_y, vel_z)
- Characteristics (max_acceleration, max_speed)
- Owner (ForeignKey to User)

**MovementOrder** - Commands for ships:
- Types: approach, orbit, keep_distance, stop
- Target: another ship, celestial object, or point (x,y,z)
- Parameters: desired_distance, approach_speed

**CelestialObject** - Static/slow-moving points of interest (planets, stations, waypoints)

## Physics Engine (`backend/api/physics.py`)

Vector math utilities plus three movement behaviors:

1. **Approach**: Accelerate toward target, auto-decelerate to arrive at rest (or desired speed)
2. **Orbit**: Maintain circular orbit at specified radius using radial + tangential corrections
3. **Keep Distance**: Stay at specified range, matching target velocity when in position

Integration: Simple Euler (v += a*dt, p += v*dt) with speed clamping

## Tick System

**Stack**: Celery + Redis + django-celery-beat

**New dependencies**:
```
celery[redis]>=5.3.0
django-celery-beat>=2.5.0
redis>=4.5.0
```

**Tick task** (`backend/api/tasks.py`):
1. Increment tick counter
2. For each active ship: get active order, calculate acceleration, apply physics, update DB
3. Mark completed orders

**Default**: 1-second tick interval

## API Endpoints (`backend/api/urls.py`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/game/status/` | GET | Current tick, running state |
| `/api/ships/` | GET | List user's ships |
| `/api/ships/create/` | POST | Create new ship |
| `/api/ships/<id>/` | GET | Ship detail + active orders |
| `/api/ships/<id>/orders/create/` | POST | Create movement order |
| `/api/ships/<id>/orders/<id>/cancel/` | POST | Cancel order |
| `/api/nearby/` | GET | Query nearby ships/objects |
| `/api/objects/` | GET | List celestial objects |

## CLI Commands (`frontend/src/spacegame/cli.py`)

```
spacegame status                    # Game state + your ships
spacegame ship list                 # List your ships
spacegame ship create <name>        # Create ship
spacegame ship status <id>          # Ship detail

spacegame order approach <ship_id> --point X Y Z
spacegame order approach <ship_id> --target-ship <id>
spacegame order orbit <ship_id> --target-object <id> --radius 50
spacegame order keep-distance <ship_id> --target-ship <id> --distance 100
spacegame order stop <ship_id>
spacegame order cancel <ship_id> <order_id>

spacegame scan --ship <id> --radius 1000
```

## Files to Create/Modify

**Backend (create)**:
- `backend/api/physics.py` - Vector math + movement algorithms
- `backend/api/tasks.py` - Celery tick task
- `backend/config/celery.py` - Celery app config

**Backend (modify)**:
- `backend/api/models.py` - Add 4 models
- `backend/api/views.py` - Add endpoints
- `backend/api/serializers.py` - Add serializers
- `backend/api/urls.py` - Add routes
- `backend/api/admin.py` - Register models
- `backend/config/settings.py` - Add Celery config
- `backend/config/__init__.py` - Load Celery
- `backend/requirements.txt` - Add dependencies

**Frontend (modify)**:
- `frontend/src/spacegame/cli.py` - Add commands
- `frontend/src/spacegame/api.py` - Add API methods

## Implementation Order

1. Models + migrations
2. Physics engine
3. Serializers + views + URLs
4. Celery setup + tick task
5. CLI commands + API client
6. Admin registration + seed data

## Verification

1. Run migrations: `python manage.py makemigrations && python manage.py migrate`
2. Start Redis: `redis-server`
3. Start Celery worker: `celery -A config worker -l info`
4. Start Celery beat: `celery -A config beat -l info`
5. Start Django: `python manage.py runserver`
6. Test flow:
   ```
   spacegame login testuser
   export SPACEGAME_TOKEN=<token>
   spacegame ship create "Explorer"
   spacegame order approach 1 --point 100 0 0
   spacegame ship status 1  # Watch position change over ticks
   ```
