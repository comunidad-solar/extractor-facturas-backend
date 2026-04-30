from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime
from api.db.database import Base


class SessionRecord(Base):
    __tablename__ = "sessions"

    session_id = Column(String(36), primary_key=True, index=True)
    payload    = Column(Text, nullable=False)        # JSON string
    url        = Column(Text, nullable=True)          # plan URL (metadata)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)      # NULL = persist forever
