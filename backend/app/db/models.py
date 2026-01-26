# db/models.py
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from .postgres import Base

#Essay Submission Table
class Submission(Base):
    __tablename__ = "submissions"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    status = Column(String, default="queued")  # queued, ocr_processing, ai_processing, completed
    mongo_id = Column(String, nullable=True)  # Link to MongoDB
    created_at = Column(DateTime, default=datetime.utcnow)
    #userId = Column(Integer, ForeignKey("users.id"))  # If user management is added later
