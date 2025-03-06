# auth_google_calendar_tasks.py
import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Define the required scopes
SCOPES = [
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.app.created",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/tasks"
]


def authenticate():
    """
    Authenticate with Google Calendar API using OAuth2

    Returns:
        Credentials: Valid Google API credentials
    """
    creds = None

    # Check if token.pickle file exists with stored credentials
    if os.path.exists('token.pickle'):
        print("Found existing token file. Checking if valid...")
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    # If no credentials found or they're invalid
    if not creds or not creds.valid:
        # If credentials expired but we have a refresh token, refresh them
        if creds and creds.expired and creds.refresh_token:
            print("Credentials expired. Refreshing...")
            creds.refresh(Request())
        else:
            # If no valid credentials available, start OAuth flow
            print("No valid credentials found. Starting OAuth flow...")
            print("Make sure you have a credentials.json file in the current directory.")
            print("You can generate this file from the Google Cloud Console:")
            print("https://console.cloud.google.com/apis/credentials")

            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for future use
        with open('token.pickle', 'wb') as token:
            print("Saving credentials to token.pickle file...")
            pickle.dump(creds, token)

    print("Successfully authenticated with Google Calendar API!")
    return creds


if __name__ == "__main__":
    print("Google Calendar API Authentication Script")
    print("=========================================")
    print("This script will authenticate with the Google Calendar API")
    print("with the following scopes:")
    for scope in SCOPES:
        print(f"  - {scope}")
    print()

    try:
        creds = authenticate()
        print("Authentication successful!")
        print("You can now run your AsyncGoogleCalendarAPIHandler tests.")
    except Exception as e:
        print(f"Authentication failed: {e}")
        print("\nTroubleshooting tips:")
        print("1. Make sure you have a valid credentials.json file in the current directory")
        print("2. Ensure your Google Cloud project has the Calendar API and Tasks API enabled")
        print("3. Verify that your OAuth consent screen is properly configured")
        print("4. If you're using a test project, make sure your Google account is added as a test user")