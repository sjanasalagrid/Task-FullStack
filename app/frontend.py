import streamlit as st
import requests
from passlib.context import CryptContext
import time
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

st.set_page_config(page_title="FastAPI Auth", layout="centered")
st.title("FastAPI Authentication")

# Initialize session state for page toggle
if "show_register" not in st.session_state:
    st.session_state.show_register = False
if "show_verify" not in st.session_state:
    st.session_state.show_verify = False
if "auth_token" not in st.session_state:
    st.session_state.auth_token = None

# Toggle between login and registration
col1, col2 = st.columns(2)
with col1:
    if st.button("Login", key="toggle_login"):
        st.session_state.show_register = False
with col2:
    if st.button("Register", key="toggle_register"):
        st.session_state.show_register = True

st.divider()

if st.session_state.show_register:
    # ===== REGISTRATION FORM =====
    st.subheader("Create Account")
    reg_username = st.text_input("Username##reg", key="reg_username")
    reg_email = st.text_input("Email", key="reg_email")
    reg_password = st.text_input("Password##reg", type="password", key="reg_password")
    reg_confirm = st.text_input("Confirm Password", type="password", key="reg_confirm")

    if st.button("Sign Up", key="signup_btn"):
        if not all([reg_username, reg_email, reg_password, reg_confirm]):
            st.warning("Please fill all fields.")
        elif reg_password != reg_confirm:
            st.warning("Passwords don't match.")
        elif len(reg_password) > 72:
            st.error("Password too long (max 72 bytes).")
        else:
            payload = {
                "username": reg_username,
                "email": reg_email,
                "password": reg_password,
            }
            response = requests.post(f"{API_URL}/register", json=payload)
            if response.status_code == 200:
                st.success("Registration successful! An OTP has been sent to your email.")
                st.session_state.show_verify = True
                st.rerun()
            else:
                try:
                    error_detail = response.json().get('detail', response.text)
                except:
                    error_detail = response.text
                st.error(f"Registration failed: {error_detail}")

    if st.session_state.show_verify:
        st.divider()
        st.subheader("Verify OTP")
        otp = st.text_input("6-digit code", key="verify_otp", max_chars=6)
        if st.button("Verify", key="verify_btn"):
            if not otp:
                st.warning("Please enter the code you received.")
            else:
                email = st.session_state.get("reg_email")
                if not email:
                    st.error("Missing email for verification. Please register again.")
                    st.session_state.show_verify = False
                    st.rerun()
                verify_resp = requests.post(
                    f"{API_URL}/verify",
                    data={"otp": otp, "email": email},
                    allow_redirects=False,
                )
                if verify_resp.status_code in (302, 303):
                    st.session_state.show_register = False
                    st.session_state.show_verify = False
                    st.success("OTP is valid. You can login successfully.")
                    time.sleep(1)
                    st.switch_page("frontend.py")
                elif verify_resp.status_code == 200:
                    st.info("Verification response:")
                    st.write(verify_resp.text)
                else:
                    st.error(f"Verification failed: {verify_resp.text}")

else:
    # ===== LOGIN FORM =====
    st.subheader("Sign In")
    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")

    if st.button("Forgot Password?", key="forgot_btn"):
        st.switch_page("pages/Reset.py")

    if st.button("Login", key="login_btn"):
        if username and password:
            payload = {"username": username, "password": password}
            # use OAuth2 password flow
            response = requests.post(f"{API_URL}/token", data=payload)
            if response.status_code == 200:
                data = response.json()
                token = data.get("access_token")
                if not token:
                    st.error("Login failed: missing token in response.")
                else:
                    st.session_state.auth_token = token
                    st.switch_page("pages/Home.py")
            else:
                st.error("Login failed: " + response.text)
        else:
            st.warning("Please enter both username and password.")
