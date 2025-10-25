from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select, Session
from ..db.session import get_session
from ..db.models import Card, Set, User
from ..auth import get_current_user
import random
import json
import re
import uuid 
from typing import Optional, List, Annotated, Dict
from fastapi import WebSocket, WebSocketDisconnect, Query 
from pathlib import Path



class PlayerScore(dict):
    """Stores a single player's score and statistics."""
    def __init__(self):
        super().__init__({"correct": 0, "half": 0, "wrong": 0, "grade": 0.0})

class GameState:
    def __init__(self, creator_id: int, creator_username: str, set_id: int, max_questions: int, max_time: int = 60):
        self.game_id = str(uuid.uuid4())[:8].upper()
        self.creator_id = creator_id
        self.creator_username = creator_username
        self.set_id = set_id
        self.max_questions = max_questions
        self.max_time = max_time
        self.status = "LOBBY" 
        self.current_question_count = 0
        self.current_card: Optional[Card] = None
 
        self.score_board: Dict[str, PlayerScore] = {creator_username: PlayerScore()}

        self.answered_users: Dict[str, bool] = {}

        self.active_connections: Dict[str, WebSocket] = {}


ACTIVE_GAMES: Dict[str, GameState] = {} 

router = APIRouter(prefix="/games")
templates = Jinja2Templates(directory="templates")
SessionDep = Annotated[Session, Depends(get_session)] 



def get_random_card_from_set(session: Session, set_id: int) -> Optional[Card]:
    """Fetches a random card from a specific set."""
    game_set = session.get(Set, set_id)
    if game_set and game_set.cards:
        return random.choice(game_set.cards)
    return None




def normalize_text(text: str) -> str:
    """Removes capitalization, extra spaces, and basic punctuation for flexible comparison."""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def grade_answer(user_answer: str, correct_answer: str) -> str:
    """Grades the user's answer as 'correct', 'half', or 'wrong'."""
    
    normalized_user = normalize_text(user_answer)
    normalized_correct = normalize_text(correct_answer)
    
    if normalized_user == normalized_correct:
        return 'correct'
    
    correct_words = set(normalized_correct.split())
    user_words = set(normalized_user.split())
    
    if not correct_words:
        return 'wrong' 

    matching_words = correct_words.intersection(user_words)
    
    if len(matching_words) > 0 and len(matching_words) >= len(correct_words) * 0.5:
        return 'half'
    
    return 'wrong'

def update_game_score(game: GameState, username: str, result: str):
    """Updates the game's scoreboard with 5-point grading system."""
    
    POINTS_CORRECT = 5.0
    POINTS_HALF = 2.5 
    
    if username not in game.score_board:
        game.score_board[username] = PlayerScore()
    
    if result == 'correct':
        game.score_board[username]['correct'] += 1
    elif result == 'half':
        game.score_board[username]['half'] += 1
    elif result == 'wrong':
        game.score_board[username]['wrong'] += 1
        
    total_grade = (game.score_board[username]['correct'] * POINTS_CORRECT) + (game.score_board[username]['half'] * POINTS_HALF)
    game.score_board[username]['grade'] = total_grade
    
    return game.score_board[username]



async def broadcast_game_message(game: GameState, message: dict):
    """Sends a JSON message to all active connections in a specific game."""

    connections_to_send = list(game.active_connections.values())
    for ws in connections_to_send:
        try:
            await ws.send_json(message)
        except Exception:

            pass




@router.get("/playwithfriends", response_class=HTMLResponse) 
async def play_game_lobby(request:Request, 
                         session: SessionDep,
                         current_user: User = Depends(get_current_user)):
    

    if not current_user:
        raise HTTPException(status_code=403, detail="User not logged in.")
    

    sets = session.exec(select(Set)).all()

    sets = [s for s in sets if s.cards] 

    return templates.TemplateResponse(
        request=request, 
        name="playwithfriends.html",
        context={"current_user": current_user, "sets": sets, "game_id": None}
    )

@router.post("/create_game")
async def create_game(current_user: User = Depends(get_current_user),
                      set_id: int = Form(...),
                      max_questions: int = Form(10),
                      session: SessionDep): #
    
    if not current_user:
        raise HTTPException(status_code=403, detail="User not logged in.")
        
    game_set = session.get(Set, set_id)
    if not game_set:
        raise HTTPException(status_code=400, detail="Invalid card set selected.")
    

    if not game_set.cards:
        raise HTTPException(status_code=400, detail="Selected card set has no cards.")
    

    max_questions = min(max_questions, len(game_set.cards), 50)
    

    new_game = GameState(
        creator_id=current_user.id,
        creator_username=current_user.username,
        set_id=set_id,
        max_questions=max_questions
    )
    

    ACTIVE_GAMES[new_game.game_id] = new_game
    

    return RedirectResponse(url=f"/games/playwithfriends/{new_game.game_id}", status_code=303)


@router.get("/playwithfriends/{game_id}", response_class=HTMLResponse)
async def join_game_page(request: Request,
                         game_id: str,
                         current_user: User = Depends(get_current_user),
                         session: SessionDep):
    

    if not current_user:
        raise HTTPException(status_code=403, detail="User not logged in.")
    

    game = ACTIVE_GAMES.get(game_id)
    
    if not game:
        raise HTTPException(status_code=404, detail="Game not found or has ended.")
    
    is_creator = (current_user.username == game.creator_username)
    is_player = (current_user.username in game.score_board)
    

    if not is_creator and not is_player:
        game.score_board[current_user.username] = PlayerScore()


    return templates.TemplateResponse(
        request=request,
        name="playwithfriends_game.html",
        context={
            "current_user": current_user, 
            "game": game,
            "is_creator": is_creator,
            "game_id": game_id,
            "card": game.current_card 
        }
    )



@router.websocket("/ws/{game_id}/{username}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, username: str, session: SessionDep): 
    
    game = ACTIVE_GAMES.get(game_id)
    

    if not game or username not in game.score_board:
        await websocket.close(code=1008, reason="Game ID or user authorization failed.")
        return


    await websocket.accept()
    game.active_connections[username] = websocket
    

    await broadcast_game_message(game, {
        "type": "chat_message",
        "sender": "SYSTEM",
        "text": f"{username} joined the game.",
        "mode": "friends",
        "players": list(game.score_board.keys()),
        "status": game.status
    })

    try:
        while True:            
            data = await websocket.receive_json()
            message_type = data.get('type')

            if message_type == 'chat':
                payload = data.get('payload', {})
                message = payload.get('message')
                if message:
                    chat_data = {
                        "type": "chat_message",
                        "sender": username,
                        "text": message,
                        "mode": "friends" 
                    }
                    await broadcast_game_message(game, chat_data)
            
            elif message_type == 'answer_submission':
                payload = data.get('payload', {})
                answer = payload.get('answer', '').strip()
                
                if game.status != "ACTIVE" or game.answered_users.get(username):
                    continue

                result = grade_answer(answer, game.current_card.back)
                update_game_score(game, username, result)
                game.answered_users[username] = True
                
                answer_data = {
                    "type": "answer_result",
                    "sender": username,
                    "answer": answer,
                    "result": result,
                    "scores": game.score_board,
                    "mode": "answer" 
                }
                await broadcast_game_message(game, answer_data)
                
            elif message_type == 'game_control' and username == game.creator_username:
                payload = data.get('payload', {})
                command = payload.get('command')
                
                if command == 'start_game' and game.status == "LOBBY":

                    game.status = "ACTIVE"
                    await broadcast_game_message(game, {"type": "game_status_update", "status": "ACTIVE", "message": "Game starting!"})
                    
  
                    command = 'request_next_card' 

                if command == 'request_next_card' and game.status == "ACTIVE":
                    
                    if game.current_question_count >= game.max_questions:
                        game.status = "FINISHED"
                        await broadcast_game_message(game, {"type": "game_status_update", "status": "FINISHED", "message": "Game finished! Displaying final leaderboard."})
                        continue
                    

                    game.answered_users = {}
                    game.current_question_count += 1
                    

                    next_card = get_random_card_from_set(session, game.set_id)
                    
                    if next_card:
                        game.current_card = next_card
                        
                        card_data = {
                            "type": "new_card",
                            "front": next_card.front,
                            "back": next_card.back,
                            "question_number": game.current_question_count,
                            "max_questions": game.max_questions
                        }
                        await broadcast_game_message(game, card_data)
                    
            elif message_type == 'score_request':
                score_data = {
                    "type": "score_update",
                    "scores": game.score_board
                }
                await websocket.send_json(score_data)

    except WebSocketDisconnect:
        if username in game.active_connections:
            del game.active_connections[username]
        
        system_message = {
            "type": "chat_message",
            "sender": "SYSTEM",
            "text": f"{username} disconnected.",
            "mode": "friends",
            "players": list(game.score_board.keys()),
            "status": game.status
        }
        await broadcast_game_message(game, system_message)
        
    except Exception as e:
        print(f"An unexpected error occurred in WebSocket: {e}")
