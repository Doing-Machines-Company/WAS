from langchain.chat_models import ChatAnthropic
from langchain.agents.agent_toolkits import PlayWrightBrowserToolkit
from langchain.chat_models import ChatOpenAI
from langchain.prompts.chat import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain.schema import HumanMessage, SystemMessage

# A synchronous browser is available, though it isn't compatible with jupyter.
from langchain.agents.agent_toolkits import PlayWrightBrowserToolkit
from langchain_community.tools.playwright.utils import (
    create_sync_playwright_browser,  # A synchronous browser is available, though it isn't compatible with jupyter.
)

from langchain.agents import initialize_agent, AgentType

class ActiontTree:
    def __init__(self):
        pass


# Following line generates the chat response using @LangChainAI's ChatAnthropic()
# To use ChatAnthropic you should have the @anthropic-ai/sdk package installed,
# with the ANTHROPIC_API_KEY environment variable set.
# llm = ChatAnthropic (model="claude-1", temperature=0, max_tokens_to_sample=2000)
chat = ChatOpenAI(model = "gpt-4", temperature=0, openai_api_key="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")

# For the above line, I could use any other LLM, e.g., ChatOpenAI(), OpenAI()

def main():
    sync_browser = create_sync_playwright_browser()
    # It's always recommended to instantiate using the from_browser method
    toolkit = PlayWrightBrowserToolkit.from_browser (sync_browser=sync_browser)

    tools = toolkit.get_tools()

    agent_chain = initialize_agent(
        tools,
        llm=chat,
        agent = AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True
    )

    result = agent_chain.run("Describe what can be done on this web page, ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770."
                             "Do not include any information about what it links to, only what can be done on this page. Give me an exhaustive list of everything that can be done. But for every piece of functionality, keep your description brief."
                            "Give me a concise answer enclosed in square brackets, separating each function description with a comma. EXAMPLE: [One function description here, another function description here]")


    print(result)

main()