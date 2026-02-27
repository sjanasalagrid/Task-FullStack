Quick setup: FastAPI + PostgreSQL (async SQLAlchemy)

1) Set `DATABASE_URL` environment variable, e.g.:

   export DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/mydb"

2) Install dependencies:

   pip install -r requirements.txt

3) Run the app:

   uvicorn app.app:app --reload --host 0.0.0.0 --port 8000

4) JWT authentication:

   - POST `/token` with form data `username` and `password` to receive an access token.
   - Include the token in requests as `Authorization: Bearer <token>` (e.g. to call `/users/`).

5) Streamlit frontend (optional):

   streamlit run frontend.py --server.port 8501
   # The frontend will prompt for username/password and contact the FastAPI server.
   # You can override the API endpoint by setting STREAMLIT_SECRETS in 
   # `~/.streamlit/secrets.toml`:
   #
   # [api]
   # url = "http://localhost:8000"

Notes:
- `init_db()` runs on startup and will create tables defined in `models.py`.
- Replace the default `DATABASE_URL` with your credentials.
