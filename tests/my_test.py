from fastapi.testclient import TestClient
from bs4 import BeautifulSoup
from main import app, Card, Set
from sqlmodel import Session, create_engine, SQLModel
import pytest

# Mock database engine for tests
engine = create_engine("sqlite:///:memory:")

@pytest.fixture
def session():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        # Add sample data
        set_ = Set(id=1, name="Test Set", user_id=1)
        session.add(set_)
        card = Card(id=1, front="Question", back="Answer", set_id=1)
        session.add(card)
        session.commit()
        yield session

# Override the get_session dependency
@pytest.fixture(autouse=True)
def setup_app(session):
    from db.session import get_session
    app.dependency_overrides[get_session] = lambda: session
    yield
    app.dependency_overrides.clear()

client = TestClient(app)

@pytest.mark.asyncio
async def test_read_main():
    response = client.get("/")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert "Flashcard" in soup.get_text()

@pytest.mark.asyncio
async def test_get_cards():
    response = client.get("/cards")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert "Cards" in soup.get_text()  # Adjust based on card.html content
