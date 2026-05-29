"""
Defines the core multi-agent workflow. Configures individual agents (Researcher, 
Screenwriter, File Writer), assigns their specific tools, and orchestrates 
their collaboration using the ADK's SequentialAgent pattern.
"""
import os
import logging
import google.cloud.logging
from callback_logging import log_query_to_model, log_model_response
from dotenv import load_dotenv
from google.adk import Agent 
from google.adk.tools.agent_tool import AgentTool
from google.adk.agents import LlmAgent, SequentialAgent, LoopAgent, ParallelAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.tools.langchain_tool import LangchainTool  # import
from google.genai import types
from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
import os
from pathlib import Path
from dotenv import load_dotenv
from tools import browser_tool
from google.adk.tools import google_search

# Load environment variables from .env file in the app directory
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

if not env_path.exists():
    print(f"❌ WARNING: .env file not found at {env_path}")
else:
    # load_dotenv returns True if it successfully loaded a file
    did_load = load_dotenv(dotenv_path=env_path)
    print(f"Loaded .env successfully? {did_load}")

# cloud_logging_client = google.cloud.logging.Client()
# cloud_logging_client.setup_logging()

# Get the directory where main.py is located
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))

model_name = os.getenv("MODEL")
print(f"Model name: {model_name}")

# Tools
def append_to_state(
    tool_context: ToolContext, field: str, response: str
) -> dict[str, str]:
    """Append new output to an existing state key.

    Args:
        field (str): a field name to append to
        response (str): a string to append to the field

    Returns:
        dict[str, str]: {"status": "success"}
    """
    existing_state = tool_context.state.get(field, [])
    tool_context.state[field] = existing_state + [response]
    logging.info(f"[Added to {field}] {response}")
    return {"status": "success"}


def write_file(
    tool_context: ToolContext,
    directory: str,
    filename: str,
    content: str
) -> dict[str, str]:
    target_path = os.path.join(directory, filename)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    with open(target_path, "w") as f:
        f.write(content)
    return {"status": "success"}

# root cause analysis agents
root_analysis_writer = Agent(
    name="root_analysis_writer",
    model=model_name,
    description="Critical analysis of root cause information and provide a professional reporting into these sections  causes, analysis, recommendations (that focus on proactive instead of reactive remediations and preventive measures) and summary",
    instruction="""
    ROOT_CAUSE:
    { ROOT_CAUSE? }

    INSTRUCTIONS:
    - Create a root cause analysis report based on the ROOT_CAUSE information.
    - Use your 'write_file' tool to create a root_cause_analysis.txt file based on the format provided earlier
    """,
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
    ),
    tools=[write_file],
)

# Root cause analyzer agent
root_cause_analyzer = Agent(
    name="root_cause_analyzer",
    model=model_name,
    description="Analyze the information provided and determine with high accuracy the root cause of an issue.",
    instruction="""
    INSTRUCTIONS:
    Your goal is to analyze the issue gathered by RESEARCH: { RESEARCH? } and determine the most likely root cause of the issue. You should use your expertise in SRE and incident analysis to make connections between the different pieces of information provided in the research and identify the underlying cause of the issue. Be as specific and detailed as possible in your analysis, and provide a clear explanation of how you arrived at your conclusion. If there are multiple potential root causes, analyze each one and determine which is most likely based on the evidence provided. Provide your findings into field ROOT_CAUSE Guidance when determining root cause: 
    Approoch to be undertaken here are:
    1. Perform impact analysis. What is the possible impact
    2. Suggeest workaround and proactive measures to prevent this in future. Focus more on proactive measures rather than reactive ones. 

    - If there is CRITICAL_FEEDBACK, use those thoughts to improve upon the outline.
    - A RESEARCH will be provided, please use details from it as much as possible.
    - Use the 'append_to_state' tool to write your root cause analysis to the field 'ROOT_CAUSE'.
    - 
    RESEARCH:
    { research? }

    CRITICAL_FEEDBACK:
    { CRITICAL_FEEDBACK? }

    """,
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
    ),
    tools=[append_to_state],
)

# researcher agent

researcher = LlmAgent(
    name="researcher",
    model=model_name,
    description="Conducts research to gather information about incidents and errors.",
    instruction="""
    
    Based on the error try to determine the root and use the provided link to load a webpage in html and understand what the error   using the browser tool. You can also use the browser tool to load other relevant links to gather more information about the error. You will be an expert in interpreting html. Your goal is to travese to the link, gather as much information as possible about the error, in determining  root causes, and add findings  in to the state field 'research'.

    Approoch to be undertaken here are:
    1. Identify the issue
    2. Gather data and evidence
    3. Analyze the data to identify possible causes
    4. Revalidating the theory based on evidence gathered so far. For example. if an egg is broken and the cause is because basket fallen down. Then revalidating this theory by validating possibility that other eggs has broken too. This will help in impact analysis 

    USER_PROVIDED_ERROR:
    { USER_PROVIDED_ERROR? }

    HTTP_LINK:
    { HTTP_LINK? }

    CRITICAL_FEEDBACK:
    { CRITICAL_FEEDBACK? }

    INSTRUCTIONS:
    - If there is CRITICAL_FEEDBACK, use those thoughts to improve upon your research.
    - If there's a HTTP_LINK provided, use the browser tool to load the page and analyze its content to gather information about the error.
    - Review the error details and HTTP link provided. If you have not seen this issue before, use the browser tool and google the error message to find relevant information about the error and its potential root cause. Use the browser tool to load the HTTP link provided and analyze its content for clues about the error.
     You are an SRE expert and use the links available or feature of the observability tool to find out the root cause of the issue. Gather as much information as possible about the error and its potential root cause using browser_tool and add it to the state field 'research' using the 'append_to_state' tool.
    """,
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
    ),
    tools=[
        google_search, browser_tool, append_to_state
    ],
    output_key="research_findings",
)

incident_analysis_team = SequentialAgent(
    name="incident_analysis_team",
    description="Analyze incident details, gather relevant information, provide analysis and reports on recommendations for what might have contributed to this incident here with highest precision possible. If you are not sure, you can ask deepseek_chat (another model agent) to provide you with more information and insights about the issue.",
    sub_agents=[
        researcher,
        root_cause_analyzer,
        root_analysis_writer
    ],
)

root_agent = LlmAgent(
    name="problem_gathering_agent",
    model=model_name,
    description="Assist user in finding out issue related to an incident",
    instruction="""
    - Let the user know you will help them find information about an incident. Ask them for   
      details about an incident, error message and if there's a observability link available let's keep this http link for further investigation.
    - When they responded, use the 'append_to_state' tool to store the user's  error message and problem description
      into the 'USER_PROVIDED_ERROR' state key, http link if it exists into the 'HTTP_LINK' state key and transfer to the 'incident_analysis_team' agent
    """,
    generate_content_config=types.GenerateContentConfig(
        temperature=0,
    ),
    tools=[append_to_state, browser_tool],
    sub_agents=[incident_analysis_team],
)