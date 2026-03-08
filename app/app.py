
import os
import signal
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta
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
from app.models import User, Verification, PasswordReset
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
)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8501")

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

@app.on_event("startup")
async def on_startup():
	await init_db()


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
