from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates 
from sqlmodel import select, Session
from ..db.session import get_session, engine
from ..db.models import Card, Set, User
from ..auth import get_current_user
import random
import json
import re
from typing import Optional, List, Annotated, Dict
from fastapi import WebSocket, WebSocketDisconnect, Cookie, Query
from pathlib import Path
from pydantic import BaseModel
import time
from sqlalchemy.orm import joinedload

class LiveGame(BaseModel):
    game_id: str
    creator_id: int
    set_id: int
    set_name: str
    card_ids: List[int]
    players: Dict[str, str] = {}
    current_card_index: int = -1
    questions_limit: int = 10
    time_limit_sec: int = 60
    state: str = "WAITING"
    is_solo: bool = False 
    score: float = 0.0
    start_time: float = time.time()

active_games: Dict[str, LiveGame] = {}
score_boards: Dict[str, Dict] = {}


router = APIRouter(prefix="/cards")
templates = Jinja2Templates(directory="templates") 

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, game_id: str, client_id: str):
        await websocket.accept()
        if game_id not in self.active_connections:
            self.active_connections[game_id] = {}
        self.active_connections[game_id][client_id] = websocket

    def disconnect(self, game_id: str, client_id: str):
        if game_id in self.active_connections and client_id in self.active_connections[game_id]:
            del self.active_connections[game_id][client_id]

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: dict, game_id: str):
        if game_id in self.active_connections:
            for connection in self.active_connections[game_id].values():
                game = active_games.get(game_id)
                if game and not game.is_solo:
                    await connection.send_json(message)

manager = ConnectionManager()
SessionDep = Annotated[Session, Depends(get_session)]

def generate_game_id() -> str:
    while True:
        game_id = "".join(random.choices('0123456789', k=6))
        if game_id not in active_games:
            return game_id

def create_new_game(session: Session, current_user: User, set_id: int, num_questions: int, is_solo: bool = False) -> LiveGame:
    game_id = generate_game_id()
    
    selected_set = session.exec(select(Set).where(Set.id == set_id)).first()
    if not selected_set:
        raise HTTPException(status_code=400, detail="Invalid card set selected.")
    
    existing_cards = session.exec(select(Card).where(Card.set_id == set_id)).all()
    cards_in_set = [card.id for card in existing_cards]

    if not cards_in_set:
        raise HTTPException(status_code=400, detail="The selected card set is empty.")

    num_questions = min(num_questions, len(cards_in_set))
    
    selected_card_ids = random.sample(cards_in_set, k=num_questions)

    new_game = LiveGame(
        game_id=game_id,
        creator_id=current_user.id,
        set_id=set_id,
        set_name=selected_set.name,
        card_ids=selected_card_ids,
        questions_limit=num_questions,
        is_solo=is_solo,
        state="IN_PROGRESS" if is_solo else "WAITING" 
    )
    active_games[game_id] = new_game
    new_game.players[current_user.username] = current_user.username
    
    return new_game

def get_current_card(session: Session, game: LiveGame) -> Optional[Card]:
    if 0 <= game.current_card_index < len(game.card_ids):
        card_id = game.card_ids[game.current_card_index]
        card = session.exec(select(Card).where(Card.id == card_id)).first()
        
        if not card:
            if game.current_card_index + 1 < len(game.card_ids):
                game.current_card_index += 1
                return get_current_card(session, game)
            else:
                return None
        
        return card
    return None

def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def grade_answer(user_answer: str, correct_answer: str) -> str:
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

def update_score_board(game_id: str, username: str, result: str):
    global score_boards
    POINTS_CORRECT = 5.0
    POINTS_HALF = 2.5
    
    if game_id not in score_boards:
        score_boards[game_id] = {}
        
    board = score_boards[game_id]
    
    if username not in board:
        board[username] = {"correct": 0, "half": 0, "wrong": 0, "grade": 0.0}
        
    if result == 'correct':
        board[username]['correct'] += 1
    elif result == 'half':
        board[username]['half'] += 1
    elif result == 'wrong':
        board[username]['wrong'] += 1
        
    total_grade = (board[username]['correct'] * POINTS_CORRECT) + (board[username]['half'] * POINTS_HALF)
    board[username]['grade'] = total_grade
    return board[username]


# ----------------------------------------------------------------------
# --- SOLO TRIVIA ROUTES (MUST COME BEFORE {card_id}) ---
# ----------------------------------------------------------------------

@router.get("/playtriv", response_class=HTMLResponse)
async def play_triv_setup(
    request: Request,
    session: SessionDep = None,
    current_user: Optional[User] = Depends(get_current_user),
    status: Optional[str] = Query(None),
    game_id: Optional[str] = Query(None)
):
    if not current_user:
        raise HTTPException(status_code=403, detail="Not logged in.")
        
    if status == "finished" and game_id in active_games:
        game = active_games[game_id]
        if game.is_solo and game.creator_id == current_user.id:
             return templates.TemplateResponse(
                request=request,
                name="play.html",
                context={
                    "current_user": current_user,
                    "game_state": "finished",
                    "set_name": game.set_name,
                    "total_questions": game.questions_limit,
                    "final_score": game.score,
                    "game_id": game_id
                }
            )

    sets = session.exec(select(Set).where(Set.user_id == current_user.id)).all()
    
    return templates.TemplateResponse(
        request=request,
        name="play.html",
        context={
            "current_user": current_user,
            "game_state": "initial_select",
            "sets": sets
        }
    )

@router.post("/playtriv/start")
async def start_solo_game(
    set_id: int = Form(...),
    num_questions: int = Form(...),
    session: SessionDep = None,
    current_user: Optional[User] = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=403, detail="Not logged in.")

    try:
        new_game = create_new_game(session, current_user, set_id, num_questions, is_solo=True)
        new_game.current_card_index = 0
        
        return RedirectResponse(url=f"/cards/playtriv/in_progress/{new_game.game_id}", status_code=303)
    except HTTPException as e:
        raise e
    except Exception:
        raise HTTPException(status_code=500, detail="Error starting solo game.")

@router.get("/playtriv/in_progress/{game_id}", response_class=HTMLResponse)
async def solo_game_in_progress(
    request: Request,
    game_id: str,
    session: SessionDep = None,
    current_user: Optional[User] = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=403, detail="Not logged in.")
        
    game = active_games.get(game_id)

    if not game or game.creator_id != current_user.id or not game.is_solo:
        raise HTTPException(status_code=404, detail="Solo game not found or unauthorized.")
    
    if game.state == "FINISHED":
        return RedirectResponse(url=f"/cards/playtriv?status=finished&game_id={game_id}", status_code=303)
        
    current_card = get_current_card(session, game)
    
    if not current_card and game.current_card_index >= len(game.card_ids):
        game.state = "FINISHED"
        return RedirectResponse(url=f"/cards/playtriv?status=finished&game_id={game_id}", status_code=303)


    return templates.TemplateResponse(
        request=request,
        name="play.html",
        context={
            "current_user": current_user,
            "game_state": "in_progress",
            "game_id": game_id,
            "set_name": game.set_name,
            "card": current_card,
            "card_index": game.current_card_index,
            "total_questions": len(game.card_ids)
        }
    )

@router.post("/playtriv/answer")
async def solo_game_submit_answer(
    data: Dict, 
    session: SessionDep = None,
    current_user: Optional[User] = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=403, detail="Not logged in.")

    game_id = data.get('game_id')
    user_answer = data.get('answer', '').strip()

    if not game_id or not user_answer:
        return JSONResponse(content={"status": "error", "message": "Missing game ID or answer."}, status_code=400)
        
    game = active_games.get(game_id)
    
    if not game or game.creator_id != current_user.id or not game.is_solo:
        return JSONResponse(content={"status": "error", "message": "Game state is invalid or unauthorized."}, status_code=404)
    
    if game.state != "IN_PROGRESS":
        return JSONResponse(content={"status": "error", "message": "The game is not in progress."}, status_code=400)
    
    try:
        current_card = get_current_card(session, game)
        if not current_card:
            game.state = "FINISHED"
            return JSONResponse(content={"status": "finished"}, status_code=200)

            
        result = grade_answer(user_answer, current_card.back)
        
        POINTS_CORRECT = 5.0
        POINTS_HALF = 2.5
        
        if result == 'correct':
            game.score += POINTS_CORRECT
        elif result == 'half':
            game.score += POINTS_HALF
        
        return {"status": "success", "result": result, "correct_answer": current_card.back}

    except Exception as e:
        print(f"Internal error during solo answer submission: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during grading.")


@router.post("/playtriv/next")
async def solo_game_next_card(
    data: Dict,
    session: SessionDep = None,
    current_user: Optional[User] = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=403, detail="Not logged in.")

    game_id = data.get('game_id')
    current_index = data.get('current_index')

    if not game_id or current_index is None:
        return JSONResponse(content={"status": "error", "message": "Missing game data."}, status_code=400)
        
    game = active_games.get(game_id)
    
    if not game or game.creator_id != current_user.id or not game.is_solo:
        raise HTTPException(status_code=404, detail="Solo game state error or unauthorized.")
        
    if game.state == "FINISHED":
        return {"status": "finished", "message": "Game completed (already finished)."}

    next_index = current_index + 1
    game.current_card_index = next_index

    if next_index >= len(game.card_ids):
        game.state = "FINISHED"
        return {"status": "finished", "message": "Game completed."}

    next_card = get_current_card(session, game)
    
    if game.current_card_index >= len(game.card_ids) or not next_card:
        game.state = "FINISHED"
        return {"status": "finished", "message": "Game completed after skipping deleted cards."}


    if next_card:
        return {
            "status": "success",
            "card": {"front": next_card.front, "back": next_card.back},
            "card_index": game.current_card_index
        }
    else:
        game.state = "FINISHED"
        return {"status": "finished", "message": "Game completed after skipping deleted cards."}


# ----------------------------------------------------------------------
# --- MULTIPLAYER ROUTES (MUST COME BEFORE {card_id}) ---
# ----------------------------------------------------------------------

@router.get("/playwithfriends", response_class=HTMLResponse)
@router.get("/playwithfriends/{game_id}", response_class=HTMLResponse)
async def play_game(
    request: Request,
    game_id: Optional[str] = None,
    session: SessionDep = None,
    current_user: Optional[User] = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=403, detail="Not logged in.")
    
    if game_id:
        if game_id not in active_games:
            return templates.TemplateResponse(
                request=request,
                name="playwithfriends.html",
                context={"current_user": current_user, "game_state": "not_found", "game_id": game_id}
            )
        
        game = active_games[game_id]
        
        if game.is_solo:
            raise HTTPException(status_code=404, detail="Multiplayer game not found.")
            
        is_creator = game.creator_id == current_user.id
        is_player = current_user.username in game.players

        if not is_player:
             game.players[current_user.username] = current_user.username
             
        initial_card = get_current_card(session, game)
        
        if game.state == "WAITING":
             return templates.TemplateResponse(
                request=request,
                name="playwithfriends.html",
                context={
                    "current_user": current_user,
                    "game_state": "waiting_to_start",
                    "game_id": game_id,
                    "is_creator": is_creator,
                    "players": game.players,
                    "set_name": game.set_name
                }
            )
        elif game.state == "IN_PROGRESS":
            return templates.TemplateResponse(
                request=request,
                name="playwithfriends.html",
                context={
                    "current_user": current_user,
                    "game_state": "in_progress",
                    "game_id": game_id,
                    "is_creator": is_creator,
                    "card": initial_card,
                    "score_board": score_boards.get(game_id, {}),
                    "set_name": game.set_name
                }
            )
        elif game.state == "FINISHED":
             return templates.TemplateResponse(
                request=request,
                name="playwithfriends.html",
                context={
                    "current_user": current_user,
                    "game_state": "finished",
                    "game_id": game_id,
                    "is_creator": is_creator,
                    "score_board": score_boards.get(game_id, {}),
                    "set_name": game.set_name
                }
            )
            
    sets = session.exec(select(Set).where(Set.user_id == current_user.id)).all()
    
    return templates.TemplateResponse(
        request=request,
        name="playwithfriends.html",
        context={
            "current_user": current_user,
            "game_state": "initial_select",
            "sets": sets
        }
    )

@router.post("/playwithfriends/create")
async def create_game(
    set_id: int = Form(...),
    num_questions: int = Form(...),
    session: SessionDep = None,
    current_user: Optional[User] = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=403, detail="Not logged in.")

    try:
        new_game = create_new_game(session, current_user, set_id, num_questions, is_solo=False)
        return RedirectResponse(url=f"/cards/playwithfriends/{new_game.game_id}", status_code=303)
    except HTTPException as e:
        raise e
    except Exception:
        raise HTTPException(status_code=500, detail="Error creating game.")

@router.post("/playwithfriends/join")
async def join_game_post(
    game_id: str = Form(...),
    current_user: Optional[User] = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=403, detail="Not logged in.")
        
    game = active_games.get(game_id)
    
    if game and not game.is_solo:
        return RedirectResponse(url=f"/cards/playwithfriends/{game_id}", status_code=303)
    else:
        return RedirectResponse(url="/cards/playwithfriends?error=notfound", status_code=303)
        

@router.post("/playwithfriends/{game_id}/start")
async def start_game(
    game_id: str,
    session: SessionDep = None,
    current_user: Optional[User] = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=403, detail="Not logged in.")
        
    if game_id not in active_games:
        raise HTTPException(status_code=404, detail="Game not found.")
        
    game = active_games[game_id]
    
    if game.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the game creator can start the game.")

    game.state = "IN_PROGRESS"
    game.current_card_index = 0
    
    first_card = get_current_card(session, game)
    
    if not first_card:
        game.state = "FINISHED"
        raise HTTPException(status_code=400, detail="The set is empty or all starting cards were deleted.")


    await manager.broadcast({
        "type": "game_start_signal",
        "message": "The game is starting! Please reload.",
        "game_id": game_id
    }, game_id)
    
    if first_card:
        card_data = {
            "type": "new_card",
            "front": first_card.front,
            "back": first_card.back,
            "game_id": game_id 
        }
        await manager.broadcast(card_data, game_id)
        
    return RedirectResponse(url=f"/cards/playwithfriends/{game_id}", status_code=303)

@router.post("/playwithfriends/{game_id}/end")
async def end_game(
    game_id: str,
    current_user: Optional[User] = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=403, detail="Not logged in.")
        
    if game_id not in active_games:
        raise HTTPException(status_code=404, detail="Game not found.")
        
    game = active_games[game_id]
    
    if game.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the game creator can end the game.")

    game.state = "FINISHED"
    
    await manager.broadcast({"type": "game_end", "message": f"Game **{game.set_name}** has been manually ended by the creator! Check the final leaderboard."}, game_id)
    
    return RedirectResponse(url=f"/cards/playwithfriends/{game_id}", status_code=303)


# --- WEB SOCKET ENDPOINT ---
@router.websocket("/ws/{game_id}/{client_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, client_id: str, session: SessionDep):
    if game_id not in active_games:
        await websocket.close(code=1008, reason="Game not found.")
        return
        
    game = active_games.get(game_id)
    current_user = session.exec(select(User).where(User.username == client_id)).first()

    if not current_user or current_user.username not in game.players:
         await websocket.close(code=1008, reason="Unauthorized access to game.")
         return
         
    if game.is_solo:
        await websocket.close(code=1003, reason="Solo games do not use this websocket endpoint.")
        return
         
    is_creator = current_user.id == game.creator_id
         
    await manager.connect(websocket, game_id, client_id)
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
                        "sender": client_id,
                        "text": message,
                        "mode": "friends"
                    }
                    await manager.broadcast(chat_data, game_id)
            
            elif message_type == 'answer_submission':
                if game.state != "IN_PROGRESS": continue
                
                payload = data.get('payload', {})
                answer = payload.get('answer', '').strip()
                viewed_answer = payload.get('viewed_answer', False) # Check for zero score flag
                
                current_card = get_current_card(session, game)
                
                # Check for bad input (no text answer AND no view flag) or missing card
                if not current_card or (not answer and not viewed_answer):
                    continue

                # --- FIX 1: Implement Zero Score Logic ---
                if viewed_answer:
                    result = 'wrong'
                    display_answer = "[ANSWER REVEALED] - Score: 0"
                else:
                    result = grade_answer(answer, current_card.back)
                    display_answer = answer
                
                update_score_board(game_id, client_id, result)
                
                answer_data = {
                    "type": "answer_result",
                    "sender": client_id,
                    "answer": display_answer,
                    "result": result,
                    "scores": score_boards[game_id],
                    "initials": client_id[0].upper(),
                    "mode": "answer"
                }
                await manager.broadcast(answer_data, game_id)
                
            elif message_type == 'game_control':
                if game.state != "IN_PROGRESS": continue
                
                payload = data.get('payload', {})
                command = payload.get('command')
                
                if not is_creator:
                    await manager.send_personal_message({"type": "error", "message": "Only the creator can control the game."}, websocket)
                    continue
                    
                if command == 'request_next_card':
                    # Increment index
                    game.current_card_index += 1
                    
                    # Check for hard end of list
                    if game.current_card_index >= len(game.card_ids):
                         game.state = "FINISHED"
                         await manager.broadcast({"type": "game_end", "message": f"Game **{game.set_name}** complete! Check the final leaderboard."}, game_id)
                         continue
                         
                    # Use get_current_card (which may advance index if the card is deleted)
                    next_card = get_current_card(session, game)
                    
                    # --- FIX 2: Handle game end after skipping deleted cards gracefully ---
                    if next_card:
                        card_data = {
                            "type": "new_card",
                            "front": next_card.front,
                            "back": next_card.back,
                            "question_number": game.current_card_index + 1,
                            "total_questions": len(game.card_ids)
                        }
                        await manager.broadcast(card_data, game_id)
                    else:
                        # If next_card is None, it means we hit the end of the list after skipping deleted ones.
                        game.state = "FINISHED"
                        await manager.broadcast({"type": "game_end", "message": f"Game **{game.set_name}** complete! All remaining cards were deleted or list exhausted."}, game_id)
                        
            elif message_type == 'score_request':
                score_data = {
                    "type": "score_update",
                    "scores": score_boards.get(game_id, {})
                }
                await manager.send_personal_message(score_data, websocket)

    except WebSocketDisconnect:
        manager.disconnect(game_id, client_id)
        system_message = {
            "type": "chat_message",
            "sender": "SYSTEM",
            "text": f"Client #{client_id} left the game.",
            "mode": "friends"
        }
        await manager.broadcast(system_message, game_id)
    except Exception as e:
        print(f"An unexpected error occurred in WebSocket for game {game_id}: {e}")


# ----------------------------------------------------------------------
# --- CARD MANAGEMENT ROUTES (REST OF ROUTES OMITTED FOR BREVITY) ---
# ----------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def get_cards(request: Request, session: SessionDep = None, 
                    q: Optional[str] = None, current_user: Optional[User] = Depends(get_current_user)):
    if not current_user:
        return templates.TemplateResponse(
            request=request,
            name="card.html",
            context={"cards": [], "current_user": None, "guest": True}
        )
    if current_user.is_admin:
        cards = session.exec(
            select(Card).options(joinedload(Card.set).joinedload(Set.user))
        ).all()
    else:
        cards = session.exec(
            select(Card)
            .join(Set).where(Set.user_id == current_user.id)
            .options(joinedload(Card.set).joinedload(Set.user))
        ).all()
    
    if q:
        cards = [card for card in cards if q.lower() in card.front.lower()]
    
    return templates.TemplateResponse(
        request=request,
        name="card.html",
        context={"cards": cards, "current_user": current_user}
    )

@router.get("/add", response_class=HTMLResponse)
async def get_add_card_form(request: Request, session: SessionDep = None,
                            current_user: Optional[User] = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=403, detail="Login required to add cards")
    
    set = session.exec(select(Set).where(Set.user_id == current_user.id)).first()
    if not set:
        default_set = Set(name=f"{current_user.username}'s Default Set", user_id=current_user.id) 
        session.add(default_set)
        session.commit()
        session.refresh(default_set)
    
    return templates.TemplateResponse(
        request=request,
        name="card_manage.html",
        context={"request": request, "current_user": current_user}
    )

@router.post("/add", response_class=RedirectResponse)
async def add_card(
    front: str = Form(...),
    back: str = Form(...),
    session: SessionDep = None,
    current_user: Optional[User] = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=403, detail="Login required to add cards")
    
    set = session.exec(select(Set).where(Set.user_id == current_user.id)).first()
    if not set:
        set = Set(name=f"{current_user.username}'s Default Set", user_id=current_user.id)
        session.add(set)
        session.commit()
        session.refresh(set)
    
    card = Card(front=front, back=back, set_id=set.id)
    session.add(card)
    session.commit()
    session.refresh(card)
    return RedirectResponse(url="/cards", status_code=303)

@router.get("/{card_id}", response_class=HTMLResponse, name="get_card")
async def get_card_by_id(request: Request, card_id: int, session: SessionDep = None,
                         current_user: Optional[User] = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=403, detail="Login required to view cards")
    
    card = session.exec(
        select(Card)
        .where(Card.id == card_id)
        .options(joinedload(Card.set).joinedload(Set.user))
    ).first()

    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    
    if not current_user.is_admin and card.set.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized access to card")
    
    return templates.TemplateResponse(
        request=request,
        name="card.html",
        context={"card": card, "current_user": current_user}
    )

@router.get("/{card_id}/edit", response_class=HTMLResponse)
async def get_edit_card_form(request: Request, card_id: int, session: SessionDep = None,
                            current_user: Optional[User] = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=403, detail="Login required to edit cards")
    
    card = session.exec(
        select(Card)
        .where(Card.id == card_id)
        .options(joinedload(Card.set).joinedload(Set.user))
    ).first()

    if not card:
         raise HTTPException(status_code=404, detail="Card not found")
        
    if not current_user.is_admin and card.set.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized access to card")
    
    return templates.TemplateResponse(
        request=request,
        name="card_edit.html",
        context={"card": card, "current_user": current_user}
    )

@router.post("/{card_id}/edit", response_class=RedirectResponse)
async def edit_card(
    card_id: int,
    front: str = Form(...),
    back: str = Form(...),
    session: SessionDep = None,
    current_user: Optional[User] = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=403, detail="Login required to edit cards")
    
    card = session.exec(
        select(Card)
        .where(Card.id == card_id)
        .options(joinedload(Card.set))
    ).first()

    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    
    if not current_user.is_admin and card.set.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized access to card")
    
    card.front = front
    card.back = back
    session.add(card)
    session.commit()
    return RedirectResponse(url=f"/cards/{card_id}/edit", status_code=303)
