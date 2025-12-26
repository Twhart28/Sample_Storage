# Freezer Sample Tracker (MVP)

A minimal LabKey-inspired sample tracking and freezer management web app built with FastAPI, SQLAlchemy, SQLite, Jinja2, and HTMX.

## Features
- Register samples and sample types
- Model freezer hierarchy (Freezer → Shelf → Rack → Box)
- Auto-generate box positions
- Place/move samples with audit events
- Search/filter/sort samples
- Immutable event feed

## Tech Stack
- Python 3.12+
- FastAPI
- SQLAlchemy 2.x
- SQLite (default)
- Jinja2 templates + HTMX
- Alembic migrations
- Pydantic models

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn itsdangerous sqlalchemy alembic jinja2 python-multipart
```

## Initialize the Database
```bash
alembic upgrade head
```

## Run the App
```bash
uvicorn app.main:app --reload
```

Open `http://localhost:8000`.

## Seed Demo Storage
- Visit `/login` and click **Seed demo storage**, or
- `POST /admin/seed` after logging in.

## Project Layout
```
app/
  main.py
  db.py
  models.py
  schemas.py
  crud.py
  routes/
    auth.py
    samples.py
    storage.py
    events.py
  templates/
  static/

alembic/
  versions/
```

## Notes
- Events are append-only; no delete routes are provided.
- Sample placement enforces one sample per position and one location per sample.