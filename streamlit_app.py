import streamlit as st
import requests
import json
import re
import pymssql
from typing import Dict, Any, List
import pandas as pd
from datetime import datetime

class AzureOpenAIChat:
    def __init__(self):
        """Initialize API credentials from Streamlit secrets."""
        self.API_ENDPOINT = st.secrets.get("AZURE_OPENAI_API_ENDPOINT", "")
        self.API_KEY = st.secrets.get("AZURE_OPENAI_API_KEY", "")

    def extract_delivery_details(self, email_body: str, max_tokens: int = 300) -> Dict[str, Any]:
        """
        Send an email body to Azure OpenAI and extract structured delivery-related details.
        """
        headers = {
            "Content-Type": "application/json",
            "api-key": self.API_KEY,
        }

        prompt = f"""
        Extract delivery-related details from the following email body and return a JSON output with these keys:
        - delivery: "yes" if delivery is confirmed, otherwise "no".
        - price_num: Extracted price amount, default to 0.00 if not found.
        - description: Short description of the product if available.
        - order_id: Extracted order ID if available.
        - delivery_date: Extracted delivery date in YYYY-MM-DD format if available.
        - store: Store or sender name.
        - tracking_number: Extracted tracking number if available.
        - carrier: Extracted carrier name (FedEx, UPS, USPS, etc.) if available.

        Email Body:
        {email_body}

        Output JSON:
        """

        data = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.5,
            "top_p": 1,
            "frequency_penalty": 0,
            "presence_penalty": 0,
        }

        try:
            response = requests.post(self.API_ENDPOINT, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            st.error(f"Error calling Azure OpenAI API: {str(e)}")
            return None

def extract_valid_json(text: str) -> str:
    """Extract a valid JSON string from the model's output."""
    try:
        text = text.strip()
        text = text.replace("```json", "").replace("```", "")

        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            return json_match.group(0)

        return text
    except Exception as e:
        st.error(f"Error extracting JSON: {str(e)}")
        return ""

def get_connection():
    """Create and return a database connection with error handling."""
    try:
        return pymssql.connect(
            server=st.secrets["AZURE_SQL_SERVER"],
            user=st.secrets["AZURE_SQL_USERNAME"],
            password=st.secrets["AZURE_SQL_PASSWORD"],
            database=st.secrets["AZURE_SQL_DATABASE"]
        )
    except Exception as e:
        st.error(f"Database connection error: {str(e)}")
        return None

def create_table_if_not_exists():
    """Create the delivery_details table if it doesn't exist."""
    try:
        conn = get_connection()
        if conn is None:
            return

        cursor = conn.cursor()
        
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='delivery_details' AND xtype='U')
            CREATE TABLE delivery_details (
                id INT IDENTITY(1,1) PRIMARY KEY,
                delivery NVARCHAR(10),
                price_num FLOAT,
                description NVARCHAR(255),
                order_id NVARCHAR(50),
                delivery_date DATE,
                store NVARCHAR(255),
                tracking_number NVARCHAR(100),
                carrier NVARCHAR(50),
                created_at DATETIME DEFAULT GETDATE()
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Error creating table: {str(e)}")

def insert_into_db(data: Dict[str, Any]) -> bool:
    """Insert extracted JSON data into database and return success status."""
    try:
        conn = get_connection()
        if conn is None:
            return False

        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO delivery_details 
            (delivery, price_num, description, order_id, delivery_date, store, tracking_number, carrier)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data.get("delivery", "no"),
            data.get("price_num", 0.0),
            data.get("description", ""),
            data.get("order_id", ""),
            data.get("delivery_date", None),
            data.get("store", ""),
            data.get("tracking_number", ""),
            data.get("carrier", "")
        ))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error inserting data: {str(e)}")
        return False

def get_delivery_history() -> pd.DataFrame:
    """Fetch all delivery details from the database with error handling."""
    try:
        conn = get_connection()
        if conn is None:
            return pd.DataFrame()

        query = """
            SELECT 
                id,
                delivery,
                price_num,
                description,
                order_id,
                delivery_date,
                store,
                tracking_number,
                carrier,
                created_at
            FROM delivery_details 
            ORDER BY created_at DESC
        """
        
        df = pd.read_sql(query, conn)
        conn.close()
        return df
        
    except Exception as e:
        st.warning(f"Unable to fetch delivery history: {str(e)}")
        return pd.DataFrame(columns=[
            'id', 'delivery', 'price_num', 'description', 'order_id',
            'delivery_date', 'store', 'tracking_number', 'carrier', 'created_at'
        ])

def main():
    """Main application function."""
    st.set_page_config(
        page_title="Delivery Email Extractor",
        page_icon="📩",
        layout="wide"
    )

    st.title("📩 Delivery Email Extractor")
    st.markdown("---")

    # Create table if it doesn't exist
    create_table_if_not_exists()

    email_body = st.text_area("📧 Paste the email body below:")
    
    if st.button("🔍 Extract Details") and email_body:
        with st.spinner("📊 Analyzing email content..."):
            chat_client = AzureOpenAIChat()
            response = chat_client.extract_delivery_details(email_body)

            if response and "choices" in response:
                extracted_json = response["choices"][0]["message"]["content"]
                extracted_json = extract_valid_json(extracted_json)

                try:
                    parsed_json = json.loads(extracted_json)
                    if insert_into_db(parsed_json):
                        st.success("✅ Data successfully saved to database!")
                    
                except json.JSONDecodeError:
                    st.error("❌ Failed to parse the response. Please try again.")
                    st.text(extracted_json)
            else:
                st.error("❌ Sorry, I couldn't extract the details. Please try again.")
    
    # Display history in a separate section
    st.markdown("---")
    df = get_delivery_history()
    if not df.empty:
        st.write("### 📋 Delivery Details History")
        st.dataframe(df)

if __name__ == "__main__":
    main()
