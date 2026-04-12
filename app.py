import streamlit as st
import pandas as pd
import json
import altair as alt
from datetime import datetime
import streamlit.components.v1 as components
from supabase import create_client, Client

# ==========================================
# 1. CONFIGURATION & CLOUD SETUP
# ==========================================
st.set_page_config(page_title="Smart Classroom LMS", page_icon="🎓", layout="wide")

# Read from GitHub repo folder instead of Raspberry Pi local path
METADATA_JSON = "student_metadata.json" 
# Note: Live video requires a public Ngrok tunnel on the Pi. 
# This local IP will only load if you are viewing the site on the same WiFi as the Pi.
VIDEO_URL = "http://172.20.10.5:8000/stream.mjpg"

@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# ==========================================
# 1.5 SECURITY (MULTI-USER LOGIN GATE)
# ==========================================
VALID_USERS = {
    "admin": "admin123",
    "adrian": "1234",
    "ecyal5": "1234"
}

def check_password():
    if st.session_state.get("password_correct", False):
        return True

    st.title("🔒 Smart Classroom - Lecturer Access")
    st.caption("Please enter your credentials to access the command center.")
    
    with st.form("login_form"):
        username = st.text_input("Username").strip().lower()
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Log In")

    if submit:
        if username in VALID_USERS and VALID_USERS[username] == password:
            st.session_state["password_correct"] = True
            st.session_state["current_user"] = username
            st.rerun() 
        else:
            st.error("❌ Incorrect username or password. Access denied.")
            
    return False

if not check_password():
    st.stop()

# ==========================================
# 2. DATA LOADING (FROM SUPABASE & GITHUB)
# ==========================================
@st.cache_data(ttl=3) # Auto-refresh every 3 seconds
def load_data():
    # 1. Load Participation from Cloud Database
    response = supabase.table("hand_raises").select("*").order("created_at", desc=True).execute()
    if response.data:
        df_part = pd.DataFrame(response.data)
        # Standardize column names to match your original UI code
        df_part = df_part.rename(columns={"student_name": "Name", "event_type": "Event", "created_at": "Time"})
        df_part['Time'] = pd.to_datetime(df_part['Time']).dt.tz_convert('Asia/Kuala_Lumpur').dt.strftime('%Y-%m-%d %H:%M:%S')
    else:
        df_part = pd.DataFrame(columns=["Name", "Time", "Event"])

    # 2. Load Metadata from GitHub File
    metadata = {}
    try:
        with open(METADATA_JSON, "r") as f:
            metadata = json.load(f)
    except Exception:
        pass # Will stay empty if file isn't uploaded to GitHub
            
    # Note: Attendance is mocked here until Door Node is connected to Supabase
    df_att = pd.DataFrame(columns=["Name", "Time"]) 
    
    return df_att, df_part, metadata

# ==========================================
# 3. SIDEBAR (Class Overview)
# ==========================================
df_att, df_part, metadata = load_data()

with st.sidebar:
    st.title("🏫 Class Monitor")
    
    current_user = st.session_state.get("current_user", "Admin").title()
    st.markdown(f"**Logged in as:** 👤 {current_user}")
    st.caption(f"Status: Cloud Connected ☁️")
    
    if st.button("🚪 Log Out", use_container_width=True):
        st.session_state["password_correct"] = False
        st.session_state["current_user"] = ""
        st.rerun()
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
        recent_events = df_part.head(10) # Top 10 newest from Supabase
        for index, row in recent_events.iterrows():
            time_text = str(row['Time'])
            display_time = time_text.split(' ')[1] if " " in time_text else time_text
            st.text(f"🙋 {row['Name']} ({display_time})")
    else:
        st.caption("Waiting for activity...")

# ==========================================
# 4. MAIN DASHBOARD
# ==========================================
st.title("🎓 Classroom Command Center")

tab1, tab2 = st.tabs(["📊 Live Monitor", "👤 Student Profiles"])

with tab1:
    col_main, col_chart = st.columns([2, 1])
    
    with col_main:
        st.subheader("📋 Attendance Sheet")
        st.info("Cloud Attendance feature pending Door Node database integration.")
        st.dataframe(df_att, use_container_width=True, hide_index=True)
        
    with col_chart:
        st.subheader("🏆 Top Participants")
        if not df_part.empty:
            counts = df_part["Name"].value_counts().reset_index()
            counts.columns = ["Name", "Count"]
            
            chart = alt.Chart(counts).mark_bar().encode(
                x='Count',
                y=alt.Y('Name', sort='-x'),
                color='Name',
                tooltip=['Name', 'Count']
            ).interactive()
            
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No participation yet.")

with tab2:
    st.subheader("Student Detail View")
    
    student_list = list(metadata.keys()) 
    
    if not student_list:
        st.warning("No students registered. Please upload 'student_metadata.json' to GitHub.")
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
