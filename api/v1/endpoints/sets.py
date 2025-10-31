from fastapi import APIRouter, HTTPException, Depends, status
from sqlmodel import Session, select
from db.models import Set
from db.session import get_session

router = APIRouter()

@router.get("/", status_code=status.HTTP_200_OK)
def get_all_sets(session: Session = Depends(get_session)):
    statement = select(Set)
    sets = session.exec(statement).all()
    return sets

@router.get("/{set_id}", status_code=status.HTTP_200_OK)
def get_set(set_id: int, session: Session = Depends(get_session)):
    set_ = session.get(Set, set_id)
    if not set_:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Set not found")
    return set_

@router.post("/", status_code=status.HTTP_204_NO_CONTENT)
def create_set(set_: Set, session: Session = Depends(get_session)):
    session.add(set_)
    session.commit()
    session.refresh(set_)
    return

@router.put("/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
def update_set(set_id: int, set_update: Set, session: Session = Depends(get_session)):
    set_ = session.get(Set, set_id)
    if not set_:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Set not found")
    set_data = set_update.dict(exclude_unset=True)
    for key, value in set_data.items():
        setattr(set_, key, value)
    session.add(set_)
    session.commit()
    session.refresh(set_)
    return

@router.delete("/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_set(set_id: int, session: Session = Depends(get_session)):
    set_ = session.get(Set, set_id)
    if not set_:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Set not found")
    session.delete(set_)
    session.commit()
    return
