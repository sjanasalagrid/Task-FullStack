
import os
import signal
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from uuid import uuid4

from fastapi import FastAPI, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        os.environ.setdefault(key, value)


_load_env()

from app.db import init_db, get_db
from app.models import (
    User,
    Verification,
    PasswordReset,
    Task,
    Subtask,
    TaskActivity,
    TaskDraft,
    TaskVersion,
    UserUpdateRequest,
)
from app.auth import (
    get_password_hash,
    authenticate_user,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    get_current_active_user,
)
from app.email_utils import (
    send_verification_email,
    send_reset_link_email,
    send_reset_otp_email,
    send_task_reminder_email,
    send_task_event_email,
)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8501")
ENABLE_REMINDER_SCHEDULER = os.getenv("ENABLE_REMINDER_SCHEDULER", "1") == "1"
APP_TZ = ZoneInfo(os.getenv("APP_TZ", "Asia/Kolkata"))
_scheduler: AsyncIOScheduler | None = None

app = FastAPI()


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    created_at: datetime = None


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    reset_token: str
    otp: str
    new_password: str


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    priority: str = "Medium"
    due_date: datetime | None = None
    tags: list[str] | None = None
    tag_colors: dict[str, str] | None = None
    recurrence: str | None = None
    reminder_at: datetime | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    status: str | None = None
    due_date: datetime | None = None
    tags: list[str] | None = None
    tag_colors: dict[str, str] | None = None
    recurrence: str | None = None
    reminder_at: datetime | None = None
    is_deleted: bool | None = None


class SubtaskCreate(BaseModel):
    title: str


class SubtaskUpdate(BaseModel):
    title: str | None = None
    is_done: bool | None = None


class TaskDraftPayload(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    due_date: datetime | None = None
    tags: list[str] | None = None
    tag_colors: dict[str, str] | None = None
    recurrence: str | None = None
    reminder_at: datetime | None = None


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    photo_data: str | None = None
    new_email: str | None = None
    new_password: str | None = None


class ProfileVerifyRequest(BaseModel):
    otp: str

@app.on_event("startup")
async def on_startup():
    await init_db()
    if ENABLE_REMINDER_SCHEDULER:
        global _scheduler
        if _scheduler is None:
            _scheduler = AsyncIOScheduler()
            _scheduler.add_job(_run_reminder_job, "interval", minutes=1, id="reminder_job")
            _scheduler.start()


@app.post("/users/")
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check for existing username
    result = await db.execute(select(User).filter_by(username=user.username))
    existing = result.scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")

    # Check for existing email
    result = await db.execute(select(User).filter_by(email=user.email))
    existing = result.scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # validate password length for bcrypt
    if len(user.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password too long (max 72 bytes)")

    new_user = User(
        username=user.username,
        email=user.email,
        password_hash=get_password_hash(user.password),
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return {"id": new_user.id, "username": new_user.username, "email": new_user.email, "created_at": new_user.created_at}


@app.post("/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=400,
            detail="Incorrect username or password",
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires,
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/users/")
async def list_users(db: AsyncSession = Depends(get_db), current_user=Depends(get_current_active_user)):
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [{"id": u.id, "username": u.username, "email": u.email, "created_at": u.created_at} for u in users]


def _serialize_tag_colors(tag_colors: dict[str, str] | None) -> str | None:
    if not tag_colors:
        return None
    return "|".join([f"{k}:{v}" for k, v in tag_colors.items()])


def _parse_tag_colors(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    result: dict[str, str] = {}
    for item in raw.split("|"):
        if ":" in item:
            k, v = item.split(":", 1)
            result[k] = v
    return result


async def _log_activity(db: AsyncSession, user_id: int, task_id: int, action: str):
    db.add(
        TaskActivity(
            user_id=user_id,
            task_id=task_id,
            action=action,
            created_at=datetime.utcnow(),
        )
    )
    await db.commit()


def _to_app_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=APP_TZ)
    return dt.astimezone(APP_TZ)


def _normalize_dt_for_db(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(APP_TZ).replace(tzinfo=None)
    return dt


async def _save_version(db: AsyncSession, user_id: int, task: Task, action: str):
    result = await db.execute(
        select(TaskVersion).filter_by(task_id=task.id).order_by(TaskVersion.version.desc())
    )
    latest = result.scalars().first()
    next_version = (latest.version + 1) if latest else 1

    db.add(
        TaskVersion(
            task_id=task.id,
            user_id=user_id,
            version=next_version,
            action=action,
            title=task.title,
            description=task.description,
            priority=task.priority,
            status=task.status,
            due_date=task.due_date,
            tags=task.tags,
            tag_colors=task.tag_colors,
            recurrence=task.recurrence,
            reminder_at=task.reminder_at,
            created_at=datetime.utcnow(),
        )
    )
    await db.commit()


@app.get("/me")
async def me(current_user=Depends(get_current_active_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "phone": current_user.phone,
        "photo_data": current_user.photo_data,
        "created_at": current_user.created_at,
    }


@app.post("/profile/request-change")
async def profile_request_change(
    payload: ProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    # Validate new email if provided
    if payload.new_email:
        result = await db.execute(select(User).filter_by(email=payload.new_email))
        if result.scalars().first():
            raise HTTPException(status_code=400, detail="Email already registered")

    if payload.new_password and len(payload.new_password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password too long (max 72 bytes)")

    import random
    otp = f"{random.randint(0, 999999):06d}"
    expires = datetime.utcnow() + timedelta(minutes=10)

    req = UserUpdateRequest(
        user_id=current_user.id,
        otp=otp,
        new_email=payload.new_email,
        new_password_hash=get_password_hash(payload.new_password) if payload.new_password else None,
        new_full_name=payload.full_name,
        new_phone=payload.phone,
        new_photo_data=payload.photo_data,
        created_at=datetime.utcnow(),
        expires_at=expires,
    )
    db.add(req)
    await db.commit()

    try:
        send_verification_email(current_user.email, otp)
    except Exception as e:
        print("send_verification_email failed:", e)

    return {"msg": "otp_sent"}


@app.post("/profile/verify-change")
async def profile_verify_change(
    payload: ProfileVerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    result = await db.execute(
        select(UserUpdateRequest)
        .filter_by(user_id=current_user.id)
        .order_by(UserUpdateRequest.created_at.desc())
    )
    req = result.scalars().first()
    if not req:
        raise HTTPException(status_code=400, detail="No pending change")
    if req.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="OTP expired")
    if req.otp != payload.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    if req.new_email:
        current_user.email = req.new_email
    if req.new_password_hash:
        current_user.password_hash = req.new_password_hash
    if req.new_full_name is not None:
        current_user.full_name = req.new_full_name
    if req.new_phone is not None:
        current_user.phone = req.new_phone
    if req.new_photo_data is not None:
        current_user.photo_data = req.new_photo_data

    await db.delete(req)
    await db.commit()
    try:
        send_task_event_email(current_user.email, "Profile", "Info", "updated")
    except Exception as e:
        print("send_task_event_email failed:", e)
    return {"msg": "profile_updated"}


@app.get("/activity/recent")
async def activity_recent(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    result = await db.execute(
        select(TaskActivity)
        .filter_by(user_id=current_user.id)
        .order_by(TaskActivity.created_at.desc())
        .limit(20)
    )
    acts = result.scalars().all()
    return [{"action": a.action, "created_at": a.created_at} for a in acts]


@app.get("/activity/heatmap")
async def activity_heatmap(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    result = await db.execute(
        select(TaskActivity).filter_by(user_id=current_user.id).order_by(TaskActivity.created_at.desc())
    )
    acts = result.scalars().all()
    counts: dict[str, int] = {}
    for a in acts:
        day = a.created_at.date().isoformat()
        counts[day] = counts.get(day, 0) + 1
    return counts


@app.get("/tasks")
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
    status: str | None = None,
    priority: str | None = None,
):
    if status == "bin":
        query = select(Task).filter_by(user_id=current_user.id, is_deleted=True)
    else:
        query = select(Task).filter_by(user_id=current_user.id, is_deleted=False)
        if status and status not in ("all", "bin"):
            query = query.filter_by(status=status)
    if priority and priority != "all":
        query = query.filter_by(priority=priority)
    result = await db.execute(query.order_by(Task.created_at.desc()))
    tasks = result.scalars().all()

    task_ids = [t.id for t in tasks]
    subtasks_map: dict[int, list[dict]] = {}
    if task_ids:
        sub_result = await db.execute(select(Subtask).filter(Subtask.task_id.in_(task_ids)))
        subs = sub_result.scalars().all()
        for s in subs:
            subtasks_map.setdefault(s.task_id, []).append(
                {
                    "id": s.id,
                    "title": s.title,
                    "is_done": s.is_done,
                    "created_at": s.created_at,
                    "updated_at": s.updated_at,
                }
            )
    draft_ids: set[int] = set()
    if task_ids:
        draft_result = await db.execute(
            select(TaskDraft).filter(TaskDraft.task_id.in_(task_ids), TaskDraft.user_id == current_user.id)
        )
        drafts = draft_result.scalars().all()
        draft_ids = {d.task_id for d in drafts}
    return [
        {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "priority": t.priority,
            "status": t.status,
            "due_date": t.due_date,
            "tags": t.tags.split(",") if t.tags else [],
            "tag_colors": _parse_tag_colors(t.tag_colors),
            "recurrence": t.recurrence,
            "reminder_at": t.reminder_at,
            "reminder_sent_day_before": t.reminder_sent_day_before,
            "reminder_sent_30min": t.reminder_sent_30min,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
            "completed_at": t.completed_at,
            "subtasks": subtasks_map.get(t.id, []),
            "has_draft": t.id in draft_ids,
        }
        for t in tasks
    ]


@app.post("/tasks")
async def create_task(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    task = Task(
        user_id=current_user.id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        status="active",
        due_date=_normalize_dt_for_db(payload.due_date),
        tags=",".join(payload.tags) if payload.tags else None,
        tag_colors=_serialize_tag_colors(payload.tag_colors),
        recurrence=payload.recurrence,
        reminder_at=_normalize_dt_for_db(payload.reminder_at),
        reminder_sent_day_before=False,
        reminder_sent_30min=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    await _log_activity(db, current_user.id, task.id, "created")
    await _save_version(db, current_user.id, task, "created")
    try:
        send_task_event_email(current_user.email, task.title, task.priority, "created")
    except Exception as e:
        print("send_task_event_email failed:", e)
    return {"id": task.id}


@app.patch("/tasks/{task_id}")
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    result = await db.execute(
        select(Task).filter_by(id=task_id, user_id=current_user.id, is_deleted=False)
    )
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    old_due = task.due_date

    if payload.title is not None:
        task.title = payload.title
    if payload.description is not None:
        task.description = payload.description
    if payload.priority is not None:
        task.priority = payload.priority
    if payload.status is not None:
        task.status = payload.status
        if payload.status == "completed":
            task.completed_at = datetime.utcnow()
            # If recurring, create next instance
            if task.recurrence in ("daily", "weekly"):
                delta_days = 1 if task.recurrence == "daily" else 7
                next_due = (task.due_date + timedelta(days=delta_days)) if task.due_date else None
                next_task = Task(
                    user_id=current_user.id,
                    title=task.title,
                    description=task.description,
                    priority=task.priority,
                    status="active",
                    due_date=next_due,
                    tags=task.tags,
                    tag_colors=task.tag_colors,
                    recurrence=task.recurrence,
                    reminder_at=task.reminder_at,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                db.add(next_task)
            try:
                send_task_event_email(current_user.email, task.title, task.priority, "completed")
            except Exception as e:
                print("send_task_event_email failed:", e)
        if payload.status == "active":
            task.completed_at = None
    if payload.due_date is not None:
        task.due_date = _normalize_dt_for_db(payload.due_date)
    if payload.tags is not None:
        task.tags = ",".join(payload.tags) if payload.tags else None
    if payload.tag_colors is not None:
        task.tag_colors = _serialize_tag_colors(payload.tag_colors)
    if payload.recurrence is not None:
        task.recurrence = payload.recurrence
    if payload.reminder_at is not None:
        normalized_reminder = _normalize_dt_for_db(payload.reminder_at)
        if task.reminder_at != normalized_reminder:
            task.reminder_sent_day_before = False
            task.reminder_sent_30min = False
        task.reminder_at = normalized_reminder
    if payload.is_deleted is not None:
        task.is_deleted = payload.is_deleted

    task.updated_at = datetime.utcnow()
    await db.commit()
    await _log_activity(db, current_user.id, task.id, "updated")
    await _save_version(db, current_user.id, task, "updated")
    if payload.due_date is not None and task.due_date != old_due:
        try:
            send_task_event_email(current_user.email, task.title, task.priority, "due date updated")
        except Exception as e:
            print("send_task_event_email failed:", e)
    return {"msg": "updated"}


@app.delete("/tasks/{task_id}")
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    result = await db.execute(
        select(Task).filter_by(id=task_id, user_id=current_user.id, is_deleted=False)
    )
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.is_deleted = True
    task.updated_at = datetime.utcnow()
    await db.commit()
    await _log_activity(db, current_user.id, task.id, "deleted")
    await _save_version(db, current_user.id, task, "deleted")
    try:
        send_task_event_email(current_user.email, task.title, task.priority, "deleted")
    except Exception as e:
        print("send_task_event_email failed:", e)
    return {"msg": "deleted"}


@app.post("/tasks/{task_id}/restore")
async def restore_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    result = await db.execute(
        select(Task).filter_by(id=task_id, user_id=current_user.id, is_deleted=True)
    )
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.is_deleted = False
    task.updated_at = datetime.utcnow()
    await db.commit()
    await _log_activity(db, current_user.id, task.id, "restored")
    await _save_version(db, current_user.id, task, "restored")
    return {"msg": "restored"}


@app.post("/tasks/{task_id}/clone")
async def clone_task(
    task_id: int,
    new_title: str = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    result = await db.execute(
        select(Task).filter_by(id=task_id, user_id=current_user.id, is_deleted=False)
    )
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not new_title:
        raise HTTPException(status_code=400, detail="Missing title")

    new_task = Task(
        user_id=current_user.id,
        title=new_title,
        description=task.description,
        priority=task.priority,
        status="active",
        due_date=task.due_date,
        tags=task.tags,
        tag_colors=task.tag_colors,
        recurrence=task.recurrence,
        reminder_at=task.reminder_at,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)
    await _log_activity(db, current_user.id, new_task.id, "created")
    await _save_version(db, current_user.id, new_task, "created")
    return {"id": new_task.id}


@app.get("/tasks/{task_id}/versions")
async def list_task_versions(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    result = await db.execute(
        select(Task).filter_by(id=task_id, user_id=current_user.id)
    )
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="Task not found")

    v_result = await db.execute(
        select(TaskVersion)
        .filter_by(task_id=task_id, user_id=current_user.id)
        .order_by(TaskVersion.version.desc())
    )
    versions = v_result.scalars().all()
    return [
        {
            "id": v.id,
            "version": v.version,
            "action": v.action,
            "title": v.title,
            "priority": v.priority,
            "status": v.status,
            "due_date": v.due_date,
            "created_at": v.created_at,
        }
        for v in versions
    ]


@app.post("/tasks/{task_id}/restore-version/{version_id}")
async def restore_task_version(
    task_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    t_result = await db.execute(
        select(Task).filter_by(id=task_id, user_id=current_user.id)
    )
    task = t_result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    v_result = await db.execute(
        select(TaskVersion).filter_by(id=version_id, task_id=task_id, user_id=current_user.id)
    )
    v = v_result.scalars().first()
    if not v:
        raise HTTPException(status_code=404, detail="Version not found")

    task.title = v.title or task.title
    task.description = v.description
    task.priority = v.priority or task.priority
    task.status = v.status or task.status
    task.due_date = v.due_date
    task.tags = v.tags
    task.tag_colors = v.tag_colors
    task.recurrence = v.recurrence
    task.reminder_at = v.reminder_at
    task.updated_at = datetime.utcnow()
    await db.commit()
    await _log_activity(db, current_user.id, task.id, f"restored_version_{v.version}")
    await _save_version(db, current_user.id, task, f"restored_to_{v.version}")
    return {"msg": "version_restored"}


@app.post("/tasks/{task_id}/subtasks")
async def create_subtask(
    task_id: int,
    payload: SubtaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    result = await db.execute(
        select(Task).filter_by(id=task_id, user_id=current_user.id, is_deleted=False)
    )
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    sub = Subtask(
        task_id=task_id,
        title=payload.title,
        is_done=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(sub)
    await db.commit()
    await _log_activity(db, current_user.id, task_id, "subtask_added")
    return {"id": sub.id}


@app.patch("/subtasks/{subtask_id}")
async def update_subtask(
    subtask_id: int,
    payload: SubtaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    result = await db.execute(select(Subtask).filter_by(id=subtask_id))
    sub = result.scalars().first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subtask not found")

    # verify ownership via parent task
    t_result = await db.execute(select(Task).filter_by(id=sub.task_id, user_id=current_user.id))
    if not t_result.scalars().first():
        raise HTTPException(status_code=403, detail="Forbidden")

    if payload.title is not None:
        sub.title = payload.title
    if payload.is_done is not None:
        sub.is_done = payload.is_done
    sub.updated_at = datetime.utcnow()
    await db.commit()
    await _log_activity(db, current_user.id, sub.task_id, "subtask_updated")
    return {"msg": "updated"}


@app.delete("/subtasks/{subtask_id}")
async def delete_subtask(
    subtask_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    result = await db.execute(select(Subtask).filter_by(id=subtask_id))
    sub = result.scalars().first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subtask not found")

    t_result = await db.execute(select(Task).filter_by(id=sub.task_id, user_id=current_user.id))
    if not t_result.scalars().first():
        raise HTTPException(status_code=403, detail="Forbidden")

    await db.delete(sub)
    await db.commit()
    await _log_activity(db, current_user.id, sub.task_id, "subtask_deleted")
    return {"msg": "deleted"}


@app.get("/tasks/{task_id}/activity")
async def task_activity(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    result = await db.execute(select(Task).filter_by(id=task_id, user_id=current_user.id))
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="Task not found")

    act_result = await db.execute(
        select(TaskActivity).filter_by(task_id=task_id).order_by(TaskActivity.created_at.desc())
    )
    acts = act_result.scalars().all()
    return [{"action": a.action, "created_at": a.created_at} for a in acts]


@app.post("/tasks/{task_id}/remind")
async def task_remind(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    result = await db.execute(select(Task).filter_by(id=task_id, user_id=current_user.id))
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        send_task_reminder_email(
            current_user.email,
            task.title,
            task.priority,
            "manual",
            task.due_date.isoformat()[:10] if task.due_date else None,
        )
    except Exception as e:
        print("send_task_reminder_email failed:", e)

    await _log_activity(db, current_user.id, task_id, "reminder_sent")
    return {"msg": "reminder_sent"}


@app.get("/tasks/{task_id}/draft")
async def get_task_draft(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    result = await db.execute(
        select(TaskDraft).filter_by(task_id=task_id, user_id=current_user.id)
    )
    draft = result.scalars().first()
    if not draft:
        return {"draft": None}
    return {
        "draft": {
            "title": draft.title,
            "description": draft.description,
            "priority": draft.priority,
            "due_date": draft.due_date,
            "tags": draft.tags.split(",") if draft.tags else [],
            "tag_colors": _parse_tag_colors(draft.tag_colors),
            "recurrence": draft.recurrence,
            "reminder_at": draft.reminder_at,
            "updated_at": draft.updated_at,
        }
    }


@app.post("/tasks/{task_id}/draft")
async def save_task_draft(
    task_id: int,
    payload: TaskDraftPayload,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    # verify ownership
    result = await db.execute(select(Task).filter_by(id=task_id, user_id=current_user.id))
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="Task not found")

    result = await db.execute(
        select(TaskDraft).filter_by(task_id=task_id, user_id=current_user.id)
    )
    draft = result.scalars().first()
    if not draft:
        draft = TaskDraft(task_id=task_id, user_id=current_user.id)
        db.add(draft)

    if payload.title is not None:
        draft.title = payload.title
    if payload.description is not None:
        draft.description = payload.description
    if payload.priority is not None:
        draft.priority = payload.priority
    if payload.due_date is not None:
        draft.due_date = _normalize_dt_for_db(payload.due_date)
    if payload.tags is not None:
        draft.tags = ",".join(payload.tags) if payload.tags else None
    if payload.tag_colors is not None:
        draft.tag_colors = _serialize_tag_colors(payload.tag_colors)
    if payload.recurrence is not None:
        draft.recurrence = payload.recurrence
    if payload.reminder_at is not None:
        draft.reminder_at = _normalize_dt_for_db(payload.reminder_at)
    draft.updated_at = datetime.utcnow()

    await db.commit()
    await _log_activity(db, current_user.id, task_id, "draft_saved")
    return {"msg": "draft_saved"}


@app.delete("/tasks/{task_id}/draft")
async def delete_task_draft(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    result = await db.execute(
        select(TaskDraft).filter_by(task_id=task_id, user_id=current_user.id)
    )
    draft = result.scalars().first()
    if draft:
        await db.delete(draft)
        await db.commit()
    return {"msg": "draft_deleted"}


@app.get("/tasks/analytics")
async def task_analytics(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    since = datetime.utcnow() - timedelta(days=28)
    result = await db.execute(
        select(Task).filter_by(user_id=current_user.id, is_deleted=False, status="completed")
    )
    tasks = [t for t in result.scalars().all() if t.completed_at and t.completed_at >= since]
    buckets: dict[str, int] = {}
    for t in tasks:
        week_start = (t.completed_at - timedelta(days=t.completed_at.weekday())).date().isoformat()
        buckets[week_start] = buckets.get(week_start, 0) + 1
    return [{"week_start": k, "count": v} for k, v in sorted(buckets.items())]


@app.post("/register")
async def register(user: UserCreate, db: AsyncSession = Depends(get_db)):
    # check for existing username
    result = await db.execute(select(User).filter_by(username=user.username))
    existing = result.scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")

    # check for existing email
    result = await db.execute(select(User).filter_by(email=user.email))
    existing = result.scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # validate password length for bcrypt
    if len(user.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password too long (max 72 bytes)")

    # generate 6-digit OTP
    import random
    otp = f"{random.randint(0, 999999):06d}"
    expires = datetime.utcnow() + timedelta(minutes=10)
    verification = Verification(
        otp=otp,
        username=user.username,
        email=user.email,
        password_hash=get_password_hash(user.password),
        created_at=datetime.utcnow(),
        expires_at=expires,
    )
    db.add(verification)
    await db.commit()

    try:
        send_verification_email(user.email, otp)
    except Exception as e:
        print("send_verification_email failed:", e)

    return {"msg": "otp_sent"}


@app.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    # Always return a generic message to avoid account enumeration
    result = await db.execute(select(User).filter_by(email=payload.email))
    user = result.scalars().first()
    if not user:
        return {"msg": "if_exists_reset_sent"}

    reset_token = uuid4().hex
    expires_at = datetime.utcnow() + timedelta(minutes=30)
    reset = PasswordReset(
        email=payload.email,
        reset_token=reset_token,
        created_at=datetime.utcnow(),
        expires_at=expires_at,
    )
    db.add(reset)
    await db.commit()

    try:
        send_reset_link_email(payload.email, reset_token)
    except Exception as e:
        print("send_reset_link_email failed:", e)

    return {"msg": "if_exists_reset_sent"}


@app.post("/reset/start")
async def reset_start(reset_token: str = Form(None), db: AsyncSession = Depends(get_db)):
    if not reset_token:
        raise HTTPException(status_code=400, detail="Missing reset token")

    result = await db.execute(select(PasswordReset).filter_by(reset_token=reset_token))
    reset = result.scalars().first()
    if not reset or reset.used_at is not None:
        raise HTTPException(status_code=400, detail="Invalid reset token")
    if reset.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Reset token expired")

    now = datetime.utcnow()
    if not reset.otp_sent_at or (now - reset.otp_sent_at).total_seconds() >= 180:
        import random

        reset.otp = f"{random.randint(0, 999999):06d}"
        reset.otp_sent_at = now
        reset.otp_expires_at = now + timedelta(minutes=10)
        await db.commit()

        try:
            send_reset_otp_email(reset.email, reset.otp)
        except Exception as e:
            print("send_reset_otp_email failed:", e)

    return {
        "msg": "otp_sent",
        "otp_sent_at": reset.otp_sent_at.isoformat() if reset.otp_sent_at else None,
    }


@app.post("/reset/verify")
async def reset_verify(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PasswordReset).filter_by(reset_token=payload.reset_token))
    reset = result.scalars().first()
    if not reset or reset.used_at is not None:
        raise HTTPException(status_code=400, detail="Invalid reset token")
    if reset.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Reset token expired")

    if not reset.otp or not reset.otp_expires_at or reset.otp_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="OTP expired. Please resend.")
    if reset.otp != payload.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    if len(payload.new_password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password too long (max 72 bytes)")

    result = await db.execute(select(User).filter_by(email=reset.email))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    user.password_hash = get_password_hash(payload.new_password)
    reset.used_at = datetime.utcnow()
    await db.commit()
    return {"msg": "password_reset_success"}


@app.post("/verify", response_class=HTMLResponse)
async def verify_submit(
    otp: str = Form(None),
    email: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    if not otp or not email:
        return "<html><body><h1>OTP and email are required.</h1></body></html>"

    result = await db.execute(
        select(Verification).filter_by(email=email).order_by(Verification.created_at.desc())
    )
    v = result.scalars().first()
    if not v:
        return "<html><body><h1>No pending verification found for this email.</h1></body></html>"

    # If OTP is invalid or expired, generate and send a new OTP
    if v.otp != otp or v.expires_at < datetime.utcnow():
        import random

        new_otp = f"{random.randint(0, 999999):06d}"
        v.otp = new_otp
        v.created_at = datetime.utcnow()
        v.expires_at = datetime.utcnow() + timedelta(minutes=10)
        await db.commit()

        try:
            send_verification_email(email, new_otp)
        except Exception as e:
            print("send_verification_email failed:", e)

        return (
            "<html><body><h1>Invalid or expired code. "
            "A new OTP has been sent to your email.</h1></body></html>"
        )

    # ensure username/email still unique
    result = await db.execute(select(User).filter_by(username=v.username))
    if result.scalars().first():
        return "<html><body><h1>Username already registered.</h1></body></html>"
    result = await db.execute(select(User).filter_by(email=v.email))
    if result.scalars().first():
        return "<html><body><h1>Email already registered.</h1></body></html>"

    new_user = User(
        username=v.username,
        email=v.email,
        password_hash=v.password_hash,
    )
    db.add(new_user)
    await db.delete(v)
    await db.commit()
    await db.refresh(new_user)

    # redirect to login page after successful verification
    return RedirectResponse(url=FRONTEND_URL, status_code=303)


@app.get("/hello", response_class=HTMLResponse)
async def hello(token: str):
    # verify token using auth utility
    from app.auth import verify_token_username

    username = verify_token_username(token)
    if not username:
        return "<html><body><h1>Invalid or expired token</h1></body></html>"
    return f"""
    <html>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>Welcome, {username}!</h1>
            <p>Status: Logged in</p>
        </body>
    </html>
    """


def _run_dev_stack():
    # Run FastAPI (uvicorn) and Streamlit in parallel for local dev
    python_exe = sys.executable
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    uvicorn_cmd = [
        python_exe,
        "-m",
        "uvicorn",
        "app.app:app",
        "--reload",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]
    streamlit_cmd = [
        python_exe,
        "-m",
        "streamlit",
        "run",
        "app/frontend.py",
        "--server.address",
        "0.0.0.0",
        "--server.port",
        "8501",
    ]

    uvicorn_proc = subprocess.Popen(uvicorn_cmd, env=env)
    streamlit_proc = subprocess.Popen(streamlit_cmd, env=env)

    def _shutdown(*_args):
        for proc in (uvicorn_proc, streamlit_proc):
            if proc.poll() is None:
                proc.terminate()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Wait until one exits, then shut down the other
    exit_code = None
    try:
        exit_code = uvicorn_proc.wait()
    finally:
        _shutdown()
        if exit_code is None:
            exit_code = streamlit_proc.wait()
    sys.exit(exit_code)


async def _run_reminder_job():
    async for db in get_db():
        now = datetime.now(APP_TZ)
        result = await db.execute(
            select(Task, User)
            .join(User, Task.user_id == User.id)
            .filter(Task.is_deleted == False)  # noqa: E712
            .filter(Task.status == "active")
            .filter(Task.reminder_at.isnot(None))
        )
        rows = result.all()
        for task, user in rows:
            if task.reminder_at is None:
                continue

            reminder_at = _to_app_tz(task.reminder_at)
            window_start = now - timedelta(minutes=1)
            window_end = now + timedelta(minutes=1)

            if not task.reminder_sent_30min and window_start <= reminder_at <= window_end:
                try:
                    send_task_reminder_email(
                        user.email,
                        task.title,
                        task.priority,
                        "custom",
                        reminder_at.astimezone(APP_TZ).isoformat()[:16].replace("T", " ") + " IST",
                    )
                except Exception as e:
                    print("send_task_reminder_email failed:", e)
                task.reminder_sent_30min = True

        await db.commit()


if __name__ == "__main__":
    _run_dev_stack()

'''
# PostgreSQL command to truncate all tables and reset identity (auto-increment) counters
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
    EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' RESTART IDENTITY CASCADE';
  END LOOP;
END $$;

'''
