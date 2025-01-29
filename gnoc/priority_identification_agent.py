import os
import json
import chromadb
from autogen import AssistantAgent, config_list_from_json
from autogen.agentchat.contrib.retrieve_user_proxy_agent import RetrieveUserProxyAgent
from dotenv import load_dotenv
from autogen.retrieve_utils import TEXT_FORMATS

class PriorityIdentificationAgent:
    def __init__(self, pdf_file_path=None, model_config_file=None, chromadb_file_path=None):
        # Load environment variables
        load_dotenv()

        # Suppress gRPC warnings
        os.environ["GRPC_VERBOSITY"] = "ERROR"
        os.environ["GRPC_FAIL_FAST"] = "true"

        # pdf_path = os.getenv("PRIORITY_FILE")
        # model_config_path = os.getenv("MODEL_CONFIG_PATH")
        # chromadb_path = os.getenv("CHROMADB_PATH")

        self.pdf_file = pdf_file_path or os.getenv("PRIORITY_FILE")
        if model_config_file is None:
            self.config_list = config_list_from_json(env_or_file=os.getenv("MODEL_CONFIG_FILE"))
        else:
            self.config_list = config_list_from_json(env_or_file=model_config_file)

        print(f"self.config_list:- {self.config_list}")

        if chromadb_file_path is None:
            # self.chromadb_path = os.path.join(os.getcwd(), os.getenv("CHROMADB_FILE_PATH"))
            self.chromadb_path = os.getcwd() + os.getenv("CHROMADB_FILE_PATH")
        else:
            self.chromadb_path = chromadb_file_path

        print(f"Loaded config_list: {self.config_list}")

        # Initialize AssistantAgent
        self.assistant = AssistantAgent(
            name="assistant",
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
                "config_list": self.config_list,
            },
        )

        # Initialize RetrieveUserProxyAgent
        self.ragproxyagent = RetrieveUserProxyAgent(
            name="ragproxyagent",
            human_input_mode="NEVER",
            retrieve_config={
                "task": "qa",
                "docs_path": self.pdf_file,
                "chunk_token_size": 2000,
                "model": self.config_list[0]["model"],
                "client": chromadb.PersistentClient(path=self.chromadb_path),
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

    def prioritize_issue(self, issue_description):
        initial_task = f"""Please prioritize the below issue reported by user.
        Issue:- {issue_description}
        """

        try:
            chat_result = self.ragproxyagent.initiate_chat(
                self.assistant, message=self.ragproxyagent.memessage_generator, problem=initial_task, n_results=30
            )

            summary = chat_result.summary.strip("```json\n").strip("\n```")
            final_result = json.loads(summary)

            return {
                "priority": final_result.get("priority"),
                "impact": final_result.get("impact"),
                "urgency": final_result.get("urgency"),
                "description": final_result.get("description"),
                "summary": final_result.get("summary"),
                "segment": final_result.get("segment"),
                "product": final_result.get("product"),
            }

        except Exception as e:
            print(f"Error during prioritization: {e}")
            return None


# Example usage
if __name__ == "__main__":
    pdf_path = os.getenv("PRIORITY_FILE")
    model_config_path = os.getenv("MODEL_CONFIG_PATH")
    chromadb_path = os.getenv("CHROMADB_FILE_PATH")

    # pdf_path = "C:\\MyData\\auto-gen\\gnoc\\Priority.pdf"
    # model_config_path = os.path.join(os.getcwd(), "MODEL_CONFIG_LIST")
    # chromadb_path = "C:\\MyData\\auto-gen\\gnoc\\tmp\\db\\chromadb"

    agent = PriorityIdentificationAgent(pdf_path, model_config_path, chromadb_path)

    issue_description = (
        "We are experiencing a critical issue in the merchant segment impacting our Transit product. "
        "Customers have been unable to perform Mastercard card transactions for the past 15 minutes, resulting in significant disruption. "
        "Approximately 10,000 transactions have been declined during this time, leading to a revenue loss of $80,000. "
        "This issue is affecting multiple merchants and requires immediate attention. "
        "The root cause appears to be related to the processing system for Mastercard transactions on the Transit product. "
        "Please prioritize this issue, as it has a high financial impact and is negatively affecting customer experience."
    )

    result = agent.prioritize_issue(issue_description)

    if result:
        print("Prioritization Result:")
        for key, value in result.items():
            print(f"{key.capitalize()}: {value}")