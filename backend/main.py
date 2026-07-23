import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import snowflake.connector
from groq import Groq
from dotenv import load_dotenv

# Bulletproof path resolving for .env (checks current and parent directory)
load_dotenv()
load_dotenv(dotenv_path="../.env")

app = FastAPI(title="Production Ready Guardrail Backend")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class ChatHistoryRequest(BaseModel):
    history: List[Dict[str, Any]]

def get_env_variable(keys: list):
    """Helper to try multiple fallback environment variables"""
    for key in keys:
        val = os.getenv(key)
        if val:
            return val
    return None

def get_snowflake_connection():
    # Fallback mappings for SF_ and SNOWFLAKE_ prefixes
    user = get_env_variable(["SF_USER", "SNOWFLAKE_USER"])
    password = get_env_variable(["SF_PASSWORD", "SNOWFLAKE_PASSWORD"])
    account = get_env_variable(["SF_ACCOUNT", "SNOWFLAKE_ACCOUNT"])
    warehouse = get_env_variable(["SF_WAREHOUSE", "SNOWFLAKE_WAREHOUSE"])
    database = get_env_variable(["SF_DATABASE", "SNOWFLAKE_DATABASE"])
    schema = get_env_variable(["SF_SCHEMA", "SNOWFLAKE_SCHEMA"])

    # Basic credentials presence check
    if not all([user, password, account]):
        raise ValueError(
            f"Missing required Snowflake configuration values in .env! "
            f"Detected: user={user is not None}, password={password is not None}, account={account is not None}"
        )

    return snowflake.connector.connect(
        user=user,
        password=password,
        account=account,
        warehouse=warehouse,
        database=database,
        schema=schema
    )

def fetch_schema():
    try:
        conn = get_snowflake_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = CURRENT_SCHEMA()
        """)
        df = cursor.fetch_pandas_all()
        cursor.close()
        conn.close()
        
        schema_text = ""
        for table in df['TABLE_NAME'].unique():
            columns = df[df['TABLE_NAME'] == table]
            col_list = [f"{row['COLUMN_NAME']} ({row['DATA_TYPE']})" for _, row in columns.iterrows()]
            schema_text += f"Table: {table}\nColumns: {', '.join(col_list)}\n\n"
        return schema_text
    except Exception as e:
        raise RuntimeError(f"Snowflake Connection Failed. Check your credentials: {str(e)}")

@app.post("/api/chat")
async def chat_endpoint(request: ChatHistoryRequest):
    try:
        schema = fetch_schema()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    system_prompt = f"""
    You are an expert Snowflake SQL assistant with conversational memory. 
    Analyze the chat history and convert the user's latest request into a valid Snowflake SQL query based on the schema below.
    
    CRITICAL SAFETY RULES:
    1. If the user tries to modify, drop, delete, or alter data, refuse to answer.
    2. Return ONLY the raw executable SQL query. No explanation, no markdown.
    
    Database Schema:
    {schema}
    """
    
    groq_messages = [{"role": "system", "content": system_prompt}]
    for msg in request.history:
        groq_messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })
    
    try:
        response = client.chat.completions.create(
            messages=groq_messages,
            model="llama-3.3-70b-versatile",
            temperature=0.0
        )
        generated_sql = response.choices[0].message.content.strip()
        
        if "```sql" in generated_sql:
            generated_sql = generated_sql.split("```sql")[1].split("```")[0].strip()
        elif "```" in generated_sql:
            generated_sql = generated_sql.split("```")[1].split("```")[0].strip()
            
        forbidden_keywords = ["drop", "delete", "truncate", "alter", "insert", "update"]
        if any(kw in generated_sql.lower() for kw in forbidden_keywords):
            raise HTTPException(status_code=403, detail="Security Violation: Unauthorized SQL operation.")
        
        conn = get_snowflake_connection()
        cursor = conn.cursor()
        cursor.execute(generated_sql)
        df = cursor.fetch_pandas_all()
        cursor.close()
        conn.close()
        
        data_dict = df.to_dict(orient="records")
        
        insights = "No data available to analyze."
        chart_type = "none"
        
        if not df.empty:
            user_latest_query = request.history[-1]["content"] if request.history else "Data Query"
            
            insight_prompt = f"""
            You are a senior business analyst. Analyze this data fetched from Snowflake for the question: "{user_latest_query}".
            Data Sample:
            {df.head(10).to_string()}
            
            Provide exactly two things:
            1. Suggest chart type strictly from ['bar', 'line', 'none'].
            2. 3 short bullet points of business insights.
            
            Format:
            CHART: <type>
            INSIGHTS:
            - point 1
            - point 2
            """
            
            insight_response = client.chat.completions.create(
                messages=[{"role": "user", "content": insight_prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.2
            )
            
            raw_insight = insight_response.choices[0].message.content.strip()
            if "CHART:" in raw_insight and "INSIGHTS:" in raw_insight:
                parts = raw_insight.split("INSIGHTS:")
                chart_part = parts[0].replace("CHART:", "").strip().lower()
                if "bar" in chart_part: chart_type = "bar"
                elif "line" in chart_part: chart_type = "line"
                insights = parts[1].strip()
        
        return {
            "success": True,
            "sql": generated_sql,
            "data": data_dict,
            "insights": insights,
            "chart_type": chart_type
        }
        
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))
