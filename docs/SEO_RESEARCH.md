# Autoreels SEO research (2026-10-18)

Sources: vidIQ keyword research (country IN), YouTube autocomplete (hl=hi, gl=IN), YouTube Data API search of the top 40
Hindi cartoon comedy Shorts published in the last 60 days (region IN, most viewed; median 6.6M views), vidIQ title scores.

## Keywords (estimated monthly searches, India-heavy)
| Phrase | Searches | Competition | Use |
|---|---|---|---|
| cartoon video | 770K | 39 | tag |
| hindi kahani | 368K | 48 | description wording ("Hindi cartoon kahani") |
| funny cartoon | 204K | 49 | tag, title phrase "Funny Cartoon Video" |
| hindi cartoon | 183K | 55 | tag, title phrase "Funny Hindi Cartoon" |
| cartoon in hindi | 53K | 54 | tag |
| hindi kahani cartoon | 16K | 41 | tag |
| cartoon comedy video | 12.7K, +40% | 49 | title phrase |
| desi comedy / indian school funny / school comedy | 4–5K | 42–49 | title phrases per location |
| Autocomplete only | — | — | "diwali comedy cartoon", "school comedy cartoon", "पप्पू की कॉमेडी", "कार्टून कॉमेडी", "देसी कॉमेडी वीडियो" |

Avoided on purpose: kids terms ("kids video", "funny cartoon for kids", nursery rhymes) because the channel is not made for kids,
and other creators' names (hardtoonz, motu patlu, titoo, cs bisht, chintu…), which break YouTube's misleading-metadata policy.

## What the top Shorts do
- Title: a short Hinglish hook with an emoji, then a keyword phrase. Example: "Alarm Ka Badla 😂⏰ | Funny Cartoon Short". Median 80 characters.
- 27 of 40 put hashtags in the title (#cartoon, #comedy, #shorts); 19 of 40 use emoji; only 8 of 40 use Devanagari in the title.
- Description: median 846 characters, about 10 hashtags. Tags: median 5, and 16 of 40 use none (tags are a weak signal).

## vidIQ title scores (Shorts)
| Title | Score |
|---|---|
| Golu ka Lunch Break toot gaya? | 73 |
| Golu ka Lunch Break toot gaya? 😂 \| Funny Hindi Cartoon | 69 |
| ₹100 Mein Poori Diwali Shopping? 😂 Pappu Ka Jugaad \| Hindi Cartoon Comedy | 61 |
| Pappu ka Diwali Budget Sirf ₹100 😂 \| Funny Cartoon Comedy #cartoon | 56 |
| Pappu ka Diwali Budget: Sau Rupaye Mein Sab Kuch! (old style) | 55 |

A short curiosity question with a character name wins; a keyword suffix costs about 4 points but targets searches with 100K+ volume.

## The formula now built into toon/seo.py
- **Title:** `<hook ≤45 chars, character name, one emoji> | <keyword phrase> #cartoon`. Claude writes 4 hooks, plain rules rank them,
  vidIQ scores the best 2, the winner is used. The keyword phrase follows the festival or season (Diwali, Holi, exams, cricket, shaadi…) or the location.
- **Description:** the first ~150 characters hold the hook, the story and the keyword phrase plus a Devanagari keyword. Then the cast and location,
  the viewer question, the footer, and hashtags with the first three (#cartoon #comedy #Autoreels) shown above the title.
- **Tags:** the exact target phrase first, then episode tags, core volume tags, two Devanagari tags, the channel name, the characters, and up to a few
  filtered vidIQ suggestions. At most 18 tags, under 480 characters.
- **Captions:** Hindi (Devanagari) captions with the exact spoken timings are uploaded with every video. Manual captions are indexed for Search.
- Keyword lists live in `data/keywords.json`; edit them freely.

## Measurement plan
After about 10 videos with the new metadata (3–4 days), compare in YouTube Studio → Analytics → Content → Shorts:
- **Shown in feed vs swiped away**: the hook's job. Aim for 70% or more viewed vs swiped away.
- **Traffic source "YouTube search"**: the keyword phrase's job. Expect it to grow from 0 to 3–8% of views.
- Record which keyword phrase each video used (`meta.json` → `seo.keyword`) and drop phrases that bring no search traffic after 2 weeks.
