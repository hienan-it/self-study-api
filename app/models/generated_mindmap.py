from sqlalchemy import Column, Integer, JSON, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base

class GeneratedMindmap(Base):
    __tablename__ = "generated_mindmaps"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    root_node_id = Column(Integer, ForeignKey("knowledge_nodes.id"))
    structure = Column(JSON)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())