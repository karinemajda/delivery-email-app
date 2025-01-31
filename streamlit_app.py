import streamlit as st
import requests
import json
import re
import pymssql
from typing import Dict, Any
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

        response = requests.post(self.API_ENDPOINT, headers=headers, json=data)
        response.raise_for_status()

        return response.json()

def extract_valid_json(text: str) -> str:
    """Extract a valid JSON string from the model's output."""
    text = text.strip()
    text = text.replace("```json", "").replace("```", "")

    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        return json_match.group(0)

    return text

def insert_into_db(data: Dict[str, Any]):
    """Insert extracted JSON data into an Azure SQL Database using pymssql."""
    conn = pymssql.connect(
        server=st.secrets["AZURE_SQL_SERVER"],
        user=st.secrets["AZURE_SQL_USERNAME"],
        password=st.secrets["AZURE_SQL_PASSWORD"],
        database=st.secrets["AZURE_SQL_DATABASE"]
    )

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
            carrier NVARCHAR(50)
        )
    """)
    conn.commit()

    cursor.execute("""
        INSERT INTO delivery_details (delivery, price_num, description, order_id, delivery_date, store, tracking_number, carrier)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        data["delivery"],
        data["price_num"],
        data["description"],
        data["order_id"],
        data["delivery_date"],
        data["store"],
        data["tracking_number"],
        data["carrier"]
    ))

    conn.commit()
    conn.close()

def format_delivery_date(date_str: str) -> str:
    """Format the delivery date string or return empty string if invalid."""
    if not date_str:
        return ""
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').strftime('%B %d, %Y')
    except ValueError:
        return date_str

def display_delivery_details(data: Dict[str, Any]):
    """Display delivery details in a formatted table with styled elements."""
    st.markdown("### 📦 Delivery Details")
    
    col1, col2 = st.columns(2)
    
    with col1:
        status_color = "success" if data["delivery"] == "yes" else "error"
        st.markdown(
            f"""
            <div style='background-color: {'#28a745' if status_color == 'success' else '#dc3545'}; 
                        padding: 10px; 
                        border-radius: 5px; 
                        color: white; 
                        display: inline-block;
                        margin-bottom: 10px;'>
                {'✓ Delivery Confirmed' if data["delivery"] == "yes" else '⚠ Delivery Not Confirmed'}
            </div>
            """,
            unsafe_allow_html=True
        )

    with col2:
        if data["price_num"] > 0:
            st.markdown(f"### 💰 ${data['price_num']:.2f}")

    details_dict = {
        "Field": [
            "Order ID",
            "Description",
            "Store",
            "Delivery Date",
            "Carrier",
            "Tracking Number"
        ],
        "Value": [
            data.get("order_id", ""),
            data.get("description", ""),
            data.get("store", ""),
            format_delivery_date(data.get("delivery_date", "")),
            data.get("carrier", ""),
            data.get("tracking_number", "")
        ]
    }
    
    df = pd.DataFrame(details_dict)
    
    st.dataframe(
        df,
        hide_index=True,
        column_config={
            "Field": st.column_config.Column(
                width="medium"
            ),
            "Value": st.column_config.Column(
                width="large"
            )
        }
    )

    if data.get("tracking_number") and data.get("carrier"):
        st.info(f"💡 You can track your package using the tracking number: {data['tracking_number']}")

def main():
    """Streamlit UI to interact with the user and display extracted delivery details."""
    st.set_page_config(
        page_title="Delivery Email Extractor",
        page_icon="📩",
        layout="centered"
    )
    
    st.markdown("""
        <style>
        .stButton>button {
            width: 100%;
        }
        .stTextArea>div>div>textarea {
            height: 200px;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.title("📩 Delivery Email Extractor")
    st.markdown("---")

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
                    display_delivery_details(parsed_json)
                    insert_into_db(parsed_json)
                    st.success("✅ Data successfully saved to database!")

                except json.JSONDecodeError:
                    st.error("❌ Failed to parse the response. Please try again.")
                    st.text(extracted_json)
            else:
                st.error("❌ Sorry, I couldn't extract the details. Please try again.")

if __name__ == "__main__":
    main()