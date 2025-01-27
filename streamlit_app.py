import streamlit as st
import requests
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class OrderInfo:
    is_order: bool
    order_number: Optional[str] = None
    total_amount: Optional[float] = None
    items: Optional[list] = None
    shipping_address: Optional[str] = None
    order_date: Optional[str] = None

class AzureOpenAIChat:
    def __init__(self):
        self.API_ENDPOINT = st.secrets.get("AZURE_OPENAI_API_ENDPOINT")
        self.API_KEY = st.secrets.get("AZURE_OPENAI_API_KEY")
        
        if not self.API_ENDPOINT or not self.API_KEY:
            raise ValueError(
                "Azure OpenAI credentials not found. Please configure AZURE_OPENAI_API_ENDPOINT "
                "and AZURE_OPENAI_API_KEY in your Streamlit secrets."
            )

    def analyze_email(self, email_content: str) -> OrderInfo:
        """Analyze email content to determine if it's an order and extract relevant information"""
        system_prompt = """
        Analyze the following email content and determine if it's related to an online order.
        If it is an order, extract the following information:
        - Order number
        - Total amount
        - Items ordered (with quantities)
        - Shipping address
        - Order date
        
        Return the response in the following JSON format:
        {
            "is_order": true/false,
            "order_number": "string or null",
            "total_amount": number or null,
            "items": [{"name": "string", "quantity": number, "price": number}] or null,
            "shipping_address": "string or null",
            "order_date": "YYYY-MM-DD or null"
        }
        """
        
        headers = {
            "Content-Type": "application/json",
            "api-key": self.API_KEY,
        }
        
        data = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": email_content}
            ],
            "max_tokens": 500,
            "temperature": 0.3,  # Lower temperature for more consistent output
            "response_format": {"type": "json_object"}  # Ensure JSON response
        }
        
        response = requests.post(self.API_ENDPOINT, headers=headers, json=data)
        response.raise_for_status()
        
        result = response.json()["choices"][0]["message"]["content"]
        parsed_result = json.loads(result)
        
        return OrderInfo(**parsed_result)

def main():
    st.set_page_config(page_title="Email Order Analyzer", page_icon="📧")
    st.title("Email Order Analyzer")
    
    # Email input area
    email_content = st.text_area("Paste email content here:", height=200)
    
    if st.button("Analyze Email"):
        if email_content:
            with st.spinner("Analyzing email content..."):
                analyzer = AzureOpenAIChat()
                try:
                    result = analyzer.analyze_email(email_content)
                    
                    if result.is_order:
                        st.success("This email contains order information!")
                        
                        # Display order details in an organized way
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.subheader("Order Details")
                            st.write(f"**Order Number:** {result.order_number}")
                            st.write(f"**Order Date:** {result.order_date}")
                            st.write(f"**Total Amount:** ${result.total_amount:.2f}")
                        
                        with col2:
                            st.subheader("Shipping Address")
                            st.write(result.shipping_address)
                        
                        if result.items:
                            st.subheader("Items Ordered")
                            for item in result.items:
                                st.write(f"• {item['quantity']}x {item['name']} - ${item['price']:.2f}")
                    else:
                        st.warning("This email does not appear to be related to an order.")
                
                except ValueError as ve:
                    st.error(str(ve))
                except requests.exceptions.InvalidURL:
                    st.error("Invalid Azure OpenAI API URL. Please check your AZURE_OPENAI_API_ENDPOINT configuration.")
                except requests.exceptions.RequestException as e:
                    st.error(f"API Request Error: {str(e)}")
                except Exception as e:
                    st.error(f"Unexpected error: {str(e)}")
                    st.error("Please check your Azure OpenAI configuration in Streamlit secrets.")
        else:
            st.warning("Please paste some email content to analyze.")

if __name__ == "__main__":
    main()
