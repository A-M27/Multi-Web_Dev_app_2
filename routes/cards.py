from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select, Session
from ..db.session import get_session
from ..db.models import Card, Set, User
from ..auth import get_current_user
import random
from typing import Optional

router = APIRouter(prefix="/cards")
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def get_cards(request: Request, session: Session = Depends(get_session), 
                   q: Optional[str] = None, current_user: Optional[User] = Depends(get_current_user)):
    if not current_user:
        return templates.TemplateResponse(
            request=request,
            name="card.html",
            context={"cards": [], "current_user": None, "guest": True}
        )
    if current_user.is_admin:
        cards = session.exec(select(Card)).all()
    else:
        # Only show cards belonging to the logged-in user's sets
        cards = session.exec(select(Card).join(Set).where(Set.user_id == current_user.id)).all()
    
    if q:
        cards = [card for card in cards if q.lower() in card.front.lower()]
    
    return templates.TemplateResponse(
        request=request,
        name="card.html",
        context={"cards": cards, "current_user": current_user}
    )

@router.get("/add", response_class=HTMLResponse)
async def get_add_card_form(request: Request, session: Session = Depends(get_session),
                          current_user: Optional[User] = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=403, detail="Login required to add cards")
    
    # Auto-create a default set if none exists
    set = session.exec(select(Set).where(Set.user_id == current_user.id)).first()
    if not set:
        # FIX: Using current_user.username instead of current_user.name
        default_set = Set(name=f"{current_user.username}'s Default Set", user_id=current_user.id) 
        session.add(default_set)
        session.commit()
        session.refresh(default_set)
    
    return templates.TemplateResponse(
        request=request,
        name="card_manage.html",
        context={"request": request, "current_user": current_user}
    )

@router.post("/add", response_class=RedirectResponse)
async def add_card(
    front: str = Form(...),
    back: str = Form(...),
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=403, detail="Login required to add cards")
    
    # Get or create user's default set
    set = session.exec(select(Set).where(Set.user_id == current_user.id)).first()
    if not set:
        # FIX: Using current_user.username instead of current_user.name
        set = Set(name=f"{current_user.username}'s Default Set", user_id=current_user.id)
        session.add(set)
        session.commit()
        session.refresh(set)
    
    card = Card(front=front, back=back, set_id=set.id)
    session.add(card)
    session.commit()
    session.refresh(card)
    return RedirectResponse(url="/cards/manage", status_code=303)

@router.get("/play", response_class=HTMLResponse)
async def play(request: Request, session: Session = Depends(get_session),
               current_user: Optional[User] = Depends(get_current_user)):
    if not current_user:
        return templates.TemplateResponse(
            request=request,
            name="card.html",
            context={"cards": [], "current_user": None, "guest": True}
        )
    
    if current_user.is_admin:
        cards = session.exec(select(Card)).all()
    else:
        cards = session.exec(select(Card).join(Set).where(Set.user_id == current_user.id)).all()
    
    if cards:
        random_card = random.choice(cards)
        return templates.TemplateResponse(
            request=request,
            name="play.html",
            context={"card": random_card, "current_user": current_user}
        )
    return templates.TemplateResponse(
        request=request,
        name="card_manage.html",
        context={"no_cards": True, "current_user": current_user}
    )

@router.get("/manage", response_class=HTMLResponse)
async def manage_cards(request: Request, session: Session = Depends(get_session),
                     current_user: Optional[User] = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=403, detail="Login required to manage cards")
    
    if current_user.is_admin:
        cards = session.exec(select(Card)).all()
    else:
        cards = session.exec(select(Card).join(Set).where(Set.user_id == current_user.id)).all()
    
    return templates.TemplateResponse(
        request=request,
        name="card_manage.html",
        context={"cards": cards, "current_user": current_user, "no_cards": not cards}
    )

@router.get("/{card_id}", response_class=HTMLResponse, name="get_card")
async def get_card_by_id(request: Request, card_id: int, session: Session = Depends(get_session),
                        current_user: Optional[User] = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=403, detail="Login required to view cards")
    
    card = session.exec(select(Card).where(Card.id == card_id)).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    
    if not current_user.is_admin and card.set.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized access to card")
    
    return templates.TemplateResponse(
        request=request,
        name="card.html",
        context={"card": card, "current_user": current_user}
    )

@router.get("/{card_id}/edit", response_class=HTMLResponse)
async def get_edit_card_form(request: Request, card_id: int, session: Session = Depends(get_session),
                           current_user: Optional[User] = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=403, detail="Login required to edit cards")
    
    card = session.exec(select(Card).where(Card.id == card_id)).first()
    if not card:
        return templates.TemplateResponse(
            request=request,
            name="card_manage.html",
            context={"no_cards": True, "current_user": current_user}
        )
    
    if not current_user.is_admin and card.set.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized access to card")
    
    return templates.TemplateResponse(
        request=request,
        name="card_edit.html",
        context={"card": card, "current_user": current_user}
    )

@router.post("/{card_id}/edit", response_class=RedirectResponse)
async def edit_card(
    card_id: int,
    front: str = Form(...),
    back: str = Form(...),
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=403, detail="Login required to edit cards")
    
    card = session.exec(select(Card).where(Card.id == card_id)).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    
    if not current_user.is_admin and card.set.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized access to card")
    
    card.front = front
    card.back = back
    session.add(card)
    session.commit()
    return RedirectResponse(url=f"/cards/{card_id}", status_code=303)
