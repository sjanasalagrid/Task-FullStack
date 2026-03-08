from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text

from .db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # new nullable bio column for testing migrations
    bio = Column(Text, nullable=True)


class Verification(Base):
    __tablename__ = "verifications"

    id = Column(Integer, primary_key=True, index=True)
    otp = Column(String(6), index=True, nullable=False)
    username = Column(String, nullable=False)
    email = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)


class PasswordReset(Base):
    __tablename__ = "password_resets"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True, nullable=False)
    reset_token = Column(String, unique=True, index=True, nullable=False)
    otp = Column(String(6), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    otp_expires_at = Column(DateTime, nullable=True)
    otp_sent_at = Column(DateTime, nullable=True)
    used_at = Column(DateTime, nullable=True)
