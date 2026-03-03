from fastapi.testclient import TestClient
from app.app import app

client = TestClient(app)

resp = client.get('/docs')
print('GET /docs status:', resp.status_code)

payload = {"username": "checkuser", "email": "check@example.com", "password": "testpass"}
resp2 = client.post('/register', json=payload)
print('POST /register status:', resp2.status_code)
try:
    print('Response JSON:', resp2.json())
except Exception:
    print('Response text:', resp2.text[:400])
