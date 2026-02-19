# ==== PART 1a STARTS HERE ====
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont
import threading, time, re, sys, traceback, json, os
import urllib.request
from pathlib import Path
from datetime import datetime, UTC, timedelta

# Regex helpers
TAG_RX = re.compile(r"<[^>]+>")
BRACKET_PREFIX_RX = re.compile(r"^\[.*?\]\s*\(\w+\)\s*")
LISTENER_RX = re.compile(r"^\s*Listener:\s*(?P<char>.+)$", re.IGNORECASE)
SESSION_RX = re.compile(r"^\s*Session Started:\s*(?P<ts>\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})", re.IGNORECASE)
TIMESTAMP_RX = re.compile(r"^\[\s*(\d{4}\.\d{2}\.\d{2})\s+(\d{2}:\d{2}:\d{2})\s*\]")

def clean_line(raw: str) -> str:
    s = raw.replace("\r", "")
    s = BRACKET_PREFIX_RX.sub("", s)
    s = TAG_RX.sub("", s)
    return re.sub(r"\s+", " ", s).strip()

def extract_timestamp(raw: str):
    """Extract timestamp from a raw log line, if present."""
    try:
        m = TIMESTAMP_RX.search(raw)
        if not m:
            return None
        ts = f"{m.group(1)} {m.group(2)}"
        return datetime.strptime(ts, "%Y.%m.%d %H:%M:%S")
    except Exception:
        return None

# Mining regex
MINED_RX    = re.compile(r"You mined\s+(\d+)\s+units\s+of\s+([A-Za-z0-9\s'\-]+)$", re.IGNORECASE)
RESIDUE_RX  = re.compile(r"Additional\s+(\d+)\s+units\s+depleted\s+from\s+asteroid\s+as\s+residue$", re.IGNORECASE)
CRIT_RX     = re.compile(r"Critical mining success!.*?additional\s+(\d+)\s+units\s+of\s+([A-Za-z0-9\s'\-]+)$", re.IGNORECASE)
COMPRESS_RX = re.compile(r"Successfully compressed", re.IGNORECASE)
DEPLETED_RX = re.compile(r"Asteroid\s+.+\s+has\s+been\s+depleted", re.IGNORECASE)

# Resource sets
RESOURCE_TYPES = {
    "ice": {"Blue Ice","Clear Icicle","Glacial Mass","White Glaze","Dark Glitter","Gelidus","Krystallos"},
    "compressed_ice": {"Compressed Blue Ice","Compressed Clear Icicle","Compressed Glacial Mass","Compressed White Glaze","Compressed Dark Glitter","Compressed Gelidus","Compressed Krystallos"},
    "ore": {"Veldspar","Scordite","Pyroxeres","Plagioclase","Omber","Kernite","Jaspet","Hemorphite","Hedbergite","Gneiss","Dark Ochre","Spodumain","Crokite","Bistot","Arkonor","Mercoxit"},
    "gas": {"Mykoserocin","Cytoserocin","Fullerite-C50","Fullerite-C60","Fullerite-C70","Fullerite-C72","Fullerite-C84","Fullerite-C320","Fullerite-C540"}
}



# Map resource names to unit volumes (m³ per unit)
UNIT_VOLUME = {
    "Blue Ice": 1000,
    "Clear Icicle": 1000,
    "Glacial Mass": 1000,
    "White Glaze": 1000,
    "Dark Glitter": 1000,
    "Gelidus": 1000,
    "Krystallos": 1000,
    "Compressed Blue Ice": 100,
    "Compressed Clear Icicle": 100,
    "Compressed Glacial Mass": 100,
    "Compressed White Glaze": 100,
    "Compressed Dark Glitter": 100,
    "Compressed Gelidus": 100,
    "Compressed Krystallos": 100,
    "Veldspar": 0.1,
    "Scordite": 0.15,
    "Pyroxeres": 0.3,
    "Plagioclase": 0.35,
    "Omber": 0.6,
    "Kernite": 1.2,
    "Jaspet": 2.0,
    "Hemorphite": 3.0,
    "Hedbergite": 3.0,
    "Gneiss": 5.0,
    "Dark Ochre": 8.0,
    "Spodumain": 16.0,
    "Crokite": 16.0,
    "Bistot": 16.0,
    "Arkonor": 16.0,
    "Mercoxit": 40.0,
    "Mykoserocin": 10.0,
    "Cytoserocin": 10.0,
    "Fullerite-C50": 5.0,
    "Fullerite-C60": 5.0,
    "Fullerite-C70": 5.0,
    "Fullerite-C72": 5.0,
    "Fullerite-C84": 5.0,
    "Fullerite-C320": 5.0,
    "Fullerite-C540": 5.0,
}

# ESI type IDs for ores, ice, and gas (used to auto-refresh prices)
ESI_TYPEIDS = {
    "Veldspar": 1230,
    "Scordite": 1228,
    "Pyroxeres": 1224,
    "Plagioclase": 18,
    "Omber": 1231,
    "Kernite": 20,
    "Jaspet": 1229,
    "Hemorphite": 1232,
    "Hedbergite": 21,
    "Gneiss": 1225,
    "Dark Ochre": 1233,
    "Spodumain": 19,
    "Crokite": 1226,
    "Bistot": 1227,
    "Arkonor": 22,
    "Mercoxit": 11396,
    "Blue Ice": 16262,
    "Clear Icicle": 16263,
    "Glacial Mass": 16264,
    "White Glaze": 16265,
    "Dark Glitter": 16266,
    "Gelidus": 16267,
    "Krystallos": 16268,
    "Mykoserocin": 25268,
    "Cytoserocin": 28606,
    "Fullerite-C50": 30370,
    "Fullerite-C60": 30371,
    "Fullerite-C70": 30372,
    "Fullerite-C72": 30373,
    "Fullerite-C84": 30374,
    "Fullerite-C320": 30375,
    "Fullerite-C540": 30376,
}

APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
PRICE_FILE = APP_DIR / "prices.json"
PROFILE_CACHE_FILE = APP_DIR / "profile_index_cache.json"

def load_profile_cache() -> dict:
    try:
        if PROFILE_CACHE_FILE.exists():
            data = json.loads(PROFILE_CACHE_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        else:
            data = {}
        files = data.get("files")
        if not isinstance(files, dict):
            data["files"] = {}
        return data
    except Exception:
        return {"files": {}}

def save_profile_cache(cache: dict):
    try:
        if not isinstance(cache, dict):
            return
        files = cache.get("files")
        if not isinstance(files, dict):
            cache = {"files": {}}
        PROFILE_CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")
    except Exception:
        pass

def _normalize_price_map(prices: dict) -> dict:
    normalized = {}
    for k in UNIT_VOLUME.keys():
        try:
            normalized[k] = float(prices.get(k, 0.0))
        except Exception:
            normalized[k] = 0.0
    return normalized

def load_price_map() -> dict:
    try:
        if PRICE_FILE.exists():
            data = json.loads(PRICE_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        else:
            data = {}
        normalized = _normalize_price_map(data)
        if not PRICE_FILE.exists() or normalized != data:
            try:
                PRICE_FILE.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
            except Exception:
                pass
        return normalized
    except Exception:
        return _normalize_price_map({})

def save_price_map(prices: dict):
    try:
        normalized = _normalize_price_map(prices)
        PRICE_FILE.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    except Exception:
        pass

def _fetch_esi_prices() -> dict:
    """Fetch average prices from ESI and return a name->price map."""
    try:
        url = "https://esi.evetech.net/latest/markets/prices/?datasource=tranquility"
        req = urllib.request.Request(url, headers={"User-Agent": "CalmDownMiner/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if not isinstance(payload, list):
            return {}
        price_by_id = {}
        for row in payload:
            if not isinstance(row, dict):
                continue
            tid = row.get("type_id")
            price = row.get("average_price")
            if tid is None or price is None:
                continue
            price_by_id[tid] = price
        results = {}
        for name, tid in ESI_TYPEIDS.items():
            price = price_by_id.get(tid)
            if price is None:
                continue
            try:
                results[name] = float(price)
            except Exception:
                continue
        return results
    except Exception:
        return {}

def refresh_esi_price_map(prices: dict | None = None) -> dict:
    """Update prices in prices.json using ESI average prices."""
    current = load_price_map() if prices is None else _normalize_price_map(prices)
    esi_prices = _fetch_esi_prices()
    if not esi_prices:
        return current
    updated = dict(current)
    updated.update(esi_prices)
    save_price_map(updated)
    return updated

def format_isk(value: float) -> str:
    try:
        return f"{value:,.2f} ISK"
    except Exception:
        return "0.00 ISK"

def hsv_to_hex(hue: int, saturation: float = 1.0, value: float = 1.0) -> str:
    """Convert HSV color to hex string. Hue is 0-360, saturation and value are 0-1."""
    import colorsys
    try:
        h = (hue % 360) / 360.0
        r, g, b = colorsys.hsv_to_rgb(h, saturation, value)
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
    except Exception:
        return "#00D4FF"  # Default cyan
# ==== PART 1a ENDS HERE ====
# ==== PART 1b STARTS HERE ====
class MiningState:
    def __init__(self):
        self.total_units = 0
        self.total_residue = 0
        self.crits = 0
        self.extra_from_crits = 0
        self.by_resource = {}
        self.last_update = None
        self.session_start = None
        self._lock = threading.Lock()

    def reset(self):
        with self._lock:
            self.total_units = 0
            self.total_residue = 0
            self.crits = 0
            self.extra_from_crits = 0
            self.by_resource.clear()
            self.last_update = None
            self.session_start = None

    def add_mined(self, name: str, qty: int):
        with self._lock:
            self.total_units += qty
            self.by_resource[name] = self.by_resource.get(name, 0) + qty
            self.last_update = datetime.now(UTC)

    def add_residue(self, qty: int):
        with self._lock:
            self.total_residue += qty
            self.last_update = datetime.now(UTC)

    def add_crit(self, name: str, qty: int):
        with self._lock:
            self.crits += 1
            self.extra_from_crits += qty
            self.by_resource[name] = self.by_resource.get(name, 0) + qty
            self.last_update = datetime.now(UTC)

    def rate_units_per_min(self):
        if not self.session_start:
            return 0.0
        elapsed = (datetime.now(UTC) - self.session_start).total_seconds()
        if elapsed <= 0:
            return 0.0
        return (self.total_units / elapsed) * 60.0

    def total_volume(self):
        vol = 0.0
        for res, qty in self.by_resource.items():
            vol += qty * UNIT_VOLUME.get(res, 0.0)
        return vol


class FileTailer(threading.Thread):
    def __init__(self, path: Path, state: MiningState, session_state: MiningState, stop_event):
        super().__init__(daemon=True)
        self.path = path
        self.state = state
        self.session_state = session_state
        self.stop_event = stop_event
        self.fp = None

    def run(self):
        try:
            self.fp = self.path.open("r", encoding="utf-8", errors="ignore")
            for line in self.fp:
                self.process(line)
        except Exception:
            traceback.print_exc(file=sys.stdout)
            return
        while not self.stop_event.is_set():
            line = self.fp.readline()
            if not line:
                time.sleep(0.3)
                continue
            self.process(line)
        try:
            if self.fp:
                self.fp.close()
        except Exception:
            pass

    def process(self, raw: str):
        s = clean_line(raw)
        if not s:
            return
        if COMPRESS_RX.search(s):
            self.state.reset()
            self.state.session_start = datetime.now(UTC)
            return
        m = MINED_RX.search(s)
        if m:
            qty = int(m.group(1))
            name = m.group(2).strip()
            self.state.add_mined(name, qty)
            self.session_state.add_mined(name, qty)
            return
        r = RESIDUE_RX.search(s)
        if r:
            qty = int(r.group(1))
            self.state.add_residue(qty)
            self.session_state.add_residue(qty)
            return
        c = CRIT_RX.search(s)
        if c:
            qty = int(c.group(1))
            name = c.group(2).strip()
            self.state.add_crit(name, qty)
            self.session_state.add_crit(name, qty)
            return
        d = DEPLETED_RX.search(s)
        if d:
            self.state.last_update = datetime.now(UTC)
            return


def _parse_header_info(p: Path):
    char_name, session_dt = None, None
    try:
        with p.open("r", encoding="utf-8", errors="ignore") as fp:
            for _ in range(80):
                hl = fp.readline()
                if not hl:
                    break
                if LISTENER_RX.search(hl) and not char_name:
                    char_name = LISTENER_RX.search(hl).group("char").strip()
                if SESSION_RX.search(hl) and not session_dt:
                    ts = SESSION_RX.search(hl).group("ts").strip()
                    session_dt = datetime.strptime(ts, "%Y.%m.%d %H:%M:%S").replace(tzinfo=UTC)
                if char_name and session_dt:
                    break
    except Exception:
        pass
    return char_name, session_dt

def extract_header_info(p: Path, cache: dict | None = None):
    char_name, session_dt = None, None
    try:
        mtime = p.stat().st_mtime
    except Exception:
        mtime = None
    cache_changed = False
    if cache is not None and mtime is not None:
        try:
            files_cache = cache.get("files")
            if not isinstance(files_cache, dict):
                files_cache = {}
                cache["files"] = files_cache
            key = str(p.resolve())
            entry = files_cache.get(key)
            if entry and entry.get("mtime") == mtime:
                char_name = entry.get("char")
                session = entry.get("session")
                if session:
                    try:
                        session_dt = datetime.fromisoformat(session)
                    except Exception:
                        session_dt = None
                return char_name, session_dt
        except Exception:
            pass

    char_name, session_dt = _parse_header_info(p)
    if cache is not None and mtime is not None:
        try:
            files_cache = cache.get("files")
            if not isinstance(files_cache, dict):
                files_cache = {}
                cache["files"] = files_cache
            key = str(p.resolve())
            files_cache[key] = {
                "mtime": mtime,
                "char": char_name,
                "session": session_dt.isoformat() if session_dt else None,
            }
            cache_changed = True
        except Exception:
            pass
    if cache_changed:
        save_profile_cache(cache)
    return char_name, session_dt

def build_char_index(folder: Path, cache: dict | None = None):
    index = {}
    if not folder.exists():
        return index
    if cache is None:
        cache = load_profile_cache()
    try:
        files_cache = cache.get("files")
        if not isinstance(files_cache, dict):
            files_cache = {}
            cache["files"] = files_cache
    except Exception:
        files_cache = {}
        cache = {"files": files_cache}

    cache_changed = False
    mtime_map = {}
    files = list(folder.glob("*.txt"))
    for f in files:
        try:
            mtime = f.stat().st_mtime
        except Exception:
            continue
        mtime_map[f] = mtime
        key = str(f.resolve())
        entry = files_cache.get(key)
        if entry and entry.get("mtime") == mtime:
            char = entry.get("char")
        else:
            char, session_dt = _parse_header_info(f)
            files_cache[key] = {
                "mtime": mtime,
                "char": char,
                "session": session_dt.isoformat() if session_dt else None,
            }
            cache_changed = True
        if not char:
            continue
        index.setdefault(char, []).append(f)
    if cache_changed:
        save_profile_cache(cache)
    for char, flist in index.items():
        flist.sort(key=lambda x: mtime_map.get(x, 0.0), reverse=True)
    return index

def latest_log_for_char(char: str, char_index: dict) -> Path | None:
    files = char_index.get(char, [])
    return files[0] if files else None

def get_newest_profiles(char_index: dict, count: int) -> list:
    """Get the characters with the newest log files, sorted by most recent."""
    profile_times = []
    for char, files in char_index.items():
        if files:
            # Get the newest file for this character
            newest_file = files[0]
            mtime = newest_file.stat().st_mtime
            profile_times.append((char, mtime))
    # Sort by modification time, newest first
    profile_times.sort(key=lambda x: x[1], reverse=True)
    # Return the character names
    return [char for char, _ in profile_times[:count]]

def compute_monthly_isk_for_folder(folder: Path, year: int, month: int, prices: dict):
    """Scan logs for the given month and compute ISK using the price map."""
    qty_by_resource = {}
    total_isk = 0.0
    if not folder or not folder.exists():
        return total_isk, qty_by_resource
    try:
        files = list(folder.glob("*.txt"))
    except Exception:
        files = []
    for f in files:
        try:
            with f.open("r", encoding="utf-8", errors="ignore") as fp:
                for raw in fp:
                    ts = extract_timestamp(raw)
                    if not ts or ts.year != year or ts.month != month:
                        continue
                    s = clean_line(raw)
                    if not s:
                        continue
                    m = MINED_RX.search(s)
                    if m:
                        qty = int(m.group(1))
                        name = m.group(2).strip()
                        qty_by_resource[name] = qty_by_resource.get(name, 0) + qty
                        continue
                    c = CRIT_RX.search(s)
                    if c:
                        qty = int(c.group(1))
                        name = c.group(2).strip()
                        qty_by_resource[name] = qty_by_resource.get(name, 0) + qty
                        continue
        except Exception:
            pass
    for res, qty in qty_by_resource.items():
        try:
            price = float(prices.get(res, 0.0) or 0.0)
        except Exception:
            price = 0.0
        total_isk += qty * price
    return total_isk, qty_by_resource

def compute_daily_isk_for_folder(folder: Path, day: datetime, prices: dict, start_time: datetime = None):
    """Scan logs for a specific day and compute ISK using the price map.
    If start_time is provided, only count ISK mined after that time."""
    qty_by_resource = {}
    total_isk = 0.0
    if not folder or not folder.exists():
        return total_isk, qty_by_resource
    try:
        files = list(folder.glob("*.txt"))
    except Exception:
        files = []
    for f in files:
        try:
            with f.open("r", encoding="utf-8", errors="ignore") as fp:
                for raw in fp:
                    ts = extract_timestamp(raw)
                    if not ts or ts.year != day.year or ts.month != day.month or ts.day != day.day:
                        continue
                    # If start_time is specified, only count after that time
                    if start_time and ts < start_time:
                        continue
                    s = clean_line(raw)
                    if not s:
                        continue
                    m = MINED_RX.search(s)
                    if m:
                        qty = int(m.group(1))
                        name = m.group(2).strip()
                        qty_by_resource[name] = qty_by_resource.get(name, 0) + qty
                        continue
                    c = CRIT_RX.search(s)
                    if c:
                        qty = int(c.group(1))
                        name = c.group(2).strip()
                        qty_by_resource[name] = qty_by_resource.get(name, 0) + qty
                        continue
        except Exception:
            pass
    for res, qty in qty_by_resource.items():
        try:
            price = float(prices.get(res, 0.0) or 0.0)
        except Exception:
            price = 0.0
        total_isk += qty * price
    return total_isk, qty_by_resource

def compute_weekly_isk_for_folder(folder: Path, prices: dict):
    """Scan logs for the current week (Monday to Sunday) and compute ISK using the price map."""
    qty_by_resource = {}
    total_isk = 0.0
    if not folder or not folder.exists():
        return total_isk, qty_by_resource
    
    # Get current week's Monday 00:00:00 to Sunday 23:59:59
    now = datetime.now()
    # weekday() returns 0=Monday, 6=Sunday
    days_since_monday = now.weekday()
    monday = now - timedelta(days=days_since_monday)
    monday_start = datetime(monday.year, monday.month, monday.day, 0, 0, 0)
    sunday_end = monday_start + timedelta(days=7)
    
    try:
        files = list(folder.glob("*.txt"))
    except Exception:
        files = []
    for f in files:
        try:
            with f.open("r", encoding="utf-8", errors="ignore") as fp:
                for raw in fp:
                    ts = extract_timestamp(raw)
                    if not ts or ts < monday_start or ts >= sunday_end:
                        continue
                    s = clean_line(raw)
                    if not s:
                        continue
                    m = MINED_RX.search(s)
                    if m:
                        qty = int(m.group(1))
                        name = m.group(2).strip()
                        qty_by_resource[name] = qty_by_resource.get(name, 0) + qty
                        continue
                    c = CRIT_RX.search(s)
                    if c:
                        qty = int(c.group(1))
                        name = c.group(2).strip()
                        qty_by_resource[name] = qty_by_resource.get(name, 0) + qty
                        continue
        except Exception:
            pass
    for res, qty in qty_by_resource.items():
        try:
            price = float(prices.get(res, 0.0) or 0.0)
        except Exception:
            price = 0.0
        total_isk += qty * price
    return total_isk, qty_by_resource
# ==== PART 1b ENDS HERE ====
# ==== PART 2 (PANEL LAYOUT WITH MANUAL PRICE ENTRY, SIX-ARG INIT) ====

class Panel(ttk.Frame):
    def __init__(self, parent, state, session_state, log=None, folder=None, style=None):
        super().__init__(parent)
        self.state = state
        self.session_state = session_state
        self.log = log
        self.folder = folder
        self.style = style
        # default hold percent text color (updated by App.apply_theme)
        self.default_hold_fg = '#000000'
        
        # Initialize tailer attributes
        self.tailer = None
        self.stop_event = threading.Event()

        # Variables
        self.ice_var = tk.StringVar(value="0")
        self.res_var = tk.StringVar(value="0")
        self.crit_var = tk.StringVar(value="0")
        self.extra_var = tk.StringVar(value="0")

        self.session_ice_var = tk.StringVar(value="0")
        self.session_res_var = tk.StringVar(value="0")
        self.session_crit_var = tk.StringVar(value="0")
        self.session_extra_var = tk.StringVar(value="0")

        self.res_pct_var = tk.StringVar(value="0.0%")
        self.crit_pct_var = tk.StringVar(value="0.0%")
        self.session_rate_var = tk.StringVar(value="0.0")
        # Current-side percentage and rate variables
        self.res_pct_current_var = tk.StringVar(value="0.0%")
        self.crit_pct_current_var = tk.StringVar(value="0.0%")
        self.current_rate_var = tk.StringVar(value="0.0")
        self.total_current_var = tk.StringVar(value="0")
        self.total_session_var = tk.StringVar(value="0")

        # Layout - header row
        ttk.Label(self, text="Stat").grid(row=0, column=0, sticky="w")
        ttk.Label(self, text="Current").grid(row=0, column=1, sticky="w")
        ttk.Label(self, text="Session").grid(row=0, column=2, sticky="w")
        # Make columns equal width so they sit closer to each other
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=1)

        # Units
        ttk.Label(self, text="Units:").grid(row=1, column=0, sticky="w")
        ttk.Label(self, textvariable=self.ice_var).grid(row=1, column=1, sticky="w")
        ttk.Label(self, textvariable=self.session_ice_var).grid(row=1, column=2, sticky="w")

        # Residue
        ttk.Label(self, text="Residue:").grid(row=2, column=0, sticky="w")
        ttk.Label(self, textvariable=self.res_var).grid(row=2, column=1, sticky="w")
        ttk.Label(self, textvariable=self.session_res_var).grid(row=2, column=2, sticky="w")

        # Crits
        ttk.Label(self, text="Crits:").grid(row=3, column=0, sticky="w", padx=1, pady=0)
        ttk.Label(self, textvariable=self.crit_var).grid(row=3, column=1, sticky="w", padx=1, pady=0)
        ttk.Label(self, textvariable=self.session_crit_var).grid(row=3, column=2, sticky="w", padx=1, pady=0)

        # Extra
        ttk.Label(self, text="Extra from Crits:").grid(row=4, column=0, sticky="w", padx=1, pady=0)
        ttk.Label(self, textvariable=self.extra_var).grid(row=4, column=1, sticky="w", padx=1, pady=0)
        ttk.Label(self, textvariable=self.session_extra_var).grid(row=4, column=2, sticky="w", padx=1, pady=0)

        # Percentages (current and session)
        ttk.Label(self, text="Residue %:").grid(row=5, column=0, sticky="w")
        ttk.Label(self, textvariable=self.res_pct_current_var).grid(row=5, column=1, sticky="w")
        ttk.Label(self, textvariable=self.res_pct_var).grid(row=5, column=2, sticky="w")

        ttk.Label(self, text="Crit %:").grid(row=6, column=0, sticky="w")
        ttk.Label(self, textvariable=self.crit_pct_current_var).grid(row=6, column=1, sticky="w")
        ttk.Label(self, textvariable=self.crit_pct_var).grid(row=6, column=2, sticky="w")

        # Rate
        ttk.Label(self, text="Rate (units/min):").grid(row=7, column=0, sticky="w")
        ttk.Label(self, textvariable=self.current_rate_var).grid(row=7, column=1, sticky="w")
        ttk.Label(self, textvariable=self.session_rate_var).grid(row=7, column=2, sticky="w")

        # Totals
        ttk.Label(self, text="Total:").grid(row=8, column=0, sticky="w", padx=1, pady=0)
        ttk.Label(self, textvariable=self.total_current_var).grid(row=8, column=1, sticky="w", padx=1, pady=0)
        ttk.Label(self, textvariable=self.total_session_var).grid(row=8, column=2, sticky="w", padx=1, pady=0)

        # Breakdown table
        self.breakdown_table = ttk.Treeview(self, columns=("resource", "qty"), show="headings", height=3)
        self.breakdown_table.heading("resource", text="Resource")
        self.breakdown_table.heading("qty", text="Qty")
        self.breakdown_table.grid(row=9, column=0, columnspan=3, sticky="nsew")

        # Log folder alias used by rescan
        self.log_folder = folder

        # Session/profile selector and label
        self.session_var = tk.StringVar(value="Profiles: 0 found")
        ttk.Label(self, textvariable=self.session_var).grid(row=10, column=0, columnspan=2, sticky="w", padx=1, pady=0)
        # Add rescan button
        ttk.Button(self, text="🔄", command=lambda: self.rescan(), width=3).grid(row=11, column=2, sticky="e", padx=1, pady=0)
        self.char_select = ttk.Combobox(self, state="readonly", width=30)
        self.char_select.grid(row=12, column=0, columnspan=3, sticky="we", padx=1, pady=0)
        self.char_select.bind("<<ComboboxSelected>>", self.select_char)

        # Capacity and hold percentage
        self.capacity_m3_var = tk.StringVar(value="0")
        ttk.Label(self, text="Hold Capacity (m3):").grid(row=13, column=0, sticky="w", padx=1, pady=2)
        ttk.Entry(self, textvariable=self.capacity_m3_var, width=10).grid(row=13, column=1, sticky="w", padx=1, pady=2)
        self.hold_pct_var = tk.StringVar(value="0.0%")
        self.hold_pct_label = ttk.Label(self, textvariable=self.hold_pct_var)
        # Large hold percent display: use a fixed-size Canvas so font can be larger
        try:
            big_font = tkfont.nametofont(self.breakdown_table.cget('font'))
            # double the font size for emphasis but cap to avoid clipping
            base = big_font.actual('size')
            size = max(8, min(base * 2, 18))
            big_font = tkfont.Font(family=big_font.actual('family'), size=size, weight='bold')
        except Exception:
            big_font = tkfont.Font(size=16, weight='bold')
        # Make the canvas match the UI height better
        self.hold_pct_canvas = tk.Canvas(self, width=90, height=24, highlightthickness=1, highlightbackground='#888888')
        # Get background color based on theme
        try:
            bg_color = self.cget('background')
        except Exception:
            bg_color = '#f0f0f0'
        self.hold_pct_canvas.configure(bg=bg_color)
        # create a right-aligned text item, we'll update it in update_hold_percent_style
        self.hold_pct_text_id = self.hold_pct_canvas.create_text(85, 12, anchor='e', text=self.hold_pct_var.get(), font=big_font)
        self.hold_pct_canvas.grid(row=13, column=2, sticky="e", padx=1, pady=2)
# ==== PART 2 ENDS HERE ====
# ==== PART 3 (MANUAL PRICE ENTRY BOX) ====



def panel_refresh(self):
    # Current stats
    self.ice_var.set(str(self.state.total_units))
    self.res_var.set(str(self.state.total_residue))
    self.crit_var.set(str(self.state.crits))
    self.extra_var.set(str(self.state.extra_from_crits))

    # Session totals
    self.session_ice_var.set(str(self.session_state.total_units))
    self.session_res_var.set(str(self.session_state.total_residue))
    self.session_crit_var.set(str(self.session_state.crits))
    self.session_extra_var.set(str(self.session_state.extra_from_crits))

    # Residue % (session and current)
    total_sess_units = self.session_state.total_units
    total_sess_residue = self.session_state.total_residue
    res_pct_sess = (total_sess_residue / (total_sess_units + total_sess_residue) * 100) if (total_sess_units + total_sess_residue) > 0 else 0.0
    self.res_pct_var.set(f"{res_pct_sess:.1f}%")
    total_units_cur = self.state.total_units
    total_residue_cur = self.state.total_residue
    res_pct_cur = (total_residue_cur / (total_units_cur + total_residue_cur) * 100) if (total_units_cur + total_residue_cur) > 0 else 0.0
    self.res_pct_current_var.set(f"{res_pct_cur:.1f}%")

    # Crit % (current & session)
    extra_crits_sess = self.session_state.extra_from_crits
    total_units_sess = self.session_state.total_units
    crit_pct_sess = (extra_crits_sess / total_units_sess * 100) if total_units_sess > 0 else 0.0
    self.crit_pct_var.set(f"{crit_pct_sess:.1f}%")
    extra_crits_cur = self.state.extra_from_crits
    total_units_cur = self.state.total_units
    crit_pct_cur = (extra_crits_cur / total_units_cur * 100) if total_units_cur > 0 else 0.0
    self.crit_pct_current_var.set(f"{crit_pct_cur:.1f}%")

    # Rate
    sess_rate = self.session_state.rate_units_per_min()
    self.session_rate_var.set(f"{sess_rate:.2f}")
    cur_rate = self.state.rate_units_per_min()
    self.current_rate_var.set(f"{cur_rate:.2f}")

    # Hold %
    hold_capacity = self.effective_capacity_m3()
    used_volume = self.state.total_volume()
    pct_hold = (used_volume / hold_capacity) if hold_capacity > 0 else 0.0
    self.update_hold_percent_style(pct_hold)

    # Totals
    current_total = self.state.total_units + self.state.extra_from_crits
    session_total = self.session_state.total_units + self.session_state.extra_from_crits
    self.total_current_var.set(str(current_total))
    self.total_session_var.set(str(session_total))

    # Breakdown table
    self.breakdown_table.delete(*self.breakdown_table.get_children())
    # Build breakdown rows
    for res, qty in self.session_state.by_resource.items():
            self.breakdown_table.insert(
                "",
                "end",
                values=(res, qty)
            )
    # Autosize the treeview columns to fit their contents
    try:
        self.breakdown_table.update_idletasks()
        try:
            font = tkfont.nametofont(self.breakdown_table.cget('font'))
        except Exception:
            font = tkfont.Font(font=self.breakdown_table.cget('font'))
        children = self.breakdown_table.get_children()
        col_map = [('resource', 0), ('qty', 1)]
        padding = 12
        for col, _ in col_map:
            hdr = self.breakdown_table.heading(col, 'text')
            max_w = font.measure(hdr)
            for item in children:
                val = self.breakdown_table.set(item, col)
                if val is None:
                    continue
                w = font.measure(str(val))
                if w > max_w:
                    max_w = w
            # let the last column stretch to fill
            if col == 'qty':
                self.breakdown_table.column(col, width=max_w + padding, stretch=True)
            else:
                self.breakdown_table.column(col, width=max_w + padding, stretch=False)
    except Exception:
        pass
# Attach refresh to Panel
Panel.refresh = panel_refresh
# ==== PART 3 ENDS HERE ====
# ==== PART 3B STARTS HERE ====
def panel_rescan(self):
    # Use shared character index from app (built once on demand)
    if not hasattr(self, 'app') or not hasattr(self.app, 'char_index'):
        # Fallback: build if app reference not set yet
        try:
            cache = getattr(self.app, 'profile_cache', None)
        except Exception:
            cache = None
        self.char_index = build_char_index(Path(self.log_folder), cache)
    else:
        self.char_index = self.app.char_index
    chars = sorted(self.char_index.keys())
    self.char_select["values"] = chars
    # Update session label
    self.session_var.set(f"Profiles: {len(chars)} found")

def panel_select_char(self, event=None):
    char = self.char_select.get()
    if not char:
        return
    # Find latest log for chosen character
    latest = latest_log_for_char(char, self.char_index)
    if not latest:
        self.session_var.set(f"No logs found for {char}")
        return
    # Update session info from header
    try:
        cache = getattr(self.app, 'profile_cache', None)
    except Exception:
        cache = None
    cname, sdt = extract_header_info(latest, cache)
    if sdt:
        self.session_state.session_start = sdt
        self.state.session_start = sdt
        self.session_var.set(f"{cname} — session {sdt.isoformat()}")
    else:
        self.session_var.set(f"{cname or char} — session unknown")
    # Start tailing
    self.start_tailer(latest)
    # Start tailing
    self.start_tailer(latest)
    # Persist profile selection for this panel
    try:
        if hasattr(self, 'app'):
            self.app.save_settings()
    except Exception:
        pass

def panel_start_tailer(self, path: Path):
    # Stop previous tailer if running
    try:
        if self.tailer and self.tailer.is_alive():
            self.stop_event.set()
            self.tailer.join(timeout=1.0)
    except Exception:
        pass
    # Reset stop event and current state
    self.stop_event = threading.Event()
    self.state.reset()
    # Create and start new tailer
    self.tailer = FileTailer(path, self.state, self.session_state, self.stop_event)
    self.tailer.start()

def panel_effective_capacity_m3(self) -> float:
    # Capacity entry is a string; sanitize to float
    v = self.capacity_m3_var.get()
    try:
        return float(v) if v else 0.0
    except ValueError:
        return 0.0

def panel_update_hold_percent_style(self, pct_hold: float):
    # Update label text and apply simple warning color near full
    pct_text = f"{pct_hold * 100:.1f}%"
    self.hold_pct_var.set(pct_text)
    # Basic style feedback: change foreground near/over 90%
    try:
        if pct_hold >= 1.0:
            color = "#FF3B30"  # red
        elif pct_hold >= 0.9:
            color = "#FF9500"  # orange
        else:
            color = None
        # update displayed percent text
        pct_text = f"{pct_hold * 100:.1f}%"
        try:
            self.hold_pct_var.set(pct_text)
        except Exception:
            pass
        # choose fill color (warning color if set, else default fg)
        fill = color if color else getattr(self, 'default_hold_fg', '#000000')
        try:
            if getattr(self, 'hold_pct_canvas', None) is not None:
                # update canvas text and color
                try:
                    self.hold_pct_canvas.itemconfigure(self.hold_pct_text_id, text=pct_text, fill=fill)
                except Exception:
                    # fallback: recreate text
                    self.hold_pct_canvas.delete(self.hold_pct_text_id)
                    self.hold_pct_text_id = self.hold_pct_canvas.create_text(85, 12, anchor='e', text=pct_text, fill=fill)
            else:
                self.hold_pct_label.configure(foreground=fill)
                try:
                    self.hold_pct_label.configure(text=pct_text)
                except Exception:
                    pass
        except Exception:
            try:
                self.hold_pct_label.configure(foreground=fill)
            except Exception:
                pass
    except Exception:
        pass
    # Panel-level popout removed; no extra updates here

def panel_open_popout(self):
    """Open or focus the hold capacity pop-out window."""
    try:
        # If window already exists and is open, just focus it
        if getattr(self, 'popout_window', None) is not None and self.popout_window.window.winfo_exists():
            self.popout_window.window.lift()
            self.popout_window.window.focus()
            return
    except Exception:
        pass
    
    # Create new pop-out window
    try:
        self.popout_window = HoldCapacityPopout(self)
        # Update with current state
        hold_capacity = self.effective_capacity_m3()
        used_volume = self.state.total_volume()
        pct_hold = (used_volume / hold_capacity) if hold_capacity > 0 else 0.0
        pct_text = f"{pct_hold * 100:.1f}%"
        if pct_hold >= 1.0:
            color = "#FF3B30"  # red
        elif pct_hold >= 0.9:
            color = "#FF9500"  # orange
        else:
            color = '#eaeaea'  # default light color
        self.popout_window.update_display(pct_text, color)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to open pop-out window: {e}")

# Bind methods onto Panel
Panel.rescan = panel_rescan
Panel.select_char = panel_select_char
Panel.start_tailer = panel_start_tailer
Panel.effective_capacity_m3 = panel_effective_capacity_m3
Panel.update_hold_percent_style = panel_update_hold_percent_style
Panel.open_popout = panel_open_popout
# ==== PART 3B ENDS HERE ====

# ==== PART 3B2: INDIVIDUAL PANEL HOLD CAPACITY POPOUT ====

class HoldCapacityPopout:
    """Always-on-top minimal window showing hold % for a single character panel."""
    def __init__(self, panel):
        self.panel = panel
        self.window = tk.Toplevel(panel.root)
        self.window.title("⬡ CARGO HOLD ⬡")
        
        # Remove title bar, keep always-on-top
        try:
            self.window.overrideredirect(True)
        except Exception:
            pass
        try:
            self.window.attributes('-topmost', True)
            self.window.attributes('-toolwindow', True)
        except Exception:
            pass
        
        # Set 50% transparency (0.5 alpha)
        try:
            self.window.attributes('-alpha', 0.5)
        except Exception:
            pass
        
        # Load saved geometry or use defaults
        saved_geom = self._load_geometry()
        if saved_geom:
            self.window.geometry(saved_geom)
        else:
            self.window.geometry("180x120+100+100")
        
        # Background to match Eve Online theme
        dark = True
        try:
            dark = bool(panel.app.dark_theme_var.get())
        except Exception:
            pass
        bg = '#0F1535' if dark else '#f0f0f0'
        fg = '#00D4FF' if dark else '#000000'
        try:
            self.window.configure(bg=bg)
        except Exception:
            pass
        
        # Content frame
        self.content = tk.Frame(self.window, bg=bg)
        self.content.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Character name label
        try:
            char_name = panel.char_select.get() or "UNKNOWN"
        except Exception:
            char_name = "UNKNOWN"
        self.name_label = tk.Label(self.content, text=char_name, bg=bg, fg='#39FF14', font=('Courier New', 9, 'bold'))
        self.name_label.pack(anchor='w')
        
        # Percentage display label
        self.pct_label = tk.Label(self.content, text="0.0%", bg=bg, fg=fg, font=('Courier New', 24, 'bold'))
        self.pct_label.pack(expand=True)
        
        # Dragging support
        self._drag_offset = (0, 0)
        try:
            self.window.bind('<ButtonPress-1>', self._start_move)
            self.window.bind('<B1-Motion>', self._do_move)
            self.window.bind('<ButtonRelease-1>', self._end_move)
        except Exception:
            pass
        
        # Resizing support via bottom-right grip
        try:
            self._resize_origin = (0, 0)
            self._resize_size = (0, 0)
            self.grip = tk.Frame(self.window, bg='#00D4FF', cursor='bottom_right_corner', width=12, height=12)
            self.grip.place(relx=1.0, rely=1.0, x=-12, y=-12, anchor='se')
            self.grip.bind('<ButtonPress-1>', self._start_resize)
            self.grip.bind('<B1-Motion>', self._do_resize)
            self.grip.bind('<ButtonRelease-1>', self._end_resize)
        except Exception:
            pass
        
        # Save geometry on window close
        try:
            self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        except Exception:
            pass
    
    def update_display(self, pct_text, color):
        """Update the percentage display with text and color."""
        try:
            self.pct_label.configure(text=pct_text, fg=color)
        except Exception:
            pass
    
    def _load_geometry(self):
        """Load saved window geometry from file."""
        try:
            geom_file = Path("holdpopout_geometry.txt")
            if geom_file.exists():
                return geom_file.read_text().strip()
        except Exception:
            pass
        return None
    
    def _save_geometry(self):
        """Save current window geometry to file."""
        try:
            geom = self.window.geometry()
            geom_file = Path("holdpopout_geometry.txt")
            geom_file.write_text(geom)
        except Exception:
            pass
    
    def _start_move(self, event):
        try:
            x = self.window.winfo_x()
            y = self.window.winfo_y()
            self._drag_offset = (event.x_root - x, event.y_root - y)
        except Exception:
            self._drag_offset = (0, 0)
    
    def _do_move(self, event):
        try:
            x = event.x_root - self._drag_offset[0]
            y = event.y_root - self._drag_offset[1]
            self.window.geometry(f"+{x}+{y}")
        except Exception:
            pass
    
    def _end_move(self, event):
        """Save geometry after moving."""
        self._save_geometry()
    
    def _start_resize(self, event):
        try:
            self._resize_origin = (event.x_root, event.y_root)
            self._resize_size = (self.window.winfo_width(), self.window.winfo_height())
        except Exception:
            self._resize_origin = (0, 0)
            self._resize_size = (0, 0)
    
    def _do_resize(self, event):
        try:
            dx = event.x_root - self._resize_origin[0]
            dy = event.y_root - self._resize_origin[1]
            new_w = max(120, self._resize_size[0] + dx)
            new_h = max(80, self._resize_size[1] + dy)
            x = self.window.winfo_x()
            y = self.window.winfo_y()
            self.window.geometry(f"{new_w}x{new_h}+{x}+{y}")
        except Exception:
            pass
    
    def _end_resize(self, event):
        """Save geometry after resizing."""
        self._save_geometry()
    
    def _on_close(self):
        """Save geometry and close window."""
        self._save_geometry()
        try:
            self.window.destroy()
        except Exception:
            pass

# ==== PART 3C: AGGREGATE HOLD CAPACITY POPOUT (ALL CHARACTERS) ====

class AggregateHoldPopout:
    """Always-on-top minimal window showing hold % for all characters vertically."""
    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        # Remove title bar, keep always-on-top, and make draggable
        try:
            self.window.overrideredirect(True)
        except Exception:
            pass
        try:
            self.window.title("⬡ FLEET CARGO STATUS ⬡")
        except Exception:
            pass
        try:
            self.window.attributes('-topmost', True)
            self.window.attributes('-toolwindow', True)
        except Exception:
            pass
        
        # Set 50% transparency (0.5 alpha)
        try:
            self.window.attributes('-alpha', 0.5)
        except Exception:
            pass
        
        # Load saved geometry or use defaults
        saved_geom = self._load_geometry()
        if saved_geom:
            self.window.geometry(saved_geom)
        else:
            self.window.geometry("220x360+100+100")
        
        self.window.resizable(True, True)

        # Background to match Eve Online theme
        dark = True
        try:
            dark = bool(app.dark_theme_var.get())
        except Exception:
            pass
        bg = '#0F1535' if dark else '#f0f0f0'
        fg = '#00D4FF' if dark else '#000000'
        try:
            self.window.configure(bg=bg)
        except Exception:
            pass

        # Scrollable container: Canvas + vertical scrollbar
        self.canvas = tk.Canvas(self.window, bg=bg, highlightthickness=0)
        self.vscroll = tk.Scrollbar(self.window, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vscroll.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.vscroll.pack(side='right', fill='y')
        # Content frame inside canvas
        self.content = tk.Frame(self.canvas, bg=bg)
        self.content_window = self.canvas.create_window(0, 0, anchor='nw', window=self.content)
        # Update scrollregion when content size changes
        self.content.bind('<Configure>', lambda e: self._update_scroll())
        self.canvas.bind('<Configure>', lambda e: self._fit_content_width(e.width))

        # Fonts
        try:
            self.name_font = tkfont.Font(family='Courier New', size=8, weight='bold')
            self.pct_font = tkfont.Font(family='Courier New', size=16, weight='bold')
            self.stats_font = tkfont.Font(family='Courier New', size=11)
        except Exception:
            self.name_font = None
            self.pct_font = None
            self.stats_font = None

        # Map panel -> (name_label, pct_label, stats_label)
        self.rows = {}
        # Crit flash tracking
        self._last_crits = {}
        self._flash_until = {}
        self._flash_duration = 2.0
        self._build_rows()
        self.refresh()

        # Dragging support (click anywhere to drag)
        self._drag_offset = (0, 0)
        try:
            self.window.bind('<ButtonPress-1>', self._start_move)
            self.window.bind('<B1-Motion>', self._do_move)
            self.window.bind('<ButtonRelease-1>', self._end_move)
        except Exception:
            pass

        # Resizing support via a bottom-right grip (works with borderless window)
        try:
            self._resize_origin = (0, 0)
            self._resize_size = (0, 0)
            self.grip = tk.Frame(self.window, bg='#00D4FF', cursor='bottom_right_corner', width=12, height=12)
            self.grip.place(relx=1.0, rely=1.0, x=-12, y=-12, anchor='se')
            self.grip.bind('<ButtonPress-1>', self._start_resize)
            self.grip.bind('<B1-Motion>', self._do_resize)
            self.grip.bind('<ButtonRelease-1>', self._end_resize)
        except Exception:
            pass
        
        # Save geometry on window close
        try:
            self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        except Exception:
            pass

    def _panel_name(self, p) -> str:
        try:
            val = p.char_select.get()
            if val:
                return val
        except Exception:
            pass
        # Fallback: panel index
        try:
            idx = self.app.panels.index(p) + 1
            return f"Panel {idx}"
        except Exception:
            return "Unknown"

    def _build_rows(self):
        # Clear previous
        for child in list(self.content.children.values()):
            child.destroy()
        self.rows.clear()
        # Build one row per non-aggregate panel
        for p in self.app.panels:
            if getattr(p, 'is_aggregate', False):
                continue
            row = tk.Frame(self.content, bg=self.content['bg'])
            row.pack(fill="x", padx=6, pady=2)
            row.columnconfigure(0, weight=1)
            row.columnconfigure(1, weight=0)
            name_lbl = tk.Label(row, text=self._panel_name(p), anchor='w', bg=self.content['bg'], fg='#00D4FF')
            if self.name_font:
                try:
                    name_lbl.configure(font=self.name_font)
                except Exception:
                    pass
            name_lbl.grid(row=0, column=0, columnspan=2, sticky="w")
            pct_lbl = tk.Label(row, text="0.0%", anchor='w', bg=self.content['bg'], fg='#39FF14')
            if self.pct_font:
                try:
                    pct_lbl.configure(font=self.pct_font)
                except Exception:
                    pass
            pct_lbl.grid(row=1, column=0, sticky="w")
            stats_lbl = tk.Label(row, text="Crit: 0.0%  Residue: 0.0%", anchor='e', bg=self.content['bg'], fg='#39FF14')
            if self.stats_font:
                try:
                    stats_lbl.configure(font=self.stats_font)
                except Exception:
                    pass
            stats_lbl.grid(row=1, column=1, sticky="e", padx=(6, 0))
            self.rows[p] = (name_lbl, pct_lbl, stats_lbl)
        # Drop tracking for panels no longer present
        try:
            current = set(self.rows.keys())
            self._last_crits = {p: v for p, v in self._last_crits.items() if p in current}
            self._flash_until = {p: v for p, v in self._flash_until.items() if p in current}
        except Exception:
            pass
        # Ensure scroll region fits all rows
        self._update_scroll()

    def refresh(self):
        # Update all labels from current panel states
        now = time.monotonic()
        for p, (_, pct_lbl, stats_lbl) in list(self.rows.items()):
            try:
                cap = p.effective_capacity_m3()
                used = p.state.total_volume()
                pct = (used / cap) if cap > 0 else 0.0
                pct_text = f"{pct * 100:.1f}%"
                stats_state = getattr(p, 'session_state', None) or getattr(p, 'state', None)
                total_units = getattr(stats_state, 'total_units', 0) or 0
                extra_from_crits = getattr(stats_state, 'extra_from_crits', 0) or 0
                total_residue = getattr(stats_state, 'total_residue', 0) or 0
                denom = float(total_units) if total_units > 0 else 0.0
                crit_pct = (extra_from_crits / denom) * 100.0 if denom else 0.0
                residue_pct = (total_residue / denom) * 100.0 if denom else 0.0
                try:
                    cur_crits = int(getattr(p.state, 'crits', 0))
                except Exception:
                    cur_crits = 0
                prev_crits = self._last_crits.get(p, 0)
                if cur_crits > prev_crits:
                    self._flash_until[p] = now + self._flash_duration
                self._last_crits[p] = cur_crits

                if now < self._flash_until.get(p, 0):
                    color = "#FFD60A"
                elif pct >= 1.0:
                    color = "#FF3B30"
                elif pct >= 0.9:
                    color = "#FF9500"
                else:
                    color = '#39FF14'
                pct_lbl.configure(text=pct_text, fg=color)
                stats_lbl.configure(
                    text=f"Crit: {crit_pct:.1f}%  Residue: {residue_pct:.1f}%",
                    fg=color,
                )
            except Exception:
                pass

    def lift(self):
        try:
            self.window.lift()
            self.window.focus()
        except Exception:
            pass

    def _update_scroll(self):
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        except Exception:
            pass

    def _fit_content_width(self, width):
        # Keep inner frame width synced with canvas width
        try:
            self.canvas.itemconfigure(self.content_window, width=width)
        except Exception:
            pass

    def _start_move(self, event):
        try:
            x = self.window.winfo_x()
            y = self.window.winfo_y()
            self._drag_offset = (event.x_root - x, event.y_root - y)
        except Exception:
            self._drag_offset = (0, 0)

    def _do_move(self, event):
        try:
            x = event.x_root - self._drag_offset[0]
            y = event.y_root - self._drag_offset[1]
            self.window.geometry(f"+{x}+{y}")
        except Exception:
            pass
    
    def _end_move(self, event):
        """Save geometry after moving."""
        self._save_geometry()

    def _start_resize(self, event):
        try:
            self._resize_origin = (event.x_root, event.y_root)
            self._resize_size = (self.window.winfo_width(), self.window.winfo_height())
        except Exception:
            self._resize_origin = (0, 0)
            self._resize_size = (0, 0)

    def _do_resize(self, event):
        try:
            dx = event.x_root - self._resize_origin[0]
            dy = event.y_root - self._resize_origin[1]
            new_w = max(160, self._resize_size[0] + dx)
            new_h = max(140, self._resize_size[1] + dy)
            x = self.window.winfo_x()
            y = self.window.winfo_y()
            self.window.geometry(f"{new_w}x{new_h}+{x}+{y}")
            self._update_scroll()
        except Exception:
            pass
    
    def _end_resize(self, event):
        """Save geometry after resizing."""
        self._save_geometry()
    
    def _load_geometry(self):
        """Load saved window geometry from file."""
        try:
            geom_file = Path("aggregate_popout_geometry.txt")
            if geom_file.exists():
                return geom_file.read_text().strip()
        except Exception:
            pass
        return None
    
    def _save_geometry(self):
        """Save current window geometry to file."""
        try:
            geom = self.window.geometry()
            geom_file = Path("aggregate_popout_geometry.txt")
            geom_file.write_text(geom)
        except Exception:
            pass
    
    def _on_close(self):
        """Save geometry and close window."""
        self._save_geometry()
        try:
            self.window.destroy()
        except Exception:
            pass

# ==== PART 3D: MONTHLY ISK POPOUT ====

class MonthlyISKPopout:
    """Popout window showing total ISK mined for the current month."""
    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("Monthly ISK")
        # Match tactical overlay styling (borderless, topmost, semi-transparent)
        try:
            self.window.overrideredirect(True)
        except Exception:
            pass
        try:
            self.window.attributes('-topmost', True)
            self.window.attributes('-toolwindow', True)
            self.window.attributes('-alpha', 0.5)
        except Exception:
            pass

        # Load saved geometry or use defaults
        saved_geom = self._load_geometry()
        if saved_geom:
            self.window.geometry(saved_geom)
        else:
            self.window.geometry("260x150+120+120")

        try:
            self.window.resizable(True, True)
        except Exception:
            pass

        self._last_refresh = 0.0
        self._refresh_interval = 60.0

        # Theme colors
        self._apply_theme_colors()

        self.content = tk.Frame(self.window, bg=self._bg)
        self.content.pack(fill='both', expand=True, padx=10, pady=10)

        self.title_label = tk.Label(self.content, text="MONTHLY ISK", bg=self._bg, fg=self._fg,
                                    font=('Courier New', 10, 'bold'))
        self.title_label.pack(anchor='w')

        self.month_label = tk.Label(self.content, text="", bg=self._bg, fg=self._accent,
                                    font=('Courier New', 10, 'bold'))
        self.month_label.pack(anchor='w', pady=(2, 6))

        self.total_label = tk.Label(self.content, text="0.00 ISK", bg=self._bg, fg=self._accent,
                                    font=('Courier New', 20, 'bold'))
        self.total_label.pack(anchor='w')

        self.today_row = tk.Frame(self.content, bg=self._bg)
        self.today_row.pack(fill='x', pady=(4, 0))
        self.today_label = tk.Label(self.today_row, text="Today: 0.00 ISK", bg=self._bg, fg=self._fg,
                font=('Courier New', 9, 'bold'))
        self.today_label.pack(side='left')
        self.today_iskph_label = tk.Label(self.today_row, text="0.00 ISK/hr", bg=self._bg, fg=self._fg,
                font=('Courier New', 9, 'bold'))
        self.today_iskph_label.pack(side='right')

        self.yesterday_label = tk.Label(self.content, text="This Week: 0.00 ISK", bg=self._bg, fg=self._fg,
                        font=('Courier New', 9, 'bold'))
        self.yesterday_label.pack(anchor='w', pady=(4, 0))

        self.note_label = tk.Label(self.content, text="", bg=self._bg, fg=self._fg,
                       font=('Courier New', 8))
        self.note_label.pack(anchor='w', pady=(6, 0))

        # Dragging support
        self._drag_offset = (0, 0)
        try:
            self.window.bind('<ButtonPress-1>', self._start_move)
            self.window.bind('<B1-Motion>', self._do_move)
            self.window.bind('<ButtonRelease-1>', self._end_move)
        except Exception:
            pass

        # Resizing support via bottom-right grip
        try:
            self._resize_origin = (0, 0)
            self._resize_size = (0, 0)
            self.grip = tk.Frame(self.window, bg=self._fg, cursor='bottom_right_corner', width=12, height=12)
            self.grip.place(relx=1.0, rely=1.0, x=-12, y=-12, anchor='se')
            self.grip.bind('<ButtonPress-1>', self._start_resize)
            self.grip.bind('<B1-Motion>', self._do_resize)
            self.grip.bind('<ButtonRelease-1>', self._end_resize)
        except Exception:
            pass

        try:
            self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        except Exception:
            pass

        self.refresh(force=True)

    def _apply_theme_colors(self):
        try:
            dark = bool(self.app.dark_theme_var.get())
        except Exception:
            dark = True
        self._bg = '#0F1535' if dark else '#f0f0f0'
        # Use custom colors from app
        self._fg = hsv_to_hex(self.app.custom_primary_hue, 1.0, 0.83) if dark else '#000000'
        self._accent = hsv_to_hex(self.app.custom_accent_hue, 1.0, 0.99) if dark else '#000000'
        try:
            self.window.configure(bg=self._bg)
        except Exception:
            pass

    def apply_theme(self):
        self._apply_theme_colors()
        try:
            self.content.configure(bg=self._bg)
            self.title_label.configure(bg=self._bg, fg=self._fg)
            self.month_label.configure(bg=self._bg, fg=self._accent)
            self.total_label.configure(bg=self._bg, fg=self._accent)
            self.today_label.configure(bg=self._bg, fg=self._fg)
            self.today_iskph_label.configure(bg=self._bg, fg=self._fg)
            self.yesterday_label.configure(bg=self._bg, fg=self._fg)
            self.note_label.configure(bg=self._bg, fg=self._fg)
            self.today_row.configure(bg=self._bg)
            self.grip.configure(bg=self._fg)
        except Exception:
            pass

    def refresh(self, force: bool = False):
        self._last_refresh = time.monotonic()
        now = datetime.now()
        self.app.request_monthly_refresh(now.year, now.month, force=force)
        self.update_from_cache()

    def update_from_cache(self):
        cached = self.app.get_monthly_cache()
        if not cached:
            try:
                self.note_label.configure(text="Refreshing...")
            except Exception:
                pass
            return
        year, month, result, _ = cached
        try:
            month_label = datetime(year, month, 1).strftime("%B %Y")
        except Exception:
            month_label = ""
        total_isk, _qty_by_res, _prices, y_total, t_total = result
        self.month_label.configure(text=month_label)
        self.total_label.configure(text=format_isk(total_isk))
        try:
            self.today_label.configure(text=f"Today: {format_isk(t_total)}")
        except Exception:
            pass
        try:
            now = datetime.now()
            # Use reset time if available and from today, otherwise use start of day
            start = datetime(now.year, now.month, now.day)
            if self.app.today_reset_time:
                reset_date = self.app.today_reset_time.date()
                today_date = now.date()
                if reset_date == today_date:
                    start = self.app.today_reset_time
            hours = (now - start).total_seconds() / 3600.0
            iskph = (t_total / hours) if hours > 0 else 0.0
            self.today_iskph_label.configure(text=f"{format_isk(iskph)}/hr")
        except Exception:
            pass
        try:
            self.yesterday_label.configure(text=f"This Week: {format_isk(y_total)}")
        except Exception:
            pass
        try:
            self.note_label.configure(text="")
        except Exception:
            pass

    def maybe_refresh(self):
        try:
            now = time.monotonic()
            if now - self._last_refresh >= self._refresh_interval:
                self.refresh()
        except Exception:
            pass

    def _load_geometry(self):
        try:
            geom_file = Path("monthly_isk_popout_geometry.txt")
            if geom_file.exists():
                return geom_file.read_text().strip()
        except Exception:
            pass
        return None

    def _save_geometry(self):
        try:
            geom = self.window.geometry()
            geom_file = Path("monthly_isk_popout_geometry.txt")
            geom_file.write_text(geom)
        except Exception:
            pass

    def _on_close(self):
        self._save_geometry()
        try:
            self.window.destroy()
        except Exception:
            pass

    def _start_move(self, event):
        try:
            x = self.window.winfo_x()
            y = self.window.winfo_y()
            self._drag_offset = (event.x_root - x, event.y_root - y)
        except Exception:
            self._drag_offset = (0, 0)

    def _do_move(self, event):
        try:
            x = event.x_root - self._drag_offset[0]
            y = event.y_root - self._drag_offset[1]
            self.window.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _end_move(self, event):
        self._save_geometry()

    def _start_resize(self, event):
        try:
            self._resize_origin = (event.x_root, event.y_root)
            self._resize_size = (self.window.winfo_width(), self.window.winfo_height())
        except Exception:
            self._resize_origin = (0, 0)
            self._resize_size = (0, 0)

    def _do_resize(self, event):
        try:
            dx = event.x_root - self._resize_origin[0]
            dy = event.y_root - self._resize_origin[1]
            new_w = max(200, self._resize_size[0] + dx)
            new_h = max(140, self._resize_size[1] + dy)
            x = self.window.winfo_x()
            y = self.window.winfo_y()
            self.window.geometry(f"{new_w}x{new_h}+{x}+{y}")
        except Exception:
            pass

    def _end_resize(self, event):
        self._save_geometry()

# ==== PART 3E: PRICE EDITOR POPOUT ====

class PriceEditorPopout:
    """Popout window for editing prices.json in a themed text editor."""
    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("Price Editor")
        # Match tactical overlay styling (borderless, topmost, semi-transparent)
        try:
            self.window.overrideredirect(True)
        except Exception:
            pass
        try:
            self.window.attributes('-topmost', True)
            self.window.attributes('-toolwindow', True)
            self.window.attributes('-alpha', 0.95)
        except Exception:
            pass

        # Load saved geometry or use defaults
        saved_geom = self._load_geometry()
        if saved_geom:
            self.window.geometry(saved_geom)
        else:
            self.window.geometry("600x500+200+200")

        try:
            self.window.resizable(True, True)
        except Exception:
            pass

        # Theme colors
        self._apply_theme_colors()

        self.content = tk.Frame(self.window, bg=self._bg)
        self.content.pack(fill='both', expand=True)

        # Title bar
        title_bar = tk.Frame(self.content, bg=self._bg)
        title_bar.pack(fill='x', padx=10, pady=(10, 5))
        
        title_label = tk.Label(title_bar, text="PRICE EDITOR", bg=self._bg, fg=self._fg,
                              font=('Courier New', 10, 'bold'))
        title_label.pack(side='left')
        
        close_btn = tk.Button(title_bar, text="✕", bg=self._bg, fg=self._fg,
                             font=('Courier New', 10, 'bold'), relief='flat',
                             command=self._on_close, cursor='hand2',
                             activebackground=self._bg, activeforeground='#FF0000')
        close_btn.pack(side='right')

        # Text editor with scrollbar
        editor_frame = tk.Frame(self.content, bg=self._bg)
        editor_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        scrollbar = tk.Scrollbar(editor_frame, bg=self._bg)
        scrollbar.pack(side='right', fill='y')
        
        self.text_editor = tk.Text(editor_frame, bg=self._entry_bg, fg=self._fg,
                                   insertbackground=self._fg, relief='flat',
                                   font=('Courier New', 10),
                                   yscrollcommand=scrollbar.set, wrap='none')
        self.text_editor.pack(fill='both', expand=True)
        scrollbar.config(command=self.text_editor.yview)

        # Load prices.json content
        self._load_prices()

        # Button row
        btn_row = tk.Frame(self.content, bg=self._bg)
        btn_row.pack(fill='x', padx=10, pady=(5, 10))
        
        self.status_label = tk.Label(btn_row, text="", bg=self._bg, fg=self._fg,
                                     font=('Courier New', 8))
        self.status_label.pack(side='left')
        
        ttk.Button(btn_row, text="Save", command=self._save_prices).pack(side='right', padx=(4, 0))
        ttk.Button(btn_row, text="Reload", command=self._load_prices).pack(side='right')

        # Dragging support
        self._drag_offset = (0, 0)
        try:
            title_bar.bind('<ButtonPress-1>', self._start_move)
            title_bar.bind('<B1-Motion>', self._do_move)
            title_bar.bind('<ButtonRelease-1>', self._end_move)
            title_label.bind('<ButtonPress-1>', self._start_move)
            title_label.bind('<B1-Motion>', self._do_move)
            title_label.bind('<ButtonRelease-1>', self._end_move)
        except Exception:
            pass

        # Resizing support via bottom-right grip
        try:
            self._resize_origin = (0, 0)
            self._resize_size = (0, 0)
            self.grip = tk.Frame(self.window, bg=self._fg, cursor='bottom_right_corner', width=12, height=12)
            self.grip.place(relx=1.0, rely=1.0, x=-12, y=-12, anchor='se')
            self.grip.bind('<ButtonPress-1>', self._start_resize)
            self.grip.bind('<B1-Motion>', self._do_resize)
            self.grip.bind('<ButtonRelease-1>', self._end_resize)
        except Exception:
            pass

        try:
            self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        except Exception:
            pass

    def _apply_theme_colors(self):
        try:
            dark = bool(self.app.dark_theme_var.get())
        except Exception:
            dark = True
        self._bg = '#0F1535' if dark else '#f0f0f0'
        self._fg = hsv_to_hex(self.app.custom_primary_hue, 1.0, 0.83) if dark else '#000000'
        self._entry_bg = '#0A0E27' if dark else '#ffffff'
        try:
            self.window.configure(bg=self._bg)
        except Exception:
            pass

    def apply_theme(self):
        self._apply_theme_colors()
        try:
            self.content.configure(bg=self._bg)
            self.text_editor.configure(bg=self._entry_bg, fg=self._fg, insertbackground=self._fg)
            self.status_label.configure(bg=self._bg, fg=self._fg)
            self.grip.configure(bg=self._fg)
        except Exception:
            pass

    def _load_prices(self):
        try:
            load_price_map()
            path = PRICE_FILE.resolve()
            if path.exists():
                content = path.read_text(encoding='utf-8')
                self.text_editor.delete('1.0', 'end')
                self.text_editor.insert('1.0', content)
                self.status_label.configure(text="Loaded prices.json")
            else:
                self.text_editor.delete('1.0', 'end')
                self.text_editor.insert('1.0', '{}')
                self.status_label.configure(text="Created new prices.json")
        except Exception as e:
            self.status_label.configure(text=f"Error loading: {e}")

    def _save_prices(self):
        try:
            content = self.text_editor.get('1.0', 'end-1c')
            # Validate JSON
            json.loads(content)
            path = PRICE_FILE.resolve()
            path.write_text(content, encoding='utf-8')
            self.status_label.configure(text="Saved successfully!")
            # Force refresh of monthly ISK data
            try:
                self.app.force_monthly_refresh()
            except Exception:
                pass
        except json.JSONDecodeError as e:
            self.status_label.configure(text=f"Invalid JSON: {e}")
        except Exception as e:
            self.status_label.configure(text=f"Error saving: {e}")

    def _load_geometry(self):
        try:
            geom_file = Path("price_editor_geometry.txt")
            if geom_file.exists():
                return geom_file.read_text().strip()
        except Exception:
            pass
        return None

    def _save_geometry(self):
        try:
            geom = self.window.geometry()
            geom_file = Path("price_editor_geometry.txt")
            geom_file.write_text(geom)
        except Exception:
            pass

    def _on_close(self):
        self._save_geometry()
        try:
            self.window.destroy()
        except Exception:
            pass

    def _start_move(self, event):
        try:
            x = self.window.winfo_x()
            y = self.window.winfo_y()
            self._drag_offset = (event.x_root - x, event.y_root - y)
        except Exception:
            self._drag_offset = (0, 0)

    def _do_move(self, event):
        try:
            x = event.x_root - self._drag_offset[0]
            y = event.y_root - self._drag_offset[1]
            self.window.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _end_move(self, event):
        self._save_geometry()

    def _start_resize(self, event):
        try:
            self._resize_origin = (event.x_root, event.y_root)
            self._resize_size = (self.window.winfo_width(), self.window.winfo_height())
        except Exception:
            self._resize_origin = (0, 0)
            self._resize_size = (0, 0)

    def _do_resize(self, event):
        try:
            dx = event.x_root - self._resize_origin[0]
            dy = event.y_root - self._resize_origin[1]
            new_w = max(400, self._resize_size[0] + dx)
            new_h = max(300, self._resize_size[1] + dy)
            x = self.window.winfo_x()
            y = self.window.winfo_y()
            self.window.geometry(f"{new_w}x{new_h}+{x}+{y}")
        except Exception:
            pass

    def _end_resize(self, event):
        self._save_geometry()

# ==== PART 4 STARTS HERE ====

class App:
    def __init__(self, root, folder: Path):
        self.root = root
        self.folder = folder
        self.folder_var = tk.StringVar(value=str(folder))
        self.state = MiningState()
        self.session_state = MiningState()
        self.profile_file = Path("profile.txt")
        self.profile_cache = load_profile_cache()
        self.style = ttk.Style()
        self.panel_count = 8
        self._monthly_cache = None
        self._monthly_cache_lock = threading.Lock()
        self._monthly_refreshing = False
        self.today_reset_time = None  # Track when user resets ISK/hr
        self.custom_primary_hue = 190  # Default cyan hue (0-360)
        self.custom_accent_hue = 100   # Default green hue (0-360)
        # compact styling: smaller padding and tighter treeview row height
        try:
            self.style.configure('TLabel', padding=1, font=(None, 9))
            self.style.configure('Treeview', rowheight=12)
            self.style.configure('TEntry', font=(None, 9))
            self.style.configure('TCombobox', font=(None, 9))
        except Exception:
            pass
        self.settings_file = APP_DIR / "settings.json"
        # persist window geometry and state and dark theme Flag
        self.window_geometry = None
        self.window_state = None
        self.dark_theme_var = tk.BooleanVar(value=True)
        # apply theme (set background, treeview colors etc.)
        # apply_theme defined later in class; no placeholder needed

        # top bar with folder browse
        topbar = ttk.Frame(root)
        topbar.pack(fill="x", pady=0)
        ttk.Label(topbar, text="EVE LOG FOLDER:").pack(side="left")
        self.folder_entry = ttk.Entry(topbar, textvariable=self.folder_var, width=48)
        self.folder_entry.pack(side="left", padx=4)
        ttk.Button(topbar, text="BROWSE", command=self.browse_folder).pack(side="left")
        ttk.Button(topbar, text="⟳ RESCAN", command=self.rescan_folder).pack(side="left", padx=2)
        # Controls bar
        controlsbar = ttk.Frame(root)
        controlsbar.pack(fill="x", pady=0)
        # Dark theme toggle
        ttk.Checkbutton(controlsbar, text="◉ SPACESHIP MODE", variable=self.dark_theme_var, command=lambda: (self.apply_theme(), self.save_settings())).pack(side="left", padx=(8,2))
        # Panel count selector
        ttk.Label(controlsbar, text="Panels:").pack(side="left", padx=(8,2))
        self.panel_count_var = tk.StringVar(value=str(self.panel_count))
        self.panel_count_combo = ttk.Combobox(
            controlsbar,
            state="readonly",
            width=4,
            textvariable=self.panel_count_var,
            values=[str(i) for i in range(2, 13)],
        )
        self.panel_count_combo.pack(side="left", padx=(0, 8))
        self.panel_count_combo.bind("<<ComboboxSelected>>", self.on_panel_count_change)
        # Global popout button for all characters
        ttk.Button(controlsbar, text="📡 TACTICAL OVERLAY", command=self.open_aggregate_popout).pack(side="right", padx=(8,6))
        ttk.Button(controlsbar, text="💰 MONTHLY ISK", command=self.open_monthly_isk_popout).pack(side="right", padx=(8,6))

        # ISK Controls and Settings bar
        settingsbar = ttk.Frame(root)
        settingsbar.pack(fill="x", pady=(2, 0))
        
        # ISK controls
        isk_controls = ttk.Frame(settingsbar)
        isk_controls.pack(side="left", padx=(8, 0))
        ttk.Label(isk_controls, text="ISK:").pack(side="left", padx=(0, 4))
        ttk.Button(isk_controls, text="⟳ Refresh", command=self.force_monthly_refresh).pack(side="left", padx=(0, 4))
        ttk.Button(isk_controls, text="Reset ISK/hr", command=self.reset_today_isk).pack(side="left", padx=(0, 4))
        ttk.Button(isk_controls, text="Edit Prices", command=self.open_prices_file).pack(side="left")
        
        # Color controls
        color_controls = ttk.Frame(settingsbar)
        color_controls.pack(side="right", padx=(0, 8))
        
        ttk.Label(color_controls, text="Primary:").pack(side="left", padx=(4, 2))
        self.primary_slider = tk.Scale(color_controls, from_=0, to=360, orient='horizontal',
                                      command=self.on_primary_color_change, length=120,
                                      showvalue=False)
        self.primary_slider.set(self.custom_primary_hue)
        self.primary_slider.pack(side="left", padx=(0, 8))
        
        ttk.Label(color_controls, text="Accent:").pack(side="left", padx=(4, 2))
        self.accent_slider = tk.Scale(color_controls, from_=0, to=360, orient='horizontal',
                                     command=self.on_accent_color_change, length=120,
                                     showvalue=False)
        self.accent_slider.set(self.custom_accent_hue)
        self.accent_slider.pack(side="left")

        # container for the single panel
        self.container = ttk.Frame(root)
        self.container.pack(fill="both", expand=True)

        # load settings if available
        self.last_profile = None
        self.last_capacity = None
        self.load_settings()
        try:
            self.panel_count_var.set(str(self.panel_count))
        except Exception:
            pass
        # apply dark theme and geometry if set
        try:
            if getattr(self, 'dark_theme_var', None) is not None:
                self.apply_theme()
        except Exception:
            pass
        # ensure prices.json exists
        try:
            load_price_map()
        except Exception:
            pass
        try:
            if getattr(self, 'window_geometry', None):
                self.root.geometry(self.window_geometry)
            if getattr(self, 'window_state', None) == 'zoomed':
                self.root.state('zoomed')
        except Exception:
            pass
        # bind to configure to capture geometry updates, then kick off initial ESI price map refresh
        try:
            self.root.bind('<Configure>', self.on_configure)
        except Exception:
            pass
        try:
            self._refresh_prices_async()
        except Exception:
            pass

        # build a grid of panels using the selected count
        self.build_panels(self.panel_count)
        # bind close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # periodic refresh
        self.root.after(1000, self.refresh_all)

        # Aggregate popout reference
        self.aggregate_popout = None
        # Monthly ISK popout reference
        self.monthly_isk_popout = None
        # Price editor popout reference
        self.price_editor_popout = None

    def browse_folder(self):
        new_folder = filedialog.askdirectory(title="Select EVE Log Folder")
        if new_folder:
            self.folder_var.set(new_folder)
            self.folder = Path(new_folder)
            self.save_settings()
            # rebuild shared character index once
            self.char_index = build_char_index(self.folder, self.profile_cache)
            # update all panels with new folder and shared index
            for p in self.panels:
                p.log_folder = self.folder
                if not getattr(p, 'is_aggregate', False):
                    try:
                        p.char_index = self.char_index
                        chars = sorted(self.char_index.keys())
                        p.char_select["values"] = chars
                        p.session_var.set(f"Profiles: {len(chars)} found")
                    except Exception:
                        pass

    def _refresh_prices_async(self):
        def worker():
            refresh_esi_price_map()
        threading.Thread(target=worker, daemon=True).start()

    def rescan_folder(self):
        """Rescan the current folder for new profiles without changing the folder."""
        try:
            # Rebuild character index for current folder
            self.char_index = build_char_index(self.folder, self.profile_cache)
            # Update all panels with refreshed index
            for p in self.panels:
                if not getattr(p, 'is_aggregate', False):
                    try:
                        p.char_index = self.char_index
                        chars = sorted(self.char_index.keys())
                        p.char_select["values"] = chars
                        p.session_var.set(f"Profiles: {len(chars)} found")
                    except Exception:
                        pass
        except Exception:
            pass

    def on_panel_count_change(self, event=None):
        try:
            new_count = int(self.panel_count_var.get())
        except Exception:
            return
        if new_count < 2:
            new_count = 2
        if new_count == getattr(self, 'panel_count', None) and len(self.panels) == new_count:
            return
        try:
            self.last_profile = [None if getattr(p, 'is_aggregate', False) else (p.char_select.get() if p.char_select.get() else None) for p in self.panels]
            self.last_capacity = [None if getattr(p, 'is_aggregate', False) else p.capacity_m3_var.get() for p in self.panels]
        except Exception:
            pass
        self.panel_count = new_count
        self.build_panels(new_count)
        try:
            self.update_aggregate_popout()
        except Exception:
            pass
        self.save_settings()

    def build_panels(self, num_panels: int):
        # Tear down existing panels
        try:
            for p in getattr(self, 'panels', []):
                try:
                    if getattr(p, 'tailer', None) and p.tailer.is_alive():
                        p.stop_event.set()
                        p.tailer.join(timeout=0.5)
                except Exception:
                    pass
                try:
                    if getattr(p, 'wrapper', None) is not None:
                        p.wrapper.destroy()
                    else:
                        p.destroy()
                except Exception:
                    pass
        except Exception:
            pass

        self.panels = []
        if num_panels < 2:
            num_panels = 2
        cols = min(4, num_panels)
        rows = (num_panels + cols - 1) // cols
        # configure container grid
        for c in range(cols):
            try:
                self.container.grid_columnconfigure(c, weight=1)
            except Exception:
                pass
        for r in range(rows):
            try:
                self.container.grid_rowconfigure(r, weight=1)
            except Exception:
                pass

        for i in range(num_panels):
            st = MiningState()
            sst = MiningState()
            r = i // cols
            c = i % cols
            wrapper = tk.Frame(self.container, bd=1, relief='ridge')
            wrapper.grid(row=r, column=c, sticky="nsew", padx=1, pady=1)
            p = Panel(
                wrapper,
                st,
                sst,
                self.profile_file,
                Path(self.folder_var.get()),
                self.style,
            )
            p.pack(fill="both", expand=True, padx=2, pady=2)
            p.wrapper = wrapper
            p.root = self.root
            if i == (num_panels - 1):
                p.is_aggregate = True
                try:
                    p.char_select.set('All Characters')
                    p.char_select.configure(state='disabled')
                    p.session_var.set('All Characters - aggregated')
                    p.capacity_m3_var.set('0')
                except Exception:
                    pass
            else:
                p.is_aggregate = False
            p.app = self
            self.panels.append(p)

        self.panel = self.panels[0] if self.panels else None

        # Build character index once and share across all panels
        self.char_index = build_char_index(self.folder, self.profile_cache)
        # Update all non-aggregate panels with the shared index
        for p in self.panels:
            if not getattr(p, 'is_aggregate', False):
                try:
                    p.char_index = self.char_index
                    chars = sorted(self.char_index.keys())
                    p.char_select["values"] = chars
                    p.session_var.set(f"Profiles: {len(chars)} found")
                except Exception:
                    pass

        # Preferred profile order (case-insensitive matching)
        preferred_order = [
            'gimpygimp',
            'navore viliana',
            'alpirant ambrye',
            'sens codolle',
            'garietta orlenard',
            'blala benuse',
            'egghetlate pappotte'
        ]

        profiles_to_assign = []
        available_chars = list(self.char_index.keys())

        if isinstance(self.last_profile, list):
            for prof in self.last_profile:
                if prof and prof in available_chars and prof not in profiles_to_assign:
                    profiles_to_assign.append(prof)
                    try:
                        available_chars.remove(prof)
                    except Exception:
                        pass

        for pref_name in preferred_order:
            for char in list(available_chars):
                if char.lower() == pref_name.lower():
                    profiles_to_assign.append(char)
                    available_chars.remove(char)
                    break

        if available_chars:
            remaining_newest = get_newest_profiles({k: v for k, v in self.char_index.items() if k in available_chars}, len(available_chars))
            profiles_to_assign.extend(remaining_newest)

        capacity_values = None
        if isinstance(self.last_capacity, list):
            capacity_values = []
            for val in self.last_capacity:
                if val is None:
                    continue
                capacity_values.append(val)

        non_agg_index = 0
        for p in self.panels:
            if getattr(p, 'is_aggregate', False):
                continue
            if non_agg_index < len(profiles_to_assign):
                try:
                    prof = profiles_to_assign[non_agg_index]
                    if capacity_values and non_agg_index < len(capacity_values) and capacity_values[non_agg_index] is not None:
                        p.capacity_m3_var.set(capacity_values[non_agg_index])
                    p.rescan()
                    if prof in p.char_select['values']:
                        p.char_select.set(prof)
                        p.select_char()
                except Exception:
                    pass
            non_agg_index += 1

    def open_aggregate_popout(self):
        # Toggle the aggregate popout window
        try:
            if self.aggregate_popout:
                try:
                    if self.aggregate_popout.window.winfo_exists():
                        # Close if already open
                        self.aggregate_popout._on_close()
                except Exception:
                    pass
                self.aggregate_popout = None
                return
        except Exception:
            pass
        try:
            self.aggregate_popout = AggregateHoldPopout(self)
        except Exception as e:
            try:
                messagebox.showerror("Error", f"Failed to open popout: {e}")
            except Exception:
                pass

    def open_monthly_isk_popout(self):
        # Toggle the monthly ISK popout window
        try:
            if self.monthly_isk_popout:
                try:
                    if self.monthly_isk_popout.window.winfo_exists():
                        # Close if already open
                        self.monthly_isk_popout._on_close()
                except Exception:
                    pass
                self.monthly_isk_popout = None
                return
        except Exception:
            pass
        try:
            self.monthly_isk_popout = MonthlyISKPopout(self)
        except Exception as e:
            try:
                messagebox.showerror("Error", f"Failed to open monthly ISK popout: {e}")
            except Exception:
                pass

    def calculate_monthly_isk(self, year: int, month: int):
        prices = load_price_map()
        total_isk, qty_by_res = compute_monthly_isk_for_folder(self.folder, year, month, prices)
        # Calculate weekly ISK instead of yesterday
        w_total, _ = compute_weekly_isk_for_folder(self.folder, prices)
        try:
            today = datetime.now()
            # Use reset time if available and it's from today
            start_time = None
            if self.today_reset_time:
                reset_date = self.today_reset_time.date()
                today_date = today.date()
                if reset_date == today_date:
                    start_time = self.today_reset_time
            t_total, _ = compute_daily_isk_for_folder(self.folder, today, prices, start_time)
        except Exception:
            t_total = 0.0
        return total_isk, qty_by_res, prices, w_total, t_total

    def get_monthly_cache(self):
        try:
            with self._monthly_cache_lock:
                return self._monthly_cache
        except Exception:
            return None

    def reset_today_isk(self):
        """Reset today's ISK tracking to start counting from now."""
        self.today_reset_time = datetime.now()
        self.save_settings()
        # Force refresh to show updated values
        now = datetime.now()
        self.request_monthly_refresh(now.year, now.month, force=True)

    def open_prices_file(self):
        """Toggle the price editor popout."""
        try:
            if self.price_editor_popout:
                try:
                    if self.price_editor_popout.window.winfo_exists():
                        # Close if already open
                        self.price_editor_popout._on_close()
                except Exception:
                    pass
                self.price_editor_popout = None
                return
        except Exception:
            pass
        try:
            self.price_editor_popout = PriceEditorPopout(self)
        except Exception as e:
            try:
                messagebox.showerror("Error", f"Failed to open price editor: {e}")
            except Exception:
                pass

    def on_primary_color_change(self, value):
        """Update primary color hue."""
        try:
            self.custom_primary_hue = int(float(value))
            self.save_settings()
            self.apply_theme()
        except Exception:
            pass

    def on_accent_color_change(self, value):
        """Update accent color hue."""
        try:
            self.custom_accent_hue = int(float(value))
            self.save_settings()
            self.apply_theme()
        except Exception:
            pass

    def force_monthly_refresh(self):
        """Force a refresh of monthly ISK data."""
        try:
            now = datetime.now()
            self.request_monthly_refresh(now.year, now.month, force=True)
        except Exception:
            pass

    def request_monthly_refresh(self, year: int, month: int, force: bool = False):
        now = time.monotonic()
        with self._monthly_cache_lock:
            if self._monthly_refreshing:
                return
            cached = self._monthly_cache
            if cached and not force:
                c_year, c_month, _result, ts = cached
                if c_year == year and c_month == month and (now - ts) < 60.0:
                    return
            self._monthly_refreshing = True

        def worker():
            try:
                result = self.calculate_monthly_isk(year, month)
                with self._monthly_cache_lock:
                    self._monthly_cache = (year, month, result, time.monotonic())
            finally:
                with self._monthly_cache_lock:
                    self._monthly_refreshing = False
            try:
                self.root.after(0, self._notify_monthly_cache_updated)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _notify_monthly_cache_updated(self):
        try:
            if self.monthly_isk_popout and self.monthly_isk_popout.window.winfo_exists():
                self.monthly_isk_popout.update_from_cache()
        except Exception:
            pass

    def update_aggregate_popout(self):
        # Refresh the aggregate popout if present
        try:
            if self.aggregate_popout and self.aggregate_popout.window.winfo_exists():
                # If panels have changed, rebuild rows
                try:
                    expected = {p for p in self.panels if not getattr(p, 'is_aggregate', False)}
                    have = set(self.aggregate_popout.rows.keys())
                    if expected != have:
                        self.aggregate_popout._build_rows()
                except Exception:
                    pass
                self.aggregate_popout.refresh()
        except Exception:
            pass

    def save_settings(self):
        # capture geometry and state here; prefer last captured values from on_configure
        try:
            if not self.window_geometry:
                self.window_geometry = self.root.geometry()
            if not self.window_state:
                self.window_state = self.root.state()
        except Exception:
            pass
        data = {
            "folder": self.folder_var.get(),
            # Save list of profiles for each panel for multi-panel support
            "profiles": [None if getattr(p, 'is_aggregate', False) else (p.char_select.get() if p.char_select.get() else None) for p in self.panels],
            "capacities": [None if getattr(p, 'is_aggregate', False) else p.capacity_m3_var.get() for p in self.panels],
            "panel_count": self.panel_count,
            "dark_theme": self.dark_theme_var.get() if getattr(self, 'dark_theme_var', None) is not None else True,
            "window_geometry": self.window_geometry,
            "window_state": self.window_state,
            "today_reset_time": self.today_reset_time.isoformat() if self.today_reset_time else None,
            "custom_primary_hue": self.custom_primary_hue,
            "custom_accent_hue": self.custom_accent_hue,
        }
        try:
            with self.settings_file.open("w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass

    def on_close(self):
        try:
            self.save_settings()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def apply_theme(self):
        try:
            dark = bool(self.dark_theme_var.get())
            # Use clam for better color control, fall back silently
            try:
                self.style.theme_use('clam')
            except Exception:
                pass
            # Eve Online spaceship theme with custom colors
            bg = '#0A0E27' if dark else '#ffffff'
            # Use custom hue for primary color (foreground/text)
            fg = hsv_to_hex(self.custom_primary_hue, 1.0, 0.83) if dark else '#000000'
            frame_bg = '#0F1535' if dark else '#f0f0f0'
            header_bg = '#1A2B4F' if dark else '#d9d9d9'
            entry_bg = '#0F1535' if dark else '#ffffff'
            # Use custom hue for accent color
            accent_fg = hsv_to_hex(self.custom_accent_hue, 1.0, 0.99) if dark else '#000000'
            # Frame and root
            try:
                self.root.configure(background=bg)
                # global listbox options affect combobox popdown lists
                self.root.option_add('*Listbox.background', entry_bg)
                self.root.option_add('*Listbox.foreground', fg)
                self.root.option_add('*Listbox.selectBackground', header_bg)
                self.root.option_add('*Listbox.selectForeground', fg)
            except Exception:
                pass
            self.style.configure('TFrame', background=frame_bg)
            self.style.configure('TLabel', background=frame_bg, foreground=fg)
            self.style.configure('TButton', background=frame_bg)
            self.style.configure('TButton', foreground=fg)
            self.style.map('TButton', foreground=[('!disabled', fg), ('active', fg)])
            self.style.configure('TCheckbutton', background=frame_bg, foreground=fg)
            self.style.configure('TEntry', fieldbackground=entry_bg, foreground=fg, background=entry_bg)
            self.style.map('TEntry', fieldbackground=[('!disabled', entry_bg)], foreground=[('!disabled', fg)])
            self.style.configure('TCombobox', fieldbackground=entry_bg, foreground=fg, background=entry_bg)
            self.style.map('TCombobox', fieldbackground=[('readonly', entry_bg), ('!disabled', entry_bg)], foreground=[('readonly', fg), ('!disabled', fg)])
            # Also set the Combobox listbox colors (platform dependent)
            try:
                self.style.configure('TListbox', background=entry_bg, foreground=fg)
            except Exception:
                pass
            self.style.configure('Treeview', background=frame_bg, fieldbackground=frame_bg, foreground=fg, rowheight=12)
            self.style.configure('Treeview.Heading', background=header_bg, foreground=fg)
            # update any labels that need specific colors
            try:
                for p in self.panels:
                    p.hold_pct_label.configure(foreground=accent_fg)
                    # Make combobox / entries match dark background
                    try:
                        p.char_select.configure(background=entry_bg, foreground=fg)
                    except Exception:
                        pass
                    # update large hold percent canvas background and text color
                    try:
                        if getattr(p, 'hold_pct_canvas', None) is not None:
                            p.hold_pct_canvas.configure(bg=frame_bg)
                            # update default fg and reapply color/text
                            p.default_hold_fg = fg
                            try:
                                cur = p.hold_pct_var.get()
                                p.update_hold_percent_style(float(cur.strip('%'))/100 if cur and '%' in cur else 0.0)
                            except Exception:
                                pass
                    except Exception:
                        pass
                    # update wrapper background if available (tk.Frame used for borders)
                    try:
                        if getattr(p, 'wrapper', None) is not None:
                            p.wrapper.configure(bg=frame_bg, highlightthickness=2, highlightbackground=fg)
                    except Exception:
                        pass
            except Exception:
                pass
            # Update aggregate popout theme if open
            try:
                if getattr(self, 'aggregate_popout', None) and self.aggregate_popout.window.winfo_exists():
                    self.aggregate_popout.window.configure(bg=bg)
                    try:
                        self.aggregate_popout.canvas.configure(bg=bg)
                        self.aggregate_popout.content.configure(bg=bg)
                        # Update row labels foregrounds
                        for p, (name_lbl, pct_lbl) in self.aggregate_popout.rows.items():
                            try:
                                name_lbl.configure(bg=bg, fg=fg)
                                pct_lbl.configure(bg=bg, fg=accent_fg)
                            except Exception:
                                pass
                        # Update resize grip color
                        try:
                            self.aggregate_popout.grip.configure(bg=fg)
                        except Exception:
                            pass
                    except Exception:
                        pass
            except Exception:
                pass
            # Update monthly ISK popout theme if open
            try:
                if getattr(self, 'monthly_isk_popout', None) and self.monthly_isk_popout.window.winfo_exists():
                    self.monthly_isk_popout.apply_theme()
            except Exception:
                pass
            # Update price editor popout theme if open
            try:
                if getattr(self, 'price_editor_popout', None) and self.price_editor_popout.window.winfo_exists():
                    self.price_editor_popout.apply_theme()
            except Exception:
                pass
            # Update color sliders in main window
            try:
                if hasattr(self, 'primary_slider'):
                    self.primary_slider.configure(bg=frame_bg, fg=fg, troughcolor=entry_bg, 
                                                 activebackground=fg, highlightbackground=frame_bg)
                if hasattr(self, 'accent_slider'):
                    self.accent_slider.configure(bg=frame_bg, fg=accent_fg, troughcolor=entry_bg,
                                                activebackground=accent_fg, highlightbackground=frame_bg)
            except Exception:
                pass
        except Exception:
            pass

    def on_configure(self, event=None):
        # only store geometry/state when window is mapped and not 'withdrawn'
        try:
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            if w > 50 and h > 50:
                # build geometry string
                try:
                    x = self.root.winfo_x()
                    y = self.root.winfo_y()
                    self.window_geometry = f"{w}x{h}+{x}+{y}"
                except Exception:
                    # fall back to raw geometry
                    self.window_geometry = self.root.geometry()
            # store current state (normal/minimized/zoomed)
            try:
                st = self.root.state()
                self.window_state = st
            except Exception:
                pass
        except Exception:
            pass

    def load_settings(self):
        if self.settings_file.exists():
            try:
                with self.settings_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if "folder" in data:
                    self.folder_var.set(data["folder"])
                    self.folder = Path(data["folder"])
                # Multi-panel settings (profiles and capacities lists)
                self.last_profile = data.get("profiles") or data.get("profile")
                self.last_capacity = data.get("capacities") or data.get("capacity_m3")
                try:
                    self.panel_count = max(2, int(data.get("panel_count", self.panel_count)))
                except Exception:
                    self.panel_count = max(2, int(self.panel_count)) if self.panel_count else 8
                # restore dark theme preference
                try:
                    self.dark_theme_var.set(data.get("dark_theme", True))
                except Exception:
                    pass
                # restore window geometry/state
                try:
                    self.window_geometry = data.get('window_geometry')
                    self.window_state = data.get('window_state')
                except Exception:
                    self.window_geometry = None
                    self.window_state = None
                # restore today reset time
                try:
                    reset_str = data.get('today_reset_time')
                    if reset_str:
                        self.today_reset_time = datetime.fromisoformat(reset_str)
                    else:
                        self.today_reset_time = None
                except Exception:
                    self.today_reset_time = None
                # restore custom colors
                try:
                    self.custom_primary_hue = int(data.get('custom_primary_hue', 190))
                    self.custom_accent_hue = int(data.get('custom_accent_hue', 100))
                except Exception:
                    self.custom_primary_hue = 190
                    self.custom_accent_hue = 100
            except Exception:
                self.last_profile = None
                self.last_capacity = None
                self.window_geometry = None
                self.window_state = None
        else:
            self.last_profile = None
            self.last_capacity = None
            self.window_geometry = None
            self.window_state = None

    def refresh_all(self):
        # Build aggregated session state for the aggregate panel (last panel)
        agg_panel = None
        try:
            agg_panel = self.panels[-1]
        except Exception:
            agg_panel = None
        agg_state = MiningState()
        for p in self.panels:
            if getattr(p, 'is_aggregate', False):
                continue
            s = p.session_state
            try:
                agg_state.total_units += s.total_units
                agg_state.total_residue += s.total_residue
                agg_state.crits += s.crits
                agg_state.extra_from_crits += s.extra_from_crits
                # merge by_resource
                for rname, qty in s.by_resource.items():
                    agg_state.by_resource[rname] = agg_state.by_resource.get(rname, 0) + qty
                # earliest session start
                if s.session_start:
                    if not agg_state.session_start or s.session_start < agg_state.session_start:
                        agg_state.session_start = s.session_start
            except Exception:
                pass
        # assign aggregated session state to aggregate panel
        if agg_panel:
            try:
                agg_panel.session_state = agg_state
                # also set a blank current state
                agg_panel.state = MiningState()
            except Exception:
                pass
        # refresh each panel now
        for p in self.panels:
            try:
                p.refresh()
            except Exception:
                pass
        # Update aggregate popout after panels refresh
        try:
            self.update_aggregate_popout()
        except Exception:
            pass
        # Update monthly ISK popout on interval
        try:
            if self.monthly_isk_popout and self.monthly_isk_popout.window.winfo_exists():
                self.monthly_isk_popout.maybe_refresh()
        except Exception:
            pass
        self.save_settings()
        self.root.after(1000, self.refresh_all)

# ==== PART 3D: SPLASH/LAUNCH WINDOW ====

class SplashWindow:
    """Splash screen shown during app launch with progress bar."""
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Calm Down Miner - Ice Edition")
        self.window.resizable(False, False)
        
        # Eve Online theme colors
        bg = '#0A0E27'
        fg = '#00D4FF'
        self.window.configure(bg=bg)
        
        # Make it always on top
        try:
            self.window.attributes('-topmost', True)
        except Exception:
            pass
        
        # Main content frame
        content = tk.Frame(self.window, bg=bg)
        content.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Title
        title = tk.Label(content, text="⚡ CALM DOWN MINER - ICE EDITION ⚡", bg=bg, fg=fg, 
                         font=('Courier New', 20, 'bold'))
        title.pack(pady=(0, 15))
        
        # Status text
        self.status_label = tk.Label(content, text="INITIALIZING...", bg=bg, fg='#39FF14',
                                     font=('Courier New', 12, 'bold'))
        self.status_label.pack(pady=(0, 15))
        
        # Progress bar
        self.progress = ttk.Progressbar(content, length=500, mode='determinate', 
                                        maximum=100, value=0)
        self.progress.pack(pady=(0, 10))
        
        # Percentage text
        self.pct_label = tk.Label(content, text="0%", bg=bg, fg=fg,
                                  font=('Courier New', 12))
        self.pct_label.pack()
        
        # Configure progress bar style to match Eve Online theme
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TProgressbar', background='#39FF14', troughcolor='#0F1535', 
                       bordercolor='#00D4FF', lightcolor='#39FF14', darkcolor='#39FF14')
        
        # Set initial geometry and center it
        self.window.geometry("600x225")
        self.window.update_idletasks()
        
        # Get actual window dimensions
        window_width = self.window.winfo_width()
        window_height = self.window.winfo_height()
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        
        # Calculate center position
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        
        # Set geometry with position
        self.window.geometry(f"+{x}+{y}")
        self.window.update()
    
    def update_status(self, status_text: str, progress: int = None):
        """Update splash screen status and progress."""
        try:
            self.status_label.configure(text=status_text)
            if progress is not None:
                self.progress['value'] = min(100, max(0, progress))
                self.pct_label.configure(text=f"{progress}%")
            self.window.update()
        except Exception:
            pass
    
    def close(self):
        """Close the splash window."""
        try:
            self.window.destroy()
        except Exception:
            pass

def main():
    folder = Path.home() / "Documents" / "EVE" / "logs" / "Gamelogs"
    
    # Create root window but keep it hidden
    root = tk.Tk()
    root.title("⚡ CALM DOWN MINER - ICE EDITION ⚡")
    root.withdraw()  # Hide the root window
    try:
        root.resizable(True, True)
    except Exception:
        pass
    
    # Create and show splash window (standalone, not child of root)
    splash = SplashWindow()
    splash.update_status("INITIALIZING...", 5)
    time.sleep(0.8)
    
    # Create app with progress updates
    splash.update_status("SCANNING PROFILES...", 25)
    time.sleep(1.0)
    app = App(root, folder)
    
    # Update splash progress for remaining initialization
    splash.update_status("BUILDING INTERFACE...", 75)
    root.update()
    time.sleep(0.8)
    
    splash.update_status("LAUNCHING COCKPIT...", 100)
    time.sleep(1.5)  # Longer pause to show completion
    
    # Close splash and show main window
    splash.close()
    root.deiconify()  # Show the root window
    
    root.mainloop()

if __name__ == "__main__":
    main()
# ==== PART 4 ENDS HERE ====