# CLAUDE.md

## Project Structure
- `backend/` - Django backend
- `frontend/` - Click-based CLI frontend
- `requirements.txt` - Python dependencies

## Setup (run once)
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd backend && python manage.py migrate
```

## Running the Server
```bash
source venv/bin/activate
cd backend && python manage.py runserver
```

## Running the CLI
```bash
source venv/bin/activate
cd frontend/src && python -m spacegame.cli --help
```

## Backend Guidelines
- Non-RESTful web API
- All views are POST endpoints
- Document each view with expected arguments and return values
