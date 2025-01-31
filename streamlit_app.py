import streamlit as st
import requests
import json
import re
import pymssql
from typing import Dict, Any
import pandas as pd
from datetime import datetime

# [Previous AzureOpenAIChat class and other functions remain the same]

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
    
    # Create a styled header
    st.markdown("### 📦 Delivery Details")
    
    # Create two columns for key information
    col1, col2 = st.columns(2)
    
    with col1:
        # Delivery Status with colored badge
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

    # Create a DataFrame for the main details
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
    
    # Apply styling to the DataFrame
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

    # If there's a tracking number, add a tracking link suggestion
    if data.get("tracking_number") and data.get("carrier"):
        st.info(f"💡 You can track your package using the tracking number: {data['tracking_number']}")

def main():
    """Streamlit UI to interact with the user and display extracted delivery details."""
    st.set_page_config(
        page_title="Delivery Email Extractor",
        page_icon="📩",
        layout="centered"
    )
    
    # Add custom CSS for better styling
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

    # Text area for the user to input an email body
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
                    
                    # Display the formatted table instead of raw JSON
                    display_delivery_details(parsed_json)

                    # Insert extracted data into Azure SQL Database
                    insert_into_db(parsed_json)
                    st.success("✅ Data successfully saved to database!")

                except json.JSONDecodeError:
                    st.error("❌ Failed to parse the response. Please try again.")
                    st.text(extracted_json)
            else:
                st.error("❌ Sorry, I couldn't extract the details. Please try again.")

if __name__ == "__main__":
    main()