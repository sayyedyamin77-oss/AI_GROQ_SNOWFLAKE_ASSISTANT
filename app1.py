import os
import streamlit as st
import pandas as pd
import snowflake.connector
from groq import Groq
from dotenv import load_dotenv
import plotly.express as px

# Robust .env loading fallback
load_dotenv()
load_dotenv(dotenv_path="../.env")

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

st.set_page_config(page_title="Groq AI Data Analyst", layout="wide")

def get_env_variable(keys: list):
    """Helper to try multiple environment variable fallback keys"""
    for key in keys:
        val = os.getenv(key)
        if val:
            return val
    return None

def get_snowflake_connection():
    # Robust fallback supporting both SF_ and SNOWFLAKE_ prefixes
    user = get_env_variable(["SF_USER", "SNOWFLAKE_USER"])
    password = get_env_variable(["SF_PASSWORD", "SNOWFLAKE_PASSWORD"])
    account = get_env_variable(["SF_ACCOUNT", "SNOWFLAKE_ACCOUNT"])
    warehouse = get_env_variable(["SF_WAREHOUSE", "SNOWFLAKE_WAREHOUSE"])
    database = get_env_variable(["SF_DATABASE", "SNOWFLAKE_DATABASE"])
    schema = get_env_variable(["SF_SCHEMA", "SNOWFLAKE_SCHEMA"])

    if not all([user, password, account]):
        raise ValueError(
            "Required Snowflake environment variables are missing! "
            "Please check that SF_USER/SNOWFLAKE_USER, SF_PASSWORD/SNOWFLAKE_PASSWORD, SF_ACCOUNT/SNOWFLAKE_ACCOUNT are configured in .env."
        )

    return snowflake.connector.connect(
        user=user,
        password=password,
        account=account,
        warehouse=warehouse,
        database=database,
        schema=schema
    )

@st.cache_data(ttl=3600)
def fetch_database_schema():
    query = """
    SELECT table_name, column_name, data_type 
    FROM information_schema.columns WHERE table_schema = 'PUBLIC'
    ORDER BY table_name, ordinal_position;
    """
    try:
        conn = get_snowflake_connection()
        cursor = conn.cursor()
        cursor.execute(query)
        records = cursor.fetchall()
        cursor.close(); conn.close()
        
        schema_dict = {}
        for table, col, dtype in records:
            if table not in schema_dict: schema_dict[table] = []
            schema_dict[table].append(f"{col} ({dtype})")
            
        context_str = ""
        for table, cols in schema_dict.items():
            context_str += f"Table: {table}\nColumns: {', '.join(cols)}\n\n"
        return context_str, schema_dict
    except Exception as e:
        st.error(f"Failed to fetch Snowflake Schema: {str(e)}")
        return "", {}

def is_query_safe(sql_query):
    forbidden = ["DROP", "DELETE", "TRUNCATE", "ALTER", "UPDATE", "GRANT", "REVOKE"]
    for word in forbidden:
        if word in sql_query.upper(): return False, word
    return True, ""

def generate_sql_query(user_question, context_schema):
    system_prompt = f"""
    You are an expert enterprise Snowflake SQL Data Analyst.
    Convert user questions into pure Snowflake SQL based ONLY on this schema:\n{context_schema}
    Output ONLY raw SQL query. Do not wrap in markdown code blocks. No explanations.
    """
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile", 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_question}
            ],
            temperature=0.0
        )
        return completion.choices[0].message.content.strip().replace("```sql", "").replace("```", "")
    except Exception as e:
        st.error(f"Groq API Error: {str(e)}")
        return ""

st.title("⚡ Supersonic Groq NL2SQL Analyst")
schema_context, raw_schema_dict = fetch_database_schema()

with st.sidebar:
    st.header("📋 Database Schema")
    for table_name, columns in raw_schema_dict.items():
        with st.expander(f"Table: {table_name}"):
            for col in columns: st.write(f"  - {col}")

user_input = st.text_input("Enter your question:")
if st.button("Run Analytics Query") and user_input:
    with st.spinner("Groq is thinking..."):
        generated_sql = generate_sql_query(user_input, schema_context)
        
    if generated_sql:
        st.markdown("### 🛠️ Generated SQL")
        st.code(generated_sql, language="sql")
        
        safe, word = is_query_safe(generated_sql)
        if not safe:
            st.error(f"❌ Security Block: Keyword '{word}' not allowed.")
        else:
            with st.spinner("Fetching data..."):
                try:
                    conn = get_snowflake_connection()
                    df = pd.read_sql(generated_sql, conn)
                    conn.close()
                    
                    st.markdown("### 📋 Results")
                    st.dataframe(df, use_container_width=True)
                    
                    num_cols = df.select_dtypes(include=['number']).columns.tolist()
                    cat_cols = df.select_dtypes(include=['object', 'category', 'datetime']).columns.tolist()
                    if num_cols and cat_cols:
                        fig = px.bar(df, x=cat_cols[0], y=num_cols[0], template="plotly_dark")
                        st.plotly_chart(fig, use_container_width=True)
                except Exception as err:
                    st.error(f"❌ Snowflake Error: {str(err)}")
```
eof

---

### 🚀 Iske baad run kaise karein?

1. Purane chal rahe terminal/CMD instances ko close karke naye terminal windows open karein.
2. Agar aap **Decoupled Architecture (FastAPI + Streamlit)** chala rahe hain:
   * **Terminal 1:**
     ```bash
     cd backend
     python -m uvicorn main:app --reload
     ```
   * **Terminal 2:**
     ```bash
     cd frontend
     python -m streamlit run app.py
     ```
3. Agar aap **Standalone single-file** chala rahe hain (No backend server required):
   * **Terminal 1:**
     ```bash
     python -m streamlit run app1.py