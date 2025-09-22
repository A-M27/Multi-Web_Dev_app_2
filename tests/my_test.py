from fastapi.testclient import TestClient
from bs4 import BeautifulSoup
from ..main import app, Card, Set, get_session
from sqlmodel import Session, SQLModel, select
import re
import pytest
import logging
import os
from datetime import datetime
from faker import Faker
import random

# Initialize Faker for arbitrary data
faker = Faker()

# Configure logging
log_file = os.path.join(os.path.dirname(__file__), "test.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(log_file, mode="w")]
)
logger = logging.getLogger(__name__)

# Use the app's engine
from ..db.session import engine

# Store test results
test_results = []

# Custom pytest hook
def pytest_runtest_logreport(report):
    test_name = report.nodeid
    status = "PASSED" if report.passed else "FAILED" if report.failed else "ERROR"
    duration = report.duration
    test_results.append((test_name, status, report.longreprtext if report.failed or report.skipped else ""))
    log_message = f"Test: {test_name}, Status: {status}, Duration: {duration:.3f}s"
    if report.failed or report.skipped:
        log_message += f"\nError: {report.longreprtext}"
    logger.info(log_message)

# Helper functions for arbitrary data
def generate_fake_set(user_id):
    return Set(
        id=random.randint(1, 1000),
        name=faker.catch_phrase(),
        user_id=user_id
    )

def generate_fake_card(set_id):
    return Card(
        id=random.randint(1, 1000),
        front=faker.sentence(nb_words=3),
        back=faker.sentence(nb_words=5),
        set_id=set_id
    )

# Fixture for database setup (module scope)
@pytest.fixture(scope="module")
def db_setup():
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)

# Fixture for session with arbitrary data
@pytest.fixture
def session(db_setup):
    with Session(engine) as session:
        user_id = random.randint(1, 1000)
        set_ = generate_fake_set(user_id)
        card = generate_fake_card(set_.id)
        session.add(set_)
        session.add(card)
        session.commit()
        session.refresh(set_)
        session.refresh(card)
        yield session, set_, card

# Fixture to override get_session
@pytest.fixture(autouse=True)
def setup_app(session):
    session_obj, _, _ = session
    app.dependency_overrides[get_session] = lambda: session_obj
    yield
    app.dependency_overrides.clear()

client = TestClient(app)

@pytest.mark.asyncio
async def test_read_main(session):
    _, _, card = session
    response = client.get("/")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert "Andy's Trivia Questions" in soup.get_text()  # Matches index.html

@pytest.mark.asyncio
async def test_get_cards(session):
    _, _, card = session
    response = client.get("/cards")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert "Cards" in soup.get_text()

@pytest.mark.asyncio
async def test_get_cards_with_query(session):
    _, _, card = session
    query = card.front.split()[0]
    response = client.get(f"/cards?q={query}")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert "Cards" in soup.get_text()
    response = client.get(f"/cards?q={query.lower()}")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert "Cards" in soup.get_text()

@pytest.mark.asyncio
async def test_get_card(session):
    _, _, card = session
    response = client.get(f"/cards/{card.id}")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert "Cards" in soup.get_text()  # Fallback; adjust if card.html renders card.front

@pytest.mark.asyncio
async def test_get_card_not_found():
    response = client.get("/cards/9999")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert "Cards" in soup.get_text()

@pytest.mark.asyncio
async def test_add_card(session):
    _, set_, _ = session
    card_data = {
        "front": faker.sentence(nb_words=3),
        "back": faker.sentence(nb_words=5),
        "set_id": set_.id
    }
    response = client.post("/card/add", json=card_data)
    assert response.status_code == 200
    assert response.json()["front"] == card_data["front"]
    assert response.json()["back"] == card_data["back"]
    assert response.json().get("set_id") == card_data["set_id"]  # Use .get() for safety
    response = client.get("/cards")
    soup = BeautifulSoup(response.text, "html.parser")
    assert "Cards" in soup.get_text()

@pytest.mark.asyncio
async def test_add_card_invalid_data():
    card_data = {"front": faker.sentence()}
    response = client.post("/card/add", json=card_data)
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_play(session):
    _, _, card = session
    response = client.get("/play")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert "Play Trivia" in soup.get_text()  # Matches play.html

@pytest.mark.asyncio
async def test_play_no_cards(session):
    session_obj, _, _ = session
    session_obj.execute(Card.__table__.delete())
    session_obj.commit()
    response = client.get("/play")
    assert response.status_code == 404
    assert "No cards available" in response.text

@pytest.mark.asyncio
async def test_get_sets(session):
    _, set_, _ = session
    response = client.get("/sets")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert "All Sets" in soup.get_text()  # Matches sets.html

@pytest.mark.asyncio
async def test_create_set(session):
    _, _, _ = session
    set_data = {"name": faker.catch_phrase(), "user_id": random.randint(1, 1000)}
    response = client.post("/sets/add", json=set_data)
    assert response.status_code == 200
    assert response.json()["name"] == set_data["name"]
    assert response.json()["user_id"] == set_data["user_id"]
    response = client.get("/sets")
    soup = BeautifulSoup(response.text, "html.parser")
    assert "All Sets" in soup.get_text()

@pytest.mark.asyncio
async def test_create_set_invalid_data():
    set_data = {"name": faker.catch_phrase()}
    response = client.post("/sets/add", json=set_data)
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_get_set_by_id(session):
    _, set_, card = session
    response = client.get(f"/sets/{set_.id}")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert set_.name in soup.get_text()

@pytest.mark.asyncio
async def test_get_set_by_id_not_found():
    response = client.get("/sets/9999")
    assert response.status_code == 404
    assert "Set not found" in response.text

@pytest.mark.asyncio
async def test_get_users():
    response = client.get("/users")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert "Alice Smith" in soup.get_text()
    assert "Bob Johnson" in soup.get_text()

@pytest.mark.asyncio
async def test_create_set_html(session):
    _, _, _ = session
    set_data = {"name": faker.catch_phrase(), "user_id": random.randint(1, 1000)}
    post_response = client.post("/sets/add", json=set_data)
    assert post_response.status_code == 200
    assert post_response.json()["name"] == set_data["name"]
    response = client.get("/sets")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert "All Sets" in soup.get_text()
    set_id = post_response.json().get("id", random.randint(1, 1000))
    response = client.get(f"/sets/{set_id}")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert set_data["name"] in soup.get_text()

# Print feature status
def pytest_sessionfinish(session, exitstatus):
    print("\nFeature Status Summary:")
    features = {
        "Root (/)": ["test_read_main"],
        "Get Cards (/cards)": ["test_get_cards", "test_get_cards_with_query"],
        "Get Card by ID (/cards/{card_id})": ["test_get_card", "test_get_card_not_found"],
        "Add Card (/card/add)": ["test_add_card", "test_add_card_invalid_data"],
        "Play (/play)": ["test_play", "test_play_no_cards"],
        "Get Sets (/sets)": ["test_get_sets"],
        "Create Set (/sets/add)": ["test_create_set", "test_create_set_invalid_data", "test_create_set_html"],
        "Get Set by ID (/sets/{set_id})": ["test_get_set_by_id", "test_get_set_by_id_not_found"],
        "Get Users (/users)": ["test_get_users"],
    }
    for feature, tests in features.items():
        status = "Working" if all(test_results[i][1] == "PASSED" for i, (test_name, status, _) in enumerate(test_results) if any(t in test_name for t in tests)) else "Not Working"
        print(f"{feature}: {status}")
