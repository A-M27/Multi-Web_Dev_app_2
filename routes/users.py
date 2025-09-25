from fastapi import APIRouter, Request, Depends, HTTPException, Form, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import select, Session
from ..db.session import get_session
from ..db.models import User
from ..auth import get_current_user
from typing import Optional

router = APIRouter(prefix="/users")
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def get_users(request: Request, session: Session = Depends(get_session),
                   current_user: Optional[User] = Depends(get_current_user)):
    if not current_user:
        return templates.TemplateResponse(
            request=request,
            name="users.html",
            context={"users": [], "current_user": None, "guest": True}
        )
    
    users = session.exec(select(User)).all()
    return templates.TemplateResponse(
        request=request,
        name="users.html",
        context={"users": users, "current_user": current_user}
    )

@router.get("/login", response_class=HTMLResponse)
async def get_login(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={}
    )

@router.post("/login", response_class=RedirectResponse)
async def login(
    username: str = Form(...),
    session: Session = Depends(get_session)
):
    user = session.exec(select(User).where(User.username == username)).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid username")
    
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="session_user_id", value=str(user.id), httponly=True)
    return response

@router.get("/register", response_class=HTMLResponse)
async def get_register(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={}
    )

@router.post("/register", response_class=RedirectResponse)
async def register(
    username: str = Form(...),
    session: Session = Depends(get_session)
):
    existing = session.exec(select(User).where(User.username == username)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    user = User(username=username, is_admin=False)
    session.add(user)
    session.commit()
    session.refresh(user)
    response = RedirectResponse(url="/users/login", status_code=303)
    return response

@router.get("/logout", response_class=RedirectResponse)
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("session_user_id")
    return response

@router.get("/add", response_class=HTMLResponse)
async def get_add_user_form(request: Request, current_user: Optional[User] = Depends(get_current_user)):
    if not current_user or not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can add users")
    return templates.TemplateResponse(
        request=request,
        name="user_add.html",
        context={"current_user": current_user}
    )

@router.post("/add", response_class=RedirectResponse)
async def add_user(
    username: str = Form(...),
    is_admin: bool = Form(False),
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user)
):
    if not current_user or not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can add users")
    
    existing = session.exec(select(User).where(User.username == username)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    user = User(username=username, is_admin=is_admin)
    session.add(user)
    session.commit()
    session.refresh(user)
    return RedirectResponse(url="/users", status_code=303)

@router.get("/{user_id}/edit", response_class=HTMLResponse)
async def get_edit_user_form(request: Request, user_id: int, session: Session = Depends(get_session),
                             current_user: Optional[User] = Depends(get_current_user)):
    if not current_user or not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can edit users")
    
    user = session.exec(select(User).where(User.id == user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return templates.TemplateResponse(
        request=request,
        name="user_edit.html",
        context={"user": user, "current_user": current_user}
    )

@router.post("/{user_id}/edit", response_class=RedirectResponse)
async def edit_user(
    user_id: int,
    username: str = Form(...),
    is_admin: bool = Form(False),
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user)
):
    if not current_user or not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can edit users")
    
    user = session.exec(select(User).where(User.id == user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    existing = session.exec(select(User).where(User.username == username, User.id != user_id)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    user.username = username
    user.is_admin = is_admin
    session.add(user)
    session.commit()
    return RedirectResponse(url="/users", status_code=303)

@router.post("/{user_id}/delete", response_class=RedirectResponse)
async def delete_user(
    user_id: int,
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user)
):
    if not current_user or not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can delete users")
    
    user = session.exec(select(User).where(User.id == user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    session.delete(user)
    session.commit()
    return RedirectResponse(url="/users", status_code=303)

@router.get("/{user_id}", response_class=HTMLResponse)
async def get_user_by_id(request: Request, user_id: int, session: Session = Depends(get_session),
                        current_user: Optional[User] = Depends(get_current_user)):
    user = session.exec(select(User).where(User.id == user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if current_user and not (current_user.is_admin or current_user.id == user_id):
        raise HTTPException(status_code=403, detail="Unauthorized access to user")
    
    return templates.TemplateResponse(
        request=request,
        name="user.html",
        context={"user": user, "current_user": current_user}
    )
