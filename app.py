import streamlit as st
from supabase import create_client, Client
import pandas as pd

# Set page layout
st.set_page_config(page_title="Smart Classroom Dashboard", layout="wide")

st.title("🎓 Smart Classroom Instructor Dashboard")
st.write("Live IoT Telemetry via Supabase")

# Initialize connection to Supabase. 
# We use st.secrets so we don't accidentally upload passwords to GitHub!
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# Fetch data with a Time-To-Live (TTL) cache so it auto-refreshes
@st.cache_data(ttl=3) # Refreshes every 3 seconds
def get_hand_raises():
    # Order by created_at descending so the newest raises are at the top
    response = supabase.table("hand_raises").select("*").order("created_at", desc=True).execute()
    return response.data

# --- DASHBOARD UI ---
data = get_hand_raises()

if data:
    # Convert JSON to a Pandas DataFrame for a clean table
    df = pd.DataFrame(data)
    
    # Clean up the timestamps to look nicer
    df['created_at'] = pd.to_datetime(df['created_at']).dt.tz_convert('Asia/Kuala_Lumpur').dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # Display top metrics
    total_raises = len(df)
    st.metric(label="Total Questions Asked Today", value=total_raises)
    
    # Display the data table
    st.subheader("Live Engagement Log")
    st.dataframe(df[['created_at', 'student_name', 'event_type']], use_container_width=True)
else:
    st.info("Waiting for data from the classroom edge node...")

# Hardware Status Note
st.sidebar.header("System Status")
st.sidebar.success("☁️ Cloud Database: ONLINE")
st.sidebar.warning("📷 Live Video Feed: Disabled in Cloud Mode (Requires Edge Tunnel)")