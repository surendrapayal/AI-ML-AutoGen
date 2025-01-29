import json
import os
import requests
from autogen import ConversableAgent, AssistantAgent, config_list_from_json
from dotenv import load_dotenv
from googleapiclient.discovery import build
from jira import JIRA
from google.oauth2.service_account import Credentials as ServiceCredential

load_dotenv()

class IncidentManager:
    def __init__(self, model_config_file: str=None):
        self.status_page_user_proxy = None
        self.status_page_creation_assistant = None
        self.white_board_user_proxy = None
        self.white_board_creation_assistant = None
        self.jira_user_proxy = None
        self.jira_ticket_creation_assistant = None
        self.issue_type = "Bug"
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
        self.scopes = [
            "https://www.googleapis.com/auth/documents.readonly",
            "https://www.googleapis.com/auth/documents",
            "https://www.googleapis.com/auth/drive"
        ]
        self.jira_options = {'server': os.getenv("JIRA_URL")}
        self.status_page_url = os.getenv("STATUS_PAGE_URL")
        self.url = f"{self.status_page_url}/pages/cgdn7cbyygwm/incidents"
        self.template_doc_id = os.getenv("WHITEBOARD_TEMPLATE_DOC_ID")
        self.jira = JIRA(options=self.jira_options, basic_auth=(os.getenv("FROM_EMAIL"), os.getenv("JIRA_API_TOKEN")))
        self.status_page_headers = {
            "Authorization": f"OAuth {os.getenv("STATUS_API_TOKEN")}",
            "Content-Type": "application/json"
        }
        self.setup_agents()

    def setup_agents(self):
        self.jira_ticket_creation_assistant = AssistantAgent(
            name="JiraTicketCreationAssistant",
            system_message=(
                "You are a helpful AI Jira ticket creator. Use the function `create_jira_ticket` "
                "with the parameters `priority`, `summary`, and `description`. Return 'TERMINATE' when done."
            ),
            llm_config=self.llm_config,
            max_consecutive_auto_reply=1
        )
        self.jira_user_proxy = ConversableAgent(
            name="JiraUserProxy",
            is_termination_msg=lambda msg: msg.get("content") and "TERMINATE" in msg["content"],
            human_input_mode="NEVER",
            max_consecutive_auto_reply=1
        )

        self.white_board_creation_assistant = AssistantAgent(
            name="WhiteBoardCreationAssistant",
            system_message=(
                "You are a helpful AI White Board link creator. Use the function `create_white_board` "
                "with the parameters `jira_id`, `summary`, `segment`, and `product`. "
                "Return 'TERMINATE' when done."
            ),
            llm_config=self.llm_config,
            max_consecutive_auto_reply=1
        )
        self.white_board_user_proxy = ConversableAgent(
            name="WhiteBoardUserProxy",
            is_termination_msg=lambda msg: msg.get("content") and "TERMINATE" in msg["content"],
            human_input_mode="NEVER",
            max_consecutive_auto_reply=1
        )

        self.status_page_creation_assistant = AssistantAgent(
            name="StatusPageCreationAssistant",
            system_message=(
                "You are a helpful AI status page creator. Use the function `create_status_page` "
                "with the parameters `jira_id`, `priority`, `summary`, and `description`."
            ),
            llm_config=self.llm_config,
            max_consecutive_auto_reply=1
        )
        self.status_page_user_proxy = ConversableAgent(
            name="StatusPageUserProxy",
            is_termination_msg=lambda msg: msg.get("content") and "TERMINATE" in msg["content"],
            human_input_mode="NEVER",
            max_consecutive_auto_reply=1
        )

        self.jira_ticket_creation_assistant.register_for_llm(name="create_jira_ticket")(self.create_jira_ticket)
        self.white_board_creation_assistant.register_for_llm(name="create_white_board")(self.create_white_board)
        self.status_page_creation_assistant.register_for_llm(name="create_status_page")(self.create_status_page)

        self.jira_user_proxy.register_for_execution(name="create_jira_ticket")(self.create_jira_ticket)
        self.white_board_user_proxy.register_for_execution(name="create_white_board")(self.create_white_board)
        self.status_page_user_proxy.register_for_execution(name="create_status_page")(self.create_status_page)

    def create_jira_ticket(self, priority: str, summary: str, description: str) -> str:
        issue_data = {
            'project': {'id': '10000'},
            'summary': f'{priority} - {summary}',
            'description': description,
            'issuetype': {'name': self.issue_type}
        }
        try:
            jira_response = self.jira.create_issue(fields=issue_data)
            return json.dumps(
                {"jira_id": jira_response.key, "priority": priority, "summary": summary, "description": description},
                indent=4)
        except Exception as e:
            print(f"Failed to create Jira ticket: {e}")
            return ""

    def create_white_board(self, jira_id: str, summary: str, segment: str, product: str) -> str:
        replacements = {"ICD_NUMER": jira_id, "ISSUE_DESCRIPTION": summary, "IMPACTED_SEGMENT": segment,
                        "IM_IMPACTED_SERVICE": product}
        document_name = f"{jira_id} - {summary}"
        new_document_id, document_link = self.fetch_clone_and_replace(self.template_doc_id, replacements, document_name)
        white_board_result_payload = {
            "white_board_id": new_document_id,
            "white_board_link": document_link
        }
        print(f"white_board_result_payload:- {white_board_result_payload}")
        return json.dumps(white_board_result_payload)

    def fetch_clone_and_replace(self, original_document_id, replacements, document_name):
        credentials = self.authenticate_google_api()
        docs_service = build('docs', 'v1', credentials=credentials)
        new_doc_id, document_link = self.clone_google_doc(original_document_id, document_name)
        replace_requests = [{'replaceAllText': {'containsText': {'text': key, 'matchCase': True}, 'replaceText': val}}
                            for key, val in replacements.items()]
        docs_service.documents().batchUpdate(documentId=new_doc_id, body={'requests': replace_requests}).execute()
        return new_doc_id, document_link

    def clone_google_doc(self, source_doc_id, document_name):
        credentials = self.authenticate_google_api()
        drive_service = build('drive', 'v3', credentials=credentials)
        copied_file = drive_service.files().copy(fileId=source_doc_id, body={'name': document_name}).execute()
        cloned_doc_id = copied_file.get('id')
        permissions = {'role': 'writer', 'type': 'anyone'}
        drive_service.permissions().create(fileId=cloned_doc_id, body=permissions).execute()
        file_link = f"https://drive.google.com/file/d/{cloned_doc_id}/view?usp=sharing"
        return cloned_doc_id, file_link

    def create_status_page(self, jira_id: str, priority: str, summary: str, description: str) -> str:
        incident_data = {
            "incident": {
                "name": f"{jira_id} - {priority} - {summary}",
                "status": "investigating",
                "impact_override": "none",
                "scheduled_remind_prior": False,
                "auto_transition_to_maintenance_state": False,
                "auto_transition_to_operational_state": False,
                "scheduled_auto_in_progress": False,
                "scheduled_auto_completed": False,
                "auto_transition_deliver_notifications_at_start": False,
                "auto_transition_deliver_notifications_at_end": False,
                "metadata": {},
                "deliver_notifications": False,
                "auto_tweet_at_beginning": False,
                "auto_tweet_on_completion": False,
                "auto_tweet_on_creation": False,
                "auto_tweet_one_hour_before": False,
                "backfill_date": "string",
                "backfilled": False,
                "body": f"{jira_id} - {priority} - {description}",
                "scheduled_auto_transition": True
            }
        }

        try:
            response = requests.post(self.url, json=incident_data, headers=self.status_page_headers)
            response.raise_for_status()  # Raise an error for HTTP errors
            print(f"Response received while creating status page:-\n{response.json()}")
            status_page_result_payload = {
                "status_io_id": response.json()["id"],
                "status_io_page_link": "https://manage.statuspage.io/pages/cgdn7cbyygwm/incidents/" + response.json()["id"]
            }
            print(f"status_page_result_payload:- {status_page_result_payload}")
            return json.dumps(status_page_result_payload)

        except requests.exceptions.RequestException as e:
            print(f"Failed to create status page: {e}")
            raise
        except Exception as e:
            print(f"Failed to create Status Page: {e}")
            raise

    def authenticate_google_api(self):
        return ServiceCredential.from_service_account_file(os.getenv("SERVICE_ACCOUNT_JSON"), scopes=self.scopes)

    def initiate_jira_ticket_creation(self, priority, summary, description):
        return self.jira_user_proxy.initiate_chat(self.jira_ticket_creation_assistant,
                                           message=f"Please create the Jira ticket with priority `{priority}`, summary `{summary}` and description `{description}`")

    def initiate_white_board_creation(self, jira_id, summary, segment, product):
        return self.white_board_user_proxy.initiate_chat(self.white_board_creation_assistant,
                                                  message=f"Please create the white board link with jira_id `{jira_id}`, summary `{summary}`, segment `{segment}`, and product `{product}`")

    def initiate_status_page_creation(self, jira_id, priority, summary, description):
        return self.status_page_user_proxy.initiate_chat(self.status_page_creation_assistant,
                                                         message=f"Please create the status page with jira_id `{jira_id}`, priority `{priority}`, summary `{summary}`, description `{description}`")


# Example Usage
if __name__ == "__main__":
    # Sample Jira ticket details
    jira_id = "JIRA-123"
    priority = "P1"
    summary = "Mastercard transactions down; $80k revenue loss."
    description = (
        "We are experiencing a critical issue in the merchant segment impacting our Transit product. "
        "Customers have been unable to perform Mastercard card transactions for the past 15 minutes, "
        "resulting in significant disruption. Approximately 10,000 transactions have been declined during "
        "this time, leading to a revenue loss of $80,000. This issue is affecting multiple merchants and "
        "requires immediate attention. The root cause appears to be related to the processing system for "
        "Mastercard transactions on the Transit product. This has a high financial impact and is negatively "
        "affecting customer experience."
    )
    segment = "Merchant"
    product = "TransIT"
    incident_manager = IncidentManager()
    jira_response = incident_manager.initiate_jira_ticket_creation(priority, summary, description)
    tool_responses = []
    for message in jira_response.chat_history:
        if 'tool_responses' in message:
            tool_responses.extend(message['tool_responses'])

    jira_extracted_responses = json.loads(tool_responses[0].get("content"))
    print(f"jira_extracted_responses:- {jira_extracted_responses}")

    white_board_response = incident_manager.initiate_white_board_creation(jira_id, summary, segment, product)
    print(f"white_board_response:- {white_board_response}")
    tool_responses = []
    for message in white_board_response.chat_history:
        if 'tool_responses' in message:
            tool_responses.extend(message['tool_responses'])

    white_board_extracted_responses = tool_responses[0].get("content")
    print(f"white_board_extracted_responses:- {white_board_extracted_responses}")
    print(f"white_board_id:- {json.loads(white_board_extracted_responses).get("white_board_id")}")
    print(f"white_board_link:- {json.loads(white_board_extracted_responses).get("white_board_link")}")

    status_page_response = incident_manager.initiate_status_page_creation(jira_id, priority, summary, description)
    tool_responses = []
    for message in status_page_response.chat_history:
        if 'tool_responses' in message:
            tool_responses.extend(message['tool_responses'])

    status_page_extracted_responses = tool_responses[0].get("content")
    print(f"status_page_extracted_responses:- {status_page_extracted_responses}")
    print(f"status_io_id:- {json.loads(status_page_extracted_responses).get("status_io_id")}")
    print(f"status_io_page_link:- {json.loads(status_page_extracted_responses).get("status_io_page_link")}")