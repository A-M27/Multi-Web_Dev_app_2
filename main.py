from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.templating import Jinja2Templates
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional, List
from datetime import datetime
from contextlib import asynccontextmanager
from .db.session import create_db_and_tables, SessionDep
import json
import random



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the DB
    create_db_and_tables(lifespan=lifespan)
    yield


# Start the app
#Modify our FastAPI app
app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# List of 5 grocery items
grocery_items = ["apples", "bread", "milk", "eggs", "cheese"]


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



class Set(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str    
    cards: list["Card"] = Relationship(back_populates="set")

class Card(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    front: str
    back: str
    set_id: int | None = Field(default=None, foreign_key="set.id")
    set: Set | None = Relationship(back_populates="cards")



# Initialize data
user_list = [
    User(id=1, name="Alice Smith", email="alice@example.com", sets=[1]),
    User(id=2, name="Bob Johnson", email="bob@example.com", sets=[2])
]

set_list = [
    Set(id=1, name="Geography", user_id=1),
    Set(id=2, name="Literature", user_id=2)
]

card_list = [
    Card(id=1, question="Where is Taylor located?", answer="Upland, IN", set_id=1),
    Card(id=2, question="What is the capital of Indiana?", answer="Indianapolis, IN", set_id=1),
    Card(id=3, question="What is the capital of France?", answer="Paris", set_id=1),
    Card(id=4, question="Who wrote Romeo and Juliet?", answer="William Shakespeare", set_id=2),
    Card(id=5, question="What is the chemical symbol for water?", answer="H2O", set_id=2)
]

deck_list = [
    Deck(id=1, name="Alice's Study Deck", user_id=1, card_ids=[1, 3, 4]),
    Deck(id=2, name="Bob's Quiz Deck", user_id=2, card_ids=[2, 5])
]

# Define routes
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"cards": card_list}
    )

@app.get("/items")
async def get_items():
    return {"items": grocery_items}

@app.get("/cards")
async def get_cards(q: Optional[str] = None):
    if q:
        search_results = [card for card in card_list if q.lower() in card.question.lower()]
        return search_results
    return card_list

@app.get("/cards/{card_id}", response_class=HTMLResponse, name="get_card")
async def get_card_by_id(request: Request, card_id: int):
    for card in card_list:
        if card.id == card_id:
            return templates.TemplateResponse(
                request=request,
                name="card.html",
                context={"card": card}
            )
    return HTMLResponse(content="Card not found", status_code=404)

@app.post("/card/add")
async def add_card(card: Card):
    card_list.append(card)
    return card_list

@app.get("/play", response_class=HTMLResponse)
async def play(request: Request):
    random_card = card_list[random.randint(0, len(card_list)-1)]
    return templates.TemplateResponse(
        request=request,
        name="play.html",
        context={"card": random_card}
    )

@app.get("/sets", response_class=HTMLResponse)
async def get_sets(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="sets.html",
        context={"sets": set_list}
    )

@app.get("/users", response_class=HTMLResponse)
async def get_users(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="users.html",
        context={"users": user_list}
    )
