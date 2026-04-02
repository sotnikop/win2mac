#!/usr/bin/env python3
"""
online_lookup.py
For every app still in the REVIEW bucket, queries:
  1. DuckDuckGo Instant Answer API (no key required)
  2. Wikipedia REST API (no key required)

Attempts to auto-classify each app as:
  MAC_AVAILABLE  - description mentions macOS / Mac
  WINDOWS_ONLY   - description mentions Windows but not macOS
  GAME           - Wikipedia type is VideoGame, or description mentions "video game"
  UNKNOWN        - couldn't determine

Outputs:
  ~/Documents/mac-migration/online_lookup_results.csv  (machine-readable)
  ~/Documents/mac-migration/online_lookup_report.md    (human-readable, sorted by verdict)

Usage:
  python online_lookup.py               # process all REVIEW items
  python online_lookup.py --limit 50    # process first 50 (for a quick test)
  python online_lookup.py --resume      # skip already-cached entries
"""

import csv, json, pathlib, re, sys, time, urllib.request, urllib.parse, urllib.error
import argparse
from datetime import date

BASE       = pathlib.Path.home() / "Documents" / "mac-migration"
CACHE_FILE = BASE / "online_lookup_cache.json"   # persists between runs
RESULT_CSV = BASE / "online_lookup_results.csv"
REPORT_MD  = BASE / "online_lookup_report.md"

RATE_LIMIT_SEC = 1.2   # pause between requests to be polite


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _get(url: str, timeout: int = 10) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "mac-migration-lookup/1.0 (personal tool)",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# DuckDuckGo Instant Answer
# ---------------------------------------------------------------------------

DDG_URL = "https://api.duckduckgo.com/?q={q}&format=json&no_html=1&skip_disambig=1"

def ddg_lookup(name: str) -> dict:
    """Returns dict with keys: abstract, abstract_type, abstract_source, url"""
    q   = urllib.parse.quote_plus(name + " software")
    data = _get(DDG_URL.format(q=q))
    if not data:
        return {}
    return {
        "abstract":        data.get("AbstractText", ""),
        "abstract_type":   data.get("Type", ""),
        "abstract_source": data.get("AbstractSource", ""),
        "url":             data.get("AbstractURL", ""),
    }


# ---------------------------------------------------------------------------
# Wikipedia REST summary
# ---------------------------------------------------------------------------

WIKI_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"

def wiki_lookup(name: str) -> dict:
    """Try exact title, then URL-encoded."""
    title = urllib.parse.quote(name.replace(" ", "_"))
    data  = _get(WIKI_URL.format(title=title))
    if not data or data.get("type") == "https://mediawiki.org/wiki/HyperSwitch/errors/not_found":
        return {}
    return {
        "extract":    data.get("extract", ""),
        "type":       data.get("type", ""),        # "standard" | "disambiguation" | …
        "categories": "",                          # not in REST summary endpoint
        "page_url":   data.get("content_urls", {}).get("desktop", {}).get("page", ""),
    }


# ---------------------------------------------------------------------------
# Classification from fetched text
# ---------------------------------------------------------------------------

_MAC_RE  = re.compile(r"\bmac(os|os x| os)?\b|\bapple mac\b", re.IGNORECASE)
_WIN_RE  = re.compile(r"\bwindows\b|\bwin32\b|\bwinnt\b", re.IGNORECASE)
_GAME_RE = re.compile(
    r"\bvideo game\b|\bpc game\b|\bcomputer game\b|\bstrategy game\b"
    r"|\brole.playing game\b|\bfirst-person shooter\b|\breal-time strategy\b"
    r"|\baction game\b|\bsimulation game\b|\bsports game\b",
    re.IGNORECASE,
)
_GAME_TYPE = re.compile(r"videoGame|BoardGame", re.IGNORECASE)


def classify_from_text(ddg: dict, wiki: dict) -> tuple[str, str]:
    """
    Returns (verdict, evidence_snippet).
    verdict: MAC_AVAILABLE | WINDOWS_ONLY | GAME | UNKNOWN
    """
    text = " ".join([
        ddg.get("abstract", ""),
        wiki.get("extract", ""),
    ])

    # Game check first (a game could also mention Mac)
    if _GAME_TYPE.search(ddg.get("abstract_type", "")) or _GAME_RE.search(text):
        snippet = _first_sentence(text)
        return "GAME", snippet

    has_mac = bool(_MAC_RE.search(text))
    has_win = bool(_WIN_RE.search(text))

    if has_mac:
        return "MAC_AVAILABLE", _first_sentence(text)
    if has_win and not has_mac:
        return "WINDOWS_ONLY", _first_sentence(text)

    if text.strip():
        return "UNKNOWN", _first_sentence(text)
    return "UNKNOWN", ""


def _first_sentence(text: str) -> str:
    text = text.strip().replace("\n", " ")
    m = re.match(r"(.{20,200}?[.!?])\s", text)
    return m.group(1) if m else text[:200]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_review_items() -> list[dict]:
    csv_path = BASE / "installed_programs.csv"
    if not csv_path.exists():
        print("ERROR: installed_programs.csv not found. Run extract_installed.ps1 first.")
        sys.exit(1)

    # Import classify from assess_mac_compat
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from assess_mac_compat import classify

    items = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = row.get("Name", "").strip()
            if not name:
                continue
            cat, _ = classify(name)
            if cat == "REVIEW":
                items.append({
                    "name":      name,
                    "version":   row.get("Version", "").strip(),
                    "publisher": row.get("Publisher", "").strip(),
                    "source":    row.get("Source", "").strip(),
                })
    return items


def load_cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict):
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def write_outputs(results: list[dict]):
    # CSV
    fields = ["name", "version", "publisher", "verdict", "evidence", "ddg_source", "wiki_url"]
    with open(RESULT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)

    # Markdown grouped by verdict
    by_verdict: dict[str, list] = {
        "MAC_AVAILABLE": [],
        "GAME":          [],
        "WINDOWS_ONLY":  [],
        "UNKNOWN":       [],
    }
    for r in results:
        by_verdict.setdefault(r["verdict"], []).append(r)
    for v in by_verdict:
        by_verdict[v].sort(key=lambda x: x["name"].lower())

    lines = []
    lines.append("# Online Lookup — REVIEW Bucket Assessment")
    lines.append(f"_Generated {date.today()}  |  {len(results)} apps queried_\n")

    total = len(results)
    lines.append("## Summary\n")
    lines.append("| Verdict | Count |")
    lines.append("|---------|------:|")
    for v, label in [
        ("MAC_AVAILABLE", "Mac version found"),
        ("GAME",          "Game / game-related"),
        ("WINDOWS_ONLY",  "Windows only"),
        ("UNKNOWN",       "Could not determine"),
    ]:
        lines.append(f"| {label} | {len(by_verdict[v])} |")
    lines.append(f"| **Total** | **{total}** |\n")

    # MAC_AVAILABLE
    lines.append("---\n## Mac version found\n")
    lines.append("| App | Publisher | Evidence |")
    lines.append("|-----|-----------|---------|")
    for r in by_verdict["MAC_AVAILABLE"]:
        ev = r.get("evidence", "")[:120].replace("|", "/")
        lines.append(f"| {r['name']} | {r['publisher'] or '—'} | {ev} |")

    # GAME
    lines.append("\n---\n## Games\n")
    lines.append("| App | Publisher | Evidence |")
    lines.append("|-----|-----------|---------|")
    for r in by_verdict["GAME"]:
        ev = r.get("evidence", "")[:120].replace("|", "/")
        lines.append(f"| {r['name']} | {r['publisher'] or '—'} | {ev} |")

    # WINDOWS_ONLY
    lines.append("\n---\n## Windows only\n")
    lines.append("| App | Publisher | Evidence |")
    lines.append("|-----|-----------|---------|")
    for r in by_verdict["WINDOWS_ONLY"]:
        ev = r.get("evidence", "")[:120].replace("|", "/")
        lines.append(f"| {r['name']} | {r['publisher'] or '—'} | {ev} |")

    # UNKNOWN
    lines.append("\n---\n## Could not determine\n")
    lines.append("| App | Publisher |")
    lines.append("|-----|-----------|")
    for r in by_verdict["UNKNOWN"]:
        lines.append(f"| {r['name']} | {r['publisher'] or '—'} |")

    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Online lookup for REVIEW bucket apps")
    parser.add_argument("--limit",  type=int, default=0,     help="Max apps to process (0 = all)")
    parser.add_argument("--resume", action="store_true",      help="Skip apps already in cache")
    args = parser.parse_args()

    BASE.mkdir(parents=True, exist_ok=True)
    items = load_review_items()
    cache = load_cache()

    if args.limit:
        items = items[:args.limit]

    to_process = [i for i in items if not args.resume or i["name"] not in cache]
    print(f"REVIEW items total : {len(items)}")
    print(f"To process now     : {len(to_process)}")
    print(f"Already cached     : {len(items) - len(to_process)}")
    print()

    for idx, item in enumerate(to_process, 1):
        name = item["name"]
        # Skip obvious GUIDs / internal IDs
        if re.match(r"^[0-9a-f\-]{30,}$", name, re.IGNORECASE) or re.match(r"^[0-9A-F]{10,}$", name):
            cache[name] = {"verdict": "SKIP_INTERNAL", "evidence": "GUID/internal ID", "ddg_source": "", "wiki_url": ""}
            continue

        print(f"[{idx:3}/{len(to_process)}] {name[:55]:<55}", end=" ", flush=True)

        ddg  = ddg_lookup(name)
        time.sleep(RATE_LIMIT_SEC / 2)
        wiki = wiki_lookup(name)
        time.sleep(RATE_LIMIT_SEC / 2)

        verdict, evidence = classify_from_text(ddg, wiki)
        cache[name] = {
            "verdict":    verdict,
            "evidence":   evidence,
            "ddg_source": ddg.get("abstract_source", ""),
            "wiki_url":   wiki.get("page_url", ""),
        }
        print(verdict)

        # Save cache every 10 items
        if idx % 10 == 0:
            save_cache(cache)

    save_cache(cache)
    print("\nCache saved.")

    # Build results list from full items + cache
    results = []
    for item in items:
        name = item["name"]
        cached = cache.get(name, {})
        results.append({
            "name":       name,
            "version":    item["version"],
            "publisher":  item["publisher"].encode("ascii", "replace").decode(),
            "verdict":    cached.get("verdict", "UNKNOWN"),
            "evidence":   cached.get("evidence", ""),
            "ddg_source": cached.get("ddg_source", ""),
            "wiki_url":   cached.get("wiki_url", ""),
        })

    write_outputs(results)
    print(f"\nReport  : {REPORT_MD}")
    print(f"CSV     : {RESULT_CSV}")

    by_v: dict[str, int] = {}
    for r in results:
        by_v[r["verdict"]] = by_v.get(r["verdict"], 0) + 1
    for v, c in sorted(by_v.items(), key=lambda x: -x[1]):
        print(f"  {v:<20}: {c}")


if __name__ == "__main__":
    main()
