from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
from .db.session import create_db_and_tables, engine
from .routes.cards import router as cards_router
from .routes.sets import router as sets_router
from .routes.users import router as users_router
from .routes.home_route import router as home_router
# Assume 'scores' router exists in 'routes/scores.py' and needs to be imported:
from .routes.scores import router as scores_router # ADD THIS IMPORT
from .db.models import User, Set, Card
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional, List
from pathlib import Path

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    with Session(engine) as session:
        admin = session.exec(select(User).where(User.is_admin == True)).first()
        if not admin:
            admin = User(username="admin", is_admin=True)
            session.add(admin)
            session.commit()
            session.refresh(admin)
        
        # Seed 5 real trivia sets with 5 cards each (delete existing test data first if needed)
        sets_data = [
            ("History Trivia", [
                ("When was the Declaration of Independence signed?", "Aug. 2, 1776"),
                ("From which country did the United States buy Alaska?", "Russia"),
                ("What word was found carved into a tree on Roanoke Island in 1590?", "Croatoan"),
                ("Who assassinated John F. Kennedy?", "Lee Harvey Oswald"),
                ("What were the names of Christopher Columbus's three ships?", "Nina, Pinta, and Santa Maria")
            ]),
            ("Science Trivia", [
                ("How much of the Earth is covered in water?", "71%"),
                ("What gas do animals need to breathe to survive?", "Oxygen"),
                ("What is the largest planet in our solar system?", "Jupiter"),
                ("What is the fastest animal on land?", "Cheetah"),
                ("How long is the lifespan of a human red blood cell?", "120 days")
            ]),
            ("Movies Trivia", [
                ("In Finding Nemo, what type of fish is Nemo?", "Clownfish"),
                ("What is the name of the cowboy in Toy Story?", "Woody"),
                ("Who voices Joy in Pixar's Inside Out?", "Amy Poehler"),
                ("Where were The Lord of the Rings movies filmed?", "New Zealand"),
                ("What is the name of the moon on which the movie 'Avatar' takes place?", "Pandora")
            ]),
            ("Sports Trivia", [
                ("How many bases are on a baseball field?", "4"),
                ("How many holes are there in a full round of golf?", "18"),
                ("What is the object you hit in badminton with?", "Shuttlecock"),
                ("What is Canada's national sport?", "Lacrosse"),
                ("Which MLB player was nicknamed 'The Bambino'?", "Babe Ruth")
            ]),
            ("Geography Trivia", [
                ("What is the tallest mountain in the world?", "Mount Everest"),
                ("What is the longest river in the world?", "The Nile River"),
                ("What is the world's largest country by physical size?", "Russia"),
                ("Which is the oldest city in the world?", "Damascus, Syria"),
                ("What is the capital of Australia?", "Canberra")
            ])
        ]
        
        for set_name, cards in sets_data:
            existing_set = session.exec(select(Set).where(Set.name == set_name)).first()
            if not existing_set:
                new_set = Set(name=set_name, user_id=admin.id)
                session.add(new_set)
                session.commit()
                session.refresh(new_set)
                for front, back in cards:
                    new_card = Card(front=front, back=back, set_id=new_set.id)
                    session.add(new_card)
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
app.include_router(scores_router) # ADD THIS INCLUDE
