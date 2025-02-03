import json
import os
import base64
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from autogen import AssistantAgent, config_list_from_json
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class NotificationService:
    def __init__(self, model_config_file: str=None):
        load_dotenv()
        if model_config_file is None:
            self.config_list = config_list_from_json(env_or_file=os.getenv("MODEL_CONFIG_FILE"))
        else:
            self.config_list = config_list_from_json(env_or_file=model_config_file)
        # self.config_list = config_list_from_json(env_or_file=os.path.join(os.getcwd(), "MODEL_CONFIG_LIST"))
        self.llm_config = {
            "config_list": self.config_list,
            "temperature": 0.9,
            "cache_seed": None
        }
        self.analysis_agent, self.email_agent = self.create_agents()

    def create_agents(self):
        analysis_agent = AssistantAgent(
            name="AnalysisAgent",
            system_message="You analyze the given description and generate a detailed report.",
            llm_config={
                "timeout": 600,
                "cache_seed": 42,
                "config_list": self.config_list,
            },
        )

        email_agent = AssistantAgent(
            name="EmailAgent",
            system_message="You take the analysis and generate a professional email with the details.",
            llm_config={
                "timeout": 600,
                "cache_seed": 42,
                "config_list": self.config_list,
            },
        )

        return analysis_agent, email_agent

    def generate_insensitive_email(self, description, segment, product, priority, impact, jira_id, jira_link, status_io_link,
                       white_board_link):
        analysis_response = self.analysis_agent.generate_reply(
            messages=[{"role": "user", "content": f"""
                Analyze the following description and provide a detailed breakdown:
                {description}
                {segment}
                {product}
                {priority}
                {impact}
                {jira_id}
                {jira_link}
                {status_io_link}
                {white_board_link}
            """}]
        )

        analysis = analysis_response.get("content", "Analysis not available.")

        email_response = self.email_agent.generate_reply(
            messages=[{"role": "user", "content": f"""
                Compose a professional email with the following analysis:
                {analysis}.
                You must return your response strictly in the following JSON format:
                {{
                    "subject": "<email_subject_value>",
                    "body": "<email_body_value>"
                }}
                Follow these rules:
                1. Compose an email in a thoughtful and helpful way.
                2. The email should be polite and it should show the urgency based on the priority of the issue.
                3. Email body should be support HTML tags.
                4. Email body should contain the Segment, Product, Priority and Impact information.
                5. Email body should contain jira_link, status_io_link and white_board_link.
                6. jira_link should be displayed as <a href="{jira_link}">{jira_id}</a>
                7. status_io_link should be displayed as <a href="{status_io_link}">Status IO Page</a>
                8. white_board_link should be displayed as <a href="{white_board_link}">White Board</a>
                9. Email body and subject should not include any quantitative data such as amount, number of transactions, number customers of etc.
                10. Email signature should be.
                ```
                Best Regards,
                AI Team,
                GNOC Project
                ```
            """}]
        )

        email_content = email_response.get("content", "Email generation failed.")
        print(f"email_content:- {email_content}")
        if "```json" in email_content:
            return json.loads(email_content.strip("```json\n").strip("\n```"))
        else:
            # return json.loads(email_content)
            return email_content

    def generate_sensitive_email(self, description, segment, product, priority, impact, jira_id, jira_link, status_io_link,
                       white_board_link):
        analysis_response = self.analysis_agent.generate_reply(
            messages=[{"role": "user", "content": f"""
                Analyze the following description and provide a detailed breakdown:
                {description}
                {segment}
                {product}
                {priority}
                {impact}
                {jira_id}
                {jira_link}
                {status_io_link}
                {white_board_link}
            """}]
        )

        analysis = analysis_response.get("content", "Analysis not available.")

        email_response = self.email_agent.generate_reply(
            messages=[{"role": "user", "content": f"""
                Compose a professional email with the following analysis:
                {analysis}.
                You must return your response strictly in the following JSON format:
                {{
                    "subject": "<email_subject_value>",
                    "body": "<email_body_value>"
                }}
                Follow these rules:
                1. Compose an email in a thoughtful and helpful way.
                2. The email should be polite and it should show the urgency based on the priority of the issue.
                3. Email body should be support HTML tags.
                4. Email body should contain the Segment, Product, Priority and Impact information.
                5. Email body should contain jira_link, status_io_link and white_board_link.
                6. jira_link should be displayed as <a href="{jira_link}">{jira_id}</a>
                7. status_io_link should be displayed as <a href="{status_io_link}">Status IO Page</a>
                8. white_board_link should be displayed as <a href="{white_board_link}">White Board</a>
                9. Email body and subject should include any quantitative data such as amount, number of transactions, number customers of etc.
                10. Email signature should be.
                ```
                Best Regards,
                AI Team,
                GNOC Project
                ```
            """}]
        )

        email_content = email_response.get("content", "Email generation failed.")
        if "```json" in email_content:
            return json.loads(email_content.strip("```json\n").strip("\n```"))
        else:
            # return json.loads(email_content)
            return email_content
        # return json.loads(email_content.strip("```json\n").strip("\n```"))

    def send_email(self, email_to, email_from, email_subject, email_body):
        try:
            creds = None
            if os.path.exists("gmail_token.json"):
                creds = Credentials.from_authorized_user_file("gmail_token.json",
                                                              ["https://www.googleapis.com/auth/gmail.send"])
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file("credentials.json",
                                                                     ["https://www.googleapis.com/auth/gmail.send"])
                    creds = flow.run_local_server(port=0)
                with open('gmail_token.json', 'w') as token:
                    token.write(creds.to_json())

            gmail_service = build("gmail", "v1", credentials=creds)

            message = MIMEMultipart()
            message.attach(MIMEText(email_body, 'html'))
            message['to'] = email_to
            message['from'] = email_from
            message['subject'] = email_subject
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            result = gmail_service.users().messages().send(userId="me", body={"raw": raw_message}).execute()
            print(f"Email sent successfully! Message ID: {result['id']}")
        except Exception as e:
            print(f"Failed to send email: {e}")

    def sensitive_notification_tool(self, subject, body):
        try:
            to = os.getenv("MERCHANT_SENSITIVE_TO_EMAIL")
            if "issuing" in body.lower():
                to = os.getenv("ISSUING_SENSITIVE_TO_EMAIL")
            from_email = os.getenv("FROM_EMAIL")
            self.send_email(to, from_email, subject, body)
            return f"Email sent successfully to {to}"
        except Exception as e:
            print(f"Failed to send sensitive notification: {e}")

    def insensitive_notification_tool(self, subject, body):
        try:
            to = os.getenv("MERCHANT_INSENSITIVE_TO_EMAIL")
            if "issuing" in body.lower():
                to = os.getenv("ISSUING_INSENSITIVE_TO_EMAIL")
            from_email = os.getenv("FROM_EMAIL")
            self.send_email(to, from_email, subject, body)
            return f"Email sent successfully to {to}"
        except Exception as e:
            print(f"Failed to send sensitive notification: {e}")


if __name__ == "__main__":
    service = NotificationService()

    description = "We are experiencing a critical issue in the merchant segment impacting our Transit product. Customers have been unable to perform Mastercard card transactions for the past 15 minutes, resulting in significant disruption. Approximately 10,000 transactions have been declined during this time, leading to a revenue loss of $50,000. This issue is affecting multiple merchants and requires immediate attention. The root cause appears to be related to the processing system for Mastercard transactions on the Transit product. Please prioritize this issue, as it has a high financial impact and is negatively affecting customer experience."
    segment = "Merchant"
    product = "TransIT"
    priority = "P1"
    impact = "High"
    jira_id = "JIRA-435"
    jira_link = "https://rahuluraneai.atlassian.net/browse/JIRA-435"
    status_io_link = "https://manage.statuspage.io/pages/cgdn7cbyygwm/incidents/6mqs47pyqzw0"
    white_board_link = "https://drive.google.com/file/d/1eUAIjQykN705b395T6UkdB8_ZqwEakhIcCNH5wZ9700/view?usp=sharing"

    email = service.generate_insensitive_email(description, segment, product, priority, impact, jira_id, jira_link, status_io_link,
                                   white_board_link)
    print("===========================")
    print(email.get("subject"))
    print(email.get("body"))
    print("===========================")

    service.insensitive_notification_tool(email.get("subject"), email.get("body"))

    email = service.generate_sensitive_email(description, segment, product, priority, impact, jira_id, jira_link,
                                               status_io_link,
                                               white_board_link)
    print("===========================")
    print(email.get("subject"))
    print(email.get("body"))
    print("===========================")

    service.sensitive_notification_tool(email.get("subject"), email.get("body"))
