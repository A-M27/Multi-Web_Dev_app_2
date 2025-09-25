from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List

class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True)
    is_admin: bool = Field(default=False)
    sets: List["Set"] = Relationship(back_populates="user")
    scores: List["Score"] = Relationship(back_populates="user")

class Set(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    user_id: int = Field(foreign_key="user.id")
    user: Optional["User"] = Relationship(back_populates="sets")
    cards: List["Card"] = Relationship(back_populates="set")
    scores: List["Score"] = Relationship(back_populates="set")

class Card(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    front: str
    back: str
    set_id: int | None = Field(default=None, foreign_key="set.id")
    set: Optional[Set] = Relationship(back_populates="cards")

class Score(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    set_id: int = Field(foreign_key="set.id")
    score: int
    date: str
    user: Optional[User] = Relationship(back_populates="scores")
    set: Optional[Set] = Relationship(back_populates="scores")
