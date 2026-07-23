import streamlit as st
import pandas as pd
import requests

st.set_page_config(
    page_title="Groq Intelligence Portal", 
    page_icon="⚡",
    layout="wide"
)

# Dark Theme and Input Box Text Visibility CSS
st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(180deg, #0F172A 0%, #1E293B 100%);
        color: #F8FAFC;
    }
    input, textarea {
        color: #0F172A !important;
        font-weight: 500 !important;
    }
    .main-title {
        font-size: 2.8rem;
        font-weight: 800;
        background: linear-gradient(90deg, #38BDF8, #818CF8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .metric-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        padding: 1.2rem;
        border-radius: 12px;
        text-align: center;
    }
    .metric-val { font-size: 1.5rem; font-weight: 700; color: #38BDF8; }
    .metric-lbl { font-size: 0.8rem; color: #94A3B8; }
    .stChatMessage {
        background-color: rgba(255, 255, 255, 0.02) !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        border-radius: 12px !important;
    }
    .stAlert {
        background-color: rgba(14, 165, 233, 0.1) !important;
        color: #38BDF8 !important;
        border: 1px solid rgba(14, 165, 233, 0.2) !important;
    }
    </style>
""", unsafe_allow_html=True)

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

VALID_USERNAME = "admin"
VALID_PASSWORD = "password123"
BACKEND_URL = "http://localhost:8000/api/chat"

if not st.session_state["logged_in"]:
    cols = st.columns([1, 2, 1])
    with cols[1]:
        st.write("<div style='height:120px;'></div>", unsafe_allow_html=True)
        st.markdown("<h2 style='text-align:center; color:#38BDF8;'>🔒 Corporate Secure Access</h2>", unsafe_allow_html=True)
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Authenticate"):
                if username == VALID_USERNAME and password == VALID_PASSWORD:
                    st.session_state["logged_in"] = True
                    st.rerun()
                else:
                    st.error("Invalid System Credentials.")
else:
    with st.sidebar:
        st.markdown(f"👤 Session: `{VALID_USERNAME.upper()}`")
        if st.button("🗑️ Reset Chat Memory", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state["logged_in"] = False
            st.rerun()

    st.markdown("<div class='main-title'>⚡ Groq Advanced Analytics Portal</div>", unsafe_allow_html=True)
    st.write("<div style='height:15px;'></div>", unsafe_allow_html=True)

    # Info Metrics
    m1, m2, m3 = st.columns(3)
    m1.markdown("<div class='metric-card'><div class='metric-val'>Snowflake</div><div class='metric-lbl'>Warehouse Target</div></div>", unsafe_allow_html=True)
    m2.markdown("<div class='metric-card'><div class='metric-val'>Llama 3.3</div><div class='metric-lbl'>AI Architecture</div></div>", unsafe_allow_html=True)
    m3.markdown("<div class='metric-card'><div class='metric-val'>Connected</div><div class='metric-lbl'>FastAPI Pipeline</div></div>", unsafe_allow_html=True)

    if "messages" not in st.session_state:
        st.session_state.messages = []

    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if "sql" in msg:
                    with st.expander("View Compiled SQL"):
                        st.code(msg["sql"], language="sql")
                if "data" in msg and msg["data"]:
                    df_h = pd.DataFrame(msg["data"])
                    st.dataframe(df_h, use_container_width=True)
                    if "chart_type" in msg and msg["chart_type"] != "none":
                        if msg["chart_type"] == "bar": st.bar_chart(df_h)
                        elif msg["chart_type"] == "line": st.line_chart(df_h)
                    if "insights" in msg:
                        st.info(f"💡 **AI Summary:**\n\n{msg['insights']}")

    if user_input := st.chat_input("Ask a business question..."):
        with chat_container:
            with st.chat_message("user"): st.markdown(user_input)
        st.session_state.messages.append({"role": "user", "content": user_input})
        
        cleaned_history = []
        for m in st.session_state.messages:
            cleaned_history.append({"role": m["role"], "content": m["content"]})
            
        with chat_container:
            with st.chat_message("assistant"):
                with st.spinner("Processing Model Context..."):
                    try:
                        response = requests.post(BACKEND_URL, json={"history": cleaned_history})
                        if response.status_code == 200:
                            res = response.json()
                            sql = res["sql"]
                            data = res["data"]
                            insights = res["insights"]
                            chart = res["chart_type"]
                            
                            st.markdown("✨ **Analysis Result:**")
                            with st.expander("View Compiled SQL"):
                                st.code(sql, language="sql")
                            
                            df = pd.DataFrame(data)
                            if not df.empty:
                                st.dataframe(df, use_container_width=True)
                                if chart != "none":
                                    if chart == "bar": st.bar_chart(df)
                                    elif chart == "line": st.line_chart(df)
                                st.info(f"💡 **AI Summary:**\n\n{insights}")
                                
                                csv = df.to_csv(index=False).encode('utf-8')
                                st.download_button("📥 Export to CSV", data=csv, file_name="analytics.csv", mime="text/csv")
                            else:
                                st.warning("Empty data returned.")
                                
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": "Analysis completed successfully.",
                                "sql": sql,
                                "data": data,
                                "chart_type": chart,
                                "insights": insights
                            })
                        else:
                            st.error(f"Error: {response.json().get('detail')}")
                    except Exception as e:
                        st.error(f"Server offline: {e}")
