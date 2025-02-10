import asyncio
import os
import streamlit as st
from dotenv import load_dotenv
import autogen
import chromadb

from autogen import config_list_from_json, AssistantAgent
from autogen.agentchat.contrib.retrieve_user_proxy_agent import RetrieveUserProxyAgent

# Load environment variables
load_dotenv()
input_future = None
chromadb_path = os.getcwd() + os.getenv("CHROMADB_FILE_PATH")
pdf_file = os.getenv("PRIORITY_FILE")

st.write(f"Model Config File: {os.getenv('MODEL_CONFIG_FILE')}")
st.write(f"Chromadb Path: {chromadb_path}")
st.write(f"PDF File: {pdf_file}")

config_list = config_list_from_json(env_or_file=os.getenv("MODEL_CONFIG_FILE"))

# Streamlit UI elements
st.title("Chatbot Application")
st.write("Enter your message below:")

class MyRetrieveUserProxyAgent(RetrieveUserProxyAgent):

    async def a_get_human_input(self, prompt: str) -> str:
        global input_future
        st.warning("Awaiting user input...")

        if input_future is None or input_future.done():
            input_future = asyncio.Future()

        await input_future  # Wait for user input

        input_value = input_future.result()
        input_future = None
        st.success(f"User input received: {input_value}")
        return input_value


# Create agents
user_proxy = AssistantAgent(
    name="user_proxy",
    system_message="""
        You are a context-aware prioritization agent.
        Maintain context across user queries and incorporate information provided earlier unless explicitly instructed to override it.
        You are an expert issue prioritization agent. You will be provided with a PDF file containing priority and impact definitions and an issue description.
        Extract the information from the PDF file and issue reported by user.
    """,
    llm_config={
        "timeout": 600,
        "cache_seed": 42,
        "config_list": config_list,
    },
    human_input_mode="NEVER",
)

ragproxyagent = MyRetrieveUserProxyAgent(
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

avatar = {user_proxy.name: "👨‍💼", ragproxyagent.name: "👩‍💻"}

def print_messages(recipient, messages, sender, config):
    content = messages[-1]['content']
    st.write(f"**{sender.name}:** {content}")
    return False, None  # Ensures communication flow continues

user_proxy.register_reply([autogen.Agent, None], reply_func=print_messages, config={"callback": None})
ragproxyagent.register_reply([autogen.Agent, None], reply_func=print_messages, config={"callback": None})

initiate_chat_task_created = False

async def delayed_initiate_chat(agent, recipient, message):
    print(f"inside delayed_initiate_chat method")
    global input_future, initiate_chat_task_created
    initiate_chat_task_created = True
    input_future = asyncio.Future()
    await asyncio.sleep(2)
    await agent.a_initiate_chat(recipient, message=message)
    # result = await agent.a_initiate_chat(recipient, message=message)
    # print(f"result:- {result}")


# Chat handling
if "messages" not in st.session_state:
    st.session_state.messages = []

async def handle_user_input():
    print(f"inside handle_user_input method")
    global initiate_chat_task_created, input_future
    user_input = st.text_input("Your message:", key="user_input")

    if st.button("Send"):
        if user_input:
            st.session_state.messages.append({"user": "User", "content": user_input})

            if not initiate_chat_task_created:
                asyncio.create_task(delayed_initiate_chat(ragproxyagent, user_proxy, user_input))
            else:
                if input_future is None or input_future.done():
                    input_future = asyncio.Future()
                input_future.set_result(user_input)

            # st.experimental_rerun()
            st.session_state.rerun = True

# Display chat messages
for msg in st.session_state.messages:
    st.write(f"**{msg['user']}:** {msg['content']}")

# Call user input handler
asyncio.run(handle_user_input())
