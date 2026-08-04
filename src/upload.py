"""Stage 7 — upload the video to YouTube and set its thumbnail.

Uses the refresh token minted by src/auth.py, so it runs unattended in the cloud.
A single upload costs ~1600 of your 10,000 daily API quota units — plenty for 1-2/day.
"""
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .settings import CONFIG, env

TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]


def _service():
    creds = Credentials(
        token=None,
        refresh_token=env("YT_REFRESH_TOKEN"),
        client_id=env("YT_CLIENT_ID"),
        client_secret=env("YT_CLIENT_SECRET"),
        token_uri=TOKEN_URI,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def upload(video_path: str, thumbnail_path: str, meta: dict) -> str:
    up = CONFIG["upload"]
    youtube = _service()

    body = {
        "snippet": {
            "title": meta["title"][:100],
            "description": meta["description"][:4900],
            "tags": meta["tags"][:30],
            "categoryId": str(up["category_id"]),
        },
        "status": {
            "privacyStatus": up["privacy"],
            "selfDeclaredMadeForKids": up["made_for_kids"],
        },
    }

    print("[upload] Uploading video to YouTube...")
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True),
    )
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"[upload]   {int(status.progress() * 100)}%")
    video_id = response["id"]
    print(f"[upload] Video live: https://youtu.be/{video_id}")

    print("[upload] Setting thumbnail...")
    youtube.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(thumbnail_path),
    ).execute()

    return video_id
