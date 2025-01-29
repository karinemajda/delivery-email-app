import streamlit as st
import requests
import json
import re
import pymssql
from typing import Dict, Any

# Class to interact with Azure OpenAI and extract delivery-related details from email bodies
class AzureOpenAIChat:
    def __init__(self):
        """Initialize API credentials from Streamlit secrets."""
        self.API_ENDPOINT = st.secrets.get("AZURE_OPENAI_API_ENDPOINT", "")
        self.API_KEY = st.secrets.get("AZURE_OPENAI_API_KEY", "")

    def extract_delivery_details(self, email_body: str, max_tokens: int = 300) -> Dict[str, Any]:
        """
        Send an email body to Azure OpenAI and extract structured delivery-related details.

        Args:
            email_body (str): The raw email content to analyze.
            max_tokens (int): Maximum response token length (default is 300).

        Returns:
            Dict[str, Any]: A dictionary containing structured delivery details.
        """
        headers = {
            "Content-Type": "application/json",
            "api-key": self.API_KEY,
        }

        # Define the prompt that instructs Azure OpenAI on how to extract data
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

        # Create request payload
        data = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.5,  # Controls randomness
            "top_p": 1,
            "frequency_penalty": 0,
            "presence_penalty": 0,
        }

        # Make API request
        response = requests.post(self.API_ENDPOINT, headers=headers, json=data)
        response.raise_for_status()  # Raises an error for HTTP failures

        return response.json()  # Return AI response

def extract_valid_json(text: str) -> str:
    """
    Extract a valid JSON string from the model's output.

    Args:
        text (str): The raw AI response.

    Returns:
        str: Extracted JSON content.
    """
    text = text.strip()
    text = text.replace("```json", "").replace("```", "")  # Remove markdown JSON wrappers

    # Use regex to locate valid JSON content within the response
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        return json_match.group(0)

    return text  # Return raw text if no JSON structure is found

def insert_into_db(data: Dict[str, Any]):
    """
    Insert extracted JSON data into an Azure SQL Database using pymssql.

    Args:
        data (Dict[str, Any]): Extracted structured data.
    """

    # Establish a connection to Azure SQL using pymssql
    conn = pymssql.connect(
        server=st.secrets["AZURE_SQL_SERVER"],
        user=st.secrets["AZURE_SQL_USERNAME"],
        password=st.secrets["AZURE_SQL_PASSWORD"],
        database=st.secrets["AZURE_SQL_DATABASE"]
    )

    cursor = conn.cursor()

    # Create the delivery_details table if it does not exist
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

    # Insert extracted data into the table
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
    conn.close()  # Close the database connection

def main():
    """Streamlit UI to interact with the user and display extracted delivery details."""
    st.set_page_config(page_title="Delivery Email Extractor", page_icon="📩")
    st.title("Delivery Email Extractor")

    # Text area for the user to input an email body
    email_body = st.text_area("Paste the email body below:")

    if st.button("Extract Details") and email_body:
        with st.spinner("Extracting details..."):
            chat_client = AzureOpenAIChat()
            response = chat_client.extract_delivery_details(email_body)

            if response and "choices" in response:
                extracted_json = response["choices"][0]["message"]["content"]
                extracted_json = extract_valid_json(extracted_json)

                try:
                    parsed_json = json.loads(extracted_json)  # Convert string to JSON
                    st.json(parsed_json)  # Display formatted JSON output

                    # Insert extracted data into Azure SQL Database
                    insert_into_db(parsed_json)
                    st.success("Data successfully inserted into Azure SQL Database! ✅")

                except json.JSONDecodeError:
                    st.error("Failed to parse JSON response. Showing raw output:")
                    st.text(extracted_json)
            else:
                st.error("Sorry, I couldn't extract the details. Please try again.")

if __name__ == "__main__":
    main()