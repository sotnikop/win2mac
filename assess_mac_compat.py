#!/usr/bin/env python3
"""
assess_mac_compat.py
Reads installed_programs.csv, classifies each app for Mac compatibility,
checks Homebrew for cask/formula availability, and writes mac_migration_report.md

Categories:
  NATIVE      - Available natively on Mac (same app, same name)
  ALTERNATIVE - A good Mac alternative exists (different app, same job)
  SKIP        - Windows-only system/driver/runtime, nothing to install on Mac
  REVIEW      - Unclear; needs manual review
"""

import csv, json, pathlib, re, sys, urllib.request, urllib.error
from datetime import date, datetime

# ---------------------------------------------------------------------------
# Homebrew lookup
# ---------------------------------------------------------------------------

BREW_API_CASKS    = "https://formulae.brew.sh/api/cask.json"
BREW_API_FORMULAS = "https://formulae.brew.sh/api/formula.json"
CACHE_MAX_AGE_HOURS = 24


def _fetch_json(url: str) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": "mac-migration-script/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_brew_index(cache_dir: pathlib.Path) -> dict:
    """
    Returns a dict keyed by normalised name → {"type": "cask"|"formula", "token": str}
    Downloads cask + formula lists from Homebrew API, caches for 24 h.
    """
    cache_file = cache_dir / "brew_cache.json"

    # Use cache if fresh enough
    if cache_file.exists():
        age_hours = (datetime.now().timestamp() - cache_file.stat().st_mtime) / 3600
        if age_hours < CACHE_MAX_AGE_HOURS:
            print(f"  Using cached Homebrew index ({age_hours:.1f}h old)")
            with open(cache_file, encoding="utf-8") as f:
                return json.load(f)

    print("  Fetching Homebrew cask list …", end=" ", flush=True)
    try:
        casks = _fetch_json(BREW_API_CASKS)
        print(f"{len(casks)} casks")
    except Exception as e:
        print(f"FAILED ({e})")
        casks = []

    print("  Fetching Homebrew formula list …", end=" ", flush=True)
    try:
        formulas = _fetch_json(BREW_API_FORMULAS)
        print(f"{len(formulas)} formulas")
    except Exception as e:
        print(f"FAILED ({e})")
        formulas = []

    if not casks and not formulas:
        print("  WARNING: Could not reach Homebrew API. Brew lookup will be skipped.")
        return {}

    index = {}

    for cask in casks:
        token = cask.get("token", "")
        # Each cask has a "name" array of human-readable strings
        for human_name in cask.get("name", []):
            key = _norm(human_name)
            if key and key not in index:
                index[key] = {"type": "cask", "token": token}
        # Also index by token itself
        key = _norm(token.replace("-", " "))
        if key and key not in index:
            index[key] = {"type": "cask", "token": token}

    for formula in formulas:
        name = formula.get("name", "")
        key  = _norm(name)
        if key and key not in index:
            index[key] = {"type": "formula", "token": name}
        # Also index description words? No – too noisy. Token + aliases only.
        for alias in formula.get("aliases", []):
            akey = _norm(alias)
            if akey and akey not in index:
                index[akey] = {"type": "formula", "token": name}

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(index, f)
    print(f"  Brew index cached ({len(index)} entries)")
    return index


def _norm(s: str) -> str:
    """Lowercase, strip version suffixes, collapse whitespace, drop punctuation."""
    s = s.lower().strip()
    # Strip trailing version numbers like "3.11", " 64-bit", " (x64)"
    s = re.sub(r"\s*[\(\[].*?[\)\]]", "", s)          # remove (…) and […]
    s = re.sub(r"\s+v?[\d]+[\.\d]*\s*$", "", s)       # trailing version
    s = re.sub(r"\s+(64|32)-?bit\s*$", "", s)
    s = re.sub(r"[^\w\s]", " ", s)                    # punctuation → space
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Hard-coded overrides: Windows app name pattern → brew token (cask preferred).
# These handle cases where the Windows name differs too much from the brew token.
BREW_OVERRIDES: list[tuple[str, str, str]] = [
    # (regex pattern,  brew type,  brew token)
    (r"^1password",                  "cask",    "1password"),
    (r"adobe acrobat",               "cask",    "adobe-acrobat-reader"),
    (r"adobe creative cloud",        "cask",    "adobe-creative-cloud"),
    (r"affinity photo",              "cask",    "affinity-photo"),
    (r"affinity designer",           "cask",    "affinity-designer"),
    (r"affinity publisher",          "cask",    "affinity-publisher"),
    (r"android studio",              "cask",    "android-studio"),
    (r"^anki",                       "cask",    "anki"),
    (r"^anydesk",                    "cask",    "anydesk"),
    (r"^arc\b",                      "cask",    "arc"),
    (r"arduino",                     "cask",    "arduino-ide"),
    (r"^audacity",                   "cask",    "audacity"),
    (r"balenaetcher|^etcher",        "cask",    "balenaetcher"),
    (r"^bitwarden",                  "cask",    "bitwarden"),
    (r"^blender",                    "cask",    "blender"),
    (r"^brave",                      "cask",    "brave-browser"),
    (r"^calibre",                    "cask",    "calibre"),
    (r"^chatgpt",                    "cask",    "chatgpt"),
    (r"^claude",                     "cask",    "claude"),
    (r"^dbeaver",                    "cask",    "dbeaver-community"),
    (r"^discord",                    "cask",    "discord"),
    (r"^docker",                     "cask",    "docker"),
    (r"draw\.?io",                   "cask",    "drawio"),
    (r"^dropbox",                    "cask",    "dropbox"),
    (r"^eclipse",                    "cask",    "eclipse-java"),
    (r"^figma",                      "cask",    "figma"),
    (r"^filezilla",                  "cask",    "filezilla"),
    (r"^firefox",                    "cask",    "firefox"),
    (r"^flutter",                    "cask",    "flutter"),
    (r"^git\b",                      "formula", "git"),
    (r"git for windows",             "formula", "git"),
    (r"github desktop",              "cask",    "github"),
    (r"^gimp",                       "cask",    "gimp"),
    (r"google chrome",               "cask",    "google-chrome"),
    (r"google drive",                "cask",    "google-drive"),
    (r"^handbrake",                  "cask",    "handbrake"),
    (r"^httpie",                     "cask",    "httpie"),
    (r"^inkscape",                   "cask",    "inkscape"),
    (r"^insomnia",                   "cask",    "insomnia"),
    (r"intellij idea community",     "cask",    "intellij-idea-ce"),
    (r"intellij idea\b",             "cask",    "intellij-idea"),
    (r"^pycharm community",          "cask",    "pycharm-ce"),
    (r"^pycharm\b",                  "cask",    "pycharm"),
    (r"^webstorm",                   "cask",    "webstorm"),
    (r"^clion",                      "cask",    "clion"),
    (r"^goland",                     "cask",    "goland"),
    (r"^rider\b",                    "cask",    "rider"),
    (r"^datagrip",                   "cask",    "datagrip"),
    (r"^phpstorm",                   "cask",    "phpstorm"),
    (r"^rubymine",                   "cask",    "rubymine"),
    (r"^kdiff3",                     "cask",    "kdiff3"),
    (r"^lastpass",                   "cask",    "lastpass"),
    (r"logitech g hub",              "cask",    "logi-options-plus"),
    (r"^libreoffice",                "cask",    "libreoffice"),
    (r"^loom",                       "cask",    "loom"),
    (r"^malwarebytes",               "cask",    "malwarebytes"),
    (r"^mattermost",                 "cask",    "mattermost"),
    (r"microsoft edge",              "cask",    "microsoft-edge"),
    (r"microsoft excel",             "cask",    "microsoft-excel"),
    (r"microsoft onedrive",          "cask",    "onedrive"),
    (r"microsoft onenote",           "cask",    "microsoft-onenote"),
    (r"microsoft outlook",           "cask",    "microsoft-outlook"),
    (r"microsoft powerpoint",        "cask",    "microsoft-powerpoint"),
    (r"microsoft teams",             "cask",    "microsoft-teams"),
    (r"microsoft word",              "cask",    "microsoft-word"),
    (r"^miro\b",                     "cask",    "miro"),
    (r"mongodb compass",             "cask",    "mongodb-compass"),
    (r"^mpv\b",                      "cask",    "mpv"),
    (r"node\.?js",                   "formula", "node"),
    (r"^notion\b",                   "cask",    "notion"),
    (r"^obs studio|^obs\b",          "cask",    "obs"),
    (r"^obsidian",                   "cask",    "obsidian"),
    (r"openvpn",                     "cask",    "openvpn-connect"),
    (r"^postman",                    "cask",    "postman"),
    (r"^powershell",                 "cask",    "powershell"),
    (r"^python 3|^python\b",         "formula", "python@3.12"),
    (r"^qbittorrent",                "cask",    "qbittorrent"),
    (r"raspberry pi imager",         "cask",    "raspberry-pi-imager"),
    (r"^rustup",                     "formula", "rustup"),
    (r"^signal",                     "cask",    "signal"),
    (r"^slack",                      "cask",    "slack"),
    (r"^sourcetree",                 "cask",    "sourcetree"),
    (r"^spotify",                    "cask",    "spotify"),
    (r"^steam",                      "cask",    "steam"),
    (r"sublime text",                "cask",    "sublime-text"),
    (r"sublime merge",               "cask",    "sublime-merge"),
    (r"^tableplus",                  "cask",    "tableplus"),
    (r"^telegram",                   "cask",    "telegram"),
    (r"^thunderbird",                "cask",    "thunderbird"),
    (r"tor browser",                 "cask",    "tor-browser"),
    (r"^typora",                     "cask",    "typora"),
    (r"unity hub",                   "cask",    "unity-hub"),
    (r"^unity\b",                    "cask",    "unity"),
    (r"^vagrant",                    "cask",    "vagrant"),
    (r"^virtualbox",                 "cask",    "virtualbox"),
    (r"^vlc",                        "cask",    "vlc"),
    (r"visual studio code|^vscode",  "cask",    "visual-studio-code"),
    (r"^whatsapp",                   "cask",    "whatsapp"),
    (r"^wireshark",                  "cask",    "wireshark"),
    (r"^zoom\b",                     "cask",    "zoom"),
    (r"^zotero",                     "cask",    "zotero"),
    (r"^cryptomator",                "cask",    "cryptomator"),
    (r"teamviewer",                  "cask",    "teamviewer"),
]

_BREW_OVERRIDES_COMPILED = [
    (re.compile(pat, re.IGNORECASE), btype, token)
    for pat, btype, token in BREW_OVERRIDES
]


def brew_command(app_name: str, index: dict) -> str:
    """
    Returns the brew install command for an app, or empty string if not found.
    Tries overrides first, then fuzzy index lookup.
    """
    # 1. Hard-coded overrides (most reliable)
    for pattern, btype, token in _BREW_OVERRIDES_COMPILED:
        if pattern.search(app_name):
            if btype == "cask":
                return f"brew install --cask {token}"
            else:
                return f"brew install {token}"

    # 2. Fuzzy index lookup
    if not index:
        return ""

    key = _norm(app_name)
    if key in index:
        entry = index[key]
        if entry["type"] == "cask":
            return f"brew install --cask {entry['token']}"
        else:
            return f"brew install {entry['token']}"

    # 3. Try progressively shorter key fragments (drop last word)
    parts = key.split()
    for length in range(len(parts) - 1, 0, -1):
        sub = " ".join(parts[:length])
        if sub in index:
            entry = index[sub]
            if entry["type"] == "cask":
                return f"brew install --cask {entry['token']}"
            else:
                return f"brew install {entry['token']}"

    return ""


# ---------------------------------------------------------------------------
# Classification rules
# ---------------------------------------------------------------------------

RULES = [
    # --- GUIDs and internal Store package IDs → SKIP ---
    (r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", "SKIP", "Internal package GUID"),
    (r"^[0-9A-F]{13,}$", "SKIP", "Internal package ID"),

    # --- Windows Store camelCase system packages → SKIP ---
    (r"^Windows\.(Apprep|AssignedAccess|CallingShell|CapturePicker|CloudExperience|ContentDelivery|DevHome|Narrator|OOBE|Parental|PeopleExperience|Photos|PinningConfirmation|Search|SecHealth|SecureAssessment|ShellExperience|StartMenu|XGpuEject)", "SKIP", "Windows Store system package"),
    (r"^Windows(Alarms|Calculator|Camera|Clock|FeedbackHub|Maps|SoundRecorder|Store|SubsystemForLinux|communicationsapps)", "SKIP", "Windows Store system package"),
    (r"^(AAD\.BrokerPlugin|aimgr|AsyncTextService|BioEnrollment|Client\.CBS|CredDialogHost|CrossDevice|DesktopAppInstaller|ECApp|LockApp|NcsiUwpApp|PrebootManager|UndockedDevKit|Win32WebViewHost)", "SKIP", "Windows internal service"),
    (r"^(BingSearch|BingWeather|Copilot|Cortana|GetHelp|Getstarted|Messaging|OneConnect|People|StorePurchaseApp|Wallet|WinAppDeploy|Winget\.Source|YourPhone)", "SKIP", "Windows built-in app"),
    (r"^(Xbox|XboxApp|XboxGame|XboxGaming|XboxIdentity|XboxSpeech)", "SKIP", "Xbox / Windows Gaming service"),
    (r"^Xbox (Console Companion|Game Bar|Game Speech|Identity Provider|TCUI)", "SKIP", "Xbox Windows service"),
    (r"^(MicrosoftEdge\.|MicrosoftOfficeHub|MicrosoftSolitaire|MicrosoftStickyNotes|Microsoft3DViewer|MicrosoftEdgeDevTools)", "SKIP", "Windows built-in app"),
    (r"^(ZuneMusic|ZuneVideo|MSTeams|MSPaint|Office\.ActionsServer|Office\.OneNote|OfficePushNotif)", "SKIP", "Windows built-in / Store app"),
    (r"^(Advertising\.Xaml|Services\.Store\.Engagement|ThunderboltControlCenter|SynapticsUtilities)", "SKIP", "Windows Store component"),
    (r"^(AV1VideoExtension|DolbyAccess|DolbyAtmos|DolbyVision|HEIFImageExtension|HEVCVideoExtension|MPEG2VideoExtension|VP9VideoExtensions|WebMediaExtensions|WebpImageExtension)", "SKIP", "Windows media codec extension"),
    (r"^(AV1 Video Extension|Dolby Access|Dolby Atmos|Dolby Vision|HEIF Image|HEVC Video|MPEG-2 Video|VP9 Video|Web Media Ext|WebP Image Ext)", "SKIP", "Windows media codec extension"),
    (r"^(GlancebyMirametrix|Glance by Mirametrix|LenovoCompanion|ELANTrackPoint|ThunderboltTM)", "SKIP", "OEM Windows utility"),

    # --- Visual Studio internal components → SKIP ---
    (r"^vs_", "SKIP", "Visual Studio internal component"),
    (r"^icecap_", "SKIP", "Visual Studio profiler component"),
    (r"^(VS Immersive|VS JIT|VS Script|IntelliTraceProfiler|MSI Development Tools|WinAppDeploy|vcpp_crt)", "SKIP", "Visual Studio internal tool"),
    (r"^(Application Verifier|Kits Configuration Installer|SDK ARM Additions|DiagnosticsHub)", "SKIP", "Windows SDK tool"),
    (r"^(WinRT Intellisense|Universal CRT|Universal General MIDI|Windows Desktop Extension SDK|Windows IoT Extension|Windows Mobile Extension|Windows Team Extension)", "SKIP", "Windows SDK component"),
    (r"^(Windows App Certification Kit|Windows Desktop Targeting|Windows Software Development Kit)", "SKIP", "Windows SDK"),
    (r"^Microsoft\.(UI\.Xaml|NET\.Sdk\.|NET\.Workload)", "SKIP", "Windows/.NET SDK component"),
    (r"^Microsoft (ASP\.NET|NetStandard SDK|TestPlatform|Web Deploy|Windows Desktop Targeting)", "SKIP", "Windows/.NET SDK component"),
    (r"^Microsoft (SQL Server 200[0-9]|SQL Server 2012|System CLR Types|Command Line Utilities \d+ for SQL)", "SKIP", "Old SQL Server component"),
    (r"^Microsoft (Azure Authoring|Azure Compute Emulator|Azure Libraries|Azure PowerShell|Azure Storage Emulator)", "SKIP", "Azure Windows SDK tool"),
    (r"^(UE4 Prerequisites|Universal CRT Extension SDK|Universal CRT Headers|Universal CRT Tools)", "SKIP", "Game engine / SDK prerequisite"),
    (r"^(D3DX10|MSVCRT\b|MSVCRT110|MSVCRT110_amd64)", "SKIP", "Windows DirectX/MSVC runtime"),

    # --- Windows system / OEM / built-ins → SKIP ---
    (r"^Windows (Live|PC Health Check|Migration Assistant|Advanced Settings|Maps|Camera|Clock|Voice Recorder|Media Player|Package Manager)", "SKIP", "Windows built-in"),
    (r"^Windows Live ", "SKIP", "Windows Live legacy app"),
    (r"^(Mixed Reality Portal|MixedReality\.Portal|Mobile Plans|Phone Link|Cross Device)", "SKIP", "Windows feature"),
    (r"^(Game Bar|Snip & Sketch|ScreenSketch|Paint 3D|Print 3D|3D Viewer|Movie Maker|Photo Gallery|Mail and Calendar)", "SKIP", "Windows built-in app"),
    (r"^(Get Help|Feedback Hub|Microsoft Tips|Microsoft Pay|Microsoft People|Microsoft Bing|Microsoft Photos|Microsoft Sticky Notes|Microsoft Maps|Outlook for Windows)", "SKIP", "Windows built-in app"),
    (r"^(Store Experience Host|Microsoft Remote Desktop|Microsoft 365 Copilot|Local AI Manager)", "SKIP", "Windows built-in / Store"),
    (r"^(Cortana|Copilot|BingSearch|aimgr|AsyncTextService)", "SKIP", "Windows built-in service"),
    (r"^(ELAN TrackPoint|Lenovo Diagnostics|Lenovo Display Optimizer|Lenovo Pen Settings|Lenovo Provisioning|Crucial Storage Executive)", "SKIP", "OEM hardware utility"),
    (r"^(Dolby Access|Dolby Atmos|Dolby Vision)", "SKIP", "OEM audio driver/app – Windows only"),
    (r"^(SpeedFan|Core Temp|TPFanControl|CrystalDiskInfo|CrystalDiskMark|SeaTools|Intel\(R\) Extreme Tuning|Intel\(R\) SUR|Intel\(R\) Computing Improvement)", "SKIP", "Windows hardware monitor/tuning tool"),
    (r"^(NETGEAR USB Control|Npcap)", "SKIP", "Windows hardware/network driver"),
    (r"^(IIS [0-9]|IIS Express)", "SKIP", "Windows IIS web server component"),
    (r"^(Ubuntu on Windows|CentOS|UbuntuonWindows|WindowsSubsystemForLinux)", "SKIP", "WSL / Linux-on-Windows"),
    (r"^(Office 16 Click-to-Run|OfficePushNotifications|OneNote for Windows 10|MicrosoftOfficeHub)", "SKIP", "Office Windows component"),
    (r"^(Taskbar icons of Yandex|Yandex\.)", "SKIP", "Yandex Windows toolbar"),
    (r"^(WinRT|WinHTTrack)", "SKIP", "Windows-specific tool"),
    (r"^(AdobeAcrobatReaderCoreApp|Adobe Refresh Manager)", "SKIP", "Adobe Windows component"),
    (r"^(LanguageExperiencePack)", "SKIP", "Windows language pack"),

    # --- GAMES → GAME category ---
    (r"^(Stellaris|Hearts of Iron|Crusader Kings|Europa Universalis|Victoria \d)", "GAME", "Paradox grand strategy game"),
    (r"^(Company of Heroes|Total War|WARHAMMER|Warhammer)", "GAME", "PC strategy game"),
    (r"^(Diablo|World of Warcraft|Overwatch|StarCraft|Hearthstone)", "GAME", "Blizzard game"),
    (r"^(Panzer Corps|Strategic Command|Shadow Empire|Headquarters: World War|TOTAL TANK)", "GAME", "PC wargame"),
    (r"^(Sunless Sea|Duck Game|Terraformers|Tabletop Simulator|Worms World Party)", "GAME", "PC game"),
    (r"^(Unreal Tournament|GOG\.com Unreal)", "GAME", "Classic PC game"),
    (r"^(Workers & Resources|World_of_Warships|7,62 High Calibre)", "GAME", "PC game"),
    (r"publisher.*GOG\.com|^GOG GALAXY", "GAME", "GOG game or launcher"),

    # --- Runtimes / redistributables / drivers → SKIP ---
    (r"microsoft (visual c\+\+|vc\+\+|mfc|atl)", "SKIP", "Windows runtime"),
    (r"microsoft \.net", "SKIP", "Windows runtime"),
    (r"\.net (framework|runtime|sdk|desktop)", "SKIP", "Windows runtime"),
    (r"windows (sdk|adk|pe|subsystem|terminal)", "SKIP", "Windows built-in"),
    (r"directx", "SKIP", "Windows graphics API"),
    (r"(nvidia|amd|intel|realtek|qualcomm|broadcom).*(driver|graphics|audio|control|geforce|radeon)", "SKIP", "Hardware driver"),
    (r"geforce experience", "SKIP", "Nvidia Windows tool"),
    (r"amd (software|radeon|chipset)", "SKIP", "AMD Windows tool"),
    (r"intel (driver|graphics|management|nuc|sst|serial io)", "SKIP", "Intel Windows tool"),
    (r"(lenovo|dell|hp|asus|acer|msi|logitech|corsair|razer) (vantage|update|connect|sync|hub|service|utility)", "SKIP", "OEM utility"),
    (r"(vcredist|vc_redist)", "SKIP", "Windows runtime"),
    (r"(microsoft|windows) (update|defender|security|store|edge|onedrive built)", "SKIP", "Windows built-in"),
    (r"bonjour", "SKIP", "Apple service – pre-installed on Mac"),
    (r"apple (mobile device|application support|software update)", "SKIP", "iTunes helper – not needed on Mac"),
    (r"(openssl|openssl for windows)", "SKIP", "Pre-installed on Mac via brew or system"),

    # --- Universal / Cross-platform (NATIVE) ---
    (r"^adobe (acrobat|reader|creative cloud|photoshop|illustrator|premiere|after effects|lightroom|indesign|audition|xd|animate|dreamweaver|substance|bridge|media encoder)", "NATIVE", "Adobe – Mac version available"),
    (r"^affinity (photo|designer|publisher)", "NATIVE", "Affinity – Mac version available"),
    (r"^android studio", "NATIVE", "Android Studio – Mac version available"),
    (r"^anki", "NATIVE", "Anki – Mac version available"),
    (r"^anydesk", "NATIVE", "AnyDesk – Mac version available"),
    (r"^arc browser", "NATIVE", "Arc – Mac version available (primary platform)"),
    (r"^arduino", "NATIVE", "Arduino IDE – Mac version available"),
    (r"^audacity", "NATIVE", "Audacity – Mac version available"),
    (r"^autodesk", "NATIVE", "Autodesk – check specific product for Mac support"),
    (r"^balenaetcher|^etcher", "NATIVE", "balenaEtcher – Mac version available"),
    (r"^bitwarden", "NATIVE", "Bitwarden – Mac version available"),
    (r"^blender", "NATIVE", "Blender – Mac version available"),
    (r"^brave", "NATIVE", "Brave – Mac version available"),
    (r"^calibre", "NATIVE", "Calibre – Mac version available"),
    (r"^chatgpt", "NATIVE", "ChatGPT desktop – Mac version available"),
    (r"^claude", "NATIVE", "Claude desktop – Mac version available"),
    (r"^amazon kindle", "NATIVE", "Kindle – Mac version available"),
    (r"^altserver", "NATIVE", "AltServer – Mac version available (primary use case)"),
    (r"^autohotkey", "ALTERNATIVE", "Use Keyboard Maestro or BetterTouchTool on Mac"),
    (r"^azure (developer cli|cli)", "NATIVE", "Azure CLI – Mac version available via Homebrew"),
    (r"^microsoft azure (developer cli|cli)", "NATIVE", "Azure CLI – Mac version available via Homebrew"),
    (r"^cisco webex", "NATIVE", "Webex – Mac version available"),
    (r"^connectify", "ALTERNATIVE", "Use macOS Internet Sharing (built-in System Settings)"),
    (r"^copytrans", "SKIP", "Windows iTunes companion – not needed on Mac"),
    (r"^cpu-z", "ALTERNATIVE", "Use GPU Monitor Pro or iStatistica on Mac"),
    (r"^crystaldisk(info|mark)", "ALTERNATIVE", "Use DriveDx or AmorphousDiskMark on Mac"),
    (r"^dbeaver", "NATIVE", "DBeaver – Mac version available"),
    (r"^discord", "NATIVE", "Discord – Mac version available"),
    (r"^docker", "NATIVE", "Docker Desktop – Mac version available"),
    (r"^drawio|^draw\.io", "NATIVE", "draw.io desktop – Mac version available"),
    (r"^dropbox", "NATIVE", "Dropbox – Mac version available"),
    (r"^eclipse", "NATIVE", "Eclipse IDE – Mac version available"),
    (r"^easeus data recovery", "NATIVE", "EaseUS Data Recovery – Mac version available"),
    (r"^easeus (os2go|partition)", "ALTERNATIVE", "Use Carbon Copy Cloner or Disk Utility on Mac"),
    (r"^everything\b", "ALTERNATIVE", "Use Alfred, Spotlight, or HoudahSpot on Mac"),
    (r"^f\.lux", "NATIVE", "f.lux – Mac version available"),
    (r"^figma", "NATIVE", "Figma – Mac version available (primary platform)"),
    (r"^filezilla", "NATIVE", "FileZilla – Mac version available"),
    (r"^firefox", "NATIVE", "Firefox – Mac version available"),
    (r"^flutter", "NATIVE", "Flutter SDK – Mac version available"),
    (r"^foxit (reader|pdf)", "NATIVE", "Foxit PDF – Mac version available"),
    (r"^git( for windows)?", "NATIVE", "Git – pre-installed or via Homebrew on Mac"),
    (r"^github desktop", "NATIVE", "GitHub Desktop – Mac version available"),
    (r"^gimp", "NATIVE", "GIMP – Mac version available"),
    (r"^google (chrome|drive|earth|meet)", "NATIVE", "Google app – Mac version available"),
    (r"^gog galaxy", "NATIVE", "GOG Galaxy – Mac version available"),
    (r"^gpt4all", "NATIVE", "GPT4All – Mac version available"),
    (r"^gpu-z", "ALTERNATIVE", "Use GPU Monitor Pro or iStatistica on Mac"),
    (r"^handbrake", "NATIVE", "HandBrake – Mac version available"),
    (r"^hiddify", "NATIVE", "Hiddify – Mac version available"),
    (r"^httpie", "NATIVE", "HTTPie – Mac version available"),
    (r"^inkscape", "NATIVE", "Inkscape – Mac version available"),
    (r"^insomnia", "NATIVE", "Insomnia – Mac version available"),
    (r"^intellij|^jetbrains|^pycharm|^webstorm|^clion|^goland|^rider|^datagrip|^rubymine|^appcode|^phpstorm", "NATIVE", "JetBrains IDE – Mac version available"),
    (r"^itunes", "SKIP", "Replaced by Music, TV, Podcasts apps on Mac"),
    (r"^iterm2", "NATIVE", "iTerm2 – Mac only (install on Mac)"),
    (r"^kdiff|^kdiff3", "NATIVE", "KDiff3 – Mac version available"),
    (r"^jami\b", "NATIVE", "Jami – Mac version available"),
    (r"^keepass", "ALTERNATIVE", "Use KeePassXC (cross-platform) or Strongbox on Mac"),
    (r"^keytweak", "ALTERNATIVE", "Use Karabiner-Elements on Mac"),
    (r"^kleopatra|^gpg4win", "ALTERNATIVE", "Use GPG Suite on Mac"),
    (r"^lastpass", "NATIVE", "LastPass – Mac version available"),
    (r"^lghub|^logitech g hub", "NATIVE", "Logitech G HUB – Mac version available"),
    (r"^libreoffice", "NATIVE", "LibreOffice – Mac version available"),
    (r"^linphone", "NATIVE", "Linphone SIP – Mac version available"),
    (r"^logitech unifying", "SKIP", "Logitech Unifying receiver – use Logi Options+ on Mac instead"),
    (r"^loom", "NATIVE", "Loom – Mac version available"),
    (r"^malwarebytes", "NATIVE", "Malwarebytes – Mac version available"),
    (r"^mattermost", "NATIVE", "Mattermost – Mac version available"),
    (r"^microsoft (office|word|excel|powerpoint|outlook|teams|onenote|onedrive|visio|project)", "NATIVE", "Microsoft Office – Mac version available"),
    (r"^microsoft (edge|vs code|visual studio code)", "NATIVE", "Available on Mac"),
    (r"^microsoft visual studio\b", "ALTERNATIVE", "Use Xcode or JetBrains Rider on Mac; VS for Mac is discontinued"),
    (r"^macrium reflect", "ALTERNATIVE", "Use Time Machine (built-in) or Carbon Copy Cloner on Mac"),
    (r"^miro", "NATIVE", "Miro – Mac version available"),
    (r"^moonlight (game streaming)?", "NATIVE", "Moonlight – Mac version available"),
    (r"^mozilla firefox", "NATIVE", "Firefox – Mac version available"),
    (r"^mozilla maintenance", "SKIP", "Firefox Windows updater service"),
    (r"^mpc-hc", "ALTERNATIVE", "Use IINA or VLC on Mac"),
    (r"^mongodb compass", "NATIVE", "MongoDB Compass – Mac version available"),
    (r"^mpv", "NATIVE", "mpv – Mac version available via Homebrew"),
    (r"^mus(ic)?ic bee|^musicbee", "ALTERNATIVE", "Use Swinsian or Vox on Mac"),
    (r"^node\.?js|^node js", "NATIVE", "Node.js – Mac version available"),
    (r"^notepad\+\+", "ALTERNATIVE", "Use BBEdit, Nova, or VS Code on Mac"),
    (r"^nmap\b", "NATIVE", "Nmap – available via Homebrew on Mac"),
    (r"^nordvpn", "NATIVE", "NordVPN – Mac version available"),
    (r"^notion", "NATIVE", "Notion – Mac version available"),
    (r"^obs studio|^obs$", "NATIVE", "OBS Studio – Mac version available"),
    (r"^obsidian", "NATIVE", "Obsidian – Mac version available"),
    (r"^openoffice", "NATIVE", "OpenOffice – Mac version available (consider LibreOffice instead)"),
    (r"^open.?vpn", "NATIVE", "OpenVPN – Mac version available"),
    (r"^postman", "NATIVE", "Postman – Mac version available"),
    (r"^powershell|^powertoys", "NATIVE", "PowerShell / PowerToys – Mac version available"),
    (r"^putty", "ALTERNATIVE", "Use built-in Terminal + SSH on Mac; or SecureCRT, SSH config"),
    (r"^python", "NATIVE", "Python – Mac version available"),
    (r"^resolume", "NATIVE", "Resolume – Mac version available"),
    (r"^rust(up|-lang)?", "NATIVE", "Rust – Mac version available"),
    (r"^signal", "NATIVE", "Signal – Mac version available"),
    (r"^sketch", "NATIVE", "Sketch – Mac only (already on Mac)"),
    (r"^slack", "NATIVE", "Slack – Mac version available"),
    (r"^sourcetree", "NATIVE", "Sourcetree – Mac version available"),
    (r"^spotify", "NATIVE", "Spotify – Mac version available"),
    (r"^steam", "NATIVE", "Steam – Mac version available"),
    (r"^sublime (text|merge)", "NATIVE", "Sublime – Mac version available"),
    (r"^tableplus", "NATIVE", "TablePlus – Mac version available"),
    (r"^telegram", "NATIVE", "Telegram – Mac version available"),
    (r"^thunderbird", "NATIVE", "Thunderbird – Mac version available"),
    (r"^tor browser", "NATIVE", "Tor Browser – Mac version available"),
    (r"^totalcommander|^total commander", "ALTERNATIVE", "Use ForkLift, Commander One, or Marta on Mac"),
    (r"^typora", "NATIVE", "Typora – Mac version available"),
    (r"^unity( hub)?", "NATIVE", "Unity – Mac version available"),
    (r"^unreal engine", "NATIVE", "Unreal Engine – Mac version available"),
    (r"^vagrant", "NATIVE", "Vagrant – Mac version available"),
    (r"^virtualbox", "NATIVE", "VirtualBox – Mac version available (limited on Apple Silicon)"),
    (r"^vlc", "NATIVE", "VLC – Mac version available"),
    (r"^vscode|^visual studio code", "NATIVE", "VS Code – Mac version available"),
    (r"^whatsapp", "NATIVE", "WhatsApp – Mac version available"),
    (r"^wireshark", "NATIVE", "Wireshark – Mac version available"),
    (r"^wsl|^windows subsystem", "SKIP", "Windows feature – not applicable on Mac"),
    (r"^xcode", "NATIVE", "Xcode – Mac only (install on Mac)"),
    (r"^zoom", "NATIVE", "Zoom – Mac version available"),
    (r"^zotero", "NATIVE", "Zotero – Mac version available"),
    (r"^7-zip", "ALTERNATIVE", "Use The Unarchiver or Keka on Mac (built-in Archive Utility also works)"),
    (r"winrar|winzip", "ALTERNATIVE", "Use The Unarchiver or Keka on Mac"),
    (r"^winscp", "ALTERNATIVE", "Use Cyberduck or Transmit on Mac"),
    (r"^winmerge", "ALTERNATIVE", "Use FileMerge (free, Xcode) or Kaleidoscope on Mac"),
    (r"^procmon|^process monitor|^process explorer|^sysinternals", "ALTERNATIVE", "Use Activity Monitor + fs_usage on Mac"),
    (r"^autoruns", "SKIP", "Windows-specific startup manager"),
    (r"^nirsoft|^nirlaunch", "SKIP", "Windows-only utilities"),
    (r"^hwinfo|^hwmonitor|^speccy", "ALTERNATIVE", "Use iStatistica, HWMonitorPro, or GPU Monitor Pro on Mac"),
    (r"msiafterburner|afterburner", "SKIP", "GPU overclocking – Windows/Nvidia only"),
    (r"^ccleaner|^defraggler|^recuva|^piriform", "ALTERNATIVE", "Use CleanMyMac or built-in Storage Management on Mac"),
    (r"teamviewer", "NATIVE", "TeamViewer – Mac version available"),
    (r"^rufus", "ALTERNATIVE", "Use balenaEtcher or dd on Mac"),
    (r"^cryptomator", "NATIVE", "Cryptomator – Mac version available"),
    (r"^paint\.net", "ALTERNATIVE", "Use Pixelmator Pro or Affinity Photo on Mac"),
    (r"^paradox launcher", "SKIP", "Windows game launcher"),
    (r"^pingplotter", "NATIVE", "PingPlotter – Mac version available"),
    (r"^protonvpn", "NATIVE", "ProtonVPN – Mac version available"),
    (r"^questrade iq edge", "NATIVE", "Questrade IQ Edge – Mac version available"),
    (r"^rainmeter", "ALTERNATIVE", "Use Ubersicht or GeekTool on Mac"),
    (r"^roon\b", "NATIVE", "Roon – Mac version available"),
    (r"^skype\b", "NATIVE", "Skype – Mac version available"),
    (r"^sonos\b", "NATIVE", "Sonos – Mac version available"),
    (r"^synergy\b", "NATIVE", "Synergy – Mac version available"),
    (r"^tightvnc", "ALTERNATIVE", "Use built-in Screen Sharing or RealVNC Viewer on Mac"),
    (r"^trader workstation", "NATIVE", "Interactive Brokers TWS – Mac version available"),
    (r"^tunepat", "NATIVE", "TunePat – Mac version available"),
    (r"^veeam agent", "ALTERNATIVE", "Use Time Machine or Carbon Copy Cloner on Mac"),
    (r"^vmware horizon client", "NATIVE", "VMware Horizon Client – Mac version available"),
    (r"^vmware workstation", "ALTERNATIVE", "Use VMware Fusion on Mac (Apple Silicon supported)"),
    (r"^wargaming\.net game center", "ALTERNATIVE", "Use Steam or native game launchers on Mac"),
    (r"^windirstat", "ALTERNATIVE", "Use GrandPerspective or DaisyDisk on Mac"),
    (r"^wireguard", "NATIVE", "WireGuard – Mac version available"),
    (r"^x2go", "ALTERNATIVE", "Use built-in Screen Sharing, NoMachine, or SSH X11 on Mac"),
    (r"^yarn\b", "NATIVE", "Yarn – available via Homebrew on Mac"),
    (r"^zoiper", "NATIVE", "Zoiper SIP – Mac version available"),
    (r"^gpl ghostscript", "NATIVE", "Ghostscript – available via Homebrew on Mac"),
    (r"^aes crypt", "NATIVE", "AES Crypt – Mac version available"),

    # --- Windows-only system components → SKIP ---
    (r"(update|redistributable|runtime|framework|driver|service pack|hotfix|kb\d{6})", "SKIP", "Windows system component"),
    (r"(windows|microsoft) (security|defender|hello|ink|cortana|mixed reality|holographic)", "SKIP", "Windows feature"),
]

COMPILED = [(re.compile(pat, re.IGNORECASE), cat, note) for pat, cat, note in RULES]


def classify(name: str):
    for pattern, category, note in COMPILED:
        if pattern.search(name):
            return category, note
    return "REVIEW", "No match found – check manually"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    base        = pathlib.Path.home() / "Documents" / "mac-migration"
    csv_path    = base / "installed_programs.csv"
    report_path = base / "mac_migration_report.md"

    if not csv_path.exists():
        print(f"ERROR: {csv_path} not found.")
        print("Run extract_installed.ps1 first.")
        sys.exit(1)

    print("Loading Homebrew index…")
    brew_index = load_brew_index(base)
    print()

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    # buckets: list of (name, version, publisher, note, brew_cmd)
    buckets: dict[str, list] = {"NATIVE": [], "ALTERNATIVE": [], "REVIEW": [], "SKIP": [], "GAME": []}

    for row in rows:
        name      = row.get("Name", "").strip()
        version   = row.get("Version", "").strip()
        publisher = row.get("Publisher", "").strip()
        if not name:
            continue
        cat, note = classify(name)
        brew_cmd  = brew_command(name, brew_index) if cat == "NATIVE" else ""
        buckets[cat].append((name, version, publisher, note, brew_cmd))

    for cat in buckets:
        buckets[cat].sort(key=lambda x: x[0].lower())

    # ---- Brew stats ----
    native_total     = len(buckets["NATIVE"])
    native_on_brew   = sum(1 for *_, bc in buckets["NATIVE"] if bc)
    native_no_brew   = native_total - native_on_brew

    # ----- Write report -----
    lines = []
    lines.append("# Mac Migration — App Compatibility Report")
    lines.append(f"_Generated {date.today()}  •  Source: installed_programs.csv_\n")

    total = sum(len(v) for v in buckets.values())
    lines.append("## Summary\n")
    lines.append("| Category | Count |")
    lines.append("|----------|------:|")
    lines.append(f"| ✅ Native / cross-platform | {native_total} |")
    lines.append(f"| &nbsp;&nbsp;&nbsp;↳ on Homebrew | {native_on_brew} |")
    lines.append(f"| &nbsp;&nbsp;&nbsp;↳ manual install | {native_no_brew} |")
    lines.append(f"| 🔄 Alternative available   | {len(buckets['ALTERNATIVE'])} |")
    lines.append(f"| ❓ Needs review            | {len(buckets['REVIEW'])} |")
    lines.append(f"| 🎮 Games                   | {len(buckets['GAME'])} |")
    lines.append(f"| ⛔ Skip (Windows-only)     | {len(buckets['SKIP'])} |")
    lines.append(f"| **Total scanned**          | **{total}** |\n")

    # ---- NATIVE: split into brew / no-brew ----
    brew_apps   = [(n, v, p, note, bc) for n, v, p, note, bc in buckets["NATIVE"] if bc]
    manual_apps = [(n, v, p, note, bc) for n, v, p, note, bc in buckets["NATIVE"] if not bc]

    lines.append("---\n")
    lines.append("## ✅ Install on Mac — same app exists\n")

    lines.append("### 🍺 Available on Homebrew\n")
    lines.append("Run the brew command to install.\n")
    lines.append("| App | Windows Version | Homebrew command |")
    lines.append("|-----|----------------|-----------------|")
    for name, version, publisher, note, brew_cmd in brew_apps:
        v = version if version else "—"
        lines.append(f"| {name} | {v} | `{brew_cmd}` |")

    lines.append("\n### 📦 Not on Homebrew — install manually\n")
    lines.append("Download from the vendor's website.\n")
    lines.append("| App | Windows Version | Note |")
    lines.append("|-----|----------------|------|")
    for name, version, publisher, note, brew_cmd in manual_apps:
        v = version if version else "—"
        lines.append(f"| {name} | {v} | {note} |")

    # ---- ALTERNATIVE ----
    lines.append("\n---\n")
    lines.append("## 🔄 Install on Mac — use an alternative\n")
    lines.append("The Windows app has no direct Mac port. A recommended alternative is listed.\n")
    lines.append("| Windows App | Version | Mac Alternative |")
    lines.append("|-------------|---------|-----------------|")
    for name, version, publisher, note, _ in buckets["ALTERNATIVE"]:
        v = version if version else "—"
        lines.append(f"| {name} | {v} | {note} |")

    # ---- REVIEW ----
    lines.append("\n---\n")
    lines.append("## ❓ Review manually\n")
    lines.append("These apps were not recognised. Check each one: does it have a Mac version?\n")
    lines.append("| App | Version | Publisher |")
    lines.append("|-----|---------|-----------|")
    for name, version, publisher, note, _ in buckets["REVIEW"]:
        v = version if version else "—"
        p = publisher if publisher else "—"
        lines.append(f"| {name} | {v} | {p} |")

    # ---- GAME ----
    lines.append("\n---\n")
    lines.append("## 🎮 Games\n")
    lines.append("These are games or game launchers. Check Steam/GOG for Mac availability per title.\n")
    lines.append("| Game | Publisher |")
    lines.append("|------|-----------|")
    for name, version, publisher, note, _ in buckets["GAME"]:
        p = publisher if publisher else "—"
        lines.append(f"| {name} | {p} |")

    # ---- SKIP ----
    lines.append("\n---\n")
    lines.append("## ⛔ Skip — Windows-only / system components\n")
    lines.append("<details><summary>Show skipped items</summary>\n")
    lines.append("| App | Reason |")
    lines.append("|-----|--------|")
    for name, version, publisher, note, _ in buckets["SKIP"]:
        lines.append(f"| {name} | {note} |")
    lines.append("\n</details>")

    # ---- Brew install script ----
    brew_script_path = base / "brew_install.sh"
    brew_lines = [
        "#!/usr/bin/env bash",
        "# Auto-generated brew install script",
        f"# Generated {date.today()} from mac_migration_report.md",
        "# Run on your Mac: bash brew_install.sh",
        "",
        "# Install Homebrew if not present",
        'if ! command -v brew &>/dev/null; then',
        '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"',
        "fi",
        "",
    ]
    for name, version, publisher, note, brew_cmd in brew_apps:
        brew_lines.append(f"# {name}")
        brew_lines.append(brew_cmd)
        brew_lines.append("")
    brew_script_path.write_text("\n".join(brew_lines), encoding="utf-8")

    report_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Report written  : {report_path}")
    print(f"Brew script     : {brew_script_path}")
    print(f"\nSummary:")
    print(f"  [NATIVE] total         : {native_total}")
    print(f"    on Homebrew          : {native_on_brew}")
    print(f"    manual install       : {native_no_brew}")
    print(f"  [ALT]    alternatives  : {len(buckets['ALTERNATIVE'])}")
    print(f"  [REVIEW] needs review  : {len(buckets['REVIEW'])}")
    print(f"  [GAME]   games         : {len(buckets['GAME'])}")
    print(f"  [SKIP]   skip          : {len(buckets['SKIP'])}")
    print(f"  Total                  : {total}")


if __name__ == "__main__":
    main()
