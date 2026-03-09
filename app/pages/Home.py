import requests
import streamlit as st
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import base64
import matplotlib.pyplot as plt

# attempt to read api_url from secrets, fall back to localhost
try:
    API_URL = st.secrets["api_url"]
except Exception:
    API_URL = "http://localhost:8000"
APP_TZ = ZoneInfo("Asia/Kolkata")

COLOR_MAP = {
    "red": "#ff4d4d",
    "green": "#4caf50",
    "blue": "#2196f3",
    "yellow": "#fbc02d",
    "orange": "#ff9800",
    "purple": "#9c27b0",
    "pink": "#e91e63",
    "teal": "#009688",
    "gray": "#9e9e9e",
    "black": "#212121",
}


def _normalize_color(value: str) -> str:
    v = value.strip().lower()
    if v in COLOR_MAP:
        return COLOR_MAP[v]
    if v.startswith("#") and len(v) in (4, 7):
        return v
    return "#9e9e9e"

st.set_page_config(page_title="Home", layout="wide")
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

.stMetric {
  background: #f8f9fb;
  border-radius: 12px;
  padding: 8px 12px;
}
</style>
""",
    unsafe_allow_html=True,
)

token = st.session_state.get("auth_token")
if not token:
    st.warning("Please login to continue.")
    st.switch_page("frontend.py")

headers = {"Authorization": f"Bearer {token}"}

if "flash_message" not in st.session_state:
    st.session_state.flash_message = None

me_resp = requests.get(f"{API_URL}/me", headers=headers)
if me_resp.status_code != 200:
    st.error("Session expired. Please login again.")
    st.session_state.auth_token = None
    st.switch_page("frontend.py")

me = me_resp.json()
header_left, header_right = st.columns([4, 1])
with header_left:
    st.title(f"Welcome, {me['username']}!")
    st.caption("Status: Logged in")
with header_right:
    st.write("")
    avatar = me.get("photo_data")
    if avatar:
        st.markdown(
            f"""
<style>
[data-testid="stPopover"] button {{
  background-image: url('{avatar}');
  background-size: cover;
  background-position: center;
  color: transparent;
  width: 36px;
  height: 36px;
  border-radius: 50%;
}}
</style>
""",
            unsafe_allow_html=True,
        )
        trigger = " "
    else:
        trigger = "☰"
    with st.popover(trigger):
        if st.button("Home"):
            st.switch_page("pages/Home.py")
        if st.button("Profile"):
            st.switch_page("pages/Profile.py")
        if st.button("Logout"):
            st.session_state.auth_token = None
            st.switch_page("frontend.py")

col_a, col_b, col_c, col_d = st.columns(4)
tasks_resp = requests.get(f"{API_URL}/tasks", headers=headers, params={"status": "all"})
tasks = tasks_resp.json() if tasks_resp.status_code == 200 else []
total = len(tasks)
completed = len([t for t in tasks if t["status"] == "completed"])
active = len([t for t in tasks if t["status"] == "active"])
def _is_overdue(t):
    if t["status"] != "active" or not t.get("due_date"):
        return False
    try:
        if "T" in t["due_date"]:
            due_dt = datetime.fromisoformat(t["due_date"])
        else:
            due_dt = datetime.fromisoformat(t["due_date"] + "T00:00:00")
        if due_dt.tzinfo is None:
            due_dt = due_dt.replace(tzinfo=APP_TZ)
        else:
            due_dt = due_dt.astimezone(APP_TZ)
        return due_dt < datetime.now(APP_TZ)
    except Exception:
        return False

overdue = len([t for t in tasks if _is_overdue(t)])
col_a.metric("Total", total)
col_b.metric("Active", active)
col_c.metric("Completed", completed)
col_d.metric("Overdue", overdue)

pie_col, _ = st.columns([1, 3])
with pie_col:
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

left, right = st.columns([1, 2])

with left:
    st.subheader("Create Task")
    title = st.text_input("Title", key="task_title")
    description = st.text_area("Description", key="task_description", height=100)
    priority = st.selectbox("Priority", ["High", "Medium", "Low"], index=1, key="task_priority")
    due_date = st.date_input("Due Date", value=None, key="task_due_date")
    due_time = st.time_input(
        "Due Time",
        value=datetime.now(APP_TZ).time().replace(second=0, microsecond=0),
        key="task_due_time",
    )
    recurrence = st.selectbox("Recurrence", ["none", "daily", "weekly"], index=0, key="task_recurrence")
    set_reminder = st.checkbox("Set Reminder", value=False, key="task_set_reminder")
    r_days = st.number_input("Reminder Days Before", min_value=0, max_value=365, value=0, key="task_reminder_days") if set_reminder else 0
    r_hours = st.number_input("Reminder Hours Before", min_value=0, max_value=23, value=0, key="task_reminder_hours") if set_reminder else 0
    r_mins = st.number_input("Reminder Minutes Before", min_value=0, max_value=59, value=30, key="task_reminder_mins") if set_reminder else 0
    tags = st.text_input("Tags (comma separated)", key="task_tags")
    tag_colors_input = st.text_input("Tag Colors (tag=color, ...)", key="task_tag_colors")
    st.caption("Tag colors accept names like green, blue, red (no hex needed).")
    if st.button("Add Task", key="add_task_btn"):
        if not title:
            st.warning("Title is required.")
        else:
            tag_colors = {}
            if tag_colors_input:
                for pair in tag_colors_input.split(","):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        tag_colors[k.strip()] = _normalize_color(v)
            due_dt = datetime.combine(due_date, due_time).replace(tzinfo=APP_TZ) if due_date else None
            reminder_at = None
            if set_reminder and due_dt:
                total_minutes = int(r_days) * 24 * 60 + int(r_hours) * 60 + int(r_mins)
                if total_minutes > 0:
                    reminder_at = due_dt - timedelta(minutes=total_minutes)
            payload = {
                "title": title,
                "description": description or None,
                "priority": priority,
                "due_date": due_dt.isoformat() if due_dt else None,
                "tags": [t.strip() for t in tags.split(",") if t.strip()],
                "tag_colors": tag_colors or None,
                "recurrence": None if recurrence == "none" else recurrence,
                "reminder_at": reminder_at.isoformat() if reminder_at else None,
            }
            resp = requests.post(f"{API_URL}/tasks", headers=headers, json=payload)
            if resp.status_code == 200:
                st.session_state.flash_message = "Task created."
                st.rerun()
            else:
                st.error("Failed to add task.")

with right:
    st.subheader("Tasks")
    filter_status = st.selectbox("Status", ["active", "history", "bin"], index=0)
    filter_priority = st.selectbox("Priority", ["all", "High", "Medium", "Low"], index=0)
    filter_draft = st.selectbox("Draft", ["all", "draft", "no_draft"], index=0)
    status_param = "active"
    if filter_status == "history":
        status_param = "completed"
    elif filter_status == "bin":
        status_param = "bin"
    tasks_resp = requests.get(
        f"{API_URL}/tasks",
        headers=headers,
        params={"status": status_param, "priority": filter_priority},
    )
    tasks = tasks_resp.json() if tasks_resp.status_code == 200 else []
    if filter_draft != "all":
        want_draft = filter_draft == "draft"
        tasks = [t for t in tasks if t.get("has_draft") == want_draft]

    if not tasks:
        st.info("No tasks found.")
    for t in tasks:
        with st.container(border=True):
            st.write(f"**{t['title']}**")
            if t.get("description"):
                st.caption(t["description"])
            st.write(f"Priority: {t['priority']} | Status: {t['status']}")
            if t.get("has_draft"):
                st.warning("Draft")
            if t.get("due_date"):
                st.write(f"Due: {t['due_date'][:10]}")
            if t.get("recurrence"):
                st.write(f"Recurs: {t['recurrence']}")
            if t.get("reminder_at"):
                st.write(f"Reminder: {t['reminder_at'][:16].replace('T', ' ')}")
            if t.get("tags"):
                tag_colors = t.get("tag_colors") or {}
                chips = []
                for tag in t["tags"]:
                    color = _normalize_color(tag_colors.get(tag, "gray"))
                    chips.append(
                        f"<span style='background:{color};color:white;padding:2px 8px;border-radius:12px;margin-right:6px;font-size:12px;'>"
                        f"{tag}</span>"
                    )
                st.markdown("".join(chips), unsafe_allow_html=True)

            c1, c2, c3 = st.columns(3)
            with c1:
                if t["status"] != "completed":
                    if st.button("Complete", key=f"complete_{t['id']}"):
                        requests.patch(
                            f"{API_URL}/tasks/{t['id']}",
                            headers=headers,
                            json={"status": "completed"},
                        )
                        st.session_state.flash_message = "Task completed."
                        st.rerun()
                else:
                    st.info("Completed task (history)")
            with c2:
                if filter_status != "history" and filter_status != "bin":
                    if st.button("Edit", key=f"edit_{t['id']}"):
                        st.session_state.edit_task_id = t["id"]
                        st.session_state.edit_task = t
                        st.rerun()
            with c3:
                if filter_status == "bin":
                    if st.button("Restore", key=f"restore_{t['id']}"):
                        requests.post(f"{API_URL}/tasks/{t['id']}/restore", headers=headers)
                        st.session_state.flash_message = "Task restored."
                        st.rerun()
                else:
                    if st.button("Delete", key=f"delete_{t['id']}"):
                        requests.delete(f"{API_URL}/tasks/{t['id']}", headers=headers)
                        st.session_state.flash_message = "Task moved to bin."
                        st.rerun()

            c4, c5 = st.columns(2)
            with c4:
                if st.button("Remind Me", key=f"remind_{t['id']}"):
                    requests.post(f"{API_URL}/tasks/{t['id']}/remind", headers=headers)
                    st.session_state.flash_message = "Reminder sent."
                    st.rerun()
            with c5:
                with st.expander("Subtasks"):
                    for s in t.get("subtasks", []):
                        s_key = f"sub_{s['id']}"
                        checked = st.checkbox(s["title"], value=s["is_done"], key=s_key)
                        if checked != s["is_done"]:
                            requests.patch(
                                f"{API_URL}/subtasks/{s['id']}",
                                headers=headers,
                                json={"is_done": checked},
                            )
                            st.rerun()
                    new_sub = st.text_input("New subtask", key=f"new_sub_{t['id']}")
                    if st.button("Add Subtask", key=f"add_sub_{t['id']}"):
                        if new_sub:
                            requests.post(
                                f"{API_URL}/tasks/{t['id']}/subtasks",
                                headers=headers,
                                json={"title": new_sub},
                            )
                            st.session_state.flash_message = "Subtask added."
                            st.rerun()

            if filter_status == "history":
                with st.expander("Use as Template"):
                    new_title = st.text_input("New Task Title", key=f"template_title_{t['id']}")
                    if st.button("Create From Template", key=f"template_btn_{t['id']}"):
                        if new_title:
                            requests.post(
                                f"{API_URL}/tasks/{t['id']}/clone",
                                headers=headers,
                                data={"new_title": new_title},
                            )
                            st.session_state.flash_message = "Task created from template."
                            st.rerun()

            with st.expander("Version History"):
                v_resp = requests.get(f"{API_URL}/tasks/{t['id']}/versions", headers=headers)
                if v_resp.status_code == 200:
                    versions = v_resp.json()
                    if not versions:
                        st.info("No versions yet.")
                    for v in versions:
                        v_label = f"v{v['version']} • {v['action']} • {v['created_at']}"
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            st.write(v_label)
                        with c2:
                            if st.button("Restore", key=f"restore_ver_{v['id']}"):
                                requests.post(
                                    f"{API_URL}/tasks/{t['id']}/restore-version/{v['id']}",
                                    headers=headers,
                                )
                                st.session_state.flash_message = "Task restored to previous version."
                                st.rerun()

    if "edit_task_id" in st.session_state and st.session_state.edit_task_id:
        st.divider()
        st.subheader("Edit Task")
        et = st.session_state.edit_task
        task_id = et["id"]

        if "draft_loaded" not in st.session_state:
            st.session_state.draft_loaded = None

        if st.session_state.draft_loaded != task_id:
            draft_resp = requests.get(f"{API_URL}/tasks/{task_id}/draft", headers=headers)
            if draft_resp.status_code == 200:
                draft = draft_resp.json().get("draft")
                if draft:
                    st.session_state.edit_title = draft.get("title", et["title"])
                    st.session_state.edit_desc = draft.get("description", et.get("description") or "")
                    st.session_state.edit_priority = draft.get("priority", et["priority"])
                    st.session_state.edit_due = (
                        date.fromisoformat(draft["due_date"][:10]) if draft.get("due_date") else None
                    )
                    st.session_state.edit_recur = draft.get("recurrence") or "none"
                    st.session_state.edit_reminder_date = (
                        date.fromisoformat(draft["reminder_at"][:10]) if draft.get("reminder_at") else None
                    )
                    st.session_state.edit_reminder_time = (
                        datetime.fromisoformat(draft["reminder_at"]).time()
                        if draft.get("reminder_at")
                        else datetime.now().time().replace(second=0, microsecond=0)
                    )
                    st.session_state.edit_tags = ",".join(draft.get("tags", []))
                    st.session_state.edit_tag_colors = ",".join(
                        [f"{k}={v}" for k, v in (draft.get("tag_colors") or {}).items()]
                    )
            st.session_state.draft_loaded = task_id

        def save_draft():
            tc = {}
            if st.session_state.edit_tag_colors:
                for pair in st.session_state.edit_tag_colors.split(","):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        tc[k.strip()] = v.strip()
            reminder_at = None
            due_dt = None
            if st.session_state.edit_due:
                due_dt = datetime.combine(st.session_state.edit_due, st.session_state.edit_due_time).replace(tzinfo=APP_TZ)
            if st.session_state.edit_set_reminder and due_dt:
                total_minutes = (
                    int(st.session_state.edit_r_days) * 24 * 60
                    + int(st.session_state.edit_r_hours) * 60
                    + int(st.session_state.edit_r_mins)
                )
                if total_minutes > 0:
                    reminder_at = due_dt - timedelta(minutes=total_minutes)
            payload = {
                "title": st.session_state.edit_title,
                "description": st.session_state.edit_desc or None,
                "priority": st.session_state.edit_priority,
                "due_date": due_dt.isoformat() if due_dt else None,
                "tags": [t.strip() for t in st.session_state.edit_tags.split(",") if t.strip()],
                "tag_colors": tc or None,
                "recurrence": None if st.session_state.edit_recur == "none" else st.session_state.edit_recur,
                "reminder_at": reminder_at.isoformat() if reminder_at else None,
            }
            requests.post(
                f"{API_URL}/tasks/{task_id}/draft",
                headers=headers,
                json=payload,
            )
        et_title = st.text_input("Title", value=et["title"], key="edit_title", on_change=save_draft)
        et_desc = st.text_area(
            "Description", value=et.get("description") or "", key="edit_desc", on_change=save_draft
        )
        et_priority = st.selectbox(
            "Priority",
            ["High", "Medium", "Low"],
            index=["High", "Medium", "Low"].index(et["priority"]),
            key="edit_priority",
            on_change=save_draft,
        )
        et_due = st.date_input(
            "Due Date",
            value=date.fromisoformat(et["due_date"][:10]) if et.get("due_date") else None,
            key="edit_due",
            on_change=save_draft,
        )
        et_due_time = st.time_input(
            "Due Time",
            value=datetime.fromisoformat(et["due_date"]).time()
            if et.get("due_date")
            else datetime.now(APP_TZ).time().replace(second=0, microsecond=0),
            key="edit_due_time",
            on_change=save_draft,
        )
        et_recur = st.selectbox(
            "Recurrence",
            ["none", "daily", "weekly"],
            index=(["none", "daily", "weekly"].index(et.get("recurrence") or "none")),
            key="edit_recur",
            on_change=save_draft,
        )
        et_set_reminder = st.checkbox("Set Reminder", value=bool(et.get("reminder_at")), key="edit_set_reminder", on_change=save_draft)
        et_r_days = st.number_input("Reminder Days Before", min_value=0, max_value=365, value=0, key="edit_r_days", on_change=save_draft) if et_set_reminder else 0
        et_r_hours = st.number_input("Reminder Hours Before", min_value=0, max_value=23, value=0, key="edit_r_hours", on_change=save_draft) if et_set_reminder else 0
        et_r_mins = st.number_input("Reminder Minutes Before", min_value=0, max_value=59, value=30, key="edit_r_mins", on_change=save_draft) if et_set_reminder else 0
        et_tags = st.text_input(
            "Tags (comma separated)", value=",".join(et.get("tags", [])), key="edit_tags", on_change=save_draft
        )
        et_tag_colors = st.text_input(
            "Tag Colors (tag=color, ...)",
            value=",".join([f"{k}={v}" for k, v in (et.get("tag_colors") or {}).items()]),
            key="edit_tag_colors",
            on_change=save_draft,
        )

        csave, ccancel = st.columns(2)
        with csave:
            if st.button("Save", key="save_edit"):
                tc = {}
                if et_tag_colors:
                    for pair in et_tag_colors.split(","):
                        if "=" in pair:
                            k, v = pair.split("=", 1)
                            tc[k.strip()] = _normalize_color(v)
                reminder_at = None
                due_dt = datetime.combine(et_due, et_due_time).replace(tzinfo=APP_TZ) if et_due else None
                if et_set_reminder and due_dt:
                    total_minutes = int(et_r_days) * 24 * 60 + int(et_r_hours) * 60 + int(et_r_mins)
                    if total_minutes > 0:
                        reminder_at = due_dt - timedelta(minutes=total_minutes)
                payload = {
                    "title": et_title,
                    "description": et_desc or None,
                    "priority": et_priority,
                    "due_date": due_dt.isoformat() if due_dt else None,
                    "tags": [t.strip() for t in et_tags.split(",") if t.strip()],
                    "tag_colors": tc or None,
                    "recurrence": None if et_recur == "none" else et_recur,
                    "reminder_at": reminder_at.isoformat() if reminder_at else None,
                }
                requests.patch(
                    f"{API_URL}/tasks/{et['id']}",
                    headers=headers,
                    json=payload,
                )
                requests.delete(f"{API_URL}/tasks/{et['id']}/draft", headers=headers)
                st.session_state.edit_task_id = None
                st.session_state.edit_task = None
                st.session_state.draft_loaded = None
                st.session_state.flash_message = "Task updated."
                st.rerun()
        with ccancel:
            if st.button("Cancel", key="cancel_edit"):
                requests.delete(f"{API_URL}/tasks/{et['id']}/draft", headers=headers)
                st.session_state.edit_task_id = None
                st.session_state.edit_task = None
                st.session_state.draft_loaded = None
                st.session_state.flash_message = "Edit cancelled."
                st.rerun()

st.divider()
if st.session_state.flash_message:
    st.success(st.session_state.flash_message)
    st.session_state.flash_message = None
