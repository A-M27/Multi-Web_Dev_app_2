from fastapi import FastAPI, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
from contextlib import asynccontextmanager
from .db.session import create_db_and_tables, get_session
from sqlmodel import SQLModel, Field, Relationship, select, Session
import random
from pathlib import Path
from datetime import datetime

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
    scores: List["Score"] = Relationship(back_populates="set")

class Card(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    front: str
    back: str
    set_id: int | None = Field(default=None, foreign_key="set.id")
    set: Optional[Set] = Relationship(back_populates="cards")

class Score(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int
    set_id: int = Field(foreign_key="set.id")
    score: int
    date: str  # Store as string (e.g., YYYY-MM-DD)
    set: Optional[Set] = Relationship(back_populates="scores")

# Initialize data
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
    return templates.TemplateResponse(
            request=request,
            name="card.html",
            context={"card": Card(front="", back="", set_id=0)}
        )

@app.post("/card/add", response_model=None)
async def add_card(card: Card, session: Session = Depends(get_session)):
    db_card = Card.model_validate(card)
    session.add(db_card)
    session.commit()
    session.refresh(db_card)
    return db_card

@app.get("/cards/{card_id}/edit", response_class=HTMLResponse)
async def edit_card(request: Request, card_id: int, session: Session = Depends(get_session)):
    card = session.exec(select(Card).where(Card.id == card_id)).first()
    if not card:
        return HTMLResponse(content="Card not found", status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="card_edit.html",
        context={"card": card}
    )

@app.post("/cards/{card_id}/edit")
async def update_card(card_id: int, front: str = Form(...), back: str = Form(...), set_id: Optional[int] = Form(None), session: Session = Depends(get_session)):
    card = session.exec(select(Card).where(Card.id == card_id)).first()
    if not card:
        return HTMLResponse(content="Card not found", status_code=404)
    card.front = front
    card.back = back
    card.set_id = set_id
    session.commit()
    session.refresh(card)
    return templates.TemplateResponse(
        request=None,  # Redirect without request context
        name="card.html",
        context={"card": card}
    )

@app.get("/card/manage", response_class=HTMLResponse)
async def manage_card(request: Request, session: Session = Depends(get_session), card_id: Optional[int] = None):
    card = session.exec(select(Card).where(Card.id == card_id)).first() if card_id else None
    cards = session.exec(select(Card)).all()
    return templates.TemplateResponse(
        request=request,
        name="card_manage.html",
        context={"card": card, "cards": cards}
    )

@app.post("/card/manage")
async def process_card_manage(action: str = Form(...), card_id: Optional[int] = Form(None), front: str = Form(...), back: str = Form(...), set_id: Optional[int] = Form(None), session: Session = Depends(get_session)):
    if action == "add":
        new_card = Card(front=front, back=back, set_id=set_id)
        session.add(new_card)
        session.commit()
        session.refresh(new_card)
        return templates.TemplateResponse(
            request=None,
            name="card.html",
            context={"card": new_card}
        )
    elif action == "edit" and card_id:
        card = session.exec(select(Card).where(Card.id == card_id)).first()
        if card:
            card.front = front
            card.back = back
            card.set_id = set_id
            session.commit()
            session.refresh(card)
            return templates.TemplateResponse(
                request=None,
                name="card.html",
                context={"card": card}
            )
    return HTMLResponse(content="Invalid action or card not found", status_code=400)

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

@app.get("/users/{user_id}", response_class=HTMLResponse)
async def get_user_dashboard(request: Request, user_id: int, session: Session = Depends(get_session)):
    user = next((u for u in user_list if u.id == user_id), None)
    if not user:
        return HTMLResponse(content="User not found", status_code=404)
    sets = session.exec(select(Set).where(Set.user_id == user_id)).all()
    scores = session.exec(select(Score).where(Score.user_id == user_id)).all()
    return templates.TemplateResponse(
        request=request,
        name="user_dashboard.html",
        context={"user": user, "sets": sets, "scores": scores}
    )

@app.get("/quiz", response_class=HTMLResponse)
async def start_quiz(request: Request, session: Session = Depends(get_session), set_id: Optional[int] = None):
    cards = session.exec(select(Card).all()).all() if set_id is None else session.exec(select(Card).where(Card.set_id == set_id)).all()
    if not cards:
        return HTMLResponse(content="No cards available for quiz", status_code=404)
    selected_cards = random.sample(cards, min(5, len(cards)))  # Limit to 5 cards
    return templates.TemplateResponse(
        request=request,
        name="quiz.html",
        context={"cards": selected_cards, "set_id": set_id}
    )

@app.post("/quiz/submit")
async def submit_quiz(request: Request, session: Session = Depends(get_session)):
    form_data = await request.form()
    user_id = int(form_data.get("user_id", 0))
    set_id = int(form_data.get("set_id", 0))
    score = 0
    total = 0
    for key, value in form_data.items():
        if key.startswith("answer_"):
            card_id = int(key.split("_")[1])
            card = session.exec(select(Card).where(Card.id == card_id)).first()
            if card and value.strip().lower() == card.back.strip().lower():
                score += 1
            total += 1
    if total > 0:
        new_score = Score(user_id=user_id, set_id=set_id, score=(score / total) * 100, date=datetime.now().strftime("%Y-%m-%d"))
        session.add(new_score)
        session.commit()
    return templates.TemplateResponse(
        request=request,
        name="quiz_result.html",
        context={"score": score, "total": total, "percentage": (score / total) * 100 if total > 0 else 0}
    )

@app.get("/scores", response_class=HTMLResponse)
async def get_scores(request: Request, session: Session = Depends(get_session)):
    scores = session.exec(select(Score).order_by(Score.date.desc())).all()
    return templates.TemplateResponse(
        request=request,
        name="scores.html",
        context={"scores": scores}
    )
