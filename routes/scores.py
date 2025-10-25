from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select, Session
from sqlalchemy.orm import selectinload
from ..db.session import get_session
from ..db.models import Set, Card, User, Score
from ..auth import get_current_user
import random
from typing import Optional
from datetime import datetime

router = APIRouter()
templates = Jinja2Templates(directory="templates")



@router.get("/quiz", response_class=HTMLResponse)
async def get_quiz_options(request: Request, session: Session = Depends(get_session),
                           current_user: Optional[User] = Depends(get_current_user)):
    """Allows user to select a set for the quiz."""
    if not current_user:
        return RedirectResponse(url="/users/login", status_code=303)
    

    

    if not current_user.is_admin:
        query = query.where(Set.user_id == current_user.id)
    
    sets = session.exec(query).all()
    

    valid_sets = [s for s in sets if s.cards and len(s.cards) > 0]
    
    return templates.TemplateResponse(
        request=request,
        name="quiz_view.html", 
        context={"sets": valid_sets, "current_user": current_user, "quiz_mode": True}
    )

@router.get("/quiz/{set_id}/start", response_class=HTMLResponse)
async def start_quiz(request: Request, set_id: int, session: Session = Depends(get_session),
                     current_user: Optional[User] = Depends(get_current_user)):
    """Starts a quiz based on the selected set."""
    if not current_user:
        raise HTTPException(status_code=403, detail="Login required to take a quiz")


    db_set = session.exec(
        select(Set)
        .options(selectinload(Set.cards))
        .where(Set.id == set_id)
    ).first()
    
    if not db_set:
        raise HTTPException(status_code=404, detail="Set not found")
    
    cards = db_set.cards

    if not cards:
        raise HTTPException(status_code=404, detail="Set contains no cards to quiz on.")

    random.shuffle(cards)
    
    return templates.TemplateResponse(
        request=request,
        name="quiz.html", 
        context={"cards": cards, "set": db_set, "current_user": current_user}
    )

@router.post("/quiz/submit", response_class=HTMLResponse)
async def submit_quiz(request: Request, session: Session = Depends(get_session),
                      current_user: Optional[User] = Depends(get_current_user)):
    """Processes the submitted quiz answers and records the score."""
    if not current_user:
        raise HTTPException(status_code=403, detail="Login required to submit a quiz")

    form_data = await request.form()
    
    score = 0
    total = 0
    set_id = None
    

    card_ids = []
    for key in form_data.keys():
        if key.startswith("answer-"):
            try:
                card_ids.append(int(key.split('-')[1]))
            except ValueError:
                continue

    if not card_ids:
        raise HTTPException(status_code=400, detail="No answers submitted")


    submitted_cards = session.exec(select(Card).where(Card.id.in_(card_ids))).all()
    card_map = {card.id: card for card in submitted_cards}

    if submitted_cards:

        set_id = submitted_cards[0].set_id
    
    for card_id in card_ids:
        user_answer = form_data.get(f"answer-{card_id}", "").strip()
        card = card_map.get(card_id)
        
        if card:
            total += 1

            if user_answer.lower() == card.back.lower().strip():
                score += 1
    
    if total == 0 or set_id is None:
        raise HTTPException(status_code=400, detail="Error processing quiz: Set ID or cards missing.")

    percentage = (score / total) * 100 if total > 0 else 0
    

    new_score = Score(
        user_id=current_user.id,
        set_id=set_id,
        score=score,
        date=datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    session.add(new_score)
    session.commit()
    session.refresh(new_score)

    return templates.TemplateResponse(
        request=request,
        name="quiz_result.html",
        context={"score": score, "total": total, "percentage": percentage, "current_user": current_user}
    )


@router.get("/scores", response_class=HTMLResponse)
async def get_scores(request: Request, session: Session = Depends(get_session),
                     current_user: Optional[User] = Depends(get_current_user)):
    """Displays all scores for the current user."""
    if not current_user:
        raise HTTPException(status_code=403, detail="Login required to view scores")
    

    scores = session.exec(
        select(Score)
        .options(selectinload(Score.set))
        .where(Score.user_id == current_user.id)
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="scores.html", 
        context={"scores": scores, "current_user": current_user}
    )
