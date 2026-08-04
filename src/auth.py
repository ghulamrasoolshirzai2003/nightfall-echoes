"""Run ONCE locally to mint a YouTube refresh token.

    python -m src.auth

It opens your browser, you click "Allow" on YOUR channel's Google account, and it
prints CLIENT_ID / CLIENT_SECRET / REFRESH_TOKEN. Paste those into GitHub Secrets.
The refresh token then lets the cloud upload forever without you logging in again.

Prerequisite: download your OAuth client file from Google Cloud Console and save it
next to this project as `client_secret.json` (see SETUP.md).
"""
from google_auth_oauthlib.flow import InstalledAppFlow

from .settings import ROOT

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]


def main():
    client_file = ROOT / "client_secret.json"
    if not client_file.exists():
        raise SystemExit(
            "Put your OAuth client file at 'client_secret.json' first (see SETUP.md)."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), SCOPES)
    creds = flow.run_local_server(port=0)
    print("\n=== Paste these into GitHub → Settings → Secrets → Actions ===\n")
    print(f"YT_CLIENT_ID={creds.client_id}")
    print(f"YT_CLIENT_SECRET={creds.client_secret}")
    print(f"YT_REFRESH_TOKEN={creds.refresh_token}")
    print("\nKeep these secret. Never commit them.")


if __name__ == "__main__":
    main()
