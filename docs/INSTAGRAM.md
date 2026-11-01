# Instagram Reels for Autoreels (@yourchannel)

Set `IG_MODE` in `.env`:
- `phone`: the Reel and caption come to you on Telegram; you share it from your phone (20 seconds). Works today.
- `api`: posted automatically through Meta's Graph API. Set it up once with the steps below.

The Reel cover is the video's first frame (the hook text with Pappu, Golu and Chhotu). It sits inside the 3:4 area the profile
grid shows. `IG_THUMB_MS=0` picks the frame used as cover (milliseconds from the start).

## Automatic posting: the Meta Business route (about 20 minutes, once)

### 1. Instagram professional account linked to a Facebook Page
1. Instagram app → @yourchannel → Settings → **Account type and tools → Switch to professional account → Creator or Business**.
2. Facebook: create a Page called **Autoreels** (facebook.com/pages/create). It can stay empty.
3. **business.facebook.com** (Meta Business Suite) → Settings → **Instagram accounts → Connect** → log in as @yourchannel,
   and attach it to the Autoreels Page.

### 2. A Meta app
1. **developers.facebook.com** → My Apps → **Create App** → use case **"Other"** → type **Business** → name "Autoreels Reels"
   → connect it to your business portfolio if asked.
2. In the app dashboard, add the products **Instagram Graph API** (or "Instagram" → API setup with Facebook login) and **Facebook Login for Business**.
3. App settings → Basic: copy the **App ID** and **App Secret**.

### 3. A token (Graph API Explorer)
1. developers.facebook.com/tools/explorer → choose your app (top right) → **User token**.
2. Add these permissions: `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`, `business_management`.
3. **Generate Access Token** → log in → choose the Autoreels Page and @yourchannel → allow everything.
4. Copy the token (it lasts about an hour; the next step turns it into a permanent one).

### 4. Connect (on this PC; secrets never go into a chat)
Open `FunChal\.env` in Notepad and add:
```
META_APP_ID=your_app_id
META_APP_SECRET=your_app_secret
META_USER_TOKEN=the_token_from_step_3
```
Save, then run:
```
python main.py ig meta-setup
```
It exchanges the token for a **Page token that does not expire**, finds @yourchannel's account ID, saves `IG_LOGIN=facebook`,
`IG_USER_ID`, `IG_TOKEN`, switches `IG_MODE=api`, and deletes `META_USER_TOKEN`.

### 5. Test
```
python main.py ig check
python main.py ig post <job>
```
`check` shows the account and how many posts are left in the 24-hour limit. `post` publishes one Reel immediately (pick a job from `python main.py list`).

From then on every Short is posted as a Reel within about 30 minutes of going live on YouTube (max `IG_MAX_PER_DAY`, default 4),
and you get the Reel link on Telegram.

## How the upload works
The factory first sends the video file directly (resumable upload). If Meta asks for a link instead, it serves the file for a minute
through a free Cloudflare tunnel (`cloudflared`, already installed) and gives Meta that link, then closes it.

## Instagram Login route (alternative, no Facebook Page)
Instagram app set to Professional → developers.facebook.com → Create App → Instagram → "API setup with Instagram login" → add the account
as tester → Generate access token with `instagram_business_basic` and `instagram_business_content_publish` → in `.env`:
`IG_MODE=api`, `IG_LOGIN=instagram`, `IG_TOKEN=...`. This token lasts 60 days and is refreshed automatically every 30 days.
