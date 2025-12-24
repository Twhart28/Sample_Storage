from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.routes import auth, events, samples, storage

app = FastAPI(title="Freezer Sample Tracker")

app.add_middleware(SessionMiddleware, secret_key="dev-secret-key")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(samples.router)
app.include_router(storage.router)
app.include_router(events.router)


@app.get("/")
async def root():
    return RedirectResponse("/dashboard")
