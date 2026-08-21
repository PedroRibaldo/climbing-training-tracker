"""
One-time WHOOP OAuth authorization: opens the WHOOP consent page, catches
the redirect on localhost, exchanges the code for an access/refresh token
pair, and seeds the single row in `whoop_tokens`.

Run once, locally: `python scripts/whoop_authorize.py`. Doesn't normally
need to run again - scripts/whoop_sync.py refreshes the token pair itself
on every run. The exception: WHOOP scopes are fixed at consent time, so
adding a scope to SCOPES (as happened when climbing-workout sync was
added) requires re-running this script once to get a token pair that
actually carries the new scope - a refresh alone cannot grant it.
"""

import http.server
import os
import secrets
import socketserver
import urllib.parse
import webbrowser
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from supabase import create_client

AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
SCOPES = "offline read:recovery read:cycles read:workout"
REDIRECT_PORT = 8942
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Catches the single OAuth redirect and stashes the `code`/`state`
    query params on the server instance so the caller can read them."""

    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        self.server.auth_code = params.get('code', [None])[0]
        self.server.auth_state = params.get('state', [None])[0]
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"<html><body>Authorized - you can close this tab.</body></html>")

    def log_message(self, format, *args):
        pass  # silence default request logging


def _get_authorization_code(client_id: str, expected_state: str) -> str:
    """Opens the WHOOP consent page and blocks until the redirect lands."""
    params = {
        'response_type': 'code',
        'client_id': client_id,
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPES,
        'state': expected_state,
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    print(f"Opening browser for WHOOP authorization:\n{url}")
    webbrowser.open(url)

    with socketserver.TCPServer(("localhost", REDIRECT_PORT), _CallbackHandler) as httpd:
        httpd.auth_code = None
        httpd.auth_state = None
        httpd.handle_request()  # blocks for exactly one request

    if httpd.auth_state != expected_state:
        raise RuntimeError("OAuth state mismatch - possible CSRF, aborting.")
    if not httpd.auth_code:
        raise RuntimeError("No authorization code received from WHOOP.")
    return httpd.auth_code


def _exchange_code_for_tokens(code: str, client_id: str, client_secret: str) -> dict:
    response = requests.post(TOKEN_URL, data={
        'grant_type': 'authorization_code',
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': REDIRECT_URI,
    })
    response.raise_for_status()
    return response.json()


def main():
    load_dotenv()
    client_id = os.environ['WHOOP_CLIENT_ID']
    client_secret = os.environ['WHOOP_CLIENT_SECRET']
    supabase = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])

    state = secrets.token_urlsafe(16)
    code = _get_authorization_code(client_id, state)
    tokens = _exchange_code_for_tokens(code, client_id, client_secret)

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens['expires_in'])
    supabase.table('whoop_tokens').upsert({
        'id': True,
        'access_token': tokens['access_token'],
        'refresh_token': tokens['refresh_token'],
        'expires_at': expires_at.isoformat(),
    }).execute()
    print("WHOOP authorization complete - token pair saved to whoop_tokens.")


if __name__ == '__main__':
    main()
