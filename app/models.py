from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Date, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
from .database import Base

def get_ist_time():
    return datetime.utcnow() + timedelta(hours=5, minutes=30)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    age = Column(Integer)
    
    reports = relationship("Report", back_populates="owner")
    fitbit_account = relationship("FitbitAccount", back_populates="user", uselist=False)
    fitbit_sleep_data = relationship("FitbitSleepData", back_populates="user")

class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=get_ist_time)
    
    physical_score = Column(Float)
    mental_score = Column(Float)
    vocal_score = Column(Float)
    overall_score = Column(Float)
    status = Column(String)
    advice = Column(Text)
    
    owner = relationship("User", back_populates="reports")

class FitbitAccount(Base):
    __tablename__ = "fitbit_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    fitbit_user_id = Column(String(100))
    access_token = Column(Text)
    refresh_token = Column(Text)
    token_expires_at = Column(DateTime)
    created_at = Column(DateTime, default=get_ist_time)
    
    user = relationship("User", back_populates="fitbit_account")

class FitbitSleepData(Base):
    __tablename__ = "fitbit_sleep_data"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(Date)
    sleep_data = Column(JSON)
    created_at = Column(DateTime, default=get_ist_time)
    
    user = relationship("User", back_populates="fitbit_sleep_data")
    
    __table_args__ = (
        {"sqlite_autoincrement": True}
    )
