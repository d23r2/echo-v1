from app.db import SessionLocal
from app.models import Conversation


def test_conversation_model_exists():
    db = SessionLocal()
    try:
        assert Conversation.__tablename__ == "conversations"
    finally:
        db.close()
