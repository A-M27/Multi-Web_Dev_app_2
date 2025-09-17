from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
from contextlib import asynccontextmanager
from db.session import create_db_and_tables, get_session
from sqlmodel import SQLModel, Field, Relationship, select, Session
import random
from pathlib import Path

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the database
    create_db_and_tables()
    yield

# Start the app
app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

# List of 5 grocery items (kept for compatibility)
grocery_items = ["apples", "bread", "milk", "eggs", "cheese"]

# Pydantic models
class User(BaseModel):
    id: int
    name: str
    email: str
    sets: List[int] = []

class Deck(BaseModel):
    id: int
    name: str
    user_id: int
    card_ids: List[int]

# SQLModel models
class Set(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    user_id: int
    cards: List["Card"] = Relationship(back_populates="set")

class Card(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    front: str
    back: str
    set_id: int | None = Field(default=None, foreign_key="set.id")
    set: Optional[Set] = Relationship(back_populates="cards")

# Initialize data (for testing, can be removed after database is populated)
user_list = [
    User(id=1, name="Alice Smith", email="alice@example.com", sets=[1]),
    User(id=2, name="Bob Johnson", email="bob@example.com", sets=[2])
]

deck_list = [
    Deck(id=1, name="Alice's Study Deck", user_id=1, card_ids=[1, 3, 4]),
    Deck(id=2, name="Bob's Quiz Deck", user_id=2, card_ids=[2, 5])
]

# Routes
@app.get("/", response_class=HTMLResponse, response_model=None)
async def root(request: Request, session: Session = Depends(get_session)):
    cards = session.exec(select(Card)).all()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"cards": cards}
    )

@app.get("/items")
async def get_items():
    return {"items": grocery_items}

@app.get("/cards", response_class=HTMLResponse, response_model=None)
async def get_cards(request: Request, session: Session = Depends(get_session), q: Optional[str] = None):
    if q:
        cards = session.exec(select(Card).where(Card.front.ilike(f"%{q}%"))).all()
    else:
        cards = session.exec(select(Card)).all()
    return templates.TemplateResponse(
        request=request,
        name="card.html",
        context={"cards": cards}
    )

@app.get("/cards/{card_id}", response_class=HTMLResponse, name="get_card", response_model=None)
async def get_card_by_id(request: Request, card_id: int, session: Session = Depends(get_session)):
    card = session.exec(select(Card).where(Card.id == card_id)).first()
    if card:
        return templates.TemplateResponse(
            request=request,
            name="card.html",
            context={"card": card}
        )
    return HTMLResponse(content="Card not found", status_code=404)

@app.post("/card/add", response_model=None)
async def add_card(card: Card, session: Session = Depends(get_session)):
    db_card = Card.model_validate(card)
    session.add(db_card)
    session.commit()
    session.refresh(db_card)
    return db_card

@app.get("/play", response_class=HTMLResponse, response_model=None)
async def play(request: Request, session: Session = Depends(get_session)):
    cards = session.exec(select(Card)).all()
    if cards:
        random_card = random.choice(cards)
        return templates.TemplateResponse(
            request=request,
            name="play.html",
            context={"card": random_card}
        )
    return HTMLResponse(content="No cards available", status_code=404)

@app.get("/sets", response_class=HTMLResponse, response_model=None)
async def get_sets(request: Request, session: Session = Depends(get_session)):
    sets = session.exec(select(Set).order_by(Set.name)).all()
    return templates.TemplateResponse(
        request=request,
        name="sets.html",
        context={"sets": sets}
    )

@app.post("/sets/add", response_model=None)
async def create_set(set: Set, session: Session = Depends(get_session)):
    db_set = Set.model_validate(set)
    session.add(db_set)
    session.commit()
    session.refresh(db_set)
    return db_set

@app.get("/sets/{set_id}", response_class=HTMLResponse, response_model=None)
async def get_set_by_id(request: Request, set_id: int, session: Session = Depends(get_session)):
    set = session.exec(select(Set).where(Set.id == set_id)).first()
    if set:
        cards = session.exec(select(Card).where(Card.set_id == set_id)).all()
        return templates.TemplateResponse(
            request=request,
            name="set_detail.html",
            context={"set": set, "cards": cards}
        )
    return HTMLResponse(content="Set not found", status_code=404)

@app.get("/users", response_class=HTMLResponse)
async def get_users(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="users.html",
        context={"users": user_list}
    )
