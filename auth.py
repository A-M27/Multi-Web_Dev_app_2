from fastapi import Depends, Cookie
from sqlmodel import Session, select
from .db.models import User
from .db.session import get_session
from typing import Optional

async def get_current_user(session_user_id: Optional[str] = Cookie(None), session: Session = Depends(get_session)):
    if session_user_id:
        try:
            db_user = session.exec(select(User).where(User.id == int(session_user_id))).first()
            if db_user:
                return db_user
        except ValueError:
            pass
    return None
