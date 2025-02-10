import asyncio
import os
from dotenv import load_dotenv
import autogen
import chromadb
import panel as pn

from autogen import config_list_from_json, AssistantAgent
from autogen.agentchat.contrib.retrieve_user_proxy_agent import RetrieveUserProxyAgent

load_dotenv()
input_future = None
chromadb_path = os.getcwd() + os.getenv("CHROMADB_FILE_PATH")
pdf_file = os.getenv("PRIORITY_FILE")

print(f"{os.getenv("MODEL_CONFIG_FILE")}")
print(f"chromadb_path:- {chromadb_path}")
print(f"pdf_file:- {pdf_file}")
config_list = config_list_from_json(env_or_file=os.getenv("MODEL_CONFIG_FILE"))

class MyConversableAgent(autogen.ConversableAgent):

    async def a_get_human_input(self, prompt: str) -> str:
        global input_future
        print('AGET!!!!!! Awaiting user input...')
        chat_interface.send(prompt, user="System", respond=False)

        if input_future is None or input_future.done():
            print("Initializing new Future object for input.")
            input_future = asyncio.Future()

        await input_future  # Wait for user input

        input_value = input_future.result()
        input_future = None
        print(f"User input received: {input_value}")
        return input_value


user_proxy = MyConversableAgent(
    name="user_proxy",
    system_message=f"""
                You are a context-aware prioritization agent.
                Maintain context across user queries and incorporate information provided earlier unless explicitly instructed to override it.
                You are an expert issue prioritization agent. You will be provided with a PDF file containing priority and impact definitions and an issue description.
                Extract the information from the PDF file and issue reported by user.
                You must return your response strictly in the following JSON format:
                {{
                    "priority": "<priority_value>",
                    "impact": "<impact_value>",
                    "urgency": "<urgency_value>",
                    "description": "<detailed_description_of_issue>",
                    "summary": "<short_summary_of_issue>",
                    "segment": "<segment_value>",
                    "product": "<product_value>"
                }}
                Follow these rules:
                1. You need to find the priority, impact, and urgency of the issue reported by user based on the information from the PDF file.
                2. You need to assign the priority from the PDF file and context from user interactions. Its value should be P1, P2, P3, or P4.
                3. You need to find the segment and product from the issue reported by user.
                4. You need to create the description of the issue reported by user.
                5. You need to create a one-liner summary of the issue reported by user in maximum 10 words.
                6. If explicitly mentioned to update/change any of the fields description, summary, segment, product, priority, impact, or urgency, please don't consider the PDF document in that scenario. Please update the respective fields accordingly.
                7. If the context/meaning of the issue reported by the user is not present in the information extracted from a PDF document and priority or impact is not identifiable, then you must return your response strictly in the following JSON format:
                {{
                    "priority": "NA",
                    "impact": "NA",
                    "urgency": "NA",
                    "description": "This issue does not appear to be related to any GP products, and unfortunately, I am unable to proceed with further action. Thank you for your understanding.",
                    "summary": "NA",
                    "segment": "NA",
                    "product": "NA",
                }}
                """,
    llm_config={
        "timeout": 600,
        "cache_seed": 42,
        "config_list": config_list,
    },
    # human_input_mode="ALWAYS",
)

ragproxyagent = RetrieveUserProxyAgent(
# ragproxyagent = MyConversableAgent(
            name="ragproxyagent",
            human_input_mode="ALWAYS",
            retrieve_config={
                "task": "qa",
                "docs_path": pdf_file,
                "chunk_token_size": 2000,
                "model": config_list[0]["model"],
                "client": chromadb.PersistentClient(path=chromadb_path),
                "collection_name": "gnoc-priority-pdf",
                "chunk_mode": "one_line",
                "embedding_model": "text-embedding-004",
                "get_or_create": True,
                "must_break_at_empty_line": False,
                "overwrite": True,
            },
            code_execution_config={
                "work_dir": "auto-gen",
                "use_docker": False,
            },
        )

# group_chat = autogen.GroupChat(agents=[ragproxyagent, user_proxy], messages=[], max_round=20)
# manager = autogen.GroupChatManager(groupchat=group_chat, llm_config={
#         "timeout": 600,
#         "cache_seed": 42,
#         "config_list": config_list,
#     })

avatar = {user_proxy.name:"👨‍💼", ragproxyagent.name:"👩‍💻"}


def print_messages(recipient, messages, sender, config):
    print(
        f"Messages from: {sender.name} sent to: {recipient.name} | num messages: {len(messages)} | message: {messages[-1]}")

    content = messages[-1]['content']

    if all(key in messages[-1] for key in ['name']):
        chat_interface.send(content, user=messages[-1]['name'], avatar=avatar[messages[-1]['name']], respond=False)
    else:
        chat_interface.send(content, user=recipient.name, avatar=avatar[recipient.name], respond=False)

    return False, None  # required to ensure the agent communication flow continues

user_proxy.register_reply(
    [autogen.Agent, None],
    reply_func=print_messages,
    config={"callback": None},
)

ragproxyagent.register_reply(
    [autogen.Agent, None],
    reply_func=print_messages,
    config={"callback": None},
)

# ragproxyagent.initiate_chat(
#     user_proxy,
#     reply_func=print_messages,
#     config={"callback": None},
# )

pn.extension(design="material")

initiate_chat_task_created = False

async def delayed_initiate_chat(agent, recipient, message):
    global input_future
    global initiate_chat_task_created
    # Indicate that the task has been created
    initiate_chat_task_created = True
    # Create a new Future object before initiating chat
    input_future = asyncio.Future()
    # Wait for 2 seconds
    await asyncio.sleep(2)

    # Now initiate the chat
    await agent.a_initiate_chat(recipient, message=message)


async def callback(contents: str, user: str, instance: pn.chat.ChatInterface):
    global initiate_chat_task_created
    global input_future

    if not initiate_chat_task_created:
        asyncio.create_task(delayed_initiate_chat(ragproxyagent, user_proxy, contents))

    else:
        if input_future is None or input_future.done():
            # Reinitialize input_future if it's None or already completed
            input_future = asyncio.Future()

        # Now set the result to allow the agent to receive input

chat_interface = pn.chat.ChatInterface(callback=callback)
chat_interface.send("Send a message!", user="System", respond=False)
chat_interface.servable()
