from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey

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


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String, default="Medium", nullable=False)
    status = Column(String, default="active", nullable=False)
    due_date = Column(DateTime, nullable=True)
    tags = Column(String, nullable=True)
    tag_colors = Column(Text, nullable=True)
    recurrence = Column(String, nullable=True)  # none|daily|weekly
    reminder_at = Column(DateTime, nullable=True)
    reminder_sent_day_before = Column(Boolean, default=False, nullable=False)
    reminder_sent_30min = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)


class Subtask(Base):
    __tablename__ = "subtasks"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), index=True, nullable=False)
    title = Column(String, nullable=False)
    is_done = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class TaskActivity(Base):
    __tablename__ = "task_activity"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    action = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class TaskDraft(Base):
    __tablename__ = "task_drafts"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    priority = Column(String, nullable=True)
    due_date = Column(DateTime, nullable=True)
    tags = Column(String, nullable=True)
    tag_colors = Column(Text, nullable=True)
    recurrence = Column(String, nullable=True)
    reminder_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class TaskVersion(Base):
    __tablename__ = "task_versions"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    version = Column(Integer, nullable=False)
    action = Column(String, nullable=False)
    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    priority = Column(String, nullable=True)
    status = Column(String, nullable=True)
    due_date = Column(DateTime, nullable=True)
    tags = Column(String, nullable=True)
    tag_colors = Column(Text, nullable=True)
    recurrence = Column(String, nullable=True)
    reminder_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
