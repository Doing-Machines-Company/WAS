import anthropic
import re
import os
import string
import json
import asyncio
from dataclasses import dataclass
from typing import List, Tuple, Optional, Any
from utils.inference_data import HiddenInput  # Ensure HiddenInput is properly defined in your module
from groq import Groq
from together import Together
from openai import OpenAI
from cerebras.cloud.sdk import Cerebras
import google.generativeai as google_client
from pydantic import BaseModel


@dataclass
class AgentCall:
    system_prompt: str
    user_prompt: str
    llm_response: Any
    parsed_output: Optional[Any] = None


# Initialize API clients outside of functions to avoid re-initialization
anthropic_client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

groq_client = Groq()

together_client = Together(api_key=os.environ.get('TOGETHER_API_KEY'))

openai_client = OpenAI()

cerebras_client = Cerebras(api_key=os.environ.get("CEREBRAS_API_KEY"))

google_client.configure(api_key=os.environ.get("GOOGLE_API_KEY"))


async def call_llm(
    system_prompt: str = '',
    user_prompt: str = '',
    provider: str = "anthropic",
    model: str = "claude-3-5-sonnet-latest",
    max_tokens: int = 15000
) -> AgentCall:
    """
    Asynchronously calls the specified LLM provider with the given prompts and parameters.
    """
    if provider == "anthropic":
        def anthropic_call():
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
            return message.content[0].text

        output = await asyncio.to_thread(anthropic_call)

    elif provider == "groq":
        def groq_call():
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
            return completion.choices[0].message.content

        output = await asyncio.to_thread(groq_call)

    elif provider == "together":
        def together_call():
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
            return response.choices[0].message.content

        output = await asyncio.to_thread(together_call)

    elif provider == 'openai':
        def openai_call():
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
            return completion.choices[0].message.content

        output = await asyncio.to_thread(openai_call)

    elif provider == 'openai-o1-preview-store':
        def openai_o1_preview_store_call():
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
            return completion.choices[0].message.content

        output = await asyncio.to_thread(openai_o1_preview_store_call)

    elif provider == 'openai-o1-mini-store':
        def openai_o1_mini_store_call():
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
            return completion.choices[0].message.content

        output = await asyncio.to_thread(openai_o1_mini_store_call)

    elif provider == 'openai-store':
        def openai_store_call():
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
                metadata={"agent": "action", "testing": "testing"}
            )
            return completion.choices[0].message.content

        output = await asyncio.to_thread(openai_store_call)

    elif provider == "cerebras":
        def cerebras_call():
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
            return completion.choices[0].message.content

        output = await asyncio.to_thread(cerebras_call)

    elif provider == "google":
        def google_call():
            generation_config = {
                "temperature": 0,
                "top_p": 1,
                "top_k": 40,
                "max_output_tokens": 8192,
                "response_mime_type": "text/plain",
            }

            model_instance = google_client.GenerativeModel(
                model_name="gemini-exp-1114",
                generation_config=generation_config,
                system_instruction=system_prompt
            )

            chat_session = model_instance.start_chat(
                history=[]
            )

            return chat_session.send_message(user_prompt).text

        output = await asyncio.to_thread(google_call)

    else:
        raise ValueError("Invalid provider. Choose 'anthropic', 'groq', 'together', 'openai', or 'cerebras'.")

    return AgentCall(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        llm_response=output
    )

async def call_4o_structured_action(
    system_prompt: str = '',
    user_prompt: str = '',
    max_tokens: int = 10000
) -> AgentCall:


    def call_structured_4o():
        class ReasoningStep(BaseModel):
            step_number: int
            thought: str
            conclusion: str

        class ChosenAction(BaseModel):
            action_number: int
            action_reason: str

        class ChainOfThought(BaseModel):
            steps: List[ReasoningStep]
            chosen_action_sequence: List[ChosenAction]

        completion = openai_client.beta.chat.completions.parse(
            model="gpt-4o-2024-08-06",
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
            response_format=ChainOfThought
        )
        return completion

    # completion = call_structured_4o()

    completion = await asyncio.to_thread(call_structured_4o)

    chosen_actions = [(chosen.action_number, chosen.action_reason) for chosen in completion.choices[0].message.parsed.chosen_action_sequence]

    return AgentCall(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        llm_response=completion.choices[0].message,
        parsed_output=chosen_actions
    )

async def call_action_part1(
        task: str,
        task_notes: str,
        scrape_tree_no_special: str,
        action_memory: List,
        context: str,
        provider: str = "cerebras",
        model: str = "llama-3.3-70b"
):
    # new_action_memory, mem_count = '\n***', 1
    # new_runtime_qa, qa_count = '\n***', 1
    memory_without_qa = '***\n'

    for i, lin_mem in enumerate(action_memory):
        if not lin_mem.is_question:
            memory_without_qa += f"{i + 1})\nINTENT: {lin_mem.intent}\nEFFECT: {lin_mem.location_details}\nREASONING: {lin_mem.difference_reasoning}\n***\n"

    def read_system_prompt():
        with open('prompts/chained_action_decider/chain_part1_system.txt', 'r') as f:
            return f.read()

    system_prompt_template = await asyncio.to_thread(read_system_prompt)
    system_prompt = system_prompt_template  # no replacements for now

    def read_user_prompt():
        with open('prompts/chained_action_decider/chain_part1_user.txt', 'r') as f:
            return f.read()

    user_prompt_template = await asyncio.to_thread(read_user_prompt)
    user_replacements = {
        'ax_tree': scrape_tree_no_special,
        'task': task,
        'task_notes': task_notes,
        'memory': memory_without_qa,
    }
    user_prompt = string.Template(user_prompt_template).substitute(user_replacements)

    agent_call = await call_llm(system_prompt=system_prompt, user_prompt=user_prompt, provider=provider, model=model)
    output = agent_call.llm_response
    print(output)
    json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'

    json_matches = re.findall(json_pattern, agent_call.llm_response, re.DOTALL)
    parsed_output: Optional[str] = ""

    if json_matches:
        for json_str in json_matches:
            try:
                data = json.loads(json_str)
                if 'grounded_progress_summary' in data:
                    grounded_progress_summary = data.get('grounded_progress_summary', '')
                    parsed_output = grounded_progress_summary
                    print("Parsed Data:", data)
                    break  # Exit after finding the first valid match
            except json.JSONDecodeError as e:
                print(f"Action Chain 1 Error: JSON decoding failed for a matched block - {e}")
                continue
    else:
        print("Action Chain 1 Error: No JSON object found in the LLM response")

    # Update the parsed_output in AgentCall
    agent_call.parsed_output = parsed_output

    return agent_call

async def call_action_part2(
        task: str,
        task_notes: str,
        summarized_info: str,
        curr_inf_tree: str,
        provider: str = "cerebras",
        model: str = "llama-3.3-70b"
):


    def read_user_prompt():
        with open('prompts/chained_action_decider/chain_part2_user.txt', 'r') as f:
            return f.read()

    user_prompt_template = await asyncio.to_thread(read_user_prompt)
    user_replacements = {
        'ax_tree': curr_inf_tree,
        'task': task,
        'task_notes': task_notes,
        'first_chain_output': summarized_info,
    }
    user_prompt = string.Template(user_prompt_template).substitute(user_replacements)

    def read_system_prompt():
        with open('prompts/chained_action_decider/chain_part2_system.txt', 'r') as f:
            return f.read()

    system_prompt_template = await asyncio.to_thread(read_system_prompt)
    system_prompt = system_prompt_template  # no replacements for now

    agent_call = await call_llm(system_prompt=system_prompt, user_prompt=user_prompt, provider=provider, model=model)
    output = agent_call.llm_response
    print("PART 2 CALL BEGIN")
    print(system_prompt)
    print(user_prompt)
    print(output)
    print("PART 2 CALL END")
    json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'

    json_matches = re.findall(json_pattern, agent_call.llm_response, re.DOTALL)
    parsed_output: Tuple[str, str] = ('', '')

    if json_matches:
        for json_str in json_matches:
            try:
                data = json.loads(json_str)
                if 'action_number' in data and 'action_reason' in data:
                    action_number = data.get('action_number', '')
                    action_reason = data.get('action_reason', '')
                    parsed_output = (action_number, action_reason)
                    print("Parsed Data:", data)
                    break  # Exit after finding the first valid match
            except json.JSONDecodeError as e:
                print(f"Action Chain 2 Error: JSON decoding failed for a matched block - {e}")
                continue
    else:
        print("Action Chain 2 Error: No JSON object found in the LLM response")

    # Update the parsed_output in AgentCall
    agent_call.parsed_output = parsed_output

    return agent_call



    return

async def call_action_agent(
    task: str,
    ax_tree: str,
    action_memory: List,  # Define the specific type if available
    context: str,
    provider: str = "openai",
    model: str = "llama-3.3-70b"
) -> AgentCall:
    """
    Asynchronously calls the action agent LLM and processes its response.
    """
    new_action_memory = '\n***'
    for i, lin_mem in enumerate(action_memory):
        # action_lines = '\n'.join(lin_mem.action_treelines)
        # location_details stores QA string
        if not lin_mem.is_question:
            new_action_memory += f"{i + 1})\nINTENT: {lin_mem.intent}\nEFFECT: {lin_mem.location_details}\nREASONING: {lin_mem.difference_reasoning}\n***\n"

    def read_system_prompt():
        with open('prompts/action_decider/action_decider_llama_system.txt', 'r') as f:
            return f.read()

    system_prompt_template = await asyncio.to_thread(read_system_prompt)
    replacements = {
        'context': context
    }
    system_prompt = string.Template(system_prompt_template).substitute(replacements)

    # Read user prompt template asynchronously
    def read_user_prompt():
        with open('prompts/action_decider/action_decider_llama_user.txt', 'r') as f:
            return f.read()

    user_prompt_template = await asyncio.to_thread(read_user_prompt)
    replacements = {
        'ax_tree': ax_tree,
        'task': task,
        'action_memory': new_action_memory,
    }
    user_prompt = string.Template(user_prompt_template).substitute(replacements)
    # Read system prompt template asynchronously
    def read_system_prompt():
        with open('prompts/action_decider/action_decider_llama_system.txt', 'r') as f:
            return f.read()

    system_prompt_template = await asyncio.to_thread(read_system_prompt)
    replacements = {
        'context': context
    }
    system_prompt = string.Template(system_prompt_template).substitute(replacements)
    print("\nACTION CALL BEGIN\n")
    print(user_prompt)
    print(system_prompt)
    print("\nACTION CALL END\n")

    # Call the updated call_llm asynchronously
    agent_call = await call_llm(system_prompt=system_prompt, user_prompt=user_prompt, provider=provider, model=model)
    # agent_call = await call_llm(system_prompt=system_prompt, user_prompt=user_prompt, provider='anthropic')

    print("LLM Response:\n", agent_call.llm_response)

    # Proceed with processing the llm_response
    pattern = r'choose\(\s*(\d+),\s*"(.*)"\)'
    match = re.search(pattern, agent_call.llm_response)

    parsed_output: Optional[Tuple[int, str]] = (int(match.group(1)), match.group(2)) if match else None

    # Update the parsed_output in AgentCall
    agent_call.parsed_output = parsed_output

    return agent_call

async def call_action_agent_multi(
    task: str,
    ax_tree: str,
    action_memory: List,  # Define the specific type if available
    context: str,
    provider:str = 'openai'
) -> AgentCall:
    """
    Asynchronously calls the action agent LLM and processes its response.
    """
    agent_call = None
    new_action_memory = ''
    for i, lin_mem in enumerate(action_memory):
        new_action_memory += f"\n{i + 1})\n{i + 1}) EFFECT: {lin_mem.location_details}"

    print('*' * 80)
    print(ax_tree)
    if provider == 'openai':
        def read_user_prompt():
            with open('prompts/action_decider/action_decider_multi_user_OAI.txt', 'r') as f:
                return f.read()

        user_prompt_template = await asyncio.to_thread(read_user_prompt)
        replacements = {
            'ax_tree': ax_tree,
            'task': task,
            'action_memory': new_action_memory,
        }
        user_prompt = string.Template(user_prompt_template).substitute(replacements)
        def read_system_prompt():
            with open('prompts/action_decider/action_decider_multi_system_OAI.txt', 'r') as f:
                return f.read()

        system_prompt_template = await asyncio.to_thread(read_system_prompt)
        replacements = {
            'context': context
        }
        system_prompt = string.Template(system_prompt_template).substitute(replacements)
        

        agent_call = await call_4o_structured_action(system_prompt=system_prompt, user_prompt=user_prompt)

    elif provider == 'anthropic':
        def read_user_prompt():
            with open('prompts/action_decider/action_decider_multi_user_anthropic.txt', 'r') as f:
                return f.read()

        user_prompt_template = await asyncio.to_thread(read_user_prompt)
        replacements = {
            'ax_tree': ax_tree,
            'task': task,
            'action_memory': new_action_memory,
        }
        user_prompt = string.Template(user_prompt_template).substitute(replacements)

        def read_system_prompt():
            with open('prompts/action_decider/action_decider_multi_system_anthropic.txt', 'r') as f:
                return f.read()

        system_prompt_template = await asyncio.to_thread(read_system_prompt)
        replacements = {
            'context': context
        }
        system_prompt = string.Template(system_prompt_template).substitute(replacements)

        agent_call = await call_llm(system_prompt=system_prompt, user_prompt=user_prompt, provider=provider)
        output = agent_call.llm_response
        print(output)
        json_pattern = re.compile(
            r'```json\s*(\{.*?}|\[.*?])\s*```',
            re.DOTALL | re.MULTILINE
        )

        match = json_pattern.search(output)
        action_tuples = []

        if match:
            json_str = match.group(1)
        else:
            raise ValueError("No JSON block found in the LLM output.")

        try:
            actions = json.loads(json_str)

            for action in actions:
                if 'action_number' in action and 'action_reason' in action:
                    tuple_entry = (action['action_number'], action['action_reason'])
                    action_tuples.append(tuple_entry)

        except json.JSONDecodeError as jde:
            print(f"JSON Decode Error: {jde}")
        except KeyError as ke:
            print(f"Key Error: {ke}")


        agent_call.parsed_output = action_tuples

    return agent_call


async def call_load_check_agent_text(
    ax_tree,
) -> bool:
    """
    Asynchronously checks if the page has loaded by analyzing the accessibility tree.
    """
    # Read user prompt template asynchronously
    def read_user_prompt():
        with open('prompts/check_load_text/check_load_user.txt', 'r') as f:
            return f.read()

    user_prompt_template = await asyncio.to_thread(read_user_prompt)
    replacements = {
        'ax_tree': ax_tree,
    }
    user_prompt = string.Template(user_prompt_template).substitute(replacements)

    # Read system prompt template asynchronously
    def read_system_prompt():
        with open('prompts/check_load_text/check_load_system.txt', 'r') as f:
            return f.read()

    system_prompt = await asyncio.to_thread(read_system_prompt)

    agent_call = await call_llm(system_prompt=system_prompt, user_prompt=user_prompt, provider="cerebras", model='llama3.1-70b')

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
                print("Error: 'pageLoaded' key not found in JSON")
                return False

        except json.JSONDecodeError:
            print("Error: Invalid JSON format")
            return False
    else:
        print("Error: No JSON object found in the answer")
        return False


async def call_check_load_agent_screenshot(
    screenshot,
    provider: str = 'groq'
) -> bool:
    """
    Asynchronously checks if the page has loaded by analyzing the screenshot.
    """
    def groq_screenshot_call():
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
        return completion.choices[0].message.content

    output = await asyncio.to_thread(groq_screenshot_call)

    print("Screenshot Analysis Response:\n", output)

    # Parse the response similar to call_load_check_agent_text
    json_match = re.search(r'\{[\s\S]*}', output)
    page_loaded = None

    if json_match:
        json_str = json_match.group(0)

        try:
            parsed_json = json.loads(json_str)
            page_loaded = parsed_json.get("pageLoaded")

            if page_loaded is not None:
                return page_loaded
            else:
                print("Error: 'pageLoaded' key not found in JSON")
                return False

        except json.JSONDecodeError:
            print("Error: Invalid JSON format")
            return False
    else:
        print("Error: No JSON object found in the answer")
        return False


async def call_memory_agent(
    web_agent_task: str,
    action_memory: List,  # Define the specific type if available
    world_memory: str,
    provider: str = "anthropic"
) -> AgentCall:
    """
    Asynchronously calls the memory agent LLM and processes its response.
    """
    new_action_memory = ''
    for i, lin_mem in enumerate(action_memory):
        new_action_memory += f"\n{i + 1})\n{i + 1}) EFFECT: {lin_mem.location_details}"

    # Read prompt template asynchronously
    def read_prompt():
        with open('prompts/world_mem_prompt_v2.txt', 'r') as f:
            return f.read()

    prompt_template = await asyncio.to_thread(read_prompt)
    replacements = {
        'web_agent_task': web_agent_task,
        'world_memory': world_memory,
        'action_memory': new_action_memory,
    }
    prompt = string.Template(prompt_template).substitute(replacements)

    # Call the updated call_llm asynchronously
    agent_call = await call_llm(user_prompt=prompt, provider='cerebras', model='llama3.1-70b')

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
                print("Error: 'new_world_memory' key not found in JSON")
                parsed_output = "Error: 'new_world_memory' key not found in JSON"

        except json.JSONDecodeError:
            print("Error: Invalid JSON format")
            parsed_output = "Error: Invalid JSON format"
    else:
        print("Error: No JSON object found in the answer")
        parsed_output = "Error: No JSON object found in the answer"

    # Update the parsed_output in AgentCall
    agent_call.parsed_output = parsed_output

    return agent_call


async def call_reflect_agent(
    reason_for_action: str,
    old_ax_tree: str,
    new_ax_tree: str,
    web_agent_task: str,
    provider: str = "openai"
) -> AgentCall:
    """
    Asynchronously calls the reflect agent LLM and processes its response.
    """
    # Read user prompt template asynchronously
    def read_user_prompt():
        with open('prompts/reflect/reflect_llama_user.txt', 'r') as f:
            return f.read()

    def read_system_prompt():
        with open('prompts/reflect/reflect_llama_system.txt', 'r') as f:
            return f.read()

    user_prompt_template = await asyncio.to_thread(read_user_prompt)
    replacements = {
        'reason_for_action': reason_for_action,
        'old_accessibility_tree': old_ax_tree,
        'new_accessibility_tree': new_ax_tree,
        'web_agent_task': web_agent_task,
    }
    user_prompt = string.Template(user_prompt_template).substitute(replacements)

    system_prompt = read_system_prompt()

    # Call the updated call_llm asynchronously
    agent_call = await call_llm(user_prompt=user_prompt, system_prompt=system_prompt, provider='cerebras', model='llama-3.3-70b')

    print("LLM Response:\n", agent_call.llm_response)

    # Updated regex pattern to capture JSON within ```json or ``` code blocks
    json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'

    # Use re.DOTALL to allow '.' to match newlines
    json_matches = re.findall(json_pattern, agent_call.llm_response, re.DOTALL)
    parsed_output: Optional[Tuple[str, str, str]] = ('', '', '')

    if json_matches:
        for json_str in json_matches:
            try:
                cleaned_json = json_str.replace("\\'", "'")
                data = json.loads(cleaned_json)
                # data = json.loads(json_str)
                if 'final_answer' in data:
                    action_effect = data.get('final_answer', '')
                    difference_reasoning = data.get('difference_reasoning', '')
                    parsed_output = (action_effect, difference_reasoning)
                    print("Parsed Data:", data)
                    break  # Exit after finding the first valid match
            except json.JSONDecodeError as e:
                print(f"Reflect Restore Error: JSON decoding failed for a matched block - {e}")
                continue
    else:
        print("Reflect Restore Error: No JSON object found in the LLM response")

    # Update the parsed_output in AgentCall
    agent_call.parsed_output = parsed_output

    return agent_call


async def call_task_separator(
    web_agent_task: str,
    provider: str = "anthropic"
) -> AgentCall:
    """
    Asynchronously calls the task separator LLM and processes its response.
    """
    # Read prompt template asynchronously
    def read_prompt():
        with open('prompts/task_separator_prompt_json.txt', 'r') as f:
            return f.read()

    prompt_template = await asyncio.to_thread(read_prompt)
    replacements = {
        'web_agent_task': web_agent_task,
    }
    prompt = string.Template(prompt_template).substitute(replacements)

    # Call the updated call_llm asynchronously
    agent_call = await call_llm(user_prompt=prompt, provider='cerebras', model='llama3.1-70b')
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
        print("Task Separator: No JSON object found in the output.")
        parsed_output = None

    # Update the parsed_output in AgentCall
    agent_call.parsed_output = parsed_output

    return agent_call


async def call_task_clarifier(  # NO LONGER USED
    user_task: str,
    item_context_pairs: str,
    context: str,
    provider: str = "anthropic"
) -> AgentCall:
    """
    Asynchronously calls the task clarifier LLM and processes its response.
    """
    # Read prompt template asynchronously
    def read_prompt():
        with open('prompts/task_parser_prompt.txt', 'r') as f:
            return f.read()

    prompt_template = await asyncio.to_thread(read_prompt)
    replacements = {
        'user_task': user_task,
        'item_of_interest': item_context_pairs,
        'context': context
    }
    prompt = string.Template(prompt_template).substitute(replacements)

    # Call the updated call_llm asynchronously
    agent_call = await call_llm(user_prompt=prompt, provider='groq')

    print("LLM Response:\n", agent_call.llm_response)

    pattern = r'"""([\s\S]*?)"""'
    match = re.search(pattern, agent_call.llm_response)

    parsed_output = match.group(1).strip() if match else ""

    # Update the parsed_output in AgentCall
    agent_call.parsed_output = parsed_output

    return agent_call


async def call_input_agent(
    user_task: str,
    agent_intent: str,
    input_ax_tree: str,
    context: str,
    hidden_inputs: List[HiddenInput],
    task_notes: str,
    provider: str = "anthropic"
) -> AgentCall:
    """
    Asynchronously calls the input agent LLM and processes its response.
    """

    # Read prompt template asynchronously
    def read_prompt():
        with open('prompts/mass_input_prompt_json.txt', 'r') as f:
            return f.read()

    prompt_template = await asyncio.to_thread(read_prompt)

    replacements = {
        'user_task': user_task,
        'agent_intent': agent_intent,
        'input_ax_tree': input_ax_tree,
        'task_notes': task_notes
    }
    prompt = string.Template(prompt_template).substitute(replacements)

    # Call the updated call_llm asynchronously
    agent_call = await call_llm(user_prompt=prompt, provider='cerebras', model='llama-3.3-70b')

    print("INPUT CALL BEGIN")
    print(prompt)
    print("INPUT CALL END")

    # Extract JSON from the response
    json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
    json_matches = re.findall(json_pattern, agent_call.llm_response, re.DOTALL)

    if not json_matches:
        raise ValueError("No JSON found in LLM response")

    try:
        # Parse the first JSON match
        response_data = json.loads(json_matches[0])

        # Extract and format the choices
        parsed_output = [
            (choice['text_area_number'], choice['desired_input'])
            for choice in response_data.get('choices', [])
        ]

        # Update the parsed_output in AgentCall
        agent_call.parsed_output = parsed_output

    except json.JSONDecodeError as e:
        raise ValueError(f"Mass input error: Invalid JSON in LLM response {e}")
    except KeyError as e:
        raise ValueError(f"Mass input error: Missing required key in JSON response {e}")

    return agent_call


async def call_unified_task_clarifier(
    user_task: str,
    context: str,
    provider: str = "anthropic"
) -> AgentCall:
    """
    Asynchronously calls the unified task clarifier LLM and processes its response.
    """
    # Read prompt template asynchronously
    def read_prompt():
        with open('prompts/unified_task_clarifier_json.txt', 'r') as f:
            return f.read()

    prompt_template = await asyncio.to_thread(read_prompt)
    replacements = {
        'user_task': user_task,
        'context': context
    }
    prompt = string.Template(prompt_template).substitute(replacements)

    # Call the updated call_llm asynchronously
    agent_call = await call_llm(user_prompt=prompt, provider='cerebras', model='llama3.1-70b')

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


async def call_unified_question_cleaner(
    user_task: str,
    user_qa: List[Tuple[str, str]],
    provider: str = "anthropic"
) -> AgentCall:
    """
    Asynchronously calls the unified question cleaner LLM and processes its response.
    """
    # Read prompt template asynchronously
    def read_prompt():
        with open('prompts/unified_question_cleaner_json.txt', 'r') as f:
            return f.read()

    prompt_template = await asyncio.to_thread(read_prompt)

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

    # Call the updated call_llm asynchronously
    agent_call = await call_llm(user_prompt=prompt, provider='cerebras', model='llama3.1-70b')

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



async def call_action_pruner(
    user_task: str,
    ax_tree: str,
    action_memory: List, 
    actions,
    provider: str = "cerebras"
) -> AgentCall:
    """
    Asynchronously calls the action pruner and retrieves a list of actions that should be pruned.
    """
    # Read prompt template asynchronously
    def read_user_prompt():
        with open('prompts/prune/prune_user.txt', 'r') as f:
            return f.read()
    def read_system_prompt():
        with open('prompts/prune/prune_system.txt', 'r') as f:
            return f.read()

    user_prompt_template = await asyncio.to_thread(read_user_prompt)
    system_prompt = await asyncio.to_thread(read_system_prompt)
    replacements = {
        'task': user_task,
        'ax_tree': ax_tree,
        'action_memory': action_memory,
        'actions': actions
    }
    user_prompt = string.Template(user_prompt_template).substitute(replacements)
    print("User Prompt:\n", user_prompt)
    print("System Prompt:\n", system_prompt)
    # Call the updated call_llm asynchronously
    agent_call = await call_llm(user_prompt=user_prompt, system_prompt = system_prompt, provider='cerebras', model='llama3.1-70b')

    print("LLM Response:\n", agent_call.llm_response)
    # input()
    # Find JSON object in the text
    match = re.search(r'\[\s*(-?\d+\s*(,\s*-?\d+\s*)*)?\]', agent_call.llm_response)
    if match:
        # Extract the matched list
        list_content = match.group(0)
        # Evaluate the list content safely
        try:
            agent_call.parsed_output = eval(list_content)
        except (SyntaxError, ValueError):
            agent_call.parsed_output = []  # Fallback to an empty list if evaluation fails
    agent_call.parsed_output = []  # No valid list found
    #
        

    return agent_call





async def call_intermediate_questions_agent(
    user_task: str,
    ax_tree: str,
    question_intent: str,
    task_notes: str
) -> AgentCall:

    def read_user_prompt():
        with open('prompts/intermediate_questions_prompt.txt', 'r') as f:
            return f.read()

    user_prompt_template = await asyncio.to_thread(read_user_prompt)
    replacements = {
        'ax_tree': ax_tree,
        'task': user_task,
        'question_intent': question_intent,
        'task_notes': task_notes
    }
    user_prompt = string.Template(user_prompt_template).substitute(replacements)

    # Call the updated call_llm asynchronously
    agent_call = await call_llm(user_prompt=user_prompt, provider='cerebras', model='llama-3.3-70b')

    print("LLM Response:\n", agent_call.llm_response)


    json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'

    json_matches = re.findall(json_pattern, agent_call.llm_response, re.DOTALL)
    parsed_output: Optional[str] = ""

    if json_matches:
        for json_str in json_matches:
            try:
                data = json.loads(json_str)
                if 'questions' in data:
                    grounded_progress_summary = data.get('questions', [])
                    parsed_output = grounded_progress_summary
                    print("Parsed Data:", data)
                    break  # Exit after finding the first valid match
            except json.JSONDecodeError as e:
                print(f"intermediate questions agent error: JSON decoding failed for a matched block - {e}")
                continue
    else:
        print("intermediate questions agent error: No JSON object found in the LLM response")

    # Update the parsed_output in AgentCall
    agent_call.parsed_output = parsed_output

    return agent_call


async def call_unified_notes_cleaner(
    user_task: str,
    task_notes: str,
    user_qa: str,
    context: str,
) -> AgentCall:

    def read_user_prompt():
        with open('prompts/task_notes_cleaner.txt', 'r') as f:
            return f.read()

    user_prompt_template = await asyncio.to_thread(read_user_prompt)
    replacements = {
        'user_task': user_task,
        'original_task_notes': task_notes,
        'new_user_answers': user_qa,
        'context': context
    }
    user_prompt = string.Template(user_prompt_template).substitute(replacements)
    # Call the updated call_llm asynchronously
    print(user_prompt)
    agent_call = await call_llm(user_prompt=user_prompt, provider='cerebras', model='llama-3.3-70b')

    print("LLM Response:\n", agent_call.llm_response)


    json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'

    json_matches = re.findall(json_pattern, agent_call.llm_response, re.DOTALL)
    parsed_output: Optional[str] = ""

    if json_matches:
        for json_str in json_matches:
            try:
                data = json.loads(json_str)
                if 'new_task_notes' in data:
                    new_task_notes = data.get('new_task_notes', [])
                    parsed_output = new_task_notes
                    print("Parsed Data:", data)
                    break  # Exit after finding the first valid match
            except json.JSONDecodeError as e:
                print(f"task notes cleaner: JSON decoding failed for a matched block - {e}")
                continue
    else:
        print("task notes agent error: No JSON object found in the LLM response")
    # Update the parsed_output in AgentCall
    agent_call.parsed_output = parsed_output

    return agent_call