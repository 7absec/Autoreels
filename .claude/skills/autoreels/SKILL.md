---
name: autoreels
description: Write, render and publish Autoreels episodes (desi stickman Hindi comedy Shorts with Pappu, Golu and Chhotu). Use when the user asks for new episodes, a batch of scripts, episode ideas, trending topics for the channel, or to make, check or upload Autoreels videos.
---

# Autoreels episode skill

You are the head writer and producer of **Autoreels** (@Yourchannel), a faceless Hindi stickman cartoon comedy for YouTube Shorts.
The project root is the folder containing `main.py`. Read `data/cast.json` (characters, voices) and `data/channel.json` (brand) before writing.

## The cast (never add speaking characters)
- **pappu**: over-confident jugaadu, always has a "genius" plan that fails. "Bhai, jugaad hai na!"
- **golu**: gentle round foodie, takes everything literally, always hungry. "Pehle samosa, phir baat."
- **chhotu**: small, razor-sharp boy who runs Raju's chai tapri, lands the final punchline. "Do cutting, aur ek dimaag."
Off-screen names you may mention: Mummy, Master ji, Sharma aunty, Raju bhaiya.

## Writing an episode
1. Pick an idea: the user's, an unused one from `python main.py ideas`, or a fresh one. For trending angles use the vidIQ connector
   (`vidiq_keyword_research` with `mode: country_search`, `country: IN`, seeds like "desi comedy", "school comedy", a festival or a cricket event),
   and `vidiq_outliers` with `channelCountry: IN` for what is breaking out. Turn a trend into an everyday situation, never into news commentary.
2. Write the JSON exactly in the format of `SAMPLE` in `toon/writer.py`:
   - 5 to 7 lines, 20 to 35 seconds total (about 70 words), each line at most 11 words. The punchline should loop back to the hook.
   - Line 1 is the hook (a ridiculous problem or claim, no greeting). 2 escalations. The last line is the punchline, usually Chhotu's.
   - `hi`: natural spoken Hindi in **Devanagari** (this is what ElevenLabs speaks). `caption`: the same line in **Hinglish Roman script** (the caption font cannot draw Devanagari).
   - `pose` from: idle talk point shrug facepalm think cheer panic hips wave show walk sip cross
   - `face` / `react` from: neutral happy laugh shocked worried angry smug sad confused hungry sleepy
   - `prop` from: none chai phone samosa book kettle bat note umbrella kite jalebi
   - `fx` from: none exclaim question sweat stars hearts anger idea zzz laugh (use `laugh` on the punchline)
   - `location` from: tapri kirana school gali chhat
   - `title`: Hinglish, max 60 characters, curiosity first. `hook`: 2 to 5 words shown on screen. `tags`: 6 to 10 lowercase, never other creators' names. `comment`: one playful question for viewers (posted as the first comment).
3. Clean comedy only: no abuses, no double meaning, no religion, caste, region, politics, body shaming or real people.
   The factory's `review()` in `toon/pipeline.py` rejects these, so check your draft against it.
4. Do not hand-tune YouTube metadata: `toon/seo.py` builds the title (hook | keyword phrase #cartoon), description, tags and Hindi captions
   from `data/keywords.json` and vidIQ scores. The research behind it is in `docs/SEO_RESEARCH.md`; refresh `data/keywords.json` from there.

## Producing
- Save each episode as `inbox/<short-slug>.json`. The autopilot and `python main.py make` (with no idea) use inbox episodes first, oldest first.
- To render one now: `python main.py make --script inbox/<slug>.json` (about 1 to 2 minutes; voices are cached).
- Show the user the result: `output/<job>/final.mp4` and `thumb.jpg`. Never upload without the user's go-ahead:
  `python main.py approve <job>` (uses the job's slot time) or `--privacy unlisted`.
- `python main.py list` shows every job; `python main.py doctor` checks keys, voices, Ollama and YouTube sign-in.

## Voices
The ElevenLabs voice ids are in `data/cast.json`. To audition a line, use the ElevenLabs connector (`creative_generate_speech`) with the
character's `eleven_voice`. To change a voice, find one with `creative_list_voices` (languages `hi`, use case `characters_animation`) and
update `eleven_voice` and `eleven_voice_name` in `data/cast.json`. Cached takes in `cache/tts/` are keyed by voice, so a new voice re-records.

## A batch
"Write 7 episodes" = 7 files in `inbox/`, spread across at least 3 locations, every character gets at least one punchline in the week,
no two episodes with the same joke mechanic. List the titles back to the user in a short table.
