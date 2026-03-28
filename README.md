# Freezer Sample Tracker

A search-first internal sample tracking and freezer workflow app built with FastAPI, SQLAlchemy, SQLite, Jinja2, and Alembic.

## Current Focus
- Register and update samples with typed metadata and custom-field JSON
- Search samples by identifier, status, type, and placement state
- Place, move, retrieve, and archive samples with append-only event history
- Browse storage as supporting context rather than the primary workflow
- Expose matching HTML and `/api` endpoints for the core operations
- Support simple `staff` and `admin` roles for internal use

## Tech Stack
- Python 3.12+
- FastAPI
- SQLAlchemy 2.x
- SQLite for local development
- Jinja2 templates
- Alembic migrations
- Pydantic models

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn itsdangerous sqlalchemy alembic jinja2 python-multipart httpx openpyxl
```

## Initialize the Database
```bash
alembic upgrade head
```

## Run the App
```bash
uvicorn app.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000).

## Access and Seeding
- Visit `/login`
- Choose `staff` or `admin`
- Admin users can open `/admin/configuration` to create sample types or seed demo storage

## Project Layout
```text
app/
  api/
    routes/
  domain/
  repositories/
  services/
  web/
    routes/
  db.py
  main.py
  models.py
  schemas.py
  static/
  templates/

alembic/
  versions/

tests/
```

## Notes
- `app/models.py` is now a compatibility export of `app/domain/models.py`
- HTML routes live under `app/web/routes`, JSON routes under `app/api/routes`
- Events remain append-only; retrieval and archival are recorded as status transitions
- Local tests use temporary SQLite databases rather than the checked-in `freezer.db`
- Bulk sample import supports an Excel template with header comments and `.xlsx` upload
