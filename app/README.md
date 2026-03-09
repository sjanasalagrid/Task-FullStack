Quick setup: FastAPI + Streamlit + PostgreSQL (async SQLAlchemy)

**Setup**
1) Create `.env` in `Project/.env`:

```
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5432/DBNAME
SECRET_KEY=REPLACE_WITH_SECURE_SECRET
FROM_EMAIL=you@example.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@example.com
SMTP_PASSWORD=REPLACE_WITH_APP_PASSWORD
STREAMLIT_SECRETS=[api]\nurl = "http://localhost:8000"
FRONTEND_URL=http://localhost:8501
ENABLE_REMINDER_SCHEDULER=1
APP_TZ=Asia/Kolkata
```

2) Install dependencies:

```bash
pip install -r requirements.txt
```

3) Run the app (FastAPI + Streamlit together):

```bash
cd Project
python -m app.app
```

**JWT authentication**
- POST `/token` with form data `username` and `password`.
- Include token in requests: `Authorization: Bearer <token>`.

**Migrations (Alembic)**
```bash
cd Project/app
alembic upgrade head
```

To generate a new migration after model changes:
```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

**Streamlit frontend (standalone)**
```bash
cd Project/app
streamlit run frontend.py --server.port 8501
```

---

## SMTP App Password (Gmail)
1) Enable 2‑Step Verification on your Google account.
2) Create an App Password (Google Account → Security → App passwords).
3) Use that app password as `SMTP_PASSWORD`.

---

## Database Schema (High Level)

**users**
- id (PK)
- username (unique)
- email (unique)
- password_hash
- full_name, phone, photo_data
- created_at

**tasks**
- id (PK)
- user_id (FK → users.id)
- title, description
- priority, status
- due_date, reminder_at
- tags, tag_colors
- recurrence
- reminder_sent_day_before, reminder_sent_30min
- created_at, updated_at, completed_at
- is_deleted

**subtasks**
- id (PK)
- task_id (FK → tasks.id)
- title, is_done

**task_activity**
- id (PK)
- task_id (FK → tasks.id)
- user_id (FK → users.id)
- action, created_at

**task_versions**
- id (PK)
- task_id (FK → tasks.id)
- user_id (FK → users.id)
- version, action
- snapshot fields (title, description, status, etc.)
- created_at

**task_drafts**
- id (PK)
- task_id (FK → tasks.id)
- user_id (FK → users.id)
- draft fields (title, description, etc.)
- updated_at

**verifications**
- id (PK)
- otp, username, email, password_hash
- created_at, expires_at

**password_resets**
- id (PK)
- email, reset_token
- otp, otp_sent_at, otp_expires_at
- created_at, expires_at, used_at

**user_update_requests**
- id (PK)
- user_id (FK → users.id)
- otp
- new_email, new_password_hash
- new_full_name, new_phone, new_photo_data
- created_at, expires_at

---

## System Design (High Level)

```
User
  └─> Streamlit UI (frontend.py / pages)
         └─> FastAPI (app.py)
               ├─> PostgreSQL (async SQLAlchemy)
               └─> SMTP Email (OTP + reminders)
```

**Notes**
- `.env` is ignored by git (secrets must not be committed).
- Scheduler sends reminder emails based on `reminder_at`.
