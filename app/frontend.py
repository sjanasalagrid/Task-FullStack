import streamlit as st
import requests
from passlib.context import CryptContext
# pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
# print(pwd_ctx.hash("st1ng"))   # copy the output

# attempt to read api_url from secrets, fall back to localhost
try:
    API_URL = st.secrets["api_url"]
except Exception:
    API_URL = "http://localhost:8000"

# you can create a file at .streamlit/secrets.toml with:
# [api]
# url = "http://localhost:8000"
# or set STREAMLIT_SECRETS environment variable

st.title("Login to FastAPI")

username = st.text_input("Username")
password = st.text_input("Password", type="password")

if st.button("Login"):
    if username and password:
        payload = {"username": username, "password": password}
        # use OAuth2 password flow
        response = requests.post(f"{API_URL}/token", data=payload)
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            st.success("Logged in!")
            st.write("JWT:", token)
            # example subsequent call
            headers = {"Authorization": f"Bearer {token}"}
            users_resp = requests.get(f"{API_URL}/users/", headers=headers)
            if users_resp.status_code == 200:
                st.write("Users:", users_resp.json())
            else:
                st.error(f"Failed fetching users: {users_resp.status_code}")
        else:
            st.error("Login failed: " + response.text)
    else:
        st.warning("Please enter both username and password.")

