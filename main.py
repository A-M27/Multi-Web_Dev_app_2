from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
from .db.session import create_db_and_tables, engine # Changed to absolute import
from .routes.cards import router as cards_router       # Changed to absolute import
from .routes.sets import router as sets_router         # Changed to absolute import
from .routes.users import router as users_router       # Changed to absolute import
from .routes.home_route import router as home_router   # Changed to absolute import
from .db.models import User
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional, List
from pathlib import Path

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    # Seed an admin user if none exists
    with Session(engine) as session:
        # This will now correctly use the imported SQLModel User
        admin = session.exec(select(User).where(User.is_admin == True)).first()
        if not admin:
            # Note: In a real app, you'd want to hash a password here
            admin = User(username="admin", is_admin=True)
            session.add(admin)
            session.commit()
    yield

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

@app.exception_handler(404)
async def not_found_exception_handler(request: Request, exc: HTTPException):
    return templates.TemplateResponse(
        "error_codes/404.html",
        {"request": request, "status_code": 404},
        status_code=404
    )

@app.exception_handler(400)
async def bad_request_exception_handler(request: Request, exc: HTTPException):
    return templates.TemplateResponse(
        "error_codes/400.html",
        {"request": request, "status_code": 400},
        status_code=400
    )

@app.exception_handler(500)
async def internal_server_error_handler(request: Request, exc: Exception):
    return templates.TemplateResponse(
        "error_codes/500.html",
        {"request": request, "status_code": 500},
        status_code=500
    )

# Renamed to UserSchema to avoid shadowing the SQLModel User class
class UserSchema(BaseModel):
    id: int
    username: str
    is_admin: bool = False
    sets: List[int] = []

class Deck(BaseModel):
    id: int
    name: str
    user_id: int
    card_ids: List[int]

app.include_router(cards_router)
app.include_router(sets_router)
app.include_router(users_router)
app.include_router(home_router)
