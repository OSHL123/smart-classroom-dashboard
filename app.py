import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime
import uuid
import streamlit.components.v1 as components
from supabase import create_client, Client

# ==========================================
# 1. CONFIGURATION & SETUP
# ==========================================
st.set_page_config(page_title="Smart Classroom LMS", page_icon="🎓", layout="wide")
VIDEO_URL = "http://172.20.10.5:8000/stream.mjpg"

@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

# ==========================================
# 2. SECURITY (LOGIN)
# ==========================================
VALID_USERS = {"admin": "admin123", "adrian": "1234"}

def check_password():
    if st.session_state.get("password_correct", False):
        return True
    st.title("🔒 Lecturer Access")
    with st.form("login_form"):
        username = st.text_input("Username").strip().lower()
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Log In"):
            if username in VALID_USERS and VALID_USERS[username] == password:
                st.session_state["password_correct"] = True
                st.session_state["current_user"] = username
                st.rerun() 
            else:
                st.error("❌ Access denied.")
    return False

if not check_password(): st.stop()

# ==========================================
# 3. DATABASE HELPER FUNCTIONS
# ==========================================
def get_system_status():
    res = supabase.table("system_command").select("*").eq("id", 1).execute()
    if res.data: return res.data[0]
    return {"status": "OFF", "current_session_id": "NONE"}

def start_class(course_name):
    # 1. Generate a unique ID for this specific class
    session_id = f"SES_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # 2. Create the session in the logbook
    supabase.table("class_sessions").insert({
        "session_id": session_id,
        "course_name": course_name,
        "status": "ACTIVE"
    }).execute()
    
    # 3. Turn the hardware ON
    supabase.table("system_command").update({
        "status": "ON", 
        "current_session_id": session_id
    }).eq("id", 1).execute()
    st.rerun()

def end_class(session_id):
    # 1. Mark session as complete
    supabase.table("class_sessions").update({
        "end_time": datetime.now().isoformat(),
        "status": "COMPLETED"
    }).eq("session_id", session_id).execute()
    
    # 2. Turn hardware OFF
    supabase.table("system_command").update({
        "status": "OFF", 
        "current_session_id": "NONE"
    }).eq("id", 1).execute()
    st.rerun()

# ==========================================
# 4. MAIN DASHBOARD ROUTING
# ==========================================
sys_status = get_system_status()
current_state = sys_status["status"]
active_session = sys_status["current_session_id"]

# --- STATE: CLASS IS OFF (PRE-CLASS SETUP) ---
if current_state == "OFF":
    st.title("🏫 Pre-Class Setup")
    st.info("The IoT Camera Hardware is currently sleeping. Select a course to wake the system and begin logging.")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Start a New Session")
        course_selection = st.selectbox("Select Course", [
            "Year 1 EEE - Engineering Mathematics", 
            "Year 2 EEE - Digital Electronics",
            "Year 3 EEE - Power Systems",
            "Final Year - Thesis Seminar"
        ])
        if st.button("🟢 START CLASS & WAKE HARDWARE", use_container_width=True, type="primary"):
            start_class(course_selection)
            
    with col2:
        st.subheader("Past Sessions History")
        past_sessions = supabase.table("class_sessions").select("*").eq("status", "COMPLETED").order("start_time", desc=True).limit(5).execute()
        if past_sessions.data:
            st.dataframe(pd.DataFrame(past_sessions.data)[['course_name', 'start_time', 'end_time']], use_container_width=True)
        else:
            st.caption("No past sessions found.")

# --- STATE: CLASS IS ON (LIVE COMMAND CENTER) ---
elif current_state == "ON":
    # Sidebar Controls
    with st.sidebar:
        st.success("🟢 HARDWARE ACTIVE")
        st.markdown(f"**Session:** `{active_session}`")
        if st.button("🔴 END CLASS & SLEEP HARDWARE", use_container_width=True, type="primary"):
            end_class(active_session)
        st.divider()
        st.subheader("📷 Live Camera")
        components.html(f'<img src="{VIDEO_URL}" style="width:100%; border-radius:10px;">', height=250)

    # Main Live Dashboard
    st.title("🔴 LIVE: Classroom Command Center")
    
    # Fetch ONLY data for the current active session
    data_res = supabase.table("hand_raises").select("*").eq("session_id", active_session).order("created_at", desc=True).execute()
    df_part = pd.DataFrame(data_res.data) if data_res.data else pd.DataFrame(columns=["student_name", "created_at", "event_type"])
    
    # Fetch registered students
    student_res = supabase.table("students").select("*").execute()
    student_dict = {s['student_id']: s['name'] for s in student_res.data} if student_res.data else {}

    col_main, col_chart = st.columns([2, 1])
    
    with col_main:
        st.subheader("Live Engagement Feed")
        if not df_part.empty:
            display_df = df_part.copy()
            display_df['Time'] = pd.to_datetime(display_df['created_at']).dt.tz_convert('Asia/Kuala_Lumpur').dt.strftime('%H:%M:%S')
            st.dataframe(display_df[['Time', 'student_name', 'event_type']], use_container_width=True)
        else:
            st.info("Waiting for students to interact...")
            
    with col_chart:
        st.subheader("Top Participants")
        if not df_part.empty:
            counts = df_part["student_name"].value_counts().reset_index()
            counts.columns = ["Name", "Count"]
            chart = alt.Chart(counts).mark_bar().encode(x='Count', y=alt.Y('Name', sort='-x'), color='Name').interactive()
            st.altair_chart(chart, use_container_width=True)
