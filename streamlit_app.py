import imaplib
import email
from email.header import decode_header
import streamlit as st
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

class EmailClient:
    def __init__(self):
        """Initialize email client with credentials from Streamlit secrets."""
        self.email_address = st.secrets.get("EMAIL_ADDRESS", "")
        self.email_password = st.secrets.get("EMAIL_APP_PASSWORD", "")  # App-specific password
        self.imap_server = st.secrets.get("IMAP_SERVER", "imap.gmail.com")  # Default to Gmail
        self.imap_port = st.secrets.get("IMAP_PORT", 993)
        self.conn = None

    def connect(self) -> bool:
        """Establish connection to the email server."""
        try:
            self.conn = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            self.conn.login(self.email_address, self.email_password)
            return True
        except Exception as e:
            st.error(f"Failed to connect to email server: {str(e)}")
            return False

    def disconnect(self):
        """Safely disconnect from the email server."""
        if self.conn:
            try:
                self.conn.logout()
            except:
                pass

    def get_delivery_emails(self, days_back: int = 30, 
                          search_terms: List[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch delivery-related emails from the last specified number of days.
        
        Args:
            days_back: Number of days to look back for emails
            search_terms: List of keywords to search for in email subjects
            
        Returns:
            List of dictionaries containing email details
        """
        if search_terms is None:
            search_terms = ["order", "shipped", "delivery", "tracking"]

        emails = []
        try:
            if not self.connect():
                return emails

            # Select the inbox
            self.conn.select("INBOX")

            # Calculate the date range
            date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
            search_criteria = f'(SINCE "{date}")'

            # Search for emails
            _, message_numbers = self.conn.search(None, search_criteria)

            for num in message_numbers[0].split():
                try:
                    _, msg_data = self.conn.fetch(num, "(RFC822)")
                    email_body = msg_data[0][1]
                    message = email.message_from_bytes(email_body)

                    # Check if subject contains any of the search terms
                    subject = decode_header(message["subject"])[0][0]
                    if isinstance(subject, bytes):
                        subject = subject.decode()

                    if any(term.lower() in subject.lower() for term in search_terms):
                        # Extract email content
                        body = self._get_email_body(message)
                        
                        emails.append({
                            "subject": subject,
                            "from": message["from"],
                            "date": message["date"],
                            "body": body
                        })

                except Exception as e:
                    st.warning(f"Error processing email: {str(e)}")
                    continue

            return emails

        finally:
            self.disconnect()

    def _get_email_body(self, message: email.message.Message) -> str:
        """Extract the email body from a message."""
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        return part.get_payload(decode=True).decode()
                    except:
                        continue
        else:
            try:
                return message.get_payload(decode=True).decode()
            except:
                return ""
        return ""

# Modify the main() function to include email integration
def main():
    st.set_page_config(
        page_title="Delivery Email Extractor",
        page_icon="📩",
        layout="wide"
    )
    
    st.title("📩 Delivery Email Extractor")
    st.markdown("---")

    # Create table if it doesn't exist
    create_table_if_not_exists()

    # Add email configuration section
    with st.sidebar:
        st.header("📧 Email Settings")
        days_back = st.slider("Days to look back", 1, 90, 30)
        search_terms = st.text_input(
            "Search terms (comma-separated)", 
            "order,shipped,delivery,tracking"
        ).split(",")
        
        if st.button("🔄 Fetch Recent Emails"):
            with st.spinner("Fetching emails..."):
                email_client = EmailClient()
                emails = email_client.get_delivery_emails(days_back, search_terms)
                
                if emails:
                    st.session_state['emails'] = emails
                    st.success(f"Found {len(emails)} delivery-related emails!")
                else:
                    st.warning("No delivery emails found in the specified period.")

    # Main content area
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Add dropdown to select from fetched emails
        if 'emails' in st.session_state and st.session_state['emails']:
            selected_email = st.selectbox(
                "Select an email to analyze:",
                options=range(len(st.session_state['emails'])),
                format_func=lambda x: st.session_state['emails'][x]['subject']
            )
            
            email_body = st.session_state['emails'][selected_email]['body']
            st.text_area("Email content:", value=email_body, height=200)
            
            if st.button("🔍 Extract Details"):
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
                    else:
                        st.error("❌ Sorry, I couldn't extract the details. Please try again.")
        else:
            st.info("👈 Use the sidebar to fetch delivery emails")

    # Statistics and history sections remain the same...
    with col2:
        st.markdown("### 📊 Statistics")
        try:
            df = get_delivery_history()
            if not df.empty:
                total_deliveries = len(df)
                confirmed_deliveries = len(df[df['delivery'] == 'yes'])
                total_spent = df['price_num'].sum()
                
                st.metric("Total Analyzed", total_deliveries)
                if total_deliveries > 0:
                    st.metric("Confirmed Deliveries", 
                             f"{confirmed_deliveries} ({(confirmed_deliveries/total_deliveries*100):.1f}%)")
                    st.metric("Total Spent", f"${total_spent:.2f}")
            else:
                st.metric("Total Analyzed", 0)
                st.metric("Confirmed Deliveries", "0 (0%)")
                st.metric("Total Spent", "$0.00")
        except Exception as e:
            st.warning("Unable to load statistics. Please try again later.")

    # Display full history table
    st.markdown("---")
    display_history_table(get_delivery_history())

if __name__ == "__main__":
    main()