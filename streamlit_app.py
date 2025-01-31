import streamlit as st
import requests
import json
import re
import pymssql
from typing import Dict, Any, List
import pandas as pd
from datetime import datetime

# [Previous AzureOpenAIChat class remains the same]

def get_connection():
    """Create and return a database connection."""
    return pymssql.connect(
        server=st.secrets["AZURE_SQL_SERVER"],
        user=st.secrets["AZURE_SQL_USERNAME"],
        password=st.secrets["AZURE_SQL_PASSWORD"],
        database=st.secrets["AZURE_SQL_DATABASE"]
    )

def create_table_if_not_exists():
    """Create the delivery_details table if it doesn't exist."""
    conn = get_connection()
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

def insert_into_db(data: Dict[str, Any]) -> bool:
    """Insert extracted JSON data into database and return success status."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO delivery_details 
            (delivery, price_num, description, order_id, delivery_date, store, tracking_number, carrier)
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
        return True
    except Exception as e:
        st.error(f"Database error: {str(e)}")
        return False

def get_delivery_history() -> pd.DataFrame:
    """Fetch all delivery details from the database."""
    conn = get_connection()
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

def display_delivery_details(data: Dict[str, Any], is_current: bool = True):
    """Display delivery details in a formatted table."""
    if is_current:
        st.markdown("### 📦 Current Analysis")
    
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
            "Field": st.column_config.Column(width="medium"),
            "Value": st.column_config.Column(width="large")
        }
    )

    if data.get("tracking_number") and data.get("carrier"):
        st.info(f"💡 You can track your package using the tracking number: {data['tracking_number']}")

def display_history_table(df: pd.DataFrame):
    """Display historical delivery details in an interactive table."""
    if df.empty:
        st.info("No previous delivery emails analyzed yet.")
        return

    st.markdown("### 📋 Analysis History")

    # Format the DataFrame for display
    display_df = df.copy()
    
    # Format price as currency
    display_df['price_num'] = display_df['price_num'].apply(lambda x: f"${x:.2f}")
    
    # Format delivery date
    display_df['delivery_date'] = pd.to_datetime(display_df['delivery_date']).dt.strftime('%B %d, %Y')
    
    # Format created_at timestamp
    display_df['created_at'] = pd.to_datetime(display_df['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # Create delivery status column with emojis
    display_df['status'] = display_df['delivery'].apply(
        lambda x: "✅" if x == "yes" else "❌"
    )

    # Reorder and rename columns for display
    columns_to_display = {
        'created_at': 'Analyzed On',
        'status': 'Status',
        'store': 'Store',
        'description': 'Description',
        'price_num': 'Price',
        'delivery_date': 'Delivery Date',
        'tracking_number': 'Tracking Number',
        'carrier': 'Carrier'
    }
    
    display_df = display_df[columns_to_display.keys()].rename(columns=columns_to_display)

    # Display the interactive table
    st.dataframe(
        display_df,
        hide_index=True,
        column_config={
            "Status": st.column_config.Column(width="small"),
            "Store": st.column_config.Column(width="medium"),
            "Description": st.column_config.Column(width="large"),
            "Price": st.column_config.Column(width="small"),
            "Analyzed On": st.column_config.Column(width="medium"),
        }
    )

def main():
    """Main application function."""
    st.set_page_config(
        page_title="Delivery Email Extractor",
        page_icon="📩",
        layout="wide"
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

    # Create table if it doesn't exist
    create_table_if_not_exists()

    # Input section
    col1, col2 = st.columns([2, 1])
    
    with col1:
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
                        
                        if insert_into_db(parsed_json):
                            st.success("✅ Data successfully saved to database!")
                        
                    except json.JSONDecodeError:
                        st.error("❌ Failed to parse the response. Please try again.")
                        st.text(extracted_json)
                else:
                    st.error("❌ Sorry, I couldn't extract the details. Please try again.")
    
    # Display history in a separate column
    with col2:
        st.markdown("### 📊 Statistics")
        # Fetch and display some basic statistics
        df = get_delivery_history()
        if not df.empty:
            total_deliveries = len(df)
            confirmed_deliveries = len(df[df['delivery'] == 'yes'])
            total_spent = df['price_num'].sum()
            
            st.metric("Total Analyzed", total_deliveries)
            st.metric("Confirmed Deliveries", f"{confirmed_deliveries} ({(confirmed_deliveries/total_deliveries*100):.1f}%)")
            st.metric("Total Spent", f"${total_spent:.2f}")

    # Display full history table
    st.markdown("---")
    display_history_table(get_delivery_history())

if __name__ == "__main__":
    main()