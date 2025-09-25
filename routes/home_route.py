from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from ..auth import get_current_user
from ..db.models import User
from typing import Optional

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def home(request: Request, current_user: Optional[User] = Depends(get_current_user)):
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={"current_user": current_user}
    )
