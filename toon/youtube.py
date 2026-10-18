import logging
from datetime import timezone
from pathlib import Path

from . import config

log = logging.getLogger("toon.youtube")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/youtube.force-ssl",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]


def _credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if config.TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(config.TOKEN_FILE), SCOPES)
    if creds:
        import json as _json
        try:
            _granted = set(_json.loads(config.TOKEN_FILE.read_text(encoding="utf-8")).get("scopes") or [])
        except Exception:
            _granted = set()
        if not set(SCOPES) <= _granted:
            creds = None  # saved sign in lacks a permission (for example Analytics): sign in again once
    if creds and not set(SCOPES) <= set(creds.scopes or []):
        creds = None  # token from an older version lacks the read scope: authorise again once
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as _e:
            if "invalid_scope" not in str(_e):
                raise
            creds = None  # the saved sign in never had a permission it lists: sign in again
    if not creds or not creds.valid:
        if not config.CLIENT_SECRET.exists():
            raise FileNotFoundError(f"Missing {config.CLIENT_SECRET}. See README step 5 (YouTube OAuth).")
        flow = InstalledAppFlow.from_client_secrets_file(str(config.CLIENT_SECRET), SCOPES)
        creds = flow.run_local_server(port=0)
    config.TOKEN_FILE.write_text(creds.to_json())
    return creds


def authenticate():
    _credentials()
    return "YouTube authorisation saved."


def build_body(title: str, description: str, tags: list, privacy: str = None, publish_at=None, shorts: bool = True) -> dict:
    """The videos.insert request body. Kept separate so it can be tested without YouTube."""
    privacy = privacy or config.YT_PRIVACY
    if privacy not in ("private", "unlisted", "public"):
        raise ValueError("privacy must be private, unlisted or public")
    if shorts and "#shorts" not in description.lower():
        description = (description + "\n\n#Shorts").strip()
    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}
    if publish_at is not None:  # YouTube publishes it by itself at that time, even if this computer is off
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if config.YT_SYNTHETIC:
        status["containsSyntheticMedia"] = True
    snippet = {"title": title[:100], "description": description[:4900], "tags": tags, "categoryId": config.YT_CATEGORY}
    if config.LANGUAGE:
        snippet["defaultLanguage"] = config.LANGUAGE
        snippet["defaultAudioLanguage"] = config.LANGUAGE
    return {"snippet": snippet, "status": status}


def upload(video: Path, title: str, description: str, tags: list, privacy: str = None, publish_at=None, with_id: bool = False,
           shorts: bool = True):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    body = build_body(title, description, tags, privacy, publish_at, shorts)
    status = body["status"]
    yt = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)
    media = MediaFileUpload(str(video), chunksize=-1, resumable=True, mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    url = f"https://youtu.be/{resp['id']}"
    log.info("uploaded %s (%s%s)", url, status["privacyStatus"], f", publishes {status['publishAt']}" if publish_at else "")
    return (url, resp["id"]) if with_id else url


def set_thumbnail(video_id: str, image: Path):
    """Put a custom thumbnail on a video. Returns (True, 'ok') or (False, reason). Never raises, a missing thumbnail must not lose the upload."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    try:
        yt = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)
        yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(image), mimetype="image/jpeg")).execute()
        return True, "ok"
    except Exception as e:
        log.warning("thumbnail for %s was not accepted: %s", video_id, str(e)[:300])
        return False, str(e)[:200]


def post_comment(video_id: str, text: str):
    """Posts a top-level comment as the channel. Returns (True, comment_id) or (False, reason). Never raises.
    The API cannot pin comments: pin it in YouTube Studio (Comments, three dots, Pin)."""
    from googleapiclient.discovery import build
    try:
        yt = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)
        body = {"snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": text[:9000]}}}}
        r = yt.commentThreads().insert(part="snippet", body=body).execute()
        return True, r["id"]
    except Exception as e:
        return False, str(e)[:200]


def upload_captions(video_id: str, srt_text: str, language: str = "hi", name: str = "Hindi"):
    """Adds a caption track (SRT text). Returns (True, caption_id) or (False, reason). Never raises."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaInMemoryUpload
    try:
        yt = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)
        body = {"snippet": {"videoId": video_id, "language": language, "name": name, "isDraft": False}}
        media = MediaInMemoryUpload(srt_text.encode("utf-8"), mimetype="application/octet-stream", resumable=False)
        r = yt.captions().insert(part="snippet", body=body, media_body=media).execute()
        return True, r["id"]
    except Exception as e:
        return False, str(e)[:200]


def update_metadata(video_id: str, title: str, description: str, tags: list):
    """Rewrites title, description and tags of an uploaded video, keeping its category and languages."""
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)
    sn = yt.videos().list(part="snippet", id=video_id).execute()["items"][0]["snippet"]
    body = {"id": video_id, "snippet": {"title": title[:100], "description": description[:4900], "tags": tags,
                                        "categoryId": sn.get("categoryId", config.YT_CATEGORY),
                                        "defaultLanguage": sn.get("defaultLanguage", config.LANGUAGE),
                                        "defaultAudioLanguage": sn.get("defaultAudioLanguage", config.LANGUAGE)}}
    yt.videos().update(part="snippet", body=body).execute()


def set_channel_trailer(video_id: str):
    """Makes this video the trailer non-subscribers see on the channel home page. Returns (True, 'ok') or (False, reason)."""
    from googleapiclient.discovery import build
    try:
        yt = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)
        ch = yt.channels().list(part="brandingSettings", mine=True).execute()["items"][0]
        branding = ch.get("brandingSettings", {})
        branding.setdefault("channel", {})["unsubscribedTrailer"] = video_id
        yt.channels().update(part="brandingSettings", body={"id": ch["id"], "brandingSettings": branding}).execute()
        return True, "ok"
    except Exception as e:
        return False, str(e)[:300]


def check_schedule(video_id: str):
    """What YouTube stored for this video: {privacy, publish_at}, or None if it cannot be found."""
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)
    items = yt.videos().list(part="status", id=video_id).execute().get("items", [])
    if not items:
        return None
    st = items[0].get("status", {})
    return {"privacy": st.get("privacyStatus"), "publish_at": st.get("publishAt")}


def get_stats(video_ids: list) -> dict:
    """{video_id: {views, likes, comments}} for videos that are public by now."""
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)
    out = {}
    for i in range(0, len(video_ids), 50):
        r = yt.videos().list(part="statistics,status", id=",".join(video_ids[i:i + 50])).execute()
        for it in r.get("items", []):
            st = it.get("statistics", {})
            out[it["id"]] = {"views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                             "comments": int(st.get("commentCount", 0)),
                             "public": it.get("status", {}).get("privacyStatus") == "public"}
    return out


def ensure_playlist(title: str, description: str = "", privacy: str = "public"):
    """The id of the channel's playlist with this title; created if there is none. Returns (id, note), id is None on failure. Never raises."""
    from googleapiclient.discovery import build
    try:
        yt = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)
        page = None
        while True:
            r = yt.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=page).execute()
            for it in r.get("items", []):
                if it["snippet"]["title"].strip().lower() == title.strip().lower():
                    return it["id"], "found"
            page = r.get("nextPageToken")
            if not page:
                break
        body = {"snippet": {"title": title[:150], "description": description[:4000]}, "status": {"privacyStatus": privacy}}
        made = yt.playlists().insert(part="snippet,status", body=body).execute()
        log.info("created playlist %s", title)
        return made["id"], "created"
    except Exception as e:
        log.warning("playlist '%s' not available: %s", title, str(e)[:300])
        return None, str(e)[:200]


def add_to_playlist(video_id: str, playlist_id: str):
    """Returns (True, 'ok') or (False, reason). Never raises, a playlist problem must not lose the upload."""
    from googleapiclient.discovery import build
    try:
        yt = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)
        body = {"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}
        yt.playlistItems().insert(part="snippet", body=body).execute()
        return True, "ok"
    except Exception as e:
        return False, str(e)[:200]


def thumbnail_hint(note: str) -> str:
    """Plain words for the usual reason a custom thumbnail is refused."""
    n = (note or "").lower()
    if "custom video thumbnails" in n or "forbidden" in n or "403" in n:
        return "Most likely the channel is not verified: open youtube.com/verify, confirm your phone number, wait a few minutes, then it works."
    if "quota" in n:
        return "The daily API quota is used up, it will work tomorrow."
    return ""
