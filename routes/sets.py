from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select, Session
from ..db.session import get_session
from ..db.models import Set, Card, User
from ..auth import get_current_user
from typing import Optional

router = APIRouter(prefix="/sets")
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def get_sets(request: Request, session: Session = Depends(get_session),
                   current_user: Optional[User] = Depends(get_current_user)):
    if not current_user:
        return templates.TemplateResponse(
            request=request,
            name="sets.html",
            context={"sets": [], "current_user": None, "guest": True}
        )
    
    if current_user.is_admin:
        sets = session.exec(select(Set).order_by(Set.name)).all()
    else:
        sets = session.exec(select(Set).where(Set.user_id == current_user.id).order_by(Set.name)).all()
    
    return templates.TemplateResponse(
        request=request,
        name="sets.html",
        context={"sets": sets, "current_user": current_user, "no_sets": not sets}
    )

@router.get("/add", response_class=HTMLResponse)
async def get_add_set_form(request: Request, current_user: Optional[User] = Depends(get_current_user)):
    if not current_user or not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can add sets")
    
    return templates.TemplateResponse(
        request=request,
        name="set_add.html",
        context={"current_user": current_user}
    )

@router.post("/add", response_class=RedirectResponse)
async def create_set(
    name: str = Form(...),
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user)
):
    if not current_user or not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can add sets")
    
    db_set = Set(name=name, user_id=current_user.id)
    session.add(db_set)
    session.commit()
    session.refresh(db_set)
    return RedirectResponse(url="/sets", status_code=303)

@router.get("/{set_id}", response_class=HTMLResponse)
async def get_set_by_id(request: Request, set_id: int, session: Session = Depends(get_session),
                        current_user: Optional[User] = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=403, detail="Login required to view sets")
    
    set = session.exec(select(Set).where(Set.id == set_id)).first()
    if not set:
        return templates.TemplateResponse(
            request=request,
            name="sets.html",
            context={"sets": [], "current_user": current_user, "no_sets": True}
        )
    
    if not current_user.is_admin and set.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized access to set")
    
    cards = session.exec(select(Card).where(Card.set_id == set_id)).all()
    return templates.TemplateResponse(
        request=request,
        name="set_detail.html",
        context={"set": set, "cards": cards, "current_user": current_user}
    )
