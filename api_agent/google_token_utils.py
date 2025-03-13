# google_token_utils.py

import os
from datetime import datetime, timezone, timedelta
import google.auth.transport.requests

async def refresh_google_token_if_needed(
    record: dict,
    authenticated_google_credentials,
    google_credentials: dict,
    supabase_handler,
    user_id: str,
    force_refresh: bool = False
) -> bool:
    """
    Checks if the Google access token is expired or about to expire (within 5 minutes)
    or forces a refresh if specified. If the token is refreshed, it updates the database
    with the new token details.

    Parameters:
        record: The user record from the database.
        authenticated_google_credentials: The Credentials object.
        google_credentials: The original google_credentials dict.
        supabase_handler: The Supabase handler (used for DB updates).
        user_id: The current user's id.
        force_refresh: If True, forces a token refresh regardless of expiration.

    Returns:
        True if the token was refreshed, False otherwise.
    """
    should_refresh = force_refresh
    access_expires_at_str = record.get("google_access_expires_at")
    if access_expires_at_str and not force_refresh:
        access_expires_at = datetime.fromisoformat(access_expires_at_str)
        if access_expires_at - datetime.now(timezone.utc) < timedelta(minutes=5):
            should_refresh = True

    if should_refresh:
        print("Refreshing Google access token...")
        try:
            request_obj = google.auth.transport.requests.Request()
            authenticated_google_credentials.refresh(request_obj)
        except Exception as e:
            print("Error refreshing token:", e)
            raise e  # Or handle the error as needed

        new_token = authenticated_google_credentials.token
        new_expiry = authenticated_google_credentials.expiry
        refresh_expiry = record.get("google_refresh_expires_at")
        updated_google_credentials = google_credentials.copy()
        updated_google_credentials["access_token"] = new_token

        # Update the database with new token details
        await supabase_handler.client.rpc("set_user_google_credentials", {
            "user_id_param": user_id,
            "token": updated_google_credentials,
            "access_expiry": new_expiry.isoformat(),
            "refresh_expiry": refresh_expiry
        }).execute()

        print("Database updated with refreshed Google credentials.")
        return True

    return False