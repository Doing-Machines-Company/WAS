# test_canvas_gcal_gtasks_agent.py
import os
import asyncio
import logging
import dotenv
import supabase
from agents.canvas.canvas_api_agent import CanvasAPIAgent
from agents.gcal.gcal_gtasks_api_agent import GCalGTasksAPIAgent
from agents.gradescope.gradescope_api_agent import GradescopeAPIAgent
from agents.supabase_cal_task.supabase_calendar_tasks_api_agent_multi import SupabaseCalendarTasksAPIAgentMulti
from google.oauth2.credentials import Credentials
import aiohttp
logging.basicConfig(level=logging.INFO)

"""

import asyncio
from agents.gcal.gcal_gtasks_api_agent import GCalGTasksAPIAgent

if __name__ == "__main__":
    # Simple test
    agent = GCalGTasksAPIAgent(
        task="I have a birthday for James Chan on Feb 10."
    )
    asyncio.run(agent.run())


"""
dotenv.load_dotenv()

async def run_gradescope_agent(credentials):
    """Run the Gradescope agent with the provided credentials."""
    try:
        if credentials and credentials.get('email') and credentials.get('password'):
            gradescope_agent = GradescopeAPIAgent(credentials=credentials)
            print("Agent task:", gradescope_agent.task)
            await gradescope_agent.run()
            print("Agent run has completed.")
            poll_output = gradescope_agent.get_poll_output()
            input(poll_output)
            return poll_output
    except Exception as e:
        print("Error running gradescope agent", e)
    return []

async def run_canvas_agent(domain, token, session):
    """Run the Canvas agent with the provided domain and token."""
    try:
        if domain and token:
            canvas_agent = CanvasAPIAgent(
                credentials={'url': 'https://' + domain, 'token': token}, 
                session=session
            )
            print("Agent task:", canvas_agent.task)
            await canvas_agent.run()
            print("Agent run has completed.")
            poll_output = canvas_agent.get_poll_output()
            input(poll_output)
            return poll_output
    except Exception as e:
        print("Error running canvas agent", e)
    return []

async def run_supabase_agent(task_string, user_id):
    """Run the Supabase Calendar Tasks agent."""
    try:
        supabase_agent = SupabaseCalendarTasksAPIAgentMulti(
            task=task_string,
            user_id=user_id
        )
        await supabase_agent.run()
    except Exception as e:
        print("Error running supabase agent", e)

async def process_polls(poll_data, user_id, step_size=1):
    """Process poll outputs and run the Supabase agent."""
    for i in range(0, len(poll_data), step_size):
        cur_chunk = poll_data[i:i + step_size]
        task_string = ""
        for i, linmem in enumerate(cur_chunk):
            task_string += f"{i})\nCall: \n{linmem.call}\nReceived: \n{linmem.received}\n"
            await run_supabase_agent(task_string, user_id)

async def main():
    valid_emails = {'yutianch@andrew.cmu.edu'}
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_KEY")
    client: supabase.Client = supabase.create_client(url, key)
    canvas_session = aiohttp.ClientSession()
    users = client.rpc("get_users").execute()
    
    if users.data:
        for record in users.data:
            google_credentials = record.get("google_credentials")
            gradescope_credentials = record.get("gradescope_credentials")
            canvas_token = record.get("canvas_token")
            canvas_domain = record.get("canvas_domain")
            # Optionally, if you only need the canvas token string:
            canvas_token_str = canvas_token.get("token") if canvas_token else None
            
            if record.get("email") not in valid_emails:
                continue
                
            print("Email:", record.get("email"))
            # print("Google Credentials:", google_credentials)
            # print("Gradescope Credentials:", gradescope_credentials)
            # print("Canvas Token:", canvas_token_str)
            # print("Canvas Domain", canvas_domain)
            
            try:
                poll_out = []
                
                # Run Gradescope agent
                poll_out_gradescope = await run_gradescope_agent(gradescope_credentials)
                poll_out.extend(poll_out_gradescope)
                
                # Run Canvas agent
                poll_out_canvas = await run_canvas_agent(canvas_domain, canvas_token_str, canvas_session)
                poll_out.extend(poll_out_canvas)
                
                # Process polls and run Supabase agent
                await process_polls(poll_out, record["user_id"])
                
            except Exception as e:
                print(e)

if __name__ == "__main__":
    asyncio.run(main())
    

        