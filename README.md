# windows-to-mac-migration

A set of scripts that inventories every program installed on a Windows PC, classifies each one for macOS compatibility, checks Homebrew availability, and generates a ready-to-run install script for your new Mac.

Built as a personal migration tool when switching from Windows to macOS.

---

## Features

- Extracts installed programs from the Windows registry, winget, and the Microsoft Store
- Classifies each app into one of five categories: **Native**, **Alternative**, **Game**, **Skip**, or **Review**
- Checks the full [Homebrew](https://brew.sh) cask and formula catalogue (7,500+ casks) for every native app
- Generates a `brew_install.sh` script you can run directly on your Mac
- For unrecognised apps, queries the **DuckDuckGo Instant Answer API** and **Wikipedia REST API** to auto-classify them — no API keys required
- Results cached locally so re-runs are instant

---

## Output files

All output is written to `~/Documents/mac-migration/`.

| File | Description |
|------|-------------|
| `installed_programs.csv` | Raw list of every installed program |
| `mac_migration_report.md` | Full compatibility report with brew commands |
| `brew_install.sh` | One-shot install script for your Mac |
| `online_lookup_report.md` | Online-researched assessment of unknown apps |
| `online_lookup_results.csv` | Machine-readable version of the above |
| `brew_cache.json` | Cached Homebrew index (refreshed every 24 h) |
| `online_lookup_cache.json` | Cached online lookup results |

---

## Requirements

- Windows 10 / 11
- PowerShell 5+ (built-in)
- Python 3.8+
- Internet connection (for Homebrew index and online lookup)

---

## Usage

### Step 1 — Extract installed programs

Run in PowerShell (Administrator recommended for full registry access):

```powershell
powershell -ExecutionPolicy Bypass -File extract_installed.ps1
```

This scans the Windows registry (64-bit, 32-bit, and per-user hives), winget, and the Microsoft Store, then writes `installed_programs.csv`.

---

### Step 2 — Assess Mac compatibility

```powershell
python assess_mac_compat.py
```

Classifies every app using a built-in rule set (~150 patterns) and checks Homebrew for each native app. On first run it downloads the full Homebrew catalogue and caches it.

**Categories:**

| Category | Meaning |
|----------|---------|
| ✅ Native | Same app available on Mac. Includes `brew install` command where applicable. |
| 🔄 Alternative | No Mac port exists, but a recommended equivalent is listed. |
| 🎮 Game | Detected as a game or game-related (e.g. DLC, launcher). |
| ⛔ Skip | Windows-only: drivers, runtimes, system components, OEM tools. |
| ❓ Review | Not recognised — run the online lookup for these. |

---

### Step 3 — Online lookup for unknown apps (optional)

```powershell
# Full run
python online_lookup.py

# Quick test on first 20 items
python online_lookup.py --limit 20

# Resume an interrupted run without re-fetching cached results
python online_lookup.py --resume
```

For each unrecognised app, queries DuckDuckGo and Wikipedia to determine whether a Mac version exists, whether it is a game, or whether it is Windows-only. Results are saved with an evidence snippet so you can verify each verdict.

---

### Step 4 — Install on your Mac

Copy `brew_install.sh` to your Mac and run:

```bash
bash brew_install.sh
```

This installs Homebrew if it is not present, then installs every app that was found in the Homebrew catalogue.

---

## Example report (excerpt)

```
## Summary

| Category                   | Count |
|----------------------------|------:|
| Native / cross-platform    |   100 |
|   ↳ on Homebrew            |    80 |
|   ↳ manual install         |    20 |
| Alternative available      |    28 |
| Needs review               |    39 |
| Games                      |    51 |
| Skip (Windows-only)        |   495 |
| Total scanned              |   713 |
```

---

## Project structure

```
.
├── extract_installed.ps1   # Step 1: collect installed programs from Windows
├── assess_mac_compat.py    # Step 2: classify + Homebrew lookup
├── online_lookup.py        # Step 3: DuckDuckGo + Wikipedia lookup for unknowns
└── README.md
```

---

## License

MIT
