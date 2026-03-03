
from fastapi import FastAPI, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from datetime import datetime, timedelta
from uuid import uuid4
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import init_db, get_db
from app.models import User, Verification
from app.auth import (
    get_password_hash,
    authenticate_user,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    get_current_active_user,
)
from app.email_utils import send_verification_email
from fastapi.security import OAuth2PasswordRequestForm

app = FastAPI()


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    created_at: datetime = None

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

    # redirect user to verification page after registration
    return RedirectResponse(url="/verify", status_code=303)


@app.get("/verify", response_class=HTMLResponse)
async def verify_form():
    # show simple HTML form for entering OTP
    return """
    <html>
        <head><meta charset="utf-8"><title>Enter OTP</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>Enter Verification Code</h1>
            <form method="post" action="/verify">
                <input type="text" name="otp" placeholder="6-digit code" maxlength="6" required>
                <br><br>
                <button type="submit">Verify</button>
            </form>
        </body>
    </html>
    """


@app.post("/verify", response_class=HTMLResponse)
async def verify_submit(otp: str = Form(None), db: AsyncSession = Depends(get_db)):
    if not otp:
        return "<html><body><h1>No code provided.</h1></body></html>"
    result = await db.execute(select(Verification).filter_by(otp=otp))
    v = result.scalars().first()
    if not v:
        return "<html><body><h1>Invalid code.</h1></body></html>"
    if v.expires_at < datetime.utcnow():
        return "<html><body><h1>Code expired. Please register again.</h1></body></html>"

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
    return RedirectResponse(url="http://localhost:8501", status_code=303)


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
            <h1>Hello, {username}!</h1>
            <p>You are logged in via verification link.</p>
        </body>
    </html>
    """
