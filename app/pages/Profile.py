import base64
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

import requests
import streamlit as st
from zoneinfo import ZoneInfo

try:
    API_URL = st.secrets["api_url"]
except Exception:
    API_URL = "http://localhost:8000"

APP_TZ = ZoneInfo("Asia/Kolkata")

st.set_page_config(page_title="Profile", layout="centered")
st.markdown(
    """
<style>
.block-container {animation: fadein 0.5s;}
@keyframes fadein {from {opacity: 0; transform: translateY(6px);} to {opacity: 1; transform: translateY(0);}}

div.stButton>button {
  border-radius: 12px;
  padding: 8px 14px;
  transition: transform .15s ease, box-shadow .15s ease;
}
div.stButton>button:hover {transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,.08);}
</style>
""",
    unsafe_allow_html=True,
)

token = st.session_state.get("auth_token")
if not token:
    st.warning("Please login to continue.")
    st.switch_page("frontend.py")

headers = {"Authorization": f"Bearer {token}"}

me_resp = requests.get(f"{API_URL}/me", headers=headers)
if me_resp.status_code != 200:
    st.error("Session expired. Please login again.")
    st.session_state.auth_token = None
    st.switch_page("frontend.py")

me = me_resp.json()

st.title("Profile")

avatar = me.get("photo_data")
if avatar:
    st.image(avatar, width=120)

edit_mode = st.checkbox("Edit Profile", value=False)

st.subheader("Profile Details")
full_name = st.text_input("Full Name", value=me.get("full_name") or "", disabled=not edit_mode)
phone = st.text_input("Phone", value=me.get("phone") or "", disabled=not edit_mode)
current_email = st.text_input("Current Email", value=me.get("email") or "", disabled=True)
new_email = st.text_input("New Email (optional)", disabled=not edit_mode)

uploaded = st.file_uploader("Upload Photo", type=["png", "jpg", "jpeg"], disabled=not edit_mode)
photo_data = None
if uploaded is not None:
    b64 = base64.b64encode(uploaded.read()).decode("utf-8")
    photo_data = f"data:{uploaded.type};base64,{b64}"

st.subheader("Change Password (optional)")
new_password = st.text_input("New Password", type="password", disabled=not edit_mode)

if edit_mode and st.button("Send OTP to Confirm Changes"):
    payload = {
        "full_name": full_name or None,
        "phone": phone or None,
        "photo_data": photo_data,
        "new_email": new_email or None,
        "new_password": new_password or None,
    }
    resp = requests.post(f"{API_URL}/profile/request-change", headers=headers, json=payload)
    if resp.status_code == 200:
        st.success("OTP sent to your current email.")
    else:
        st.error(resp.json().get("detail", "Failed to send OTP."))

otp = st.text_input("Enter OTP", disabled=not edit_mode)
if edit_mode and st.button("Verify & Save"):
    resp = requests.post(f"{API_URL}/profile/verify-change", headers=headers, json={"otp": otp})
    if resp.status_code == 200:
        st.success("Profile updated.")
        st.rerun()
    else:
        st.error(resp.json().get("detail", "Invalid OTP."))

st.divider()
st.subheader("Activity Heatmap")
hm_resp = requests.get(f"{API_URL}/activity/heatmap", headers=headers)
if hm_resp.status_code == 200:
    counts = hm_resp.json()
    # Build simple 12-week heatmap
    today = datetime.now(APP_TZ).date()
    days = [today]
    for i in range(1, 84):
        days.append(today - timedelta(days=i))
    days.reverse()

    max_count = max(counts.values()) if counts else 1
    def color_for(count):
        if count == 0:
            return "#ebedf0"
        if count < max_count * 0.33:
            return "#9be9a8"
        if count < max_count * 0.66:
            return "#40c463"
        return "#216e39"

    squares = []
    for d in days:
        c = counts.get(d.isoformat(), 0)
        squares.append(f"<div title='{d} : {c}' style='width:12px;height:12px;background:{color_for(c)};margin:2px;'></div>")

    grid = "<div style='display:flex;flex-wrap:wrap;width:220px;'>" + "".join(squares) + "</div>"
    st.markdown(grid, unsafe_allow_html=True)

st.divider()
st.subheader("Recent Activity")
recent_resp = requests.get(f"{API_URL}/activity/recent", headers=headers)
if recent_resp.status_code == 200:
    for a in recent_resp.json():
        st.write(f"{a['created_at']} — {a['action']}")

st.divider()
st.subheader("Task Breakdown")
tasks_resp = requests.get(f"{API_URL}/tasks", headers=headers, params={"status": "all"})
tasks = tasks_resp.json() if tasks_resp.status_code == 200 else []
def _is_overdue(t):
    if t["status"] != "active" or not t.get("due_date"):
        return False
    try:
        due_dt = datetime.fromisoformat(t["due_date"])
        if due_dt.tzinfo is None:
            due_dt = due_dt.replace(tzinfo=APP_TZ)
        else:
            due_dt = due_dt.astimezone(APP_TZ)
        return due_dt < datetime.now(APP_TZ)
    except Exception:
        return False

active = len([t for t in tasks if t["status"] == "active"])
completed = len([t for t in tasks if t["status"] == "completed"])
overdue = len([t for t in tasks if _is_overdue(t)])
fig, ax = plt.subplots(figsize=(2.5, 2.5))
ax.pie(
    [active, completed, overdue],
    labels=["Active", "Completed", "Overdue"],
    autopct="%1.0f%%",
    startangle=90,
    textprops={"fontsize": 8},
)
ax.axis("equal")
st.pyplot(fig, use_container_width=False)

st.divider()
if st.button("Back to Home"):
    st.switch_page("pages/Home.py")
