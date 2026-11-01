"""YouTube Analytics learning loop.

Once a day the autopilot reads, for every Autoreels video that has been public for 2+ days (YouTube Analytics lags ~48 h):
views, average % viewed, likes, comments, shares, subscribers gained, and where the views came from (Shorts feed, search,
browse...). It joins that with what the factory knows about each video (keyword phrase, location, who had the punchline,
hook style) and writes data/learnings.json:

  * seo.keyword_phrase prefers the phrases that actually bring search views,
  * writer.pick_idea prefers locations that hold viewers,
  * the episode writer is shown the best and worst hooks so far.

Nothing is applied until a group has at least MIN_N videos, so a few lucky videos cannot steer the channel.
`python main.py analytics` prints the report.
"""
import datetime as dt
import json
import logging
import statistics as st

from . import config, store

log = logging.getLogger("toon.analytics")
PATH = config.DATA / "learnings.json"
MIN_N = 3
METRICS = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,shares,subscribersGained"


def _services():
    from googleapiclient.discovery import build
    from . import youtube
    creds = youtube._credentials()
    return build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)


def _videos() -> list:
    """Episode jobs that are on YouTube and public for at least two days, with what the factory knows about them."""
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for jid, j in store.jobs().items():
        vid = j.get("video_id")
        if not vid or j.get("kind") == "trailer":
            continue
        pub = j.get("publish_at")
        when = dt.datetime.fromisoformat(pub) if pub else dt.datetime.fromisoformat(j.get("updated", j.get("created"))).replace(tzinfo=dt.timezone.utc)
        if j.get("privacy") == "private" and not pub:
            continue
        if now - when.astimezone(dt.timezone.utc) < dt.timedelta(days=2):
            continue
        d = config.OUTPUT / jid
        try:
            ep = json.loads((d / "episode.json").read_text(encoding="utf-8"))
            meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        seo = meta.get("seo", {})
        out.append({"job": jid, "video_id": vid, "title": meta.get("title", ""), "hook": seo.get("hook", ep.get("title", "")),
                    "keyword": seo.get("keyword", ""), "location": ep.get("location"), "closer": ep["lines"][-1]["who"],
                    "lines": len(ep["lines"]), "duration": j.get("duration"), "published": when.date().isoformat(),
                    "question_hook": "?" in seo.get("hook", ep.get("title", ""))})
    return out


def fetch() -> list:
    vids = _videos()
    if not vids:
        return []
    ya = _services()
    start = min(v["published"] for v in vids)
    end = dt.date.today().isoformat()
    by_id = {v["video_id"]: v for v in vids}
    ids = list(by_id)
    for i in range(0, len(ids), 200):
        r = ya.reports().query(ids="channel==MINE", startDate=start, endDate=end, metrics=METRICS, dimensions="video",
                               filters="video==" + ",".join(ids[i:i + 200]), maxResults=200).execute()
        cols = [h["name"] for h in r.get("columnHeaders", [])]
        for row in r.get("rows", []):
            rec = dict(zip(cols, row))
            by_id[rec["video"]].update({k: rec[k] for k in cols if k != "video"})
    for v in vids:
        if not v.get("views"):
            continue
        try:  # where the views came from
            r = ya.reports().query(ids="channel==MINE", startDate=start, endDate=end, metrics="views",
                                   dimensions="insightTrafficSourceType", filters=f"video=={v['video_id']}").execute()
            src = {row[0]: row[1] for row in r.get("rows", [])}
        except Exception as e:
            log.warning("traffic sources for %s: %s", v["video_id"], str(e)[:120])
            src = {}
        total = sum(src.values()) or 1
        v["sources"] = src
        v["search_share"] = round(100 * src.get("YT_SEARCH", 0) / total, 1)
    return vids


def _group(vids: list, key: str) -> dict:
    groups = {}
    for v in vids:
        if v.get("views") is None:
            continue
        groups.setdefault(str(v.get(key)), []).append(v)
    out = {}
    for k, vs in groups.items():
        out[k] = {"n": len(vs), "views": round(st.mean(x["views"] for x in vs)),
                  "view_pct": round(st.mean(x.get("averageViewPercentage", 0) for x in vs), 1),
                  "search_share": round(st.mean(x.get("search_share", 0) for x in vs), 1),
                  "likes_per_1k": round(1000 * sum(x.get("likes", 0) for x in vs) / max(1, sum(x["views"] for x in vs)), 1)}
    return out


def update() -> dict:
    vids = fetch()
    measured = [v for v in vids if v.get("views") is not None]
    ranked = sorted(measured, key=lambda v: (v.get("averageViewPercentage", 0), v["views"]), reverse=True)
    data = {
        "updated": dt.datetime.now().isoformat(timespec="minutes"),
        "videos": measured,
        "by_keyword": _group(measured, "keyword"),
        "by_location": _group(measured, "location"),
        "by_closer": _group(measured, "closer"),
        "by_question_hook": _group(measured, "question_hook"),
        "best_hooks": [v["hook"] for v in ranked[:5]],
        "worst_hooks": [v["hook"] for v in ranked[-3:]] if len(ranked) >= 8 else [],
    }
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("analytics: %d videos measured", len(measured))
    return data


def load() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def due(hours: int = 20) -> bool:
    d = load()
    if not d.get("updated"):
        return True
    return dt.datetime.now() - dt.datetime.fromisoformat(d["updated"]) > dt.timedelta(hours=hours)


# ======================================================================= what the rest of the factory asks
def weight(group: str, key: str, metric: str) -> float:
    """A multiplier around 1.0 for this group value (e.g. location 'school' by view_pct). 1.0 until there are MIN_N videos."""
    g = load().get(group, {})
    rows = [r for r in g.values() if r["n"] >= MIN_N]
    me = g.get(key)
    if not me or me["n"] < MIN_N or len(rows) < 2:
        return 1.0
    avg = st.mean(r[metric] for r in rows) or 1.0
    return max(0.5, min(2.0, (me[metric] or 0.01) / avg))


def writer_notes() -> str:
    d = load()
    if len(d.get("videos", [])) < 5:
        return ""
    notes = []
    if d.get("best_hooks"):
        notes.append("Titles of our best performing episodes (most watched to the end): " + " / ".join(d["best_hooks"][:3]))
    if d.get("worst_hooks"):
        notes.append("Titles that viewers swiped away from: " + " / ".join(d["worst_hooks"]))
    best_closer = max(((k, v) for k, v in d.get("by_closer", {}).items() if v["n"] >= MIN_N), key=lambda kv: kv[1]["view_pct"], default=None)
    if best_closer:
        notes.append(f"Episodes where {best_closer[0]} lands the punchline are watched furthest ({best_closer[1]['view_pct']}%).")
    return "\n".join(notes)


def report() -> str:
    d = load()
    if not d:
        return "No analytics yet. Run: python main.py analytics --update  (videos need to be public for 2 days)."
    lines = [f"Analytics updated {d['updated']}: {len(d['videos'])} videos measured", ""]
    for v in sorted(d["videos"], key=lambda v: -v["views"]):
        lines.append(f"{v['views']:>7} views  {v.get('averageViewPercentage', 0):>5.1f}% viewed  {v.get('search_share', 0):>4}% search  "
                     f"{v.get('likes', 0):>4} likes  {v.get('subscribersGained', 0):>3} subs  | {v['title'][:60]}")
    for name in ("by_keyword", "by_location", "by_closer"):
        if d.get(name):
            lines += ["", name.replace("by_", "By ").replace("_", " ") + ":"]
            for k, r in sorted(d[name].items(), key=lambda kv: -kv[1]["view_pct"]):
                lines.append(f"  {k:28} n={r['n']:<3} {r['views']:>7} avg views  {r['view_pct']:>5}% viewed  {r['search_share']:>4}% search")
    return "\n".join(lines)
