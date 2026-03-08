import time
from datetime import datetime

import requests
import streamlit as st

# attempt to read api_url from secrets, fall back to localhost
try:
    API_URL = st.secrets["api_url"]
except Exception:
    API_URL = "http://localhost:8000"

st.set_page_config(page_title="Reset Password", layout="centered")
st.title("Reset Password")

if "reset_token" not in st.session_state:
    st.session_state.reset_token = None
if "otp_sent_at" not in st.session_state:
    st.session_state.otp_sent_at = None

reset_token_param = st.query_params.get("reset_token")
if reset_token_param:
    st.session_state.reset_token = reset_token_param

if not st.session_state.reset_token:
    st.write("Enter your registered email to receive a reset link.")
    fp_email = st.text_input("Registered Email", key="fp_email")
    if st.button("Send Reset Link", key="send_reset_link"):
        if not fp_email:
            st.warning("Please enter your email.")
        else:
            resp = requests.post(f"{API_URL}/forgot-password", json={"email": fp_email})
            if resp.status_code == 200:
                st.info("If the email exists, a reset link has been sent.")
            else:
                st.error("Failed to send reset link.")
else:
    st.write("Enter the OTP sent to your email and set a new password.")

    if st.session_state.otp_sent_at is None:
        start_resp = requests.post(
            f"{API_URL}/reset/start",
            data={"reset_token": st.session_state.reset_token},
        )
        if start_resp.status_code == 200:
            data = start_resp.json()
            otp_sent_at = data.get("otp_sent_at")
            if otp_sent_at:
                st.session_state.otp_sent_at = otp_sent_at
        else:
            st.error("Reset token invalid or expired.")

    otp = st.text_input("OTP", key="reset_otp", max_chars=6)
    new_password = st.text_input("New Password", type="password", key="reset_new_password")
    confirm_password = st.text_input("Confirm New Password", type="password", key="reset_confirm_password")

    # Resend OTP after 3 minutes
    resend_enabled = True
    if st.session_state.otp_sent_at:
        sent_dt = datetime.fromisoformat(st.session_state.otp_sent_at)
        sent_ts = sent_dt.timestamp()
        remaining = max(0, 180 - int(time.time() - sent_ts))
        if remaining > 0:
            resend_enabled = False
            st.info(f"You can resend OTP in {remaining} seconds.")

    if st.button("Resend OTP", key="resend_otp", disabled=not resend_enabled):
        start_resp = requests.post(
            f"{API_URL}/reset/start",
            data={"reset_token": st.session_state.reset_token},
        )
        if start_resp.status_code == 200:
            data = start_resp.json()
            otp_sent_at = data.get("otp_sent_at")
            if otp_sent_at:
                st.session_state.otp_sent_at = otp_sent_at
            st.success("OTP sent.")
        else:
            st.error("Could not resend OTP.")

    if st.button("Reset Password", key="reset_password_btn"):
        if not otp or not new_password or not confirm_password:
            st.warning("Please fill all fields.")
        elif new_password != confirm_password:
            st.warning("Passwords do not match.")
        elif len(new_password.encode("utf-8")) > 72:
            st.error("Password too long (max 72 bytes).")
        else:
            resp = requests.post(
                f"{API_URL}/reset/verify",
                json={
                    "reset_token": st.session_state.reset_token,
                    "otp": otp,
                    "new_password": new_password,
                },
            )
            if resp.status_code == 200:
                st.success("Password reset successful. You can login now.")
                st.session_state.reset_token = None
                st.session_state.otp_sent_at = None
                st.query_params.clear()
                st.switch_page("frontend.py")
            else:
                st.error(resp.json().get("detail", "Reset failed."))

st.divider()
if st.button("Back to Login", key="back_to_login"):
    st.switch_page("frontend.py")
