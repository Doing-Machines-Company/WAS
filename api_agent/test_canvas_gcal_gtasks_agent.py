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

async def main():
    valid_emails = {'cadatepe@andrew.cmu.edu'}
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_KEY")
    client: supabase.Client = supabase.create_client(url, key)

    users = client.table("users").select("user_id").execute().data
    for user_id in users:
        response = client.rpc("get_user", {"user_id_param": user_id["user_id"]}).execute()
        if response.data:  # Ensure we got a record back
            record = response.data[0]  # Get the user record
            google_credentials = record.get("google_credentials")
            gradescope_credentials = record.get("gradescope_credentials")
            canvas_token = record.get("canvas_token")
            canvas_domain = record.get("canvas_domain")
            # Optionally, if you only need the canvas token string:
            canvas_token_str = canvas_token.get("token") if canvas_token else None
            if record.get("email") not in valid_emails:
                continue
            print("Email:", record.get("email"))
            print("Google Credentials:", google_credentials)
            print("Gradescope Credentials:", gradescope_credentials)
            print("Canvas Token:", canvas_token_str)
            print("Canvas Domain", canvas_domain)
            poll_out = []
            try:
                try:
                    if gradescope_credentials and gradescope_credentials.get('email') and gradescope_credentials.get('password'):
                        gradescope_agent = GradescopeAPIAgent(credentials = gradescope_credentials)
                    
                        print("Agent task:", gradescope_agent.task)
                    
                        await gradescope_agent.run()
                        print("Agent run has completed.")
                        poll_out_gradescope = gradescope_agent.get_poll_output()
                        input(poll_out_gradescope)
                        poll_out.extend(poll_out_gradescope)
                except Exception as e:
                    print("Error running gradescope agent", e)
                
                try:
                    if canvas_domain and canvas_token_str:
                        canvas_agent = CanvasAPIAgent(credentials = {'url': 'https://' + canvas_domain, 'token': canvas_token_str})
                    
                        print("Agent task:", canvas_agent.task)
                    
                        await canvas_agent.run()
                        print("Agent run has completed.")
                        poll_out_canvas = canvas_agent.get_poll_output()
                        input(poll_out_canvas)
                        poll_out.extend(poll_out_canvas)

                except Exception as e:
                    print("Error running canvas agent", e)

                step_size = 1

                # if google_credentials.get("access_token") and google_credentials.get("scope") and google_credentials.get("refresh_token"):
                #     authenticated_google_credentials = Credentials(token = google_credentials["access_token"],
                #                                                     refresh_token=google_credentials["refresh_token"], 
                #                                                     token_uri = 'https://oauth2.googleapis.com/token',
                #                                                     client_id = os.getenv('CLIENT_ID'),
                #                                                     client_secret = os.getenv('CLIENT_SECRET'),
                #                                                     scopes = google_credentials["scope"].split())
                # else:
                #     continue
                for i in range(0, len(poll_out), step_size):
                    cur_chunk = poll_out[i:i + step_size]
                    task_string = ""
                    for i, linmem in enumerate(cur_chunk):
                        task_string += f"{i})\nCall: \n{linmem.call}\nReceived: \n{linmem.received}\n"
                        # gcalgtasks_agent = GCalGTasksAPIAgent(
                        #         task=task_string,
                        #         from_user=False,
                        #         credentials = authenticated_google_credentials
                        #     )
                        # await gcalgtasks_agent.run()
                        supabase_agent = SupabaseCalendarTasksAPIAgentMulti(
                            task = task_string,
                            user_id = user_id["user_id"]
                        )
                        await supabase_agent.run()
            except Exception as e:
                print(e)

if __name__ == "__main__":
    asyncio.run(main())
    

        