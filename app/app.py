
from fastapi import FastAPI, Depends, HTTPException
from datetime import datetime, timedelta
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import init_db, get_db
from app.models import User
from app.auth import (
    get_password_hash,
    authenticate_user,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    get_current_active_user,
)
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
