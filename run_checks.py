import asyncio
import json

import httpx

from app.app import app

async def main():
    async with httpx.AsyncClient(app=app, base_url="http://testserver") as client:
        # GET /docs
        r = await client.get("/docs")
        print("GET /docs status:", r.status_code)

        # POST /register with test payload
        payload = {"username": "checkuser", "email": "check@example.com", "password": "testpass"}
        r2 = await client.post("/register", json=payload)
        print("POST /register status:", r2.status_code)
        try:
            print("Response JSON:", r2.json())
        except Exception:
            print("Response text:", r2.text[:400])

if __name__ == '__main__':
    asyncio.run(main())
