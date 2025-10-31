from fastapi import APIRouter, HTTPException, Depends, status
from sqlmodel import Session, select
from db.models import Card
from db.session import get_session

router = APIRouter()

@router.get("/", status_code=status.HTTP_200_OK)
def get_all_cards(session: Session = Depends(get_session)):
    statement = select(Card)
    cards = session.exec(statement).all()
    return cards

@router.get("/{card_id}", status_code=status.HTTP_200_OK)
def get_card(card_id: int, session: Session = Depends(get_session)):
    card = session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    return card

@router.post("/", status_code=status.HTTP_204_NO_CONTENT)
def create_card(card: Card, session: Session = Depends(get_session)):
    session.add(card)
    session.commit()
    session.refresh(card)
    return

@router.put("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def update_card(card_id: int, card_update: Card, session: Session = Depends(get_session)):
    card = session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    card_data = card_update.dict(exclude_unset=True)
    for key, value in card_data.items():
        setattr(card, key, value)
    session.add(card)
    session.commit()
    session.refresh(card)
    return

@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_card(card_id: int, session: Session = Depends(get_session)):
    card = session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    session.delete(card)
    session.commit()
    return
