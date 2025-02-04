import json
import os
import streamlit as st

from notification_manager_agent import NotificationService
from incident_manager_agent import IncidentManager
from priority_identification_agent import PriorityIdentificationAgent

def extract_tool_responses(chat_result):
  """
  Extracts tool_responses from a given ChatResult object.

  Args:
    chat_result: A ChatResult object containing chat history.

  Returns:
    A list of tool_responses.
  """

  tool_responses = []
  for message in chat_result.chat_history:
    if 'tool_responses' in message:
      tool_responses.extend(message['tool_responses'])
  return tool_responses

image_path = f"{os.getcwd()}/gp.png"
i = 0

# Custom CSS to hide Streamlit default header, menu, and footer
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    #header {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stAppDeployButton"] {visibility: hidden;} 
    </style>
"""

# Apply the custom CSS
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# initialize chat history
if "messages" not in st.session_state:
    st.session_state["messages"] = []

if "feedback" not in st.session_state:
    st.session_state["feedback"] = []

# Display chat messages from history on app rerun
for i, message in enumerate(st.session_state["messages"]):
    with st.chat_message(message["role"]):
        st.markdown(message["content"], unsafe_allow_html=True)
        # Display feedback buttons for assistant messages
        if message["role"] == "assistant":
            if "Jira Information" not in message["content"]:
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("👍", key=f"thumbs_up_{i}"):
                        st.session_state.feedback.append({"message_index": i, "feedback": "positive"})
                        st.success("Thanks for your feedback!")
                        assistant_message = message["content"]
                        if "This issue does not appear to be related to any GP products, and unfortunately, I am unable to proceed with further action. Thank you for your understanding.".lower() not in assistant_message.lower():
                            assistant_messages = assistant_message.split("\n\n")
                            summary = assistant_messages[0].split("</b>")[1].strip()
                            description = assistant_messages[1].split("</b>")[1].strip()
                            priority = assistant_messages[2].split("</b>")[1].strip()
                            segment = assistant_messages[3].split("</b>")[1].strip()
                            product = assistant_messages[4].split("</b>")[1].strip()
                            impact = assistant_messages[5].split("</b>")[1].strip()
                            urgency = assistant_messages[6].split("</b>")[1].strip()
                            # jira_creator = IncidentManager()
                            incident_manager = IncidentManager()
                            jira_response = incident_manager.initiate_jira_ticket_creation(priority, summary, description)
                            jira_extracted_responses = json.loads(
                            extract_tool_responses(jira_response)[0].get("content"))
                            jira_id = jira_extracted_responses.get("jira_id")
                            jira_link = f"https://rahuluraneai.atlassian.net/browse/{jira_id}"

                            white_board_response = incident_manager.initiate_white_board_creation(jira_id, summary,
                                                                                                  segment, product)
                            white_board_extracted_responses = json.loads(
                                extract_tool_responses(white_board_response)[0].get("content"))
                            white_board_link = white_board_extracted_responses.get("white_board_link")

                            status_page_response = incident_manager.initiate_status_page_creation(jira_id, priority,
                                                                                                  summary, description)
                            status_page_extracted_responses = json.loads(
                                extract_tool_responses(status_page_response)[0].get("content"))
                            status_io_page_link = status_page_extracted_responses.get("status_io_page_link")

                            # result = main.kickoff(summary, description, priority, segment, product, impact, urgency)
                            assistant_response = ""
                            assistant_response = assistant_response + f"<b>Jira Information:</b> <a href='{jira_link}'>{jira_id}</a>\n\n"
                            assistant_response = assistant_response + f"<b>Status IO Page Information:</b> <a href='{status_io_page_link}'>Status IO Page</a>\n\n"
                            assistant_response = assistant_response + f"<b>White Board Information:</b> <a href='{white_board_link}'>White Board</a>\n\n"
                            st.session_state.messages.append({"role": "assistant", "content": assistant_response})

                            # Notification service
                            notification_service = NotificationService()

                            # Insensitive email
                            email_insensitive_content = notification_service.generate_insensitive_email(description, segment, product, priority, impact,
                                                                       jira_id, jira_link, status_io_page_link,
                                                                       white_board_link)
                            print(f"email_insensitive_content:- {email_insensitive_content}")
                            print(f"email_insensitive_content :: subject:- {email_insensitive_content.get("subject")}")
                            print(f"email_insensitive_content :: body:- {email_insensitive_content.get("body")}")
                            notification_service.insensitive_notification_tool(email_insensitive_content.get("subject"), email_insensitive_content.get("body"))

                            # Sensitive email
                            email_sensitive_content = notification_service.generate_sensitive_email(description,
                                                                                                        segment,
                                                                                                        product,
                                                                                                        priority,
                                                                                                        impact,
                                                                                                        jira_id,
                                                                                                        jira_link,
                                                                                                        status_io_page_link,
                                                                                                        white_board_link)
                            print(f"email_sensitive_content:- {email_sensitive_content}")
                            print(f"email_sensitive_content :: subject:- {email_sensitive_content.get("subject")}")
                            print(f"email_sensitive_content :: body:- {email_sensitive_content.get("body")}")
                            notification_service.sensitive_notification_tool(
                                email_sensitive_content.get("subject"), email_sensitive_content.get("body"))

                            continue
                with col2:
                    if st.button("👎", key=f"thumbs_down_{i}"):
                        st.session_state.feedback.append({"message_index": i, "feedback": "negative"})
                        st.warning("Thanks for your feedback!\n\nPlease provide more details so that the system can process your request.")
                        continue

# React to user input
if user_input := st.chat_input("Please enter your GNOC related query..."):
    # Fetch the last message with role "user"
    last_user_message = None
    for message in reversed(st.session_state["messages"]):
        if message["role"] == "user":
            last_user_message = message["content"]
            break

    feedback_type = None
    for feedback_item in reversed(st.session_state["feedback"]):
        feedback_type = feedback_item["feedback"]
        break

    # Use the last_user_message if it exists
    if last_user_message and feedback_type == "negative":
        user_input = last_user_message + "\n" + user_input

    # Display user message in the chat message container
    with st.chat_message("user"):
        st.markdown(user_input, unsafe_allow_html=True)
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": user_input})
    initial_task = f"""Please prioritize the below issue reported by user.
    Issue:- {user_input}
    """
    result = PriorityIdentificationAgent().prioritize_issue(user_input)
    # Append bot message
    assistant_response = ""
    # if result.get("description").lower() == "This issue does not appear to be related to any GP products, and unfortunately, I am unable to proceed with further action. Thank you for your understanding.".lower():
    if result is None:
        assistant_response = assistant_response + f"<b>Issue Description:</b> <span style='color:red;'>This issue does not appear to be related to any GP products, and unfortunately, I am unable to proceed with further action. Thank you for your understanding.</span>"
    else:
        assistant_response = assistant_response + f"<b>Issue Summary:</b> {result.get("summary")}\n\n"
        assistant_response = assistant_response + f"<b>Issue Description:</b> {result.get("description")}\n\n"
        assistant_response = assistant_response + f"<b>Issue Priority:</b> {result.get("priority")}\n\n"
        assistant_response = assistant_response + f"<b>Issue Segment:</b> {result.get("segment")}\n\n"
        assistant_response = assistant_response + f"<b>Issue Product:</b> {result.get("product")}\n\n"
        assistant_response = assistant_response + f"<b>Issue Impact:</b> {result.get("impact")}\n\n"
        assistant_response = assistant_response + f"<b>Issue Urgency:</b> {result.get("urgency")}\n\n"

    # Display assistant response in the chat message containers
    with st.chat_message("assistant"):
        st.markdown(assistant_response, unsafe_allow_html=True)
        if "Jira Information" not in assistant_response:
            i += 1
            col1, col2 = st.columns(2)
            with col1:
                if st.button("👍", key=f"thumbs_up_{i}"):
                    st.session_state.feedback.append({"message_index": i, "feedback": "positive"})
                    st.success("Thanks for your feedback!")
                    assistant_message = assistant_response
                    if "This issue does not appear to be related to any GP products, and unfortunately, I am unable to proceed with further action. Thank you for your understanding.".lower() not in assistant_message.lower():
                        assistant_messages = assistant_message.split("\n\n")
                        summary = assistant_messages[0].split("</b>")[1].strip()
                        description = assistant_messages[1].split("</b>")[1].strip()
                        priority = assistant_messages[2].split("</b>")[1].strip()
                        segment = assistant_messages[3].split("</b>")[1].strip()
                        product = assistant_messages[4].split("</b>")[1].strip()
                        impact = assistant_messages[5].split("</b>")[1].strip()
                        urgency = assistant_messages[6].split("</b>")[1].strip()
                        # jira_creator = JiraTicketCreator()
                        incident_manager = IncidentManager()
                        # jira_response = jira_creator.create_ticket(priority, summary, description)
                        jira_response = incident_manager.initiate_jira_ticket_creation(priority, summary, description)
                        jira_extracted_responses = json.loads(extract_tool_responses(jira_response)[0].get("content"))
                        jira_id = jira_extracted_responses.get("jira_id")
                        jira_link = f"https://rahuluraneai.atlassian.net/browse/{jira_id}"

                        white_board_response = incident_manager.initiate_white_board_creation(jira_id, summary, segment, product)
                        white_board_extracted_responses = json.loads(extract_tool_responses(white_board_response)[0].get("content"))
                        white_board_link = white_board_extracted_responses.get("white_board_link")

                        status_page_response = incident_manager.initiate_status_page_creation(jira_id, priority,
                                                                                              summary, description)
                        status_page_extracted_responses = json.loads(extract_tool_responses(status_page_response)[0].get("content"))
                        status_io_page_link = status_page_extracted_responses.get("status_io_page_link")

                        assistant_response = ""
                        assistant_response = assistant_response + f"<b>Jira Information:</b> <a href='{jira_link}'>{jira_id}</a>\n\n"
                        assistant_response = assistant_response + f"<b>Status IO Page Information:</b> <a href='{status_io_page_link}'>Status IO Page</a>\n\n"
                        assistant_response = assistant_response + f"<b>White Board Information:</b> <a href='{white_board_link}'>White Board</a>\n\n"
                        st.session_state.messages.append({"role": "assistant", "content": assistant_response})

                        # Notification service
                        notification_service = NotificationService()

                        # Insensitive email
                        email_insensitive_content = notification_service.generate_insensitive_email(description,
                                                                                                    segment, product,
                                                                                                    priority, impact,
                                                                                                    jira_id, jira_link,
                                                                                                    status_io_page_link,
                                                                                                    white_board_link)
                        notification_service.insensitive_notification_tool(email_insensitive_content.get("subject"),
                                                                           email_insensitive_content.get("body"))

                        # Sensitive email
                        email_sensitive_content = notification_service.generate_sensitive_email(description,
                                                                                                segment,
                                                                                                product,
                                                                                                priority,
                                                                                                impact,
                                                                                                jira_id,
                                                                                                jira_link,
                                                                                                status_io_page_link,
                                                                                                white_board_link)
                        notification_service.sensitive_notification_tool(
                            email_sensitive_content.get("subject"), email_sensitive_content.get("body"))
            with col2:
                if st.button("👎", key=f"thumbs_down_{i}"):
                    st.session_state.feedback.append({"message_index": i, "feedback": "negative"})
                    st.warning(
                        "Thanks for your feedback!\n\nPlease provide more details so that the system can process your request.")
    # Add assistant response to the chat history
    st.session_state.messages.append({"role": "assistant", "content": assistant_response})

print(f"\n\n#### execution completed ####\n\n")