from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi import WebSocket, WebSocketDisconnect, Cookie #Import websocket and cookies
from sqlmodel import select, Session
from ..db.session import get_session
from ..db.models import Card, Set, User
from ..auth import get_current_user
import random
from typing import Optional
from ..db.session import create_db_and_tables, engine
from fastapi import Depends
from typing import Annotated




SessionDep = Annotated[Session, Depends(get_session)] 

router = APIRouter(prefix="/playwithfriends")
templates = Jinja2Templates(directory="templates")



#Route for playwithfriends
#Route for playwithfriends




@router.get("/playwithfriends", response_class=HTMLResponse) 
async def play_game(request:Request, session: Session = Depends(get_session), 
                    current_user: Optional[User] = Depends(get_current_user)):
    if not current_user:
        # If not logged in, just raise the HTTPException (or redirect to login)
        raise HTTPException(status_code=403, detail="Login required to play")

    # FIX: Pass the logged-in user's username to the template context
    return templates.TemplateResponse(
        request=request, 
        name="playwithfriends.html",
        # Pass the username here!
        context={"user_name": current_user.username} 
    )





@router.post("/")
async def enter_play(request:Request, session:SessionDep, user_name: str= Form(...)):

    # This handles the form submission for non-logged-in users.
    response =  templates.TemplateResponse(
        request=request, name="playwithfriends.html", context={"user_name":user_name}
    )

    # Set the cookie so the user doesn't have to enter the name again on refresh/revisit
    response.set_cookie(key="user_name",value=user_name, httponly=False)
    return response
  
# Define a WebSocket endpoint at the path /ws/{client_id}
@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str, session: SessionDep):
    
    # Accept the WebSocket connection and register it with the connection manager
    await manager.connect(websocket)
    
    try:
        # Keep the connection open and listen for incoming messages
        while True:           
            # Wait for a JSON message from the client
            data = await websocket.receive_json()
                       
            # Broadcast the chat message to all connected clients
            # client_id will be the logged-in username or the name entered in the form
            await manager.broadcast(f"{client_id} says: {data['payload']['message']}")

    # Handle client disconnects
    except WebSocketDisconnect:
        # Remove the client from the connection manager
        manager.disconnect(websocket)
        
        # Notify other clients that this client has left
        await manager.broadcast(f"Client #{client_id} left the chat")
