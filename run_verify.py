from fastapi.testclient import TestClient
from app.app import app

client = TestClient(app)

otp = "459077"
# send as query param so FastAPI picks it up as simple parameter
resp = client.post(f'/verify?otp={otp}')
print('POST /verify status:', resp.status_code)
print(resp.text[:1000])

# now try to login with the credentials we registered earlier
token_resp = client.post('/token', data={'username': 'checkuser', 'password': 'testpass'})
print('/token status:', token_resp.status_code)
try:
	print('token response:', token_resp.json())
	access = token_resp.json().get('access_token')
except Exception:
	print('token response text:', token_resp.text[:400])
	access = None

if access:
	users_resp = client.get('/users/', headers={'Authorization': f'Bearer {access}'})
	print('GET /users/ status:', users_resp.status_code)
	try:
		print('users:', users_resp.json())
	except Exception:
		print('users text:', users_resp.text[:400])
