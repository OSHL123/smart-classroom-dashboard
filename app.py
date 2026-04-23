import streamlit as st
import pandas as pd
import json
import altair as alt
from datetime import datetime
import streamlit.components.v1 as components
from supabase import create_client, Client
import base64

# ==========================================
# 1. CONFIGURATION & CLOUD SETUP
# ==========================================
st.set_page_config(page_title="Smart Classroom LMS", page_icon="🎓", layout="wide")

METADATA_JSON = "student_metabase.json" 
VIDEO_URL = "http://172.20.10.5:8000/stream.mjpg"

@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()
# ==========================================
# 1. Sounnd Alert 
# ==========================================
# ==========================================
# 1. Sound Alert 
# ==========================================
def play_alert_sound():
    try:
        # Using Streamlit's native audio engine with autoplay forced ON
        st.audio("Beep - Sound Effect.mp3", format="audio/mp3", autoplay=True)
    except Exception as e:
        st.error(f"⚠️ Audio system failed: {e}")
# ==========================================
# 1.5 SECURITY (MULTI-USER LOGIN GATE)
# ==========================================
VALID_USERS = {"admin": "admin123", "adrian": "1234", "ecyal5": "1234"}

def check_password():
    if st.session_state.get("password_correct", False): return True
    st.title("🔒 Smart Classroom - Lecturer Access")
    st.caption("Please enter your credentials to access the command center.")
    with st.form("login_form"):
        username = st.text_input("Username").strip().lower()
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Log In"):
            if username in VALID_USERS and VALID_USERS[username] == password:
                st.session_state["password_correct"] = True
                st.session_state["current_user"] = username
                st.rerun() 
            else:
                st.error("❌ Incorrect username or password. Access denied.")
    return False

if not check_password(): st.stop()

# ==========================================
# 2. SYSTEM COMMAND LOGIC (NEW)
# ==========================================
def get_system_status():
    res = supabase.table("system_command").select("*").eq("id", 1).execute()
    if res.data: return res.data[0]
    return {"status": "OFF", "current_session_id": "NONE"}

def start_class(course_name):
    session_id = f"SES_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    supabase.table("class_sessions").insert({"session_id": session_id, "course_name": course_name, "status": "ACTIVE"}).execute()
    supabase.table("system_command").update({"status": "ON", "current_session_id": session_id}).eq("id", 1).execute()
    st.session_state["active_course"] = course_name # Save course for filtering
    st.session_state["last_raise_count"] = 0
    st.rerun()

def end_class(session_id):
    supabase.table("class_sessions").update({"end_time": datetime.now().isoformat(), "status": "COMPLETED"}).eq("session_id", session_id).execute()
    supabase.table("system_command").update({"status": "OFF", "current_session_id": "NONE"}).eq("id", 1).execute()
    st.session_state["active_course"] = None
    st.rerun()

# ==========================================
# 3. DATA LOADING
# ==========================================
sys_status = get_system_status()
current_state = sys_status["status"]
active_session = sys_status["current_session_id"]

@st.cache_data(ttl=3)


def load_data(session_id):
    # Only load data for THIS specific class session
    response = supabase.table("hand_raises").select("*").eq("session_id", session_id).order("created_at", desc=True).execute()
    
    if response.data:
        df = pd.DataFrame(response.data)
        df = df.rename(columns={"student_name": "Name", "event_type": "Event", "created_at": "Time"})
        df['Time'] = pd.to_datetime(df['Time']).dt.tz_convert('Asia/Kuala_Lumpur').dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Split the data based on the Event type
        df_att = df[df['Event'] == 'Door Scan'][['Name', 'Time']].drop_duplicates(subset=['Name'], keep='first')
        df_part = df[df['Event'] == 'Hand Raise']
    else:
        df_att = pd.DataFrame(columns=["Name", "Time"])
        df_part = pd.DataFrame(columns=["Name", "Time", "Event"])

    metadata = {}
    try:
        with open(METADATA_JSON, "r") as f:
            metadata = json.load(f)
    except Exception: pass
            
    return df_att, df_part, metadata
# ==========================================
# 4. ROUTING: PRE-CLASS SETUP (OFF STATE)
# ==========================================
if current_state == "OFF":
    st.title("🏫 Pre-Class Setup")
    st.info("The Classroom IoT System is currently sleeping. Select a class to begin.")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("Start New Class")
        course_selection = st.selectbox("Select Course Routine", [
            "Year 1 EEE - Engineering Mathematics", 
            "Year 2 EEE - Digital Electronics",
            "Final Year EEE - Thesis Seminar"
        ])
        if st.button("🟢 START CLASS", use_container_width=True, type="primary"):
            start_class(course_selection)
            
    with col2:
        st.subheader("Lecturer Info")
        st.write(f"**Logged in as:** {st.session_state.get('current_user', 'Admin').title()}")
        st.write("**Database:** Connected ☁️")
        if st.button("🚪 Log Out"):
            st.session_state["password_correct"] = False
            st.rerun()

# ==========================================
# 5. ROUTING: LIVE COMMAND CENTER (ON STATE)
# ==========================================

elif current_state == "ON":
    play_alert_sound()
    df_att, df_part, metadata = load_data(active_session)
    active_course = st.session_state.get("active_course", "Unknown Course")
    
   # ==========================================
    # --- NEW: TOAST ALERT NOTIFICATION LOGIC ---
    # ==========================================
    # 1. Initialize the memory if it doesn't exist
    if "last_raise_count" not in st.session_state:
        st.session_state["last_raise_count"] = len(df_part)

    # 2. Check if the database has MORE hand raises than we last remembered
    current_raise_count = len(df_part)
    if current_raise_count > st.session_state["last_raise_count"]:
        # --- NEW: Play the audio alert once ---
        play_alert_sound()
        
        # 3. Calculate how many new raises happened
        new_raises = current_raise_count - st.session_state["last_raise_count"]
        
        # 4. Trigger a pop-up for each new raise
        for i in range(new_raises):
            # Because your SQL query orders by desc=True, the newest ones are at the top (index 0)
            new_student = df_part.iloc[i]['Name']
            st.toast(f"Teacher Alert: {new_student} just raised their hand!", icon="🔔")
            
        # 5. Update our memory so it doesn't pop up again next refresh
        st.session_state["last_raise_count"] = current_raise_count
    # ==========================================
    
    # --- EXACT ORIGINAL SIDEBAR ---
    with st.sidebar:
        st.title("🏫 Class Monitor")
        current_user = st.session_state.get("current_user", "Admin").title()
        st.markdown(f"**Logged in as:** 👤 {current_user}")
        st.caption(f"Course: {active_course}")
        
        # NEW END CLASS BUTTON
        if st.button("🔴 END CLASS", use_container_width=True, type="primary"):
            end_class(active_session)
        st.divider()
            
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.rerun()

        st.subheader("📷 Front Camera Feed")
        st.caption("Requires local network or Edge Tunnel")
        components.html(
            f'<img src="{VIDEO_URL}" style="width:100%; border-radius:10px;" alt="Camera Offline/Not on Local Network">',
            height=300
        )
        st.divider()
        col1, col2 = st.columns(2)
        col1.metric("Present", len(df_att))
        col2.metric("Hand Raises", len(df_part))
        st.divider()
        
        st.subheader("🔴 Live Event Log")
        if not df_part.empty:
            recent_events = df_part.head(10)
            for index, row in recent_events.iterrows():
                time_text = str(row['Time'])
                display_time = time_text.split(' ')[1] if " " in time_text else time_text
                st.text(f"🙋 {row['Name']} ({display_time})")
        else:
            st.caption("Waiting for activity...")

    # --- EXACT ORIGINAL MAIN DASHBOARD ---
    st.title("🎓 Classroom Command Center")

    tab1, tab2 = st.tabs(["📊 Live Monitor", "👤 Student Profiles"])

    with tab1:
        col_main, col_chart = st.columns([2, 1])
        with col_main:
            st.subheader("📋 Attendance Sheet")
          #  st.info("Cloud Attendance feature pending Door Node database integration.")
            st.dataframe(df_att, use_container_width=True, hide_index=True)
            
        with col_chart:
            st.subheader("🏆 Top Participants")
            if not df_part.empty:
                counts = df_part["Name"].value_counts().reset_index()
                counts.columns = ["Name", "Count"]
                chart = alt.Chart(counts).mark_bar().encode(x='Count', y=alt.Y('Name', sort='-x'), color='Name', tooltip=['Name', 'Count']).interactive()
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info("No participation yet.")

    with tab2:
        st.subheader(f"Student Detail View ({active_course})")
        
        # NEW FILTERING LOGIC: Only show students who are registered for this course
        student_list = []
        for name, info in metadata.items():
            # If the student's registered courses include this active course, add them to the dropdown
            if active_course in info.get("courses", []):
                student_list.append(name)
        
        if not student_list:
            st.warning(f"No students registered for {active_course}. Please update 'student_metadata.json' on GitHub.")
        else:
            selected_student = st.selectbox("Select a Student:", sorted(student_list))
            
            if selected_student:
                default_info = {"student_id": "N/A", "major": "Unknown"}
                info = metadata.get(selected_student, default_info)
                student_raises = len(df_part[df_part["Name"] == selected_student])
                
                c1, c2 = st.columns([1, 3])
                with c1:
                    st.image("https://via.placeholder.com/150", caption=selected_student)
                    st.metric("Engagement Score", f"{student_raises} pts")
                with c2:
                    st.markdown(f"### {selected_student}")
                    st.markdown(f"**Student ID:** {info.get('student_id', 'N/A')}")
                    st.markdown(f"**Major:** {info.get('major', 'N/A')}")
