from fastapi import APIRouter
from api.v1.endpoints import users, sets, cards

api_router = APIRouter()
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(sets.router, prefix="/sets", tags=["Sets"])
api_router.include_router(cards.router, prefix="/cards", tags=["Cards"])
