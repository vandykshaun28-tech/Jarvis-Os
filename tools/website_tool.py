"""
website_tool.py — writes real files to real disk, then proves it.

The verification step is the whole point. Writing a file and returning
"done" is exactly the pattern that produced hallucinated work: the claim
and the outcome were never checked against each other.

So after every write this tool re-opens the file from disk, hashes the
bytes it finds there, and compares them to the bytes it meant to write.
The ToolResult reports the on-disk size, the SHA-256, and the absolute
path. If the file isn't there, or its contents differ, that's a failure —
even if the write() call itself raised nothing.

Anything that would destroy existing work (overwriting files, writing
outside the projects root) is gated behind a confirmation token.
"""

from __future__ import annotations

import hashlib
import html
import os
import re
import time
from datetime import datetime
from pathlib import Path

import config
from tool_result import ToolResult, Stopwatch

# Everything this tool writes lands under here. A path that escapes it
# is refused outright — no confirmation offered, because there is no
# good reason for a website builder to write to C:\Windows.
PROJECTS_ROOT = Path(getattr(config, "SITES_DIR",
                             Path(config.ROOT_DIR) / "sites")).resolve()

MAX_FILE_BYTES = 2_000_000


# ── safety ─────────────────────────────────────────────────────────

def _safe_slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "").strip()).strip("-.")
    return (slug or "site")[:64].lower()


def _resolve_in_root(rel: str) -> tuple[Path | None, str]:
    """Resolve a relative path inside PROJECTS_ROOT, or explain why not."""
    if not rel:
        return None, "no path given"
    if os.path.isabs(rel) or rel.startswith("~"):
        return None, f"absolute paths are refused ({rel})"
    candidate = (PROJECTS_ROOT / rel).resolve()
    try:
        candidate.relative_to(PROJECTS_ROOT)
    except ValueError:
        return None, (f"path escapes the projects folder: {rel} → "
                      f"{candidate}. Refused.")
    return candidate, ""


def _token_for(action: str, detail: str) -> str:
    raw = f"{action}|{detail}|{int(time.time() // 600)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:10]


def _write_and_verify(path: Path, text: str) -> dict:
    """Write, then read back from disk and hash. Returns evidence."""
    data = text.encode("utf-8")
    intended = hashlib.sha256(data).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())          # actually on disk, not just buffered

    if not path.exists():
        return {"ok": False, "path": str(path),
                "error": "file does not exist after write"}
    on_disk = path.read_bytes()
    actual = hashlib.sha256(on_disk).hexdigest()
    return {"ok": actual == intended and len(on_disk) == len(data),
            "path": str(path), "bytes": len(on_disk),
            "sha256": actual,
            "verified": actual == intended,
            "error": ("" if actual == intended else
                      f"hash mismatch: wrote {intended[:12]}, disk has "
                      f"{actual[:12]}")}


# ── page generation ────────────────────────────────────────────────

_CSS = """*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#050b12;--panel:#0c1a26;--line:#123048;--accent:#3dd8ff;
--text:#dff2ff;--dim:#8fb0c8}
body{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;
background:var(--bg);color:var(--text);line-height:1.6}
header{padding:64px 24px 40px;text-align:center;
background:radial-gradient(ellipse at 50% -20%,rgba(61,216,255,.18),transparent 60%);
border-bottom:1px solid var(--line)}
h1{font-size:clamp(28px,5vw,46px);letter-spacing:-.5px;margin-bottom:10px}
.tag{color:var(--accent);letter-spacing:3px;font-size:12px;font-weight:700;
text-transform:uppercase;margin-bottom:14px}
.sub{color:var(--dim);max-width:620px;margin:0 auto;font-size:17px}
.cta{display:inline-block;margin-top:26px;background:var(--accent);
color:#04141f;padding:13px 30px;border-radius:8px;text-decoration:none;
font-weight:700}
main{max-width:1000px;margin:0 auto;padding:56px 24px}
h2{font-size:24px;margin-bottom:8px}
.lead{color:var(--dim);margin-bottom:28px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));
gap:18px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
padding:22px}
.card h3{color:var(--accent);font-size:17px;margin-bottom:8px}
.card p{color:var(--dim);font-size:14px}
.card img{width:100%;height:170px;object-fit:cover;border-radius:9px;
margin-bottom:13px;display:block;background:#0a1622}
header.hashero{background-size:cover;background-position:center}
.credits{max-width:1000px;margin:0 auto;padding:0 24px 40px;color:#5f7d95;
font-size:12px}
.credits h3{color:var(--dim);font-size:12px;letter-spacing:2px;
margin-bottom:8px;text-transform:uppercase}
.credits ul{margin-left:16px}.credits a{color:var(--accent)}
footer{border-top:1px solid var(--line);padding:28px 24px;text-align:center;
color:#5f7d95;font-size:13px}
"""


# ── REAL PICTURES ──────────────────────────────────────────────────
# A site of pure text reads like a placeholder. Two free sources, and
# both are honest about what they are:
#
#   Openverse — real photographs, openly licensed, no API key. Every
#   image carries its creator and licence into the page footer, because
#   CC attribution is a condition of use, not a nicety.
#
#   Gemini — she already generates images free via draw_image. Good for
#   a hero/banner where a specific photo does not exist.
#
# NOT Higgsfield: it is an image-to-VIDEO generator, the API is paid per
# clip through a third-party gateway, and it needs a key. Wrong tool and
# a running cost. See the note in the reply to Shaun.

OPENVERSE = "https://api.openverse.org/v1/images/"


def find_photos(query, count=3, timeout=12):
    """Openly-licensed photographs for a topic. Returns [] on any
    failure — a site without photos is fine; a site claiming photos it
    could not fetch is not."""
    try:
        import httpx
    except Exception:
        return []
    try:
        r = httpx.get(OPENVERSE,
                      params={"q": query, "page_size": max(1, min(count, 8)),
                              "license_type": "commercial",
                              "mature": "false"},
                      headers={"User-Agent": "Allison/1.0 (personal assistant)"},
                      timeout=timeout)
        if r.status_code >= 400:
            return []
        out = []
        for it in (r.json().get("results") or []):
            url = it.get("url") or it.get("thumbnail")
            if not url:
                continue
            out.append({
                "url": url,
                "thumb": it.get("thumbnail") or url,
                "title": (it.get("title") or query)[:120],
                "creator": (it.get("creator") or "Unknown")[:80],
                "license": (it.get("license") or "").upper(),
                "license_url": it.get("license_url") or "",
                "source": it.get("foreign_landing_url") or "",
            })
        return out[:count]
    except Exception:
        return []


def _attribution_html(photos):
    if not photos:
        return ""
    rows = "".join(
        f'<li>{html.escape(p["title"])} — {html.escape(p["creator"])}'
        f' ({html.escape(p["license"] or "CC")})'
        + (f' · <a href="{html.escape(p["source"])}">source</a>'
           if p.get("source") else "")
        + "</li>"
        for p in photos)
    return ('<div class="credits"><h3>Image credits</h3><ul>'
            + rows + "</ul></div>")


def _page(title, tagline, intro, sections, cta, lead="",
          photos=None, hero="") -> str:
    # `lead` used to be the hardcoded string 'Built for <title>.',
    # which read as placeholder text on a real business site
    # because that is exactly what it was. Now it is either real
    # content or omitted entirely.
    e = html.escape
    photos = photos or []
    # one photo per card, in order, so the pictures sit next to the
    # copy they belong to rather than in a decorative strip
    cards = "\n".join(
        '      <div class="card">'
        + (f'<img src="{e(photos[i]["thumb"])}" alt="{e(photos[i]["title"])}" '
           f'loading="lazy">' if i < len(photos) else "")
        + f'<h3>{e(str(sec.get("heading", "")))}</h3>'
          f'<p>{e(str(sec.get("body", "")))}</p></div>'
        for i, sec in enumerate(sections))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header{' class="hashero"' if hero else ''}{f' style="background-image:linear-gradient(rgba(5,11,18,.78),rgba(5,11,18,.94)),url({hero})"' if hero else ''}>
  <div class="tag">{e(tagline)}</div>
  <h1>{e(title)}</h1>
  <p class="sub">{e(intro)}</p>
  {f'<a class="cta" href="#contact">{e(cta)}</a>' if cta else ''}
</header>
<main>
  <h2>What we do</h2>
  {f'<p class="lead">{e(lead)}</p>' if lead else ''}
  <div class="grid">
{cards}
  </div>
</main>
{_attribution_html(photos)}
<footer id="contact">
  {e(title)} · built by Allison on {datetime.now():%d %B %Y}
</footer>
</body>
</html>
"""


# ── the tool ───────────────────────────────────────────────────────

# ── ASK BEFORE BUILDING ────────────────────────────────────────────
# Shaun: "its not asking for details to go with it its just adding in
# random stuff". Right. A real designer asks what the business is
# called, what it sells, and how to contact it BEFORE building. Guessing
# and calling it a website is the same disease as guessing and calling
# it a tool result.

_QUESTION_SYS = (
    "You are a web designer taking a brief. Ask the FEWEST questions you "
    "need to build a site that is actually about this business, not a "
    "template. Reply with ONLY JSON:\n"
    '{"questions": ["...", "..."]}\n'
    "RULES:\n"
    "- 3 to 5 questions, each one short and concrete.\n"
    "- Ask about things you CANNOT know: business/trading name, contact "
    "details, area served, what he most wants to sell, prices or lead "
    "times if relevant, anything he wants shown.\n"
    "- Do NOT ask about things already in the owner briefing.\n"
    "- Never ask vague questions like 'what is your vision'.")


def website_questions(brief, about, think) -> list:
    """The questions to put to him before anything is built."""
    who = f"\n\nAlready known about the owner:\n{about}" if about else ""
    raw = think(_QUESTION_SYS, f"He asked for: {brief}{who}")
    data = _extract_json(raw) or {}
    qs = [str(q).strip() for q in (data.get("questions") or [])
          if str(q).strip()][:5]
    if not qs:
        # never block on a parsing failure — fall back to the essentials
        qs = ["What is the business called?",
              "How should customers contact you (phone, email, WhatsApp)?",
              "Which area do you serve?",
              "What do you most want the site to sell?"]
    return qs


def _clean_title(t: str, fallback: str = "") -> str:
    """Strip the echoed noun off a title.

    The planner was handed "make me a website for turbo fitment" and
    dutifully titled the page "Turbo Fitting and Engine Conversions
    Website". Nobody names their business "… Website".
    """
    t = re.sub(r"\s*\b(web\s?site|website|web\s?page|webpage|site|page|"
               r"landing\s?page|homepage|home\s?page)\b\s*$", "",
               str(t or "").strip(), flags=re.I).strip(" -–—:|")
    return t or fallback


def _plan_and_write(brief, ctx, think, progress):
    """Plan the site AND write every section, in ONE call.

    THE MISTAKE THIS FIXES: making it "thorough" meant 1 planning call
    plus one call per section — six or more round trips fired back to
    back. On a free tier that is the fastest possible way to hit a rate
    limit, and it did: "groq: HTTP 429 after retries" while Gemini was
    down on a stale model name, so every brain failed and Shaun got
    nothing at all. Depth that costs you the whole feature is not depth.

    One well-specified call asks for the same content. Per-section
    refinement still exists behind deep=True for when there is headroom.
    """
    if progress:
        progress("① Designing the site and writing the copy…")
    sys_p = (
        "You are a web designer AND copywriter building a real small "
        "business site. Reply with ONLY JSON, no prose, no code fence:\n"
        '{"title": "...", "tagline": "SHORT ALL-CAPS", '
        '"intro": "1-2 sentences", "cta": "button text", '
        '"photo_topic": "2-4 words describing the photos this site needs", '
        '"sections": [{"heading": "...", "body": "2-3 sentences"}]}\n'
        "RULES:\n"
        "- 4 to 6 sections, each with REAL body copy, not a placeholder.\n"
        "- The title is the business name or what it does. Never put "
        "'Website', 'Page' or 'Site' in it.\n"
        "- Use the owner's real trade, materials, processes and location. "
        "Name specific things he actually works on.\n"
        "- BANNED, they say nothing: 'high-performance', 'skilled "
        "technicians', 'full potential', 'state of the art', "
        "'passionate about', 'tailored solutions'.\n"
        "- Invent NOTHING: no testimonials, prices, years in business, "
        "staff numbers or awards. If you were not told it, leave it out.")
    plan = _extract_json(think(sys_p, f"Build a site for: {brief}\n\n{ctx}"))
    if not isinstance(plan, dict) or not plan.get("sections"):
        raise ValueError(f"planner returned nothing usable: "
                         f"{str(plan)[:160]}")
    return plan


def _plan_site(brief, think, progress, about=""):
    """Stage 1 — decide what the site should actually contain.

    This is the stage that was missing. A one-shot "write me some HTML"
    call returns a title and a paragraph in about a second, because that
    is all it was asked for. Planning first means the copy stage has
    something real to write against, and the extra seconds buy content
    rather than the appearance of effort.
    """
    if progress:
        progress("① Planning the site — working out what it needs…")
    sys_p = ("You are a web designer planning a real small business site. "
             "Reply with ONLY a JSON object, no prose, no code fence:\n"
             '{"title": "...", "tagline": "SHORT ALL-CAPS PHRASE", '
             '"intro": "one or two sentences", '
             '"cta": "button text", '
             '"sections": [{"heading": "...", "angle": "what this section '
             'should say, one line"}]}\n'
             "RULES:\n"
             "- 4 to 6 sections.\n"
             "- The title is the BUSINESS name or what it does. Never put "
             "the word 'Website', 'Page' or 'Site' in the title.\n"
             "- Use the owner's REAL trade, engines, parts and location "
             "from the briefing. Name specific things he actually works "
             "on. Generic phrases like 'high-performance vehicles', "
             "'skilled technicians' or 'full potential' are failures.\n"
             "- Do NOT invent testimonials, galleries, awards, years in "
             "business, prices or staff counts. Only plan sections whose "
             "content can be written truthfully from the briefing.")
    who = f"\n\nABOUT THE OWNER — use this, it is true:\n{about}" if about else ""
    raw = think(sys_p, f"Plan a website for: {brief}{who}")
    plan = _extract_json(raw)
    if not isinstance(plan, dict) or not plan.get("sections"):
        raise ValueError(f"planner returned nothing usable: {str(raw)[:200]}")
    return plan


def _write_section(sec, brief, think, progress, i, total, about=""):
    """Stage 2 — real copy per section, one call each.

    One call per section rather than one call for the whole page. It is
    slower on purpose: each section gets the model's full attention
    instead of a sentence apiece from a single rushed generation.
    """
    heading = str(sec.get("heading", f"Section {i}"))[:80]
    if progress:
        progress(f"② Writing copy {i}/{total} — “{heading}”…")
    sys_p = ("You write short, concrete website copy for a real business. "
             "2-3 sentences. Plain confident English. Name the actual "
             "engines, parts, processes and places from the briefing — "
             "specifics are the whole point. BANNED because they say "
             "nothing: 'high-performance vehicles', 'skilled technicians', "
             "'full potential', 'state of the art', 'passionate about'. "
             "Never invent testimonials, prices, years in business or "
             "customer numbers. No lists, no headings, no surrounding "
             "quotes. Reply with the copy ONLY.")
    who = f"\nAbout the owner (true, use it):\n{about}" if about else ""
    try:
        body = think(sys_p,
                     f"Business: {brief}{who}\nSection heading: {heading}\n"
                     f"This section should say: {sec.get('angle', heading)}")
    except Exception as e:
        body = ""
        if progress:
            progress(f"   (copy for “{heading}” failed: {e} — "
                     f"keeping the section, leaving it blank)")
    return {"heading": heading, "body": str(body).strip().strip('"')[:600]}


def _extract_json(raw):
    """Pull a JSON object out of a model reply that may be wrapped."""
    import json as _json
    t = str(raw or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"```\s*$", "", t).strip()
    try:
        return _json.loads(t)
    except Exception:
        pass
    depth, start = 0, -1
    for i, ch in enumerate(t):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return _json.loads(t[start:i + 1])
                except Exception:
                    start = -1
    return None


def website_build(name: str,
                  title: str = "",
                  tagline: str = "",
                  intro: str = "",
                  sections: list | None = None,
                  cta: str = "Get in touch",
                  confirm: str = "",
                  brief: str = "",
                  about: str = "",
                  details: str = "",
                  skip_questions: bool = False,
                  with_photos: bool = True,
                  photo_topic: str = "",
                  deep: bool = False,
                  think=None,
                  progress=None) -> ToolResult:
    """Build a real static site on disk and verify every byte.

    If `think` (an LLM callable) and `brief` are supplied, the build runs
    as a genuine multi-stage job — plan, then write each section's copy
    in its own pass, then build, then verify — reporting progress as it
    goes. That takes tens of seconds instead of one, because it is doing
    several times more work, not because it is padded with sleeps.

    Without `think` it falls back to the original single-pass build, so
    the selftest and any direct caller still work.

    Overwriting an existing site requires confirmation.
    """
    tool = "website_build"
    slug = _safe_slug(name or title)
    if not slug:
        return ToolResult.failure(tool, "a site name is required")

    folder, why = _resolve_in_root(slug)
    if folder is None:
        return ToolResult.failure(tool, why)

    sections = sections or []
    if isinstance(sections, str):
        sections = [{"heading": s.strip(), "body": ""}
                    for s in sections.split(",") if s.strip()]
    sections = [s for s in sections if isinstance(s, dict)][:12]

    # ── ASK FIRST ────────────────────────────────────────────────────
    # Nothing is written until he has answered, unless he explicitly
    # waived the questions or already supplied details.
    if think and not details and not skip_questions:
        try:
            qs = website_questions(brief or name, about, think)
            numbered = "\n".join(f"  {i}. {q}" for i, q in enumerate(qs, 1))
            return ToolResult(
                tool=tool, ok=False, needs_confirmation=True,
                confirm_token="answers",
                confirm_prompt=(
                    f"Before I build it, {len(qs)} things I need from you "
                    f"so this is YOUR site and not a template:\n{numbered}\n\n"
                    f"Answer in one message and I'll build it. Or say "
                    f"'just build it' and I'll use what I already know "
                    f"about you."),
                summary=f"asked {len(qs)} question(s) before building",
                data={"questions": qs, "asked": True, "wrote_nothing": True})
        except Exception as e:
            if progress:
                progress(f"   (couldn't draft questions: {e} — building "
                         f"from what I know)")

    # ── THOROUGH PATH ────────────────────────────────────────────────
    # Plan first, then write each section in its own pass. Slower
    # because it is more work: 1 planning call + N copy calls, each
    # reported as it happens, instead of one blob generated in a second.
    stages = ["single-pass"]
    if think and (brief or name):
        stages = []
        try:
            _ctx = about + (f"\n\nHIS ANSWERS — use these, they are"
                            f" the most important input:\n{details}"
                            if details else "")
            # ONE call by default (see _plan_and_write). deep=True
            # restores the per-section pass for when rate limits allow.
            plan = (_plan_site(brief or name, think, progress, _ctx)
                    if deep else
                    _plan_and_write(brief or name, _ctx, think, progress))
            stages.append("planned+written in one call" if not deep
                          else "planned")
            title    = title   or _clean_title(
                str(plan.get("title") or name), name)[:120]
            tagline  = tagline or str(plan.get("tagline") or "")[:60]
            intro    = intro   or str(plan.get("intro") or "")[:400]
            cta      = str(plan.get("cta") or cta)[:40]
            planned  = [s for s in (plan.get("sections") or [])
                        if isinstance(s, dict)][:6]
            photo_topic = photo_topic or str(plan.get("photo_topic") or "")

            if deep:
                written = []
                for i, sec in enumerate(planned, 1):
                    written.append(_write_section(sec, brief or name, think,
                                                  progress, i, len(planned),
                                                  _ctx))
                    time.sleep(0.4)      # be kind to free-tier limits
                sections = written or sections
                stages.append(f"refined {len(written)} section(s) separately")
            else:
                sections = [{"heading": str(x.get("heading", ""))[:80],
                             "body": str(x.get("body", ""))[:600]}
                            for x in planned] or sections
                stages.append(f"{len(sections)} section(s) in one call")
        except Exception as e:
            # Do NOT silently fall back to the shallow build and let it
            # look like the thorough one ran. Say which path produced
            # this site.
            if progress:
                progress(f"   (planning failed: {e} — falling back to a "
                         f"basic single-pass build)")
            stages.append(f"planning FAILED ({str(e)[:80]}), fell back to "
                          f"single-pass")

    title   = (title or name or slug).strip()
    tagline = (tagline or "").strip()
    intro   = (intro or "").strip()

    # ── pictures ─────────────────────────────────────────────────────
    photos, hero = [], ""
    if with_photos:
        if progress:
            progress("③ Finding real photographs…")
        topic = (photo_topic or brief or title or name)
        photos = find_photos(topic, count=max(2, len(sections)))
        if progress:
            progress(f"   {len(photos)} openly-licensed photo(s) found"
                     if photos else
                     "   no photos found (offline, or nothing suitable) — "
                     "building without them rather than faking it")
        if photos:
            hero = photos[0]["url"]

    if progress:
        progress("④ Building the files…")
    files = {"index.html": _page(title, tagline, intro, sections, cta,
                                 lead=intro if len(sections) else "",
                                 photos=photos, hero=hero),
             "style.css": _CSS}

    oversized = [n for n, c in files.items()
                 if len(c.encode()) > MAX_FILE_BYTES]
    if oversized:
        return ToolResult.failure(tool, f"generated files too large: {oversized}")

    # CONFIRMATION GATE — only when real work would be destroyed
    existing = [n for n in files if (folder / n).exists()]
    if existing:
        want = _token_for("overwrite", f"{folder}:{sorted(existing)}")
        if confirm != want:
            return ToolResult.confirm(
                tool,
                f"{len(existing)} file(s) already exist in {folder} "
                f"({', '.join(existing)}). Overwrite them? The current "
                f"contents will be lost.",
                want,
                data={"folder": str(folder), "would_overwrite": existing})

    with Stopwatch() as sw:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            evidence = {n: _write_and_verify(folder / n, c)
                        for n, c in files.items()}
        except Exception as e:
            return ToolResult.from_exception(tool, e,
                                             duration_ms=sw.elapsed_ms)

    if progress:
        progress("⑤ Verifying every byte on disk…")

    bad = {n: ev for n, ev in evidence.items() if not ev["ok"]}
    if bad:
        return ToolResult.failure(
            tool,
            "wrote files but verification FAILED for: "
            + ", ".join(f"{n} ({ev.get('error')})" for n, ev in bad.items()),
            duration_ms=sw.elapsed_ms, data={"evidence": evidence})

    total = sum(ev["bytes"] for ev in evidence.values())
    listing = "\n".join(
        f"  {n:<12} {ev['bytes']:>7} bytes  sha256:{ev['sha256'][:16]}…"
        for n, ev in sorted(evidence.items()))
    words = sum(len(str(s.get("body", "")).split()) for s in sections)

    if progress:
        progress(f"⑥ Done — {len(sections)} section(s), {words} words, "
                 f"{len(photos)} photo(s), {total} bytes verified.")

    return ToolResult.success(
        tool,
        f"wrote and verified {len(files)} file(s), {total} bytes total, "
        f"{len(sections)} section(s) and {words} words of real copy, "
        f"in {folder}. Build path: {'; '.join(stages)}.",
        duration_ms=sw.elapsed_ms,
        stdout=f"{folder}\n{listing}",
        data={"folder": str(folder), "open_with": str(folder / 'index.html'),
              "file_count": len(files), "total_bytes": total,
              "section_count": len(sections), "word_count": words,
              "photo_count": len(photos),
              "photos": [{"title": p["title"], "creator": p["creator"],
                          "license": p["license"]} for p in photos],
              "build_path": stages,
              "files": {n: {"bytes": ev["bytes"], "sha256": ev["sha256"],
                            "verified": ev["verified"]}
                        for n, ev in evidence.items()}})


def website_list() -> ToolResult:
    """What has actually been built, read from disk."""
    tool = "website_list"
    try:
        PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
        sites = []
        for d in sorted(PROJECTS_ROOT.iterdir()):
            if not d.is_dir():
                continue
            fs = [f for f in d.rglob("*") if f.is_file()]
            sites.append({"name": d.name, "files": len(fs),
                          "bytes": sum(f.stat().st_size for f in fs),
                          "modified": datetime.fromtimestamp(
                              d.stat().st_mtime).isoformat(timespec="seconds"),
                          "path": str(d)})
    except Exception as e:
        return ToolResult.from_exception(tool, e)
    return ToolResult.success(
        tool, f"{len(sites)} site(s) in {PROJECTS_ROOT}",
        data={"root": str(PROJECTS_ROOT), "sites": sites})


def selftest() -> ToolResult:
    """Build a real site, verify it, prove the confirmation gate works."""
    global PROJECTS_ROOT
    out = ["=" * 62,
           "WEBSITE TOOL SELFTEST — real files, verified on disk",
           "=" * 62,
           f"projects root: {PROJECTS_ROOT}",
           f"run at       : {datetime.now().isoformat(timespec='seconds')}",
           ""]
    name = "allison-selftest"
    passed = 0

    # A test that only passes on a clean machine is a test that lies the
    # second time you run it. Check 1 asserts "folder is new", so make
    # that true rather than assuming it — otherwise the confirmation gate
    # (correctly) blocks the build and check 1 fails on every re-run.
    try:
        import shutil
        prior = PROJECTS_ROOT / _safe_slug(name)
        if prior.exists():
            shutil.rmtree(prior)
            out.append(f"(cleared previous run: {prior})")
            out.append("")
    except Exception as e:
        out.append(f"(could not clear previous run: {e})")
        out.append("")

    out.append("-" * 62)
    out.append("▶ 1. first build (folder is new — should just write)")
    r1 = website_build(
        name=name, title="Allison Selftest",
        tagline="proof of execution", intro="Written and verified on disk.",
        sections=[{"heading": "Real write", "body": "fsync'd to disk."},
                  {"heading": "Verified", "body": "Re-read and hashed."}])
    out.append(f"  ok      : {r1.ok}")
    out.append(f"  summary : {r1.summary}")
    if r1.stdout:
        out.extend("  " + ln for ln in r1.stdout.splitlines())
    passed += 1 if r1.ok else 0

    out.append("-" * 62)
    out.append("▶ 2. rebuild over existing files (must REFUSE and ask)")
    r2 = website_build(name=name, title="Allison Selftest")
    gate_ok = r2.needs_confirmation and not r2.ok
    out.append(f"  needs_confirmation : {r2.needs_confirmation}")
    out.append(f"  ok                 : {r2.ok}  (must be False)")
    out.append(f"  prompt             : {r2.confirm_prompt[:120]}")
    out.append(f"  GATE HELD          : {gate_ok}")
    passed += 1 if gate_ok else 0

    out.append("-" * 62)
    out.append("▶ 3. same call WITH the token (should now write)")
    r3 = website_build(name=name, title="Allison Selftest Confirmed",
                       confirm=r2.confirm_token)
    out.append(f"  ok      : {r3.ok}")
    out.append(f"  summary : {r3.summary}")
    passed += 1 if r3.ok else 0

    out.append("-" * 62)
    out.append("▶ 4. path traversal (nothing may land outside the root)")
    # The invariant that matters is CONTAINMENT, not which layer enforces
    # it. Two defences exist: _safe_slug flattens separators, and
    # _resolve_in_root refuses anything that still escapes. Test both,
    # and test the outcome rather than the mechanism.
    evil = "../../../etc/allison-escape"
    out.append(f"  slug({evil!r}) → {_safe_slug(evil)!r}  (separators flattened)")
    r4 = website_build(name=evil, title="nope")
    written = Path(r4.data.get("folder", "")) if r4.data.get("folder") else None
    contained = True
    if written:
        try:
            written.resolve().relative_to(PROJECTS_ROOT)
        except ValueError:
            contained = False
    out.append(f"  wrote to : {written}")
    out.append(f"  CONTAINED: {contained}  (must be True)")
    # second defence, exercised directly
    p, why = _resolve_in_root("../../../etc/passwd")
    direct_refused = p is None
    out.append(f"  _resolve_in_root('../../../etc/passwd') → refused="
               f"{direct_refused} ({why[:70]})")
    ok4 = contained and direct_refused
    passed += 1 if ok4 else 0
    # don't leave test litter in the real sites folder
    try:
        import shutil
        if written and written.exists() and written.name == "etc-allison-escape":
            shutil.rmtree(written)
            out.append(f"  cleaned up: {written}")
    except Exception:
        pass

    out.append("-" * 62)
    out.append("▶ 5. failure is reported as failure (unwritable path)")
    # point the root at something that cannot be written, and confirm we
    # get ok=False rather than a cheerful lie
    import tempfile
    saved = PROJECTS_ROOT
    try:
        blocker = Path(tempfile.mkdtemp()) / "blocked"
        blocker.write_text("i am a file, not a directory")
        PROJECTS_ROOT = blocker.resolve()
        r5 = website_build(name="cannot-work", title="x")
        honest = not r5.ok
        out.append(f"  ok       : {r5.ok}  (must be False)")
        out.append(f"  error    : {(r5.error or r5.summary)[:130]}")
        out.append(f"  HONEST   : {honest}")
        passed += 1 if honest else 0
    finally:
        PROJECTS_ROOT = saved

    out.append("-" * 62)
    out.append(f"RESULT: {passed}/5 checks passed.")
    return ToolResult(tool="website_selftest", ok=passed == 5,
                      summary=f"{passed}/5 checks passed",
                      stdout="\n".join(out),
                      error="" if passed == 5 else "one or more checks failed")


if __name__ == "__main__":
    print(selftest().stdout)
