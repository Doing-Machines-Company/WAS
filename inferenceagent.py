import anthropic
import re
import os
import string
import json
from dataclasses import dataclass
from typing import List, Tuple, Optional
from utils.inference_data import HiddenInput  # Ensure HiddenInput is properly defined in your module
from groq import Groq
from together import Together
from openai import OpenAI
from cerebras.cloud.sdk import Cerebras
import google.generativeai as google_client


@dataclass
class AgentCall:
    system_prompt: str
    user_prompt: str
    llm_response: str
    parsed_output: Optional[str] = None  # Made optional for flexibility


# Set up the Anthropic API client
anthropic_client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

# Set up the Groq API client
groq_client = Groq()

# Set up Together API client
together_client = Together(api_key=os.environ.get('TOGETHER_API_KEY'))

# Set up OpenAI API client
openai_client = OpenAI()

# Set up Cerebras API client
cerebras_client = Cerebras(api_key=os.environ.get("CEREBRAS_API_KEY"))

google_client.configure(api_key=os.environ.get("GOOGLE_API_KEY"))


def call_llm(
    system_prompt: str = '',
    user_prompt: str = '',
    provider: str = "anthropic",
    model: str = "claude-3-5-sonnet-latest",
    max_tokens: int = 4000
) -> AgentCall:
    """
    Calls the specified LLM provider with the given prompts and parameters.

    Args:
        system_prompt (str): The system prompt to provide context to the LLM.
        user_prompt (str): The user prompt containing the actual query or instruction.
        provider (str): The LLM provider to use (e.g., "anthropic", "groq", "together", "openai", "cerebras").
        model (str): The specific model to use from the provider.
        max_tokens (int): The maximum number of tokens to generate.

    Returns:
        AgentCall: An instance of AgentCall containing prompts and LLM response.
    """
    if provider == "anthropic":
        message = anthropic_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": user_prompt
                        }
                    ]
                }
            ]
        )
        output = message.content[0].text

    elif provider == "groq":
        completion = groq_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            temperature=0,
            max_tokens=max_tokens,
            top_p=1,
            stream=False,
            stop=None,
        )
        output = completion.choices[0].message.content

    elif provider == "together":
        response = together_client.chat.completions.create(
            model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=max_tokens,
            temperature=0,
            top_p=1,
            top_k=50,
            repetition_penalty=1,
            stop=["<|eot_id|>"],
            stream=False,
        )
        output = response.choices[0].message.content

    elif provider == 'openai':
        completion = openai_client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            max_tokens=max_tokens,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]
        )
        output = completion.choices[0].message.content

    elif provider == 'openai-o1-preview-store':
        completion = openai_client.chat.completions.create(
            model="o1-preview",
            messages=[
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            store=True,
            metadata={"agent": "action", "testing": "testing"}
        )
        output = completion.choices[0].message.content

    elif provider == 'openai-o1-mini-store':
        completion = openai_client.chat.completions.create(
            model="o1-mini",
            messages=[
                {
                    "role": "system",
                    "content": user_prompt
                },
            ],
            store=True,
            metadata={"agent": "action", "testing": "testing"}
        )
        output = completion.choices[0].message.content

    elif provider == 'openai-store':
        completion = openai_client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            max_tokens=max_tokens,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
          store=True,
          metadata={"agent":"action", "testing":"testing"}
        )
        output = completion.choices[0].message.content

    elif provider == 'cerebras':
        completion = cerebras_client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            model=model,
            stream=False,
            max_tokens=max_tokens,
            temperature=0,
            top_p=1
        )
        output = completion.choices[0].message.content

    elif provider == "google":
        generation_config = {
            "temperature": 0,
            "top_p": 1,
            "top_k": 40,
            "max_output_tokens": 8192,
            "response_mime_type": "text/plain",
        }

        model = google_client.GenerativeModel(
            model_name="gemini-1.5-pro-002",
            generation_config=generation_config,
            system_instruction=system_prompt
        )

        chat_session = model.start_chat(
            history=[
            ]
        )

        output = chat_session.send_message(user_prompt).text

    else:
        raise ValueError("Invalid provider. Choose 'anthropic', 'groq', 'together', 'openai', or 'cerebras'.")

    return AgentCall(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        llm_response=output
    )


def call_action_agent(
    task: str,
    ax_tree: str,
    action_memory: List,  # Define the specific type if available
    context: str,
    provider: str = "openai"
) -> AgentCall:
    """
    Calls the action agent LLM and processes its response.

    Args:
        task (str): The task to be performed.
        ax_tree (str): Accessibility tree information.
        world_memory (str): World memory context.
        action_memory (list): List of action memories.
        context (str): Additional context.
        provider (str): The LLM provider to use.

    Returns:
        AgentCall: An instance of AgentCall containing prompts, LLM response, and parsed output.
    """
    new_action_memory = ''
    for i, lin_mem in enumerate(action_memory):
        new_action_memory += f"\n{i + 1}) LOCATION: {lin_mem.object_details}\n{i + 1}) EFFECT: {lin_mem.location_details}"

    with open('prompts/action_decider/action_decider_user_v2.txt', 'r') as f:
        user_prompt_template = f.read()
    replacements = {
        'ax_tree': ax_tree,
        'task': task,
        'action_memory': new_action_memory,
    }
    user_prompt = string.Template(user_prompt_template).substitute(replacements)

    with open('prompts/action_decider/action_decider_system_v2.txt', 'r') as f:
        system_prompt_template = f.read()
    replacements = {
        'context': context
    }
    system_prompt = string.Template(system_prompt_template).substitute(replacements)

    # Call the updated call_llm without return_prompt
    agent_call = call_llm(system_prompt=system_prompt, user_prompt=user_prompt, provider=provider)

    print("LLM Response:\n", agent_call.llm_response)

    # Proceed with processing the llm_response
    pattern = r'choose\(\s*(\d+),\s*"(.*)"\)'
    match = re.search(pattern, agent_call.llm_response)

    parsed_output: Optional[Tuple[int, str]] = (int(match.group(1)), match.group(2)) if match else None

    # Update the parsed_output in AgentCall
    agent_call.parsed_output = parsed_output

    return agent_call

def call_check_load_agent_text(
    ax_tree,
) -> bool:
    with open('prompts/check_load_text/check_load_user.txt', 'r') as f:
        user_prompt_template = f.read()
    replacements = {
        'ax_tree': ax_tree,
    }
    user_prompt = string.Template(user_prompt_template).substitute(replacements)

    with open('prompts/check_load_text/check_load_system.txt', 'r') as f:
        system_prompt = f.read()

    agent_call = call_llm(system_prompt=system_prompt, user_prompt=user_prompt, provider="cerebras", model='llama3.1-8b')

    json_match = re.search(r'\{[\s\S]*}', agent_call.llm_response)
    page_loaded = None

    if json_match:
        json_str = json_match.group(0)

        try:
            # Step 3: Parse the JSON string
            parsed_json = json.loads(json_str)

            # Step 4: Extract the pageLoaded value
            page_loaded = parsed_json.get("pageLoaded")

            if page_loaded is not None:
                return page_loaded
            else:
                parsed_output = "Error: 'pageLoaded' key not found in JSON"
                return False

        except json.JSONDecodeError:
            parsed_output = "Error: Invalid JSON format"
            return False
    else:
        parsed_output = "Error: No JSON object found in the answer"
        return False

def call_check_load_agent_screenshot(
    screenshot,
    provider: str = 'groq'
) -> bool:
    # Move the system message content into the user message
    completion = groq_client.chat.completions.create(
        model="llama-3.2-11b-vision-preview",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": ""
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": screenshot
                        }
                    }
                ]
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "You are an expert at analyzing webpage screenshots to determine if a webpage has fully loaded or if there are errors. I will provide you with a screenshot of a webpage, and your task will be reasoning to answer a set of indicator questions to determine if the page has successfully loaded, then giving me your final answer in a JSON format I will specify.\n\nFirst, reason step-by-step and answer these indicator questions:\n\n1) Are there any loading spinners or progress indicators visible?\n2) Is the page content fully rendered, with readable text, images, and interactive elements appearing in their correct places?\n3) Are there any missing sections, placeholders, or broken images that suggest incomplete loading?\n\nThen finally reason step-by-step, based on the screenshot and your answers to the indicator questions, provide your answer in the following JSON format:\n{\n  \"pageLoaded\": true | false\n}\nIf the page did not load correctly, choose false. If the page is loaded choose true. Ensure your output is formatted strictly as JSON."
                    }
                ]
            }
        ],
        temperature=1,
        max_tokens=8000,
        top_p=1,
        stream=False,
        stop=None,
    )

    print(completion.choices[0].message.content)

    return False

def call_memory_agent(
    web_agent_task: str,
    action_memory: List,  # Define the specific type if available
    world_memory: str,
    provider: str = "anthropic"
) -> AgentCall:
    """
    Calls the memory agent LLM and processes its response.

    Args:
        web_agent_task (str): The web agent task description.
        action_memory (list): List of action memories.
        world_memory (str): World memory context.
        provider (str): The LLM provider to use.

    Returns:
        AgentCall: An instance of AgentCall containing prompts, LLM response, and parsed output.
    """
    new_action_memory = ''
    for i, lin_mem in enumerate(action_memory):
        new_action_memory += f"\n{i + 1}) LOCATION: {lin_mem.object_details}\n{i + 1}) EFFECT: {lin_mem.location_details}"

    with open('prompts/world_mem_prompt_v2.txt', 'r') as f:
        prompt_template = f.read()
    replacements = {
        'web_agent_task': web_agent_task,
        'world_memory': world_memory,
        'action_memory': new_action_memory,
    }
    prompt = string.Template(prompt_template).substitute(replacements)

    # Call the updated call_llm without return_prompt
    agent_call = call_llm(user_prompt=prompt, provider='cerebras', model='llama3.1-70b')

    print("LLM Response:\n", agent_call.llm_response)

    # Step 1 & 2: Find the JSON object in the answer
    json_match = re.search(r'\{[\s\S]*}', agent_call.llm_response)

    if json_match:
        json_str = json_match.group(0)

        try:
            # Step 3: Parse the JSON string
            parsed_json = json.loads(json_str)

            # Step 4: Extract the new_world_memory
            new_world_memory = parsed_json.get("new_world_memory")

            if new_world_memory is not None:
                parsed_output = new_world_memory
            else:
                parsed_output = "Error: 'new_world_memory' key not found in JSON"

        except json.JSONDecodeError:
            parsed_output = "Error: Invalid JSON format"
    else:
        parsed_output = "Error: No JSON object found in the answer"

    # Update the parsed_output in AgentCall
    agent_call.parsed_output = parsed_output

    return agent_call


def call_reflect_agent(
    # action_number: int,
    reason_for_action: str,
    old_ax_tree: str,
    new_ax_tree: str,
    web_agent_task: str,
    provider: str = "openai"
) -> AgentCall:
    """
    Calls the reflect agent LLM and processes its response.

    Args:
        action_number (int): The number of the action.
        # reason_for_action (str): Reason for the action.
        old_ax_tree (str): Old accessibility tree.
        new_ax_tree (str): New accessibility tree.
        web_agent_task (str): The web agent task description.
        provider (str): The LLM provider to use.

    Returns:
        AgentCall: An instance of AgentCall containing prompts, LLM response, and parsed output.
    """
    with open('prompts/reflect_store_prompt_v3.txt', 'r') as f:
        user_prompt_template = f.read()
    replacements = {
        # 'action_number': action_number,
        'reason_for_action': reason_for_action,
        'old_accessibility_tree': old_ax_tree,
        'new_accessibility_tree': new_ax_tree,
        'web_agent_task': web_agent_task,
    }
    user_prompt = string.Template(user_prompt_template).substitute(replacements)
    #print("User Prompt:\n", user_prompt)

    # Call the updated call_llm without return_prompt
    agent_call = call_llm(user_prompt=user_prompt, provider='cerebras', model='llama3.1-70b')

    print("LLM Response:\n", agent_call.llm_response)

    json_pattern = r'\{[^{}]*\}'

    # Find all matches
    json_matches = re.findall(json_pattern, agent_call.llm_response)
    parsed_output: Optional[Tuple[str, str]] = ('', '')

    if json_matches:
        for json_str in json_matches:
            try:
                data = json.loads(json_str)
                if 'old_web_page_purpose' in data and 'final_answer' in data:
                    old_web_page_purpose = data.get('old_web_page_purpose', '')
                    action_effect = data.get('final_answer', '')
                    parsed_output = (old_web_page_purpose, action_effect)
                    print("Parsed Data:", data)
                    break  # Exit after finding the first valid match
            except json.JSONDecodeError:
                continue
    else:
        print("Reflect Restore Error: No JSON object found in the LLM response")

    # Update the parsed_output in AgentCall
    agent_call.parsed_output = parsed_output

    return agent_call


def call_task_separator(
    web_agent_task: str,
    provider: str = "anthropic"
) -> AgentCall:
    """
    Calls the task separator LLM and processes its response.

    Args:
        web_agent_task (str): The web agent task description.
        provider (str): The LLM provider to use.

    Returns:
        AgentCall: An instance of AgentCall containing prompts, LLM response, and parsed output.
    """
    with open('prompts/task_separator_prompt_json.txt', 'r') as f:
        prompt_template = f.read()
    replacements = {
        'web_agent_task': web_agent_task,
    }
    prompt = string.Template(prompt_template).substitute(replacements)

    # Call the updated call_llm without return_prompt
    agent_call = call_llm(user_prompt=prompt, provider='cerebras', model='llama3.1-70b')
    answer = agent_call.llm_response.strip()
    print("LLM Response:\n", answer)

    # Step 1: Use regex to find the JSON object
    json_pattern = r'\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}'
    match = re.search(json_pattern, answer)

    if match:
        # Step 2: Extract the JSON string
        json_str = match.group(0)
        try:
            # Step 3: Parse the extracted JSON string
            parsed_json = json.loads(json_str)
            # Step 4: Extract the required information
            items = parsed_json.get('items', [])
            parsed_output = items
        except json.JSONDecodeError:
            print("Task Separator: Failed to parse JSON.")
            parsed_output = None
    else:
        print("Task Separator: No JSON object found in the answer.")
        parsed_output = None

    # Update the parsed_output in AgentCall
    agent_call.parsed_output = parsed_output

    return agent_call


def call_task_clarifier(
    user_task: str,
    item_context_pairs: str,
    context: str,
    provider: str = "anthropic"
) -> AgentCall:
    """
    Calls the task clarifier LLM and processes its response.

    Args:
        user_task (str): The user's task description.
        item_context_pairs (str): Pairs of items and their contexts.
        context (str): Additional context.
        provider (str): The LLM provider to use.

    Returns:
        AgentCall: An instance of AgentCall containing prompts, LLM response, and parsed output.
    """
    with open('prompts/task_parser_prompt.txt', 'r') as f:
        prompt_template = f.read()
    replacements = {
        'user_task': user_task,
        'item_of_interest': item_context_pairs,
        'context': context
    }
    prompt = string.Template(prompt_template).substitute(replacements)

    # Call the updated call_llm without return_prompt
    agent_call = call_llm(user_prompt=prompt, provider='groq')

    print("LLM Response:\n", agent_call.llm_response)

    pattern = r'"""([\s\S]*?)"""'
    match = re.search(pattern, agent_call.llm_response)

    parsed_output = match.group(1).strip() if match else ""

    # Update the parsed_output in AgentCall
    agent_call.parsed_output = parsed_output

    return agent_call


def call_input_agent(
    user_task: str,
    agent_intent: str,
    input_ax_tree: str,
    context: str,
    hidden_inputs: List[HiddenInput],
    provider: str = "anthropic"
) -> AgentCall:
    """
    Calls the input agent LLM and processes its response.

    Args:
        user_task (str): The user's task description.
        agent_intent (str): The intent of the agent.
        input_ax_tree (str): Accessibility tree information.
        context (str): Additional context.
        hidden_inputs (list[HiddenInput]): List of hidden inputs.
        provider (str): The LLM provider to use.

    Returns:
        AgentCall: An instance of AgentCall containing prompts, LLM response, and parsed output.
    """
    with open('prompts/mass_input_prompt_json.txt', 'r') as f:
        prompt_template = f.read()

    formatted_hidden_items = ''
    for item in hidden_inputs:
        formatted_hidden_items += f"{item.key.strip()}: {item.description.strip()}\n"
    formatted_hidden_items = formatted_hidden_items.strip()

    replacements = {
        'user_task': user_task,
        'agent_intent': agent_intent,
        'input_ax_tree': input_ax_tree,
        'context': context,
        'hidden_items': formatted_hidden_items
    }
    prompt = string.Template(prompt_template).substitute(replacements)

    # Call the updated call_llm without return_prompt
    agent_call = call_llm(user_prompt=prompt, provider='cerebras', model='llama3.1-70b')

    print("LLM Response:\n", agent_call.llm_response)

    pattern = r'"text_area_number":\s*(\d+).*?"desired_input":\s*"(.*?)"'

    # Find all matches in the answer
    matches = re.findall(pattern, agent_call.llm_response, re.DOTALL)

    parsed_output = [(int(num), input_text) for num, input_text in matches]

    # Update the parsed_output in AgentCall
    agent_call.parsed_output = parsed_output

    return agent_call


def call_unified_task_clarifier(
    user_task: str,
    context: str,
    provider: str = "anthropic"
) -> AgentCall:
    """
    Calls the unified task clarifier LLM and processes its response.

    Args:
        user_task (str): The user's task description.
        context (str): Additional context.
        provider (str): The LLM provider to use.

    Returns:
        AgentCall: An instance of AgentCall containing prompts, LLM response, and parsed output.
    """
    with open('prompts/unified_task_clarifier_json.txt', 'r') as f:
        prompt_template = f.read()
    replacements = {
        'user_task': user_task,
        'context': context
    }
    prompt = string.Template(prompt_template).substitute(replacements)

    # Call the updated call_llm without return_prompt
    agent_call = call_llm(user_prompt=prompt, provider='cerebras', model='llama3.1-70b')

    print("LLM Response:\n", agent_call.llm_response)

    # Use regex to find the JSON array in the output
    json_matches = re.findall(r'\[.*?\]', agent_call.llm_response, re.DOTALL)

    questions: List[str] = []
    if json_matches:
        for json_str in json_matches:
            try:
                parsed_json = json.loads(json_str)
                # Verify that we have a list of strings
                if isinstance(parsed_json, list) and all(isinstance(q, str) for q in parsed_json):
                    questions = parsed_json
                    break  # Exit after finding the first valid match
            except json.JSONDecodeError:
                continue
        else:
            print("Unified Task Clarifier Error: Invalid JSON format")
    else:
        print("Unified Task Clarifier Error: No JSON array found in the output")

    # Update the parsed_output in AgentCall
    agent_call.parsed_output = questions

    return agent_call


def call_unified_question_cleaner(
    user_task: str,
    user_qa: List[Tuple[str, str]],
    provider: str = "anthropic"
) -> AgentCall:
    """
    Calls the unified question cleaner LLM and processes its response.

    Args:
        user_task (str): The user's task description.
        user_qa (list): List of tuples containing questions and answers.
        provider (str): The LLM provider to use.

    Returns:
        AgentCall: An instance of AgentCall containing prompts, LLM response, and parsed output.
    """
    with open('prompts/unified_question_cleaner_json.txt', 'r') as f:
        prompt_template = f.read()

    formatted_user_qa = ''
    for question, answer in user_qa:
        formatted_user_qa += 'Question: \n'
        formatted_user_qa += question.strip() + '\n'
        formatted_user_qa += 'Answer: \n'
        formatted_user_qa += answer.strip() + '\n'

    replacements = {
        'formatted_user_qa': formatted_user_qa,
        'user_task': user_task
    }
    prompt = string.Template(prompt_template).substitute(replacements)
    print("User Prompt:\n", prompt)

    # Call the updated call_llm without return_prompt
    agent_call = call_llm(user_prompt=prompt, provider='cerebras', model='llama3.1-70b')

    print("LLM Response:\n", agent_call.llm_response)

    # Find JSON object in the text
    json_pattern = r'\{[^{}]*\}'
    json_matches = re.findall(json_pattern, agent_call.llm_response)

    new_task: Optional[str] = ''
    if json_matches:
        for json_str in json_matches:
            try:
                data = json.loads(json_str)
                if 'new_task' in data:
                    new_task = data.get('new_task', '')
                    print("Parsed Data:", data)
                    break  # Exit after finding the first valid match
            except json.JSONDecodeError:
                continue
    else:
        print("Question Cleaner Error: No JSON object found in the LLM response")

    # Update the parsed_output in AgentCall
    agent_call.parsed_output = new_task

    return agent_call