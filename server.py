#!/usr/bin/env python3
"""
Sagar Kerhalkar System Monitor Tool - zero dependency receiver + premium dashboard.
Runs with Python standard library only.
Default: http://0.0.0.0:2278
"""
from __future__ import annotations

import argparse
import ast
import base64
import csv
import datetime as dt
import html
import hmac
import hashlib
import io
import json
import os
import re
import secrets
import sqlite3
import subprocess
import threading
import time
import traceback
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# SK_NOTIFICATION_EXTRA_METRICS_START
def _sk_num(v, default=0.0):
    try:
        if isinstance(v, bool):
            return 1.0 if v else 0.0
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip().replace("%", "").replace("°C", "").replace("C", "")
        return float(s)
    except Exception:
        return default

def _sk_walk_values(obj, prefix=""):
    try:
        if isinstance(obj, dict):
            for k, v in obj.items():
                kk = (prefix + "." + str(k)).strip(".")
                yield kk, v
                yield from _sk_walk_values(v, kk)
        elif isinstance(obj, list):
            for i, v in enumerate(obj[:200]):
                yield prefix + "." + str(i), v
                yield from _sk_walk_values(v, prefix + "." + str(i))
    except Exception:
        return

def _sk_enrich_notification_metrics(summary, payload):
    """Adds composite metrics used by notification rules without changing existing logic."""
    try:
        if not isinstance(summary, dict):
            return summary

        all_pairs = []
        try:
            all_pairs.extend(list(_sk_walk_values(summary)))
        except Exception:
            pass
        try:
            all_pairs.extend(list(_sk_walk_values(payload)))
        except Exception:
            pass

        def first_metric(names):
            for k, v in all_pairs:
                lk = str(k).lower()
                if any(n in lk for n in names):
                    n = _sk_num(v, None)
                    if n is not None:
                        return n
            return 0.0

        cpu = _sk_num(summary.get("cpu_percent") or summary.get("cpu_usage_percent") or summary.get("cpu_usage") or first_metric(["cpu_percent", "cpu.usage", "cpu_usage"]), 0)
        ram = _sk_num(summary.get("ram_percent") or summary.get("memory_percent") or summary.get("ram_usage_percent") or first_metric(["ram_percent", "memory_percent", "ram.usage", "memory.usage"]), 0)

        if cpu and ram:
            summary["cpu_ram_combined_percent"] = round(min(cpu, ram), 2)
            summary["cpu_ram_peak_percent"] = round(max(cpu, ram), 2)
        else:
            summary["cpu_ram_combined_percent"] = round(max(cpu, ram), 2)
            summary["cpu_ram_peak_percent"] = round(max(cpu, ram), 2)

        disk_vals = []
        temp_vals = []
        core_vals = []

        for k, v in all_pairs:
            lk = str(k).lower()
            n = _sk_num(v, None)
            if n is None:
                continue

            # Disk / SSD / HDD usage percent
            if (
                ("disk" in lk or "ssd" in lk or "hdd" in lk or "drive" in lk or "storage" in lk)
                and ("percent" in lk or "pct" in lk or "usage" in lk or "used" in lk)
                and 0 <= n <= 100
            ):
                disk_vals.append(n)

            # CPU / GPU temperature
            if (
                ("temp" in lk or "temperature" in lk)
                and ("cpu" in lk or "gpu" in lk or "processor" in lk or "graphics" in lk)
                and 10 <= n <= 130
            ):
                temp_vals.append(n)

            # Thread / Core usage
            if (
                ("core" in lk or "thread" in lk or "logical" in lk)
                and ("percent" in lk or "pct" in lk or "usage" in lk or "load" in lk)
                and 0 <= n <= 100
            ):
                core_vals.append(n)

        summary["max_disk_used_percent"] = round(max(disk_vals) if disk_vals else _sk_num(summary.get("disk_used_percent") or summary.get("storage_used_percent"), 0), 2)
        summary["cpu_gpu_temp_max_c"] = round(max(temp_vals) if temp_vals else _sk_num(summary.get("cpu_temp_c") or summary.get("gpu_temp_c") or summary.get("temperature_c"), 0), 2)
        summary["thread_core_usage_percent"] = round(max(core_vals) if core_vals else _sk_num(summary.get("cpu_core_max_percent") or summary.get("thread_usage_percent"), 0), 2)

        return summary
    except Exception:
        return summary
# SK_NOTIFICATION_EXTRA_METRICS_END



BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"
SCRIPTS_DIR = BASE_DIR / "scripts"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "monitor.db"
LOG_PATH = DATA_DIR / "server.log"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_LOCK = threading.RLock()
SERVER_ISP_LOCK = threading.RLock()
SERVER_ISP_REFRESHING = False
SERVER_ISP_MEMORY: Dict[str, Any] = {"public_ip":"", "isp":"", "org":"", "as":"", "country":"", "city":"", "checked_at":"", "source":"not_checked", "ok":False}

APP_NAME = "Sagar Kerhalkar System Health Monitor Tool"
DEFAULT_ADMIN_PASSWORD = os.environ.get("CMP_ADMIN_PASSWORD", "Admin@12345")
SESSIONS: Dict[str, float] = {}
SESSION_TTL_SECONDS = 12 * 60 * 60
INTERNET_HEALTH_LOCK = threading.RLock()
INTERNET_HEALTH_CACHE: Dict[str, Any] = {"ok": False, "checked_at": "", "source": "not_checked"}
INTERNET_HEALTH_REFRESHING = False


BAD_IDS = {
    "", "none", "null", "unknown", "na", "n/a", "not available", "not applicable",
    "default string", "to be filled by o.e.m.", "to be filled by oem", "system serial number",
    "base board serial number", "chassis serial number", "0", "00000000", "ffffffff",
    "00000000-0000-0000-0000-000000000000", "ffffffff-ffff-ffff-ffff-ffffffffffff",
    "bss-0123456789", "bss0123456789", "0123456789", "123456789", "1234567890",
    "serial number", "system product name", "all series", "not specified", "not to be filled"
}

BAD_ID_PATTERNS = [
    r"^bss[-_ ]*0*123456789$",
    r"^bss[-_ ]*[0-9]{4,}$",
    r"^o\.e\.m",
    r"^to be filled",
    r"^default",
    r"^1234567",
    r"^0{4,}$",
    r"^f{4,}$",
]

DEFAULT_RULES = [
    {"id":"cpu_high","name":"CPU usage high","metric":"cpu_percent","op":">=","threshold":90,"enabled":True,"severity":"warning","cooldown_minutes":15},
    {"id":"ram_high","name":"RAM usage high","metric":"ram_percent","op":">=","threshold":90,"enabled":True,"severity":"warning","cooldown_minutes":15},
    {"id":"disk_high","name":"Disk usage high","metric":"disk_max_percent","op":">=","threshold":90,"enabled":True,"severity":"critical","cooldown_minutes":30},
    {"id":"cpu_temp_high","name":"CPU temperature high","metric":"cpu_temp_c","op":">=","threshold":85,"enabled":False,"severity":"critical","cooldown_minutes":20},
    {"id":"gpu_temp_high","name":"GPU temperature high","metric":"gpu_max_temp_c","op":">=","threshold":85,"enabled":False,"severity":"critical","cooldown_minutes":20},
    {"id":"wan_down_low","name":"Current download speed low","metric":"wan_download_mbps","op":"<=","threshold":1,"enabled":False,"severity":"warning","cooldown_minutes":15},
    {"id":"wan_up_low","name":"Current upload speed low","metric":"wan_upload_mbps","op":"<=","threshold":1,"enabled":False,"severity":"warning","cooldown_minutes":15},
    {"id":"offline","name":"Machine offline","metric":"offline_minutes","op":">=","threshold":1,"enabled":True,"severity":"critical","cooldown_minutes":5},
    {"id":"usb_change","name":"USB or peripheral changed","metric":"change_usb","op":"event","threshold":1,"enabled":False,"severity":"info","cooldown_minutes":1},
    {"id":"hardware_change","name":"Hardware changed","metric":"change_hardware","op":"event","threshold":1,"enabled":False,"severity":"warning","cooldown_minutes":2},
    {"id":"software_change","name":"Software installed/removed","metric":"change_software","op":"event","threshold":1,"enabled":False,"severity":"info","cooldown_minutes":5},
    {"id":"ip_change","name":"IP address changed","metric":"change_ip","op":"event","threshold":1,"enabled":False,"severity":"info","cooldown_minutes":2},
    {"id":"vpn_change","name":"VPN status changed","metric":"change_vpn","op":"event","threshold":1,"enabled":False,"severity":"warning","cooldown_minutes":2},
]

MIME = {
    ".html":"text/html; charset=utf-8", ".css":"text/css; charset=utf-8", ".js":"application/javascript; charset=utf-8",
    ".json":"application/json; charset=utf-8", ".svg":"image/svg+xml", ".ico":"image/x-icon", ".txt":"text/plain; charset=utf-8", ".ps1":"text/plain; charset=utf-8", ".sh":"text/plain; charset=utf-8", ".bat":"text/plain; charset=utf-8", ".deb":"application/vnd.debian.binary-package"
}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def log(msg: str) -> None:
    line = f"{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}\n"
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def hash_password(password: str, salt: Optional[str] = None) -> str:
    salt = salt or _b64(secrets.token_bytes(16))
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return "pbkdf2_sha256$120000$" + salt + "$" + _b64(dk)


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt, good = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iters))
        return hmac.compare_digest(_b64(dk), good)
    except Exception:
        return False


def parse_cookies(header: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in (header or "").split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            out[k] = v
    return out


def is_local_request(client_ip: str) -> bool:
    ip = (client_ip or "").strip()
    return ip in {"127.0.0.1", "::1", "localhost"} or ip.startswith("127.")


def new_session(username: str = "admin", role: str = "admin") -> str:
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = {"expires": time.time() + SESSION_TTL_SECONDS, "username": username or "admin", "role": role or "admin"}
    return token


def session_info(token: str) -> Dict[str, Any]:
    raw = SESSIONS.get(token or "")
    if not raw:
        return {}
    # Backward compatibility for older in-memory sessions that stored only expiry as float.
    if isinstance(raw, (int, float)):
        exp = float(raw)
        info = {"expires": exp, "username": "admin", "role": "admin"}
    elif isinstance(raw, dict):
        info = dict(raw)
        exp = float(info.get("expires") or 0)
    else:
        return {}
    if exp < time.time():
        SESSIONS.pop(token, None)
        return {}
    info["expires"] = time.time() + SESSION_TTL_SECONDS
    SESSIONS[token] = info
    return info


def valid_session(token: str) -> bool:
    return bool(session_info(token))


def auth_required_path(method: str, path: str) -> bool:
    # Heartbeats and install scripts must stay open so clients can report and update.
    public_get = {"/api/health", "/api/auth/status"}
    public_post = {"/api/heartbeat", "/heartbeat", "/submit", "/api/auth/login"}
    if method == "GET" and (path in public_get or path.startswith("/scripts/")):
        return False
    if method == "POST" and path in public_post:
        return False
    if method == "GET" and not path.startswith("/api/"):
        return False
    return path.startswith("/api/")


def tcp_latency_ms(host: str, port: int, timeout: float = 1.5) -> Optional[float]:
    import socket
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return round((time.perf_counter() - t0) * 1000, 1)
    except Exception:
        return None


def run_ping_probe(host: str = "1.1.1.1", count: int = 4) -> Dict[str, Any]:
    result: Dict[str, Any] = {"host": host, "sent": count, "received": 0, "loss_percent": 100.0, "avg_ms": None, "min_ms": None, "max_ms": None, "jitter_ms": None}
    try:
        if os.name == "nt":
            cmd = ["ping", "-n", str(count), "-w", "1000", host]
        else:
            cmd = ["ping", "-c", str(count), "-W", "1", host]
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=count + 3)
        text = (cp.stdout or "") + "\n" + (cp.stderr or "")
        times = [float(x) for x in re.findall(r"time[=<]\s*([0-9.]+)\s*ms", text, flags=re.I)]
        result["received"] = len(times)
        if count > 0:
            result["loss_percent"] = round(max(0, (count - len(times)) * 100.0 / count), 1)
        if times:
            result["avg_ms"] = round(sum(times)/len(times), 1)
            result["min_ms"] = round(min(times), 1)
            result["max_ms"] = round(max(times), 1)
            result["jitter_ms"] = round(max(times)-min(times), 1)
    except Exception as e:
        result["error"] = str(e)
    return result


def server_internet_health(force: bool = False, speed_probe: bool = False) -> Dict[str, Any]:
    """Live server-side ISP health. Latency/loss is light; speed probe is small and cached."""
    global INTERNET_HEALTH_CACHE, INTERNET_HEALTH_REFRESHING
    with INTERNET_HEALTH_LOCK:
        try:
            checked = dt.datetime.fromisoformat(str(INTERNET_HEALTH_CACHE.get("checked_at", "")).replace("Z", "+00:00"))
            age = (dt.datetime.now(dt.timezone.utc) - checked).total_seconds()
        except Exception:
            age = 9999
        if not force and INTERNET_HEALTH_CACHE.get("ok") and age < 15:
            return dict(INTERNET_HEALTH_CACHE)
    isp = server_public_internet_info(False)
    # Use multiple latency methods. ICMP ping can be blocked on many Windows networks,
    # so TCP 443 fallback keeps the dashboard from showing N/A for live-class latency.
    tcp_targets = [("cloudflare_dns", "1.1.1.1", 443), ("cloudflare_site", "www.cloudflare.com", 443), ("google_dns", "8.8.8.8", 53)]
    latency = []
    for name, host, port in tcp_targets:
        latency.append({"name": name, "host": host, "port": port, "tcp_ms": tcp_latency_ms(host, port)})
    ping = run_ping_probe("1.1.1.1", 4)
    down_mbps = None
    up_mbps = None
    speed_note = "Live server ISP health probe. This is for class stability; use Full Speed Test for capacity."
    if speed_probe:
        try:
            size = 2_000_000
            url = f"https://speed.cloudflare.com/__down?bytes={size}"
            t0 = time.perf_counter()
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": APP_NAME}), timeout=8) as r:
                data = r.read(size + 128)
            elapsed = max(0.001, time.perf_counter() - t0)
            down_mbps = round((len(data) * 8 / 1_000_000) / elapsed, 2)
        except Exception as e:
            speed_note = "Download probe failed: " + str(e)[:120]
        try:
            size = 512_000
            req = urllib.request.Request("https://speed.cloudflare.com/__up", data=(b"0" * size), headers={"User-Agent": APP_NAME, "Content-Type":"application/octet-stream"}, method="POST")
            t0 = time.perf_counter()
            urllib.request.urlopen(req, timeout=8).read(2000)
            elapsed = max(0.001, time.perf_counter() - t0)
            up_mbps = round((size * 8 / 1_000_000) / elapsed, 2)
            speed_note = "Live server probe for online classes; not a full ISP capacity test."
        except Exception as e:
            if speed_note.startswith("Speed probe"):
                speed_note = "Upload probe failed: " + str(e)[:120]
    health = {
        "ok": True,
        "checked_at": now_iso(),
        "app_name": APP_NAME,
        "isp": isp,
        "isp_name": isp.get("isp") or isp.get("org") or isp.get("as") or "",
        "public_ip": isp.get("public_ip") or "",
        "latency": latency,
        "ping": ping,
        "latency_ms": ping.get("avg_ms") or next((x.get("tcp_ms") for x in latency if x.get("tcp_ms") is not None), None),
        "avg_latency_ms": ping.get("avg_ms") or next((x.get("tcp_ms") for x in latency if x.get("tcp_ms") is not None), None),
        "jitter_ms": ping.get("jitter_ms") or 0,
        "packet_loss_percent": ping.get("loss_percent") if ping.get("loss_percent") is not None else (0 if any(x.get("tcp_ms") is not None for x in latency) else None),
        "loss_percent": ping.get("loss_percent") if ping.get("loss_percent") is not None else (0 if any(x.get("tcp_ms") is not None for x in latency) else None),
        "probe_download_mbps": down_mbps,
        "probe_upload_mbps": up_mbps,
        "speed_note": speed_note,
        "source": "server_probe"
    }
    with INTERNET_HEALTH_LOCK:
        INTERNET_HEALTH_CACHE = health
    return health

def fetch_json_url(url: str, timeout: int = 2) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "SagarSystemMonitor/6.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(200000).decode("utf-8", errors="replace")
    return json.loads(raw)


def _server_public_internet_lookup(timeout: int = 2) -> Dict[str, Any]:
    errors: List[str] = []
    candidates = [
        ("ipinfo", "https://ipinfo.io/json"),
        ("ip-api", "http://ip-api.com/json/?fields=status,query,isp,org,as,country,city"),
        ("ipify", "https://api.ipify.org?format=json"),
    ]
    for source, url in candidates:
        try:
            d = fetch_json_url(url, timeout=timeout)
            if source == "ipinfo":
                obj = {"public_ip": clean_str(d.get("ip")), "isp": clean_str(d.get("org")), "org": clean_str(d.get("org")), "as": clean_str(d.get("org")), "country": clean_str(d.get("country")), "city": clean_str(d.get("city")), "checked_at": now_iso(), "source": source, "ok": True}
            elif source == "ip-api":
                obj = {"public_ip": clean_str(d.get("query")), "isp": clean_str(d.get("isp") or d.get("org") or d.get("as")), "org": clean_str(d.get("org")), "as": clean_str(d.get("as")), "country": clean_str(d.get("country")), "city": clean_str(d.get("city")), "checked_at": now_iso(), "source": source, "ok": True}
            else:
                obj = {"public_ip": clean_str(d.get("ip")), "isp": "", "org": "", "as": "", "country": "", "city": "", "checked_at": now_iso(), "source": source, "ok": True}
            if obj.get("public_ip") or obj.get("isp"):
                return obj
        except Exception as e:
            errors.append(f"{source}: {e}")
    return {"public_ip":"", "isp":"", "org":"", "as":"", "country":"", "city":"", "checked_at":now_iso(), "source":"unavailable", "ok":False, "errors":errors[-3:]}


def _refresh_server_isp_background() -> None:
    global SERVER_ISP_MEMORY, SERVER_ISP_REFRESHING
    try:
        obj = _server_public_internet_lookup(timeout=2)
        with SERVER_ISP_LOCK:
            SERVER_ISP_MEMORY = obj
        try:
            (DATA_DIR / "server_isp_cache.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    finally:
        with SERVER_ISP_LOCK:
            SERVER_ISP_REFRESHING = False


def server_cloudflare_speed_test(download_bytes: int = 5_000_000, upload_bytes: int = 1_000_000) -> Dict[str, Any]:
    """Small manual server-side speed check. It uses real traffic, so it is not run automatically."""
    result: Dict[str, Any] = {"ok": False, "checked_at": now_iso(), "source": "cloudflare_speed_endpoint", "download_mbps": 0.0, "upload_mbps": 0.0, "note": "Manual test; not auto-run because speed tests consume bandwidth."}
    try:
        size = max(100_000, min(int(download_bytes), 50_000_000))
        url = f"https://speed.cloudflare.com/__down?bytes={size}"
        t0 = time.perf_counter()
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent":"SagarSystemMonitor/6.0"}), timeout=20) as r:
            data = r.read(size + 1000)
        elapsed = max(0.001, time.perf_counter() - t0)
        result["download_mbps"] = round((len(data) * 8 / 1_000_000) / elapsed, 2)
    except Exception as e:
        result["download_error"] = str(e)
    try:
        size = max(10_000, min(int(upload_bytes), 10_000_000))
        data = b"0" * size
        req = urllib.request.Request("https://speed.cloudflare.com/__up", data=data, headers={"User-Agent":"SagarSystemMonitor/6.0", "Content-Type":"application/octet-stream"}, method="POST")
        t0 = time.perf_counter()
        urllib.request.urlopen(req, timeout=20).read(2000)
        elapsed = max(0.001, time.perf_counter() - t0)
        result["upload_mbps"] = round((size * 8 / 1_000_000) / elapsed, 2)
    except Exception as e:
        result["upload_error"] = str(e)
    result["ok"] = bool(result.get("download_mbps") or result.get("upload_mbps"))
    return result


def server_public_internet_info(force: bool = False) -> Dict[str, Any]:
    """Non-blocking server-side ISP fallback for the dashboard home screen."""
    global SERVER_ISP_MEMORY, SERVER_ISP_REFRESHING
    cache_path = DATA_DIR / "server_isp_cache.json"
    if SERVER_ISP_MEMORY.get("source") == "not_checked" and cache_path.exists():
        try:
            with SERVER_ISP_LOCK:
                SERVER_ISP_MEMORY = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    if force:
        obj = _server_public_internet_lookup(timeout=2)
        with SERVER_ISP_LOCK:
            SERVER_ISP_MEMORY = obj
        try:
            cache_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        return obj
    # If stale/missing, refresh in background and immediately return old value so /api/overview never hangs.
    stale = True
    try:
        checked = dt.datetime.fromisoformat(str(SERVER_ISP_MEMORY.get("checked_at", "")).replace("Z", "+00:00"))
        stale = (dt.datetime.now(dt.timezone.utc) - checked).total_seconds() > 1800
    except Exception:
        stale = True
    with SERVER_ISP_LOCK:
        current = dict(SERVER_ISP_MEMORY)
        if stale and not SERVER_ISP_REFRESHING:
            SERVER_ISP_REFRESHING = True
            threading.Thread(target=_refresh_server_isp_background, daemon=True).start()
    return current


def clean_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def valid_machine_id_part(v: Any) -> str:
    s = clean_str(v)
    if not s:
        return ""
    low = re.sub(r"\s+", " ", s.lower()).strip()
    compact = re.sub(r"[^a-z0-9]", "", low)
    if low in BAD_IDS or compact in BAD_IDS:
        return ""
    if re.fullmatch(r"0+", compact) or re.fullmatch(r"f+", compact):
        return ""
    for pat in BAD_ID_PATTERNS:
        try:
            if re.search(pat, low) or re.search(pat, compact):
                return ""
        except Exception:
            pass
    if len(s) < 3:
        return ""
    return s


def first_physical_mac(payload: Dict[str, Any]) -> str:
    """Pick a stable network MAC for fallback identity.
    Many Windows PCs report fake board serials like BSS-0123456789.
    This fallback stops one PC replacing another in the dashboard.
    """
    adapters = get_nested(payload, ["network.adapters", "adapters"], [])
    best = ""
    for a in listify(adapters):
        if not isinstance(a, dict):
            continue
        mac = clean_str(a.get("mac") or a.get("mac_address") or a.get("MACAddress"))
        if not mac:
            continue
        mac_norm = re.sub(r"[^A-Fa-f0-9]", "", mac).upper()
        if len(mac_norm) < 12 or mac_norm in {"000000000000", "FFFFFFFFFFFF"}:
            continue
        desc = (clean_str(a.get("name")) + " " + clean_str(a.get("description"))).lower()
        if a.get("is_virtual") or a.get("is_vpn") or re.search(r"virtual|hyper-v|vmware|virtualbox|docker|wsl|loopback|tunnel|tap|tun|vpn", desc):
            if not best:
                best = mac_norm
            continue
        return mac_norm
    return best


def _safe_id(prefix: str, value: str) -> str:
    return prefix + ":" + re.sub(r"[^A-Za-z0-9_.:-]", "_", value)[:160]


def machine_fingerprint_value(payload: Dict[str, Any]) -> Tuple[str, str, str]:
    """Return stable, collision-safe machine identity.

    Client count fix:
    - Do NOT include hostname in the stable machine hash when MAC/UUID/BIOS/board exists.
      If the hostname changes, the same physical client must stay one dashboard machine.
    - Use hostname only as display text and as a last fallback when no stable anchor exists.
    """
    identity = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
    hostname = valid_machine_id_part(payload.get("hostname") or identity.get("hostname") or payload.get("computer_name")) or "UNKNOWN-HOST"
    mac = first_physical_mac(payload)
    board = valid_machine_id_part(identity.get("motherboard_serial") or payload.get("motherboard_serial") or payload.get("baseboard_serial"))
    uuid = valid_machine_id_part(identity.get("system_uuid") or payload.get("system_uuid") or payload.get("uuid"))
    bios = valid_machine_id_part(identity.get("bios_serial") or payload.get("bios_serial"))

    if mac:
        raw = "|".join(["MAC", mac.upper(), uuid.upper(), bios.upper(), board.upper()])
        short = hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16].upper()
        shown = f"{hostname} / {mac}" if hostname != "UNKNOWN-HOST" else mac
        return f"ASSET:{short}", "asset_fingerprint", shown
    if uuid:
        raw = "|".join(["UUID", uuid.upper(), bios.upper(), board.upper()])
        short = hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16].upper()
        shown = f"{hostname} / {uuid}" if hostname != "UNKNOWN-HOST" else uuid
        return f"ASSET:{short}", "uuid_fingerprint", shown
    if bios:
        raw = "|".join(["BIOS", bios.upper(), board.upper()])
        short = hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16].upper()
        shown = f"{hostname} / {bios}" if hostname != "UNKNOWN-HOST" else bios
        return f"ASSET:{short}", "bios_fingerprint", shown
    if board:
        return _safe_id("MOTHERBOARD_SERIAL", board), "motherboard_serial", board
    if hostname != "UNKNOWN-HOST":
        return _safe_id("HOSTNAME", hostname), "hostname_fallback", hostname
    return _safe_id("UNKNOWN", "UNKNOWN-HOST"), "unknown_fallback", "UNKNOWN-HOST"


def make_machine_identity(payload: Dict[str, Any]) -> Tuple[str, str, str]:
    return machine_fingerprint_value(payload)


def stable_machine_merge_key(payload: Dict[str, Any], summary: Optional[Dict[str, Any]] = None) -> str:
    """Stable duplicate-detection key for client count.

    This key ignores hostname whenever hardware/network identity exists. That lets the
    dashboard merge old-hostname and new-hostname rows as one physical client.
    """
    summary = summary or {}
    if not isinstance(payload, dict):
        payload = {}
    identity = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}

    mac = first_physical_mac(payload)
    uuid = valid_machine_id_part(identity.get("system_uuid") or payload.get("system_uuid") or payload.get("uuid"))
    bios = valid_machine_id_part(identity.get("bios_serial") or payload.get("bios_serial"))
    board = valid_machine_id_part(identity.get("motherboard_serial") or payload.get("motherboard_serial") or payload.get("baseboard_serial"))
    hostname = valid_machine_id_part(payload.get("hostname") or identity.get("hostname") or summary.get("hostname") or payload.get("computer_name"))

    if mac:
        return "mac:" + mac.upper()
    if uuid:
        return "uuid:" + uuid.upper()
    if bios:
        return "bios:" + bios.upper()
    if board:
        return "board:" + board.upper()
    if hostname:
        return "host:" + hostname.lower()
    return ""


def cleanup_duplicate_latest_rows(con: sqlite3.Connection, summary: Dict[str, Any], payload: Dict[str, Any]) -> List[str]:
    """Delete repeated/wrong current-state rows for the same client from `latest` only.

    Historical `heartbeats` stay untouched, so day history and reports remain available.
    """
    target_mid = clean_str(summary.get("machine_id"))
    target_key = stable_machine_merge_key(payload, summary)
    if not target_mid or not target_key:
        return []

    removed: List[str] = []
    rows = con.execute("SELECT machine_id,summary_json,payload_json FROM latest WHERE machine_id<>?", (target_mid,)).fetchall()
    for row in rows:
        try:
            old_payload = safe_json_loads(row["payload_json"], {})
            old_summary = safe_json_loads(row["summary_json"], {})
            old_key = stable_machine_merge_key(old_payload if isinstance(old_payload, dict) else {}, old_summary if isinstance(old_summary, dict) else {})
            if old_key and old_key == target_key:
                old_mid = clean_str(row["machine_id"])
                if old_mid and old_mid != target_mid:
                    removed.append(old_mid)
        except Exception:
            continue

    for old_mid in sorted(set(removed)):
        log("REAL_FIX_V3 blocked latest delete for " + str(old_mid))
    if removed:
        log(f"client_count_fix: removed duplicate latest rows for {target_mid}: {sorted(set(removed))}")
    return sorted(set(removed))

def get_nested(d: Dict[str, Any], paths: List[str], default: Any=None) -> Any:
    for p in paths:
        cur: Any = d
        ok = True
        for part in p.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur not in (None, ""):
            return cur
    return default


def to_float(v: Any, default: Optional[float]=None) -> Optional[float]:
    try:
        if v is None or v == "":
            return default
        return float(str(v).replace("%", "").strip())
    except Exception:
        return default


def safe_json_loads(s: str, fallback: Any) -> Any:
    try:
        return json.loads(s)
    except Exception:
        return fallback


def parse_usb_repr_string(text: str) -> Any:
    """Best-effort parser for raw Windows/Powershell/Python repr USB strings.
    Handles values like "[{'name': 'Razer', 'device_id': 'USB\\VID_1532...'}]" even when Device ID contains braces/backslashes.
    """
    if not isinstance(text, str):
        return text
    t = text.strip()
    if not ("name" in t.lower() or "display_name" in t.lower() or "device_id" in t.lower() or "vid" in t.lower()):
        return text
    try:
        obj = ast.literal_eval(t)
        if isinstance(obj, (list, dict)):
            return obj
    except Exception:
        pass
    parts = re.split(r"\}\s*,\s*\{", t.strip().strip("[]"))
    out = []
    for part in parts[:120]:
        b = part.strip()
        if not b.startswith("{"):
            b = "{" + b
        if not b.endswith("}"):
            b = b + "}"
        obj = {}
        for key in ["name","display_name","friendly_name","class","type","vid","pid","device_id","manufacturer","status","source","connection"]:
            m = re.search(r"['\"]" + re.escape(key) + r"['\"]\s*:\s*(['\"])(.*?)\1", b, re.I | re.S)
            if m:
                obj[key] = m.group(2).replace('\\\\', '\\').strip()[:1000]
                continue
            m = re.search(r"\b" + re.escape(key) + r"\b\s*[:=]\s*([^,}]+)", b, re.I | re.S)
            if m:
                obj[key] = m.group(1).strip().strip("'\"")[:1000]
        if obj.get("name") or obj.get("display_name") or obj.get("device_id"):
            out.append(obj)
    return out if out else text

def loose_json_or_python(value: Any) -> Any:
    """Parse JSON/Python-looking strings that sometimes arrive from PowerShell as text.
    Example: "[{'name':'Razer Kraken', 'vid':'1532'}]" should become a list, not one raw string.
    """
    if not isinstance(value, str):
        return value
    t = value.strip()
    if not t:
        return value
    if (t.startswith("[") and t.endswith("]")) or (t.startswith("{") and t.endswith("}")):
        try:
            return json.loads(t)
        except Exception:
            pass
        try:
            return ast.literal_eval(t)
        except Exception:
            parsed = parse_usb_repr_string(value)
            return parsed
    parsed = parse_usb_repr_string(value)
    return parsed


def listify(value: Any) -> List[Any]:
    """Return a real list even when PowerShell/JSON sends one object, dictionary, or list-as-string.
    This fixes single USB device / single app / single adapter cases and strings like [{'name':...}].
    """
    value = loose_json_or_python(value)
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [x for x in value if x not in (None, "")]
    if isinstance(value, tuple):
        return [x for x in value if x not in (None, "")]
    if isinstance(value, dict):
        # Direct object, e.g. {name,class,type,device_id}.
        direct_keys = {"name", "class", "type", "device_id", "vid", "pid", "manufacturer", "status", "mount", "total_gb", "version", "publisher"}
        if any(k in value for k in direct_keys):
            return [value]
        # Dictionary keyed by instance id, e.g. {"USB\VID...": {...}}.
        vals = list(value.values())
        return [x for x in vals if x not in (None, "")]
    return [value]


def is_noisy_windows_usb_name(name: str, cls: str = "", did: str = "") -> bool:
    text = f"{name} {cls} {did}".lower()
    keep = r"keyboard|mouse|headset|headphone|speaker|microphone|audio|camera|webcam|printer|storage|flash|disk|bluetooth|ethernet|wi-fi|wifi|802\.11|wireless|razer|logitech|realtek|tp-link|hp|canon|epson"
    if re.search(keep, text):
        return False
    noisy = [
        "hid button", "hid-compliant system controller", "hid-compliant consumer control",
        "hid-compliant vendor-defined", "hid-compliant device", "hid sensor", "i2c hid",
        "gpio buttons", "system control", "usb composite device", "usb input device",
        "generic usb hub", "usb root hub", "root hub", "composite parent",
        "tap-windows adapter", "wan miniport", "virtual adapter", "loopback", "microsoft wi-fi direct virtual"
    ]
    if any(x in text for x in noisy):
        return True
    if re.search(r"^(acpi|root|swc|swd|display)\\", did.lower()):
        return True
    if "hidclass" in cls.lower() and not re.search(keep, text):
        return True
    return False

def normalize_usb_device(item: Any) -> Dict[str, Any]:
    """Convert raw Windows/Ubuntu USB item into a safe human-readable object."""
    if isinstance(item, dict):
        name = clean_str(item.get("display_name") or item.get("friendly_name") or item.get("name") or item.get("device_name") or item.get("description"))
        cls = clean_str(item.get("class") or item.get("pnp_class") or item.get("category"))
        dtype = clean_str(item.get("type") or cls or "Peripheral")
        did = clean_str(item.get("device_id") or item.get("instance_id") or item.get("id"))
        if is_noisy_windows_usb_name(name, cls, did):
            return {}
        if not name and did:
            name = re.split(r"[\\/]", did)[-1][:80]
        if not dtype or dtype.lower() in ("hidclass", "usb"):
            low = f"{name} {cls}".lower()
            if "keyboard" in low: dtype="Keyboard"
            elif "mouse" in low or "pointing" in low: dtype="Mouse"
            elif re.search(r"audio|headset|headphone|speaker|microphone", low): dtype="Audio"
            elif re.search(r"camera|webcam|image", low): dtype="Camera"
            elif re.search(r"storage|disk|flash|mass", low): dtype="Storage"
            elif "bluetooth" in low: dtype="Bluetooth"
            elif re.search(r"network|ethernet|wi-fi|wifi|802\.11|wireless", low): dtype="USB Network"
            else: dtype="Peripheral"
        return {"name": name or "Unknown USB / Peripheral", "display_name": name or "Unknown USB / Peripheral", "class": cls, "type": dtype or "Peripheral", "vid": clean_str(item.get("vid") or item.get("vendor_id")), "pid": clean_str(item.get("pid") or item.get("product_id")), "manufacturer": clean_str(item.get("manufacturer")), "status": clean_str(item.get("status")), "source": clean_str(item.get("source")), "device_id": did}
    parsed_item = parse_usb_repr_string(item) if isinstance(item, str) else item
    if isinstance(parsed_item, list) and parsed_item:
        # normalize_usb_list will flatten this; this branch protects direct calls.
        return normalize_usb_device(parsed_item[0])
    if isinstance(parsed_item, dict):
        return normalize_usb_device(parsed_item)
    s = clean_str(item)
    if not s:
        return {"name":"Unknown USB / Peripheral", "display_name":"Unknown USB / Peripheral", "class":"", "type":"Peripheral", "device_id":""}
    parts = [p.strip() for p in s.split("|")]
    if len(parts) >= 2:
        dtype = parts[0] or "Peripheral"
        name = parts[1] or "Unknown USB / Peripheral"
        vidpid = parts[2] if len(parts) > 2 else ""
        did = parts[3] if len(parts) > 3 else ""
        vid = ""; pid = ""
        if ":" in vidpid:
            vid, pid = [x.strip() for x in vidpid.split(":", 1)]
        return {"name":name, "display_name":name, "class":dtype, "type":dtype, "vid":vid, "pid":pid, "device_id":did, "source":"parsed"}
    short = s[:120] + ("..." if len(s) > 120 else "")
    return {"name": short, "display_name": short, "class":"", "type":"Peripheral", "device_id": s if len(s) < 250 else s[:250]+"...", "source":"raw"}


def normalize_usb_list(items: Any) -> List[Dict[str, Any]]:
    """Flatten and clean USB/peripheral payloads from Windows/Linux.
    Older Windows clients sometimes sent a whole list as one raw string, for example
    "[{\'name\': \'Razer...\'}]". This function recursively parses that so the UI
    receives clean device objects, not raw Python/PowerShell text.
    """
    out: List[Dict[str, Any]] = []
    seen = set()

    def walk(value: Any, depth: int = 0) -> None:
        if depth > 4:
            return
        value = loose_json_or_python(value)
        if value is None or value == "":
            return
        if isinstance(value, list) or isinstance(value, tuple):
            for v in value:
                walk(v, depth + 1)
            return
        if isinstance(value, dict):
            direct_keys = {"name", "display_name", "friendly_name", "class", "type", "device_id", "vid", "pid", "manufacturer", "status", "source"}
            if not any(k in value for k in direct_keys):
                for v in value.values():
                    walk(v, depth + 1)
                return
        obj = normalize_usb_device(value)
        if not obj or is_noisy_windows_usb_name(obj.get("name",""), obj.get("class",""), obj.get("device_id","")):
            return
        # Avoid showing VPN/TAP adapters under USB/peripherals. Network page already handles them.
        text = f"{obj.get('name','')} {obj.get('device_id','')} {obj.get('class','')}".lower()
        if re.search(r"tap-windows|wan miniport|wireguard|openvpn|vpn|virtual adapter|loopback", text):
            return
        key = (obj.get("type",""), obj.get("name",""), obj.get("vid",""), obj.get("pid",""), obj.get("device_id","")[:80])
        if key in seen:
            return
        seen.add(key)
        out.append(obj)

    walk(items)
    return out


def normalize_payload_inplace(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize client payload before saving so API + UI always receive arrays."""
    if not isinstance(payload, dict):
        return payload
    # USB devices: always store a clean list of objects, never a raw PowerShell string/object.
    usb = payload.get("usb")
    if isinstance(usb, dict):
        usb["devices"] = normalize_usb_list(loose_json_or_python(usb.get("devices")))
        usb["count"] = len(usb["devices"])
    elif usb:
        clean_usb = normalize_usb_list(usb)
        payload["usb"] = {"devices": clean_usb, "count": len(clean_usb)}
    else:
        payload.setdefault("usb", {"devices": [], "count": 0})
    # Installed software
    sw = payload.get("software")
    if isinstance(sw, dict):
        sw["installed"] = listify(sw.get("installed"))
    elif sw:
        payload["software"] = {"installed": listify(sw)}
    else:
        payload.setdefault("software", {"installed": []})
    # Hardware arrays
    hw = payload.get("hardware")
    if isinstance(hw, dict):
        hw["gpus"] = listify(hw.get("gpus"))
    st = payload.get("storage")
    if isinstance(st, dict):
        st["disks"] = listify(st.get("disks"))
    net = payload.get("network")
    if isinstance(net, dict):
        net["adapters"] = listify(net.get("adapters"))
    # Changes
    if "changes" in payload:
        payload["changes"] = listify(payload.get("changes"))
    else:
        payload["changes"] = []
    return payload


def summarize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    mid, id_source, id_value = make_machine_identity(payload)
    hostname = clean_str(get_nested(payload, ["identity.hostname", "hostname", "computer_name"], ""))
    os_name = clean_str(get_nested(payload, ["os.name", "os", "os_name", "platform"], ""))

    adapters = listify(get_nested(payload, ["network.adapters", "adapters", "interfaces"], []))
    primary_ip = clean_str(get_nested(payload, ["network.primary_ip", "primary_ip", "ip"], ""))
    all_ips: List[str] = []
    if isinstance(adapters, list):
        for a in adapters:
            if isinstance(a, dict):
                ips = a.get("ips") or a.get("ip_addresses") or []
                if isinstance(ips, str):
                    ips = [ips]
                for ip in ips:
                    if ip and str(ip) not in all_ips:
                        all_ips.append(str(ip))
    if primary_ip and primary_ip not in all_ips:
        all_ips.insert(0, primary_ip)
    if not primary_ip and all_ips:
        primary_ip = all_ips[0]

    disks = listify(get_nested(payload, ["storage.disks", "disks"], []))
    disk_max = 0.0
    if isinstance(disks, list):
        for d in disks:
            if isinstance(d, dict):
                disk_max = max(disk_max, to_float(d.get("used_percent") or d.get("usage_percent"), 0) or 0)

    gpus = listify(get_nested(payload, ["hardware.gpus", "gpus", "gpu"], []))
    gpu_names: List[str] = []
    gpu_max_usage = None
    gpu_max_temp = None
    gpu_total_mem = 0.0
    gpu_memory_values = []
    if isinstance(gpus, dict):
        gpus = [gpus]
    if isinstance(gpus, list):
        for g in gpus:
            if isinstance(g, dict):
                name = clean_str(g.get("name") or g.get("gpu_name"))
                if name:
                    gpu_names.append(name)
                u = to_float(g.get("usage_percent") or g.get("utilization_gpu") or g.get("load_percent"))
                t = to_float(g.get("temperature_c") or g.get("temp_c"))
                m = to_float(g.get("memory_total_mb") or g.get("adapter_ram_mb"), 0) or 0
                dedicated_m = to_float(g.get("dedicated_memory_mb"), 0) or 0
                shared_m = to_float(g.get("shared_memory_mb"), 0) or 0
                effective_m = max(m, dedicated_m, shared_m)
                if effective_m:
                    gpu_memory_values.append(effective_m)
                if u is not None:
                    gpu_max_usage = u if gpu_max_usage is None else max(gpu_max_usage, u)
                if t is not None:
                    gpu_max_temp = t if gpu_max_temp is None else max(gpu_max_temp, t)
                gpu_total_mem += effective_m

    usb = listify(get_nested(payload, ["usb.devices", "usb", "peripherals"], []))
    software = listify(get_nested(payload, ["software.installed", "software", "apps"], []))
    vpn = get_nested(payload, ["network.vpn", "vpn"], {}) or {}
    vpn_active = False
    if isinstance(vpn, dict):
        vpn_active = bool(vpn.get("active") or vpn.get("is_active"))
    elif isinstance(vpn, bool):
        vpn_active = vpn

    public_internet = get_nested(payload, ["network.public_internet", "public_internet", "isp"], {}) or {}
    if not isinstance(public_internet, dict):
        public_internet = {}
    internet_speed = get_nested(payload, ["network.internet_speed", "internet_speed"], {}) or {}
    if not isinstance(internet_speed, dict):
        internet_speed = {}
    isp_name = clean_str(public_internet.get("isp") or public_internet.get("org") or public_internet.get("as") or "")
    public_ip = clean_str(public_internet.get("public_ip") or public_internet.get("query") or public_internet.get("ip") or "")
    changes = listify(payload.get("changes"))

    memory = get_nested(payload, ["hardware.memory", "memory", "ram"], {}) or {}
    if not isinstance(memory, dict):
        memory = {}
    traffic = get_nested(payload, ["network.traffic", "traffic"], {}) or {}
    if not isinstance(traffic, dict):
        traffic = {}

    return {
        "machine_id": mid,
        "id_source": id_source,
        "id_value": id_value,
        "hostname": hostname,
        "os": os_name,
        "primary_ip": primary_ip,
        "all_ips": all_ips,
        "cpu_percent": to_float(get_nested(payload, ["hardware.cpu.usage_percent", "cpu_percent", "cpu.usage_percent"]), 0),
        "cpu_temp_c": to_float(get_nested(payload, ["hardware.cpu.temperature_c", "cpu_temp_c", "cpu.temperature_c"])),
        "ram_percent": to_float(get_nested(payload, ["hardware.memory.used_percent", "ram_percent", "memory.used_percent"]), 0),
        "ram_total_gb": to_float(memory.get("total_gb") or get_nested(payload, ["hardware.memory.total_gb", "memory.total_gb", "ram_total_gb"]), 0),
        "ram_used_gb": to_float(memory.get("used_gb") or get_nested(payload, ["hardware.memory.used_gb", "memory.used_gb", "ram_used_gb"]), 0),
        "ram_free_gb": to_float(memory.get("free_gb") or get_nested(payload, ["hardware.memory.free_gb", "memory.free_gb", "ram_free_gb"]), 0),
        "disk_max_percent": round(disk_max, 2),
        "wan_download_mbps": to_float(traffic.get("current_download_mbps") or get_nested(payload, ["network.current_download_mbps", "current_download_mbps", "download_mbps", "wan_download_mbps"]), 0),
        "wan_upload_mbps": to_float(traffic.get("current_upload_mbps") or get_nested(payload, ["network.current_upload_mbps", "current_upload_mbps", "upload_mbps", "wan_upload_mbps"]), 0),
        "today_download_gb": to_float(traffic.get("today_download_gb") or get_nested(payload, ["network.today_download_gb", "today_download_gb"]), 0),
        "today_upload_gb": to_float(traffic.get("today_upload_gb") or get_nested(payload, ["network.today_upload_gb", "today_upload_gb"]), 0),
        "traffic_date": clean_str(traffic.get("date") or get_nested(payload, ["network.traffic_date", "traffic_date"], "")),
        "gpu_names": gpu_names,
        "gpu_count": len(gpu_names),
        "gpu_max_usage": gpu_max_usage,
        "gpu_max_temp_c": gpu_max_temp,
        "gpu_total_memory_mb": round((max(gpu_memory_values) if gpu_memory_values else gpu_total_mem), 2),
        "vpn_active": vpn_active,
        "isp_name": isp_name,
        "public_ip": public_ip,
        "isp_download_mbps": to_float(internet_speed.get("download_mbps"), to_float(traffic.get("current_download_mbps") or get_nested(payload, ["network.current_download_mbps", "current_download_mbps", "download_mbps", "wan_download_mbps"]), 0)),
        "isp_upload_mbps": to_float(internet_speed.get("upload_mbps"), to_float(traffic.get("current_upload_mbps") or get_nested(payload, ["network.current_upload_mbps", "current_upload_mbps", "upload_mbps", "wan_upload_mbps"]), 0)),
        "isp_speed_source": clean_str(internet_speed.get("source") or "live_adapter_usage"),
        "change_count": len(changes),
        "adapter_count": len(adapters) if isinstance(adapters, list) else 0,
        "software_count": len(software) if isinstance(software, list) else 0,
        "usb_count": len(usb) if isinstance(usb, list) else 0,
        "payload": payload,
    }


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with DB_LOCK, db_connect() as con:
        cur = con.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS latest (
            machine_id TEXT PRIMARY KEY,
            hostname TEXT,
            id_source TEXT,
            id_value TEXT,
            updated_at TEXT,
            summary_json TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS heartbeats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            machine_id TEXT NOT NULL,
            received_at TEXT NOT NULL,
            hostname TEXT,
            payload_json TEXT NOT NULL
        )""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_heartbeats_machine_time ON heartbeats(machine_id, received_at)")
        cur.execute("""CREATE TABLE IF NOT EXISTS notification_rules (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            metric TEXT NOT NULL,
            op TEXT NOT NULL,
            threshold REAL NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            severity TEXT NOT NULL DEFAULT 'warning',
            cooldown_minutes INTEGER NOT NULL DEFAULT 15
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            severity TEXT NOT NULL,
            machine_id TEXT,
            hostname TEXT,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            rule_id TEXT
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS change_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            machine_id TEXT NOT NULL,
            hostname TEXT,
            change_type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            detail_json TEXT NOT NULL
        )""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_change_events_time ON change_events(created_at)")
        cur.execute("""CREATE TABLE IF NOT EXISTS notification_state (
            rule_id TEXT NOT NULL,
            machine_id TEXT NOT NULL,
            last_sent_ts REAL NOT NULL,
            PRIMARY KEY(rule_id, machine_id)
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS client_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            target_machine_id TEXT,
            target_hostname TEXT,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'normal',
            status TEXT NOT NULL DEFAULT 'pending',
            delivered_at TEXT
        )""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_client_messages_target ON client_messages(target_machine_id,status)")
        cur.execute("""CREATE TABLE IF NOT EXISTS client_message_receipts (
            message_id INTEGER NOT NULL,
            machine_id TEXT NOT NULL,
            hostname TEXT,
            delivered_at TEXT NOT NULL,
            PRIMARY KEY(message_id, machine_id)
        )""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_client_message_receipts_msg ON client_message_receipts(message_id)")
        for r in DEFAULT_RULES:
            cur.execute("SELECT id FROM notification_rules WHERE id=?", (r["id"],))
            if not cur.fetchone():
                cur.execute("""INSERT INTO notification_rules(id,name,metric,op,threshold,enabled,severity,cooldown_minutes)
                    VALUES(?,?,?,?,?,?,?,?)""", (r["id"], r["name"], r["metric"], r["op"], r["threshold"], int(r["enabled"]), r["severity"], r["cooldown_minutes"]))
        cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('google_chat_webhook','')")
        cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('offline_timeout_minutes','0.20')")
        cur.execute("UPDATE settings SET value='0.20' WHERE key='offline_timeout_minutes' AND value IN ('','1')")
        cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('company_name',?)", (APP_NAME,))
        cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('admin_password_hash',?)", (hash_password(DEFAULT_ADMIN_PASSWORD),))
        cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('auto_speed_probe','1')")
        cur.execute("""CREATE TABLE IF NOT EXISTS users(
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        # Admin user for role-based login/download permission. Existing password-only login still works.
        cur.execute("SELECT username FROM users WHERE username='admin'")
        if not cur.fetchone():
            cur.execute("INSERT INTO users(username,password_hash,role,enabled,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                ('admin', hash_password(DEFAULT_ADMIN_PASSWORD), 'admin', 1, now_iso(), now_iso()))
        con.commit()


def get_settings() -> Dict[str, str]:
    with DB_LOCK, db_connect() as con:
        rows = con.execute("SELECT key,value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def set_settings(values: Dict[str, Any]) -> None:
    with DB_LOCK, db_connect() as con:
        for k, v in values.items():
            if k in {"google_chat_webhook", "offline_timeout_minutes", "company_name", "auto_speed_probe", "admin_password_hash", "deploy_commands_json"}:
                con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k, str(v)))
        con.commit()


def list_users_public() -> List[Dict[str, Any]]:
    with DB_LOCK, db_connect() as con:
        rows = con.execute("SELECT username,role,enabled,created_at,updated_at FROM users ORDER BY username").fetchall()
    return [dict(r) for r in rows]


def get_user_row(username: str) -> Optional[sqlite3.Row]:
    with DB_LOCK, db_connect() as con:
        return con.execute("SELECT * FROM users WHERE lower(username)=lower(?) AND enabled=1", (username or "",)).fetchone()


def upsert_user(username: str, password: str, role: str, enabled: bool = True) -> Dict[str, Any]:
    username = clean_str(username).strip()
    role = (clean_str(role) or "viewer").lower()
    if role not in {"admin", "viewer"}:
        role = "viewer"
    if not username:
        return {"ok": False, "error": "Username required"}
    if username.lower() == "admin" and role != "admin":
        return {"ok": False, "error": "Built-in admin must remain admin"}
    if password and len(password) < 8:
        return {"ok": False, "error": "Password must be at least 8 characters"}
    with DB_LOCK, db_connect() as con:
        row = con.execute("SELECT username FROM users WHERE lower(username)=lower(?)", (username,)).fetchone()
        if row:
            if password:
                con.execute("UPDATE users SET password_hash=?, role=?, enabled=?, updated_at=? WHERE lower(username)=lower(?)", (hash_password(password), role, 1 if enabled else 0, now_iso(), username))
            else:
                con.execute("UPDATE users SET role=?, enabled=?, updated_at=? WHERE lower(username)=lower(?)", (role, 1 if enabled else 0, now_iso(), username))
        else:
            if not password:
                return {"ok": False, "error": "Password required for new user"}
            con.execute("INSERT INTO users(username,password_hash,role,enabled,created_at,updated_at) VALUES(?,?,?,?,?,?)", (username, hash_password(password), role, 1 if enabled else 0, now_iso(), now_iso()))
        con.commit()
    return {"ok": True, "users": list_users_public()}


def delete_user(username: str) -> Dict[str, Any]:
    username = clean_str(username).strip()
    if username.lower() == "admin":
        return {"ok": False, "error": "admin user cannot be deleted"}
    with DB_LOCK, db_connect() as con:
        con.execute("DELETE FROM users WHERE lower(username)=lower(?)", (username,))
        con.commit()
    return {"ok": True, "users": list_users_public()}


def public_settings() -> Dict[str, Any]:
    s = get_settings()
    return {k:v for k,v in s.items() if k != "admin_password_hash"}


def rules_list() -> List[Dict[str, Any]]:
    with DB_LOCK, db_connect() as con:
        rows = con.execute("SELECT * FROM notification_rules ORDER BY name").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["enabled"] = bool(d["enabled"])
        out.append(d)
    return out


def eval_rule(value: Optional[float], op: str, threshold: float) -> bool:
    if op == "event":
        return True
    if value is None:
        return False
    if op == ">=": return value >= threshold
    if op == ">": return value > threshold
    if op == "<=": return value <= threshold
    if op == "<": return value < threshold
    if op == "==": return value == threshold
    return False


def can_send_alert(con: sqlite3.Connection, rule_id: str, machine_id: str, cooldown: int) -> bool:
    row = con.execute("SELECT last_sent_ts FROM notification_state WHERE rule_id=? AND machine_id=?", (rule_id, machine_id)).fetchone()
    now = time.time()
    if row and now - float(row["last_sent_ts"]) < cooldown * 60:
        return False
    con.execute("INSERT OR REPLACE INTO notification_state(rule_id,machine_id,last_sent_ts) VALUES(?,?,?)", (rule_id, machine_id, now))
    return True


def send_google_chat(text: str) -> None:
    settings = get_settings()
    url = (settings.get("google_chat_webhook") or "").strip()
    if not url:
        return
    data = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=8).read()
    except Exception as e:
        log(f"Google Chat notification failed: {e}")


def record_notification(con: sqlite3.Connection, severity: str, machine_id: str, hostname: str, title: str, message: str, rule_id: str) -> None:
    con.execute("""INSERT INTO notifications(created_at,severity,machine_id,hostname,title,message,rule_id)
        VALUES(?,?,?,?,?,?,?)""", (now_iso(), severity, machine_id, hostname, title, message, rule_id))
    threading.Thread(target=send_google_chat, args=(f"[{severity.upper()}] {title}\n{message}",), daemon=True).start()


def evaluate_notifications(summary: Dict[str, Any]) -> None:
    with DB_LOCK, db_connect() as con:
        rows = con.execute("SELECT * FROM notification_rules WHERE enabled=1 AND metric!='offline_minutes' AND metric NOT LIKE 'change_%'").fetchall()
        for r in rows:
            value = to_float(summary.get(r["metric"]))
            if eval_rule(value, r["op"], float(r["threshold"])):
                if can_send_alert(con, r["id"], summary["machine_id"], int(r["cooldown_minutes"])):
                    host = summary.get("hostname") or summary["machine_id"]
                    msg = f"{host}: {r['metric']} is {value} {r['op']} {r['threshold']}"
                    record_notification(con, r["severity"], summary["machine_id"], host, r["name"], msg, r["id"])
        con.commit()


def process_change_events(summary: Dict[str, Any], payload: Dict[str, Any]) -> None:
    changes = listify(payload.get("changes"))
    if not changes:
        return
    host = summary.get("hostname") or summary.get("machine_id", "UNKNOWN")
    mid = summary.get("machine_id", "UNKNOWN")
    with DB_LOCK, db_connect() as con:
        for ch in changes[:50]:
            if not isinstance(ch, dict):
                continue
            ctype = re.sub(r"[^a-z0-9_]+", "_", clean_str(ch.get("type") or "unknown").lower()).strip("_") or "unknown"
            title = clean_str(ch.get("title")) or f"{ctype.replace('_', ' ').title()} changed"
            message = clean_str(ch.get("message")) or json.dumps(ch, ensure_ascii=False)[:500]
            con.execute("""INSERT INTO change_events(created_at,machine_id,hostname,change_type,title,message,detail_json)
                VALUES(?,?,?,?,?,?,?)""", (now_iso(), mid, host, ctype, title, message, json.dumps(ch, ensure_ascii=False)))
            rules = con.execute("SELECT * FROM notification_rules WHERE enabled=1 AND metric=?", ("change_" + ctype,)).fetchall()
            for r in rules:
                if can_send_alert(con, r["id"], mid, int(r["cooldown_minutes"])):
                    record_notification(con, r["severity"], mid, host, r["name"], f"{host}: {message}", r["id"])
        con.commit()


def format_change_value(v: Any) -> str:
    """Compact a change item so human change log does not become unreadable."""
    if isinstance(v, dict):
        name = clean_str(v.get("display_name") or v.get("friendly_name") or v.get("name") or v.get("device_name") or v.get("description"))
        dtype = clean_str(v.get("type") or v.get("class") or v.get("category"))
        version = clean_str(v.get("version"))
        vid = clean_str(v.get("vid")); pid = clean_str(v.get("pid"))
        bits = []
        if dtype:
            bits.append(dtype)
        if name:
            bits.append(name)
        if version:
            bits.append("v" + version)
        if vid or pid:
            bits.append(f"VID:{vid or '-'} PID:{pid or '-'}")
        if bits:
            return " - ".join(bits)[:180]
        return json.dumps(v, ensure_ascii=False)[:180]
    s = clean_str(v)
    # Old broken Windows clients sometimes sent one huge raw string containing many hardware IDs.
    # Turn it into a short human sentence instead of a screen-filling paragraph.
    if len(s) > 220:
        # Try to preserve the first useful name before raw IDs.
        compact = re.sub(r"(USB|HID|PCI|SWD|BTH|ACPI)\\[^\s,;]+", "", s, flags=re.I)
        compact = re.sub(r"\s+", " ", compact).strip(" ,;|-")
        return (compact[:140] + " ... [details hidden; download CSV for full ID]") if compact else "Multiple USB/peripheral IDs changed [details hidden]"
    parts = [p.strip() for p in s.split("|")]
    if len(parts) >= 2:
        dtype = parts[0] or "Peripheral"
        name = parts[1] or "Unknown device"
        vidpid = parts[2] if len(parts) > 2 else ""
        out = f"{dtype} - {name}"
        if vidpid and vidpid != ":":
            out += f" ({vidpid})"
        return out[:160]
    s = re.sub(r"(USB|HID|PCI|SWD|BTH|ACPI)\\[^\s,;]+", "[hardware-id]", s, flags=re.I)
    return (s[:160] + "...") if len(s) > 160 else s


def humanize_change_row(row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
    d = dict(row)
    detail = safe_json_loads(d.get("detail_json", "{}"), {}) if isinstance(d.get("detail_json", "{}"), str) else (d.get("detail_json") or {})
    added = [format_change_value(x) for x in listify(detail.get("added"))]
    removed = [format_change_value(x) for x in listify(detail.get("removed"))]
    ctype = clean_str(d.get("change_type") or detail.get("type") or "change")
    host = clean_str(d.get("hostname") or d.get("machine_id") or "Unknown machine")
    title = clean_str(d.get("title")) or f"{ctype.replace('_',' ').title()} changed"
    # Friendly sentence for humans.
    sentence = clean_str(d.get("message"))
    if ctype == "usb":
        sentence = f"{host}: USB/peripheral changed. Added {len(added)}, removed {len(removed)}."
    elif ctype == "software":
        sentence = f"{host}: Software list changed. Installed/updated {len(added)}, removed {len(removed)}."
    elif ctype == "hardware":
        sentence = f"{host}: Hardware inventory changed. Added {len(added)}, removed {len(removed)}."
    elif ctype == "ip":
        sentence = f"{host}: IP address changed. Added {len(added)}, removed {len(removed)}."
    elif ctype == "vpn":
        sentence = f"{host}: VPN status changed."
    d["human_title"] = title
    d["human_message"] = sentence
    d["added_items"] = added[:50]
    d["removed_items"] = removed[:50]
    d["added_text"] = " || ".join(added[:50])
    d["removed_text"] = " || ".join(removed[:50])
    d["added_count"] = len(added)
    d["removed_count"] = len(removed)
    return d


def latest_change_events(limit: int = 100, human: bool = False) -> List[Dict[str, Any]]:
    with DB_LOCK, db_connect() as con:
        rows = con.execute("SELECT * FROM change_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = [dict(r) for r in rows]
    if human:
        out = [humanize_change_row(r) for r in out]
    return out


def change_events_for_export(limit: int = 5000, machine_id: str = "") -> List[Dict[str, Any]]:
    with DB_LOCK, db_connect() as con:
        if machine_id:
            rows = con.execute("SELECT * FROM change_events WHERE machine_id=? ORDER BY id DESC LIMIT ?", (machine_id, limit)).fetchall()
        else:
            rows = con.execute("SELECT * FROM change_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    export = []
    for row in rows:
        r = humanize_change_row(dict(row))
        export.append({
            "time": r.get("created_at", ""),
            "machine": r.get("hostname") or r.get("machine_id") or "",
            "machine_id": r.get("machine_id", ""),
            "change_type": r.get("change_type", ""),
            "summary": r.get("human_message") or r.get("message") or "",
            "added_count": r.get("added_count", 0),
            "removed_count": r.get("removed_count", 0),
            "added_details": r.get("added_text", ""),
            "removed_details": r.get("removed_text", ""),
        })
    return export


def latest_payload_for_machine(machine_id: str = "") -> List[Dict[str, Any]]:
    machines = load_latest()
    if machine_id:
        machines = [m for m in machines if m.get("machine_id") == machine_id]
    return machines


def export_software_rows(machine_id: str = "") -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for m in latest_payload_for_machine(machine_id):
        p = m.get("payload") or {}
        apps = listify(get_nested(p, ["software.installed", "software"], []))
        for a in apps:
            if not isinstance(a, dict):
                continue
            rows.append({
                "machine": m.get("hostname") or m.get("machine_id"),
                "machine_id": m.get("machine_id"),
                "ip": m.get("primary_ip", ""),
                "name": clean_str(a.get("name") or a.get("display_name")),
                "version": clean_str(a.get("version")),
                "publisher": clean_str(a.get("publisher")),
                "install_date": clean_str(a.get("install_date") or a.get("installDate")),
            })
    return rows


def export_usb_rows(machine_id: str = "") -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for m in latest_payload_for_machine(machine_id):
        p = m.get("payload") or {}
        devices = normalize_usb_list(get_nested(p, ["usb.devices", "usb", "peripherals"], []))
        for u in devices:
            rows.append({
                "machine": m.get("hostname") or m.get("machine_id"),
                "machine_id": m.get("machine_id"),
                "ip": m.get("primary_ip", ""),
                "device": clean_str(u.get("display_name") or u.get("name")),
                "type": clean_str(u.get("type")),
                "class": clean_str(u.get("class")),
                "vid": clean_str(u.get("vid")),
                "pid": clean_str(u.get("pid")),
                "manufacturer": clean_str(u.get("manufacturer")),
                "status": clean_str(u.get("status")),
                "source": clean_str(u.get("source")),
                "device_id": clean_str(u.get("device_id")),
            })
    return rows

def check_offline_notifications() -> None:
    settings = get_settings()
    try:
        default_timeout = float(settings.get("offline_timeout_minutes", "0.25"))
    except Exception:
        default_timeout = 5.0
    now_ts = dt.datetime.now(dt.timezone.utc).timestamp()
    with DB_LOCK, db_connect() as con:
        rule = con.execute("SELECT * FROM notification_rules WHERE enabled=1 AND metric='offline_minutes' LIMIT 1").fetchone()
        if not rule:
            return
        timeout = float(rule["threshold"] or default_timeout or 5)
        rows = con.execute("SELECT machine_id,hostname,updated_at FROM latest").fetchall()
        for row in rows:
            try:
                updated = dt.datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00")).timestamp()
            except Exception:
                continue
            mins = (now_ts - updated) / 60.0
            if mins >= timeout and can_send_alert(con, rule["id"], row["machine_id"], int(rule["cooldown_minutes"])):
                host = row["hostname"] or row["machine_id"]
                record_notification(con, rule["severity"], row["machine_id"], host, rule["name"], f"{host} has not sent data for {mins:.1f} minutes", rule["id"])
        con.commit()


def create_client_message(target_machine_id: str, target_hostname: str, title: str, message: str, priority: str = "normal") -> Dict[str, Any]:
    with DB_LOCK, db_connect() as con:
        cur = con.execute("""INSERT INTO client_messages(created_at,target_machine_id,target_hostname,title,message,priority,status)
            VALUES(?,?,?,?,?,?,?)""", (now_iso(), target_machine_id or "", target_hostname or "", title or "Admin message", message or "", priority or "normal", "pending"))
        con.commit()
        mid = cur.lastrowid
    return {"ok": True, "id": mid}


def list_client_messages(limit: int = 200) -> List[Dict[str, Any]]:
    with DB_LOCK, db_connect() as con:
        rows = con.execute("""SELECT m.*, COUNT(r.machine_id) AS delivered_count, MAX(r.delivered_at) AS last_delivered_at,
                            GROUP_CONCAT(COALESCE(r.hostname, r.machine_id), ', ') AS delivered_hosts
                            FROM client_messages m
                            LEFT JOIN client_message_receipts r ON r.message_id=m.id
                            GROUP BY m.id
                            ORDER BY m.id DESC LIMIT ?""", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["delivered_count"] = int(d.get("delivered_count") or 0)
        if d.get("target_machine_id") or d.get("target_hostname"):
            d["status_label"] = "delivered" if d["delivered_count"] else "pending"
        else:
            d["status_label"] = f"broadcast delivered to {d['delivered_count']}" if d["delivered_count"] else "broadcast pending"
        out.append(d)
    return out


def take_pending_messages(con: sqlite3.Connection, machine_id: str, hostname: str) -> List[Dict[str, Any]]:
    """Return messages not yet delivered to THIS machine.
    Old bug: broadcast messages were marked delivered after the first client only.
    New logic stores per-machine receipts, so every Windows/Ubuntu client gets the broadcast once.
    """
    rows = con.execute("""SELECT * FROM client_messages m
        WHERE (m.target_machine_id='' OR m.target_machine_id=? OR lower(m.target_hostname)=lower(?))
          AND NOT EXISTS (SELECT 1 FROM client_message_receipts r WHERE r.message_id=m.id AND r.machine_id=?)
        ORDER BY m.id ASC LIMIT 10""", (machine_id, hostname or "", machine_id)).fetchall()
    out = []
    delivered_ids = []
    for r in rows:
        d = dict(r)
        out.append({"id": d["id"], "created_at": d["created_at"], "title": d["title"], "message": d["message"], "priority": d["priority"]})
        con.execute("""INSERT OR REPLACE INTO client_message_receipts(message_id,machine_id,hostname,delivered_at)
                       VALUES(?,?,?,?)""", (d["id"], machine_id, hostname or "", now_iso()))
        delivered_ids.append(d["id"])
    for mid in delivered_ids:
        # Targeted message becomes delivered after its target receives it. Broadcast remains trackable by receipts.
        con.execute("""UPDATE client_messages SET status='delivered', delivered_at=COALESCE(delivered_at, ?)
                       WHERE id=? AND (target_machine_id!='' OR target_hostname!='')""", (now_iso(), mid))
        con.execute("""UPDATE client_messages SET status='broadcast', delivered_at=COALESCE(delivered_at, ?)
                       WHERE id=? AND target_machine_id='' AND target_hostname=''""", (now_iso(), mid))
    return out

def upsert_heartbeat(payload: Dict[str, Any], client_ip: str) -> Dict[str, Any]:
    payload = normalize_payload_inplace(payload)
    if not isinstance(payload.get("network"), dict):
        payload["network"] = {}
    if not payload["network"].get("receiver_seen_ip"):
        payload["network"]["receiver_seen_ip"] = client_ip
    summary = summarize_payload(payload)
    received_at = now_iso()
    with DB_LOCK, db_connect() as con:
        cleanup_duplicate_latest_rows(con, summary, payload)
        con.execute("INSERT INTO heartbeats(machine_id,received_at,hostname,payload_json) VALUES(?,?,?,?)",
                    (summary["machine_id"], received_at, summary.get("hostname", ""), json.dumps(payload, ensure_ascii=False)))
        con.execute("""INSERT OR REPLACE INTO latest(machine_id,hostname,id_source,id_value,updated_at,summary_json,payload_json)
            VALUES(?,?,?,?,?,?,?)""",
            (summary["machine_id"], summary.get("hostname", ""), summary.get("id_source", ""), summary.get("id_value", ""), received_at,
             json.dumps(summary, ensure_ascii=False), json.dumps(payload, ensure_ascii=False)))
        pending_messages = take_pending_messages(con, summary["machine_id"], summary.get("hostname", ""))
        con.commit()
    evaluate_notifications(summary)
    try:
        _sk_enrich_notification_metrics(summary, payload)
    except Exception:
        pass
    process_change_events(summary, payload)
    return {"ok": True, "machine_id": summary["machine_id"], "id_source": summary["id_source"], "received_at": received_at, "changes_received": len(payload.get("changes") or []), "pending_messages": pending_messages}


def load_latest() -> List[Dict[str, Any]]:
    check_offline_notifications()
    settings = get_settings()
    try:
        timeout = float(settings.get("offline_timeout_minutes", "0.25"))
    except Exception:
        timeout = 0.25
    with DB_LOCK, db_connect() as con:
        rows = con.execute("SELECT * FROM latest ORDER BY updated_at DESC").fetchall()
    now_ts = dt.datetime.now(dt.timezone.utc).timestamp()
    out: List[Dict[str, Any]] = []
    seen_hosts_with_good_id = set()
    prepared: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        summary = safe_json_loads(d.get("summary_json", "{}"), {})
        payload = safe_json_loads(d.get("payload_json", "{}"), {})
        if isinstance(payload, dict):
            payload = normalize_payload_inplace(payload)
        if isinstance(summary, dict):
            # Always expose clean inventory counts from the normalized payload so old/raw USB rows do not pollute the UI.
            if isinstance(payload, dict):
                try:
                    summary["usb_count"] = int((payload.get("usb") or {}).get("count") or len(normalize_usb_list(get_nested(payload, ["usb.devices", "usb", "peripherals"], []))))
                except Exception:
                    summary["usb_count"] = summary.get("usb_count", 0)
                try:
                    summary["software_count"] = len(listify(get_nested(payload, ["software.installed", "software", "apps"], [])))
                except Exception:
                    pass
            summary.update({"machine_id": d["machine_id"], "hostname": d.get("hostname") or summary.get("hostname", ""), "id_source": d.get("id_source") or summary.get("id_source", ""), "id_value": d.get("id_value") or summary.get("id_value", ""), "updated_at": d.get("updated_at"), "payload": payload})
            try:
                updated = dt.datetime.fromisoformat((d.get("updated_at") or "").replace("Z", "+00:00")).timestamp()
                mins = max(0.0, (now_ts - updated)/60.0)
            except Exception:
                mins = 9999.0
            summary["offline_minutes"] = round(mins, 2)
            summary["online"] = mins <= timeout
            prepared.append(summary)
            host = (summary.get("hostname") or "").strip().lower()
            if host and summary.get("id_source") not in {"motherboard_serial", "hostname_fallback"}:
                seen_hosts_with_good_id.add(host)

    seen_merge_keys: Dict[str, str] = {}
    duplicate_latest_ids: List[str] = []

    for summary in prepared:
        host = (summary.get("hostname") or "").strip().lower()

        merge_key = stable_machine_merge_key(summary.get("payload") or {}, summary)
        if merge_key:
            previous_mid = seen_merge_keys.get(merge_key)
            if previous_mid and previous_mid != summary.get("machine_id"):
                # Same physical/client machine already kept from newer row.
                # Hide this stale duplicate from count and delete from current latest table.
                duplicate_latest_ids.append(summary.get("machine_id"))
                continue
            seen_merge_keys[merge_key] = summary.get("machine_id")

        # Hide stale legacy rows that used fake motherboard serial once a stable ASSET row exists for same host.
        if host and host in seen_hosts_with_good_id and summary.get("id_source") in {"motherboard_serial", "hostname_fallback"}:
            if not valid_machine_id_part(summary.get("id_value")) or str(summary.get("machine_id", "")).startswith("MOTHERBOARD_SERIAL:BSS"):
                duplicate_latest_ids.append(summary.get("machine_id"))
                continue

        out.append(summary)

    if duplicate_latest_ids:
        try:
            with DB_LOCK, db_connect() as con:
                for mid in sorted(set(x for x in duplicate_latest_ids if x)):
                    log("REAL_FIX_V3 blocked latest delete for " + str(mid))
                con.commit()
            log(f"client_count_fix: cleaned duplicate latest machine rows: {sorted(set(duplicate_latest_ids))}")
        except Exception as e:
            log(f"client_count_fix cleanup failed: {e}")

    return out





# ISP_DEEP_BOX_ONLY_START
ISP_DEEP_CACHE: Dict[str, Any] = {"ts": 0.0, "data": {}}

def sk_isp_norm_provider(v: str) -> str:
    s = clean_str(v).lower()
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s

def sk_num_first(*vals):
    for v in vals:
        try:
            if v is not None and v != "":
                return float(v)
        except Exception:
            pass
    return None

def sk_merge_isp_group(groups: Dict[str, Dict[str, Any]], provider: str, public_ip: str = "", source: str = "client", meta: str = "", metrics: Dict[str, Any] = None, host: str = "", interface_name: str = "", vlan_id: str = ""):
    provider = clean_str(provider) or "Unknown ISP"
    interface_name = clean_str(interface_name)
    vlan_id = clean_str(vlan_id)
    key = sk_isp_norm_provider(provider) + "|" + clean_str(public_ip) + "|" + interface_name.lower() + "|" + vlan_id.lower()
    if key == "|||":
        key = "unknown"
    g = groups.setdefault(key, {"provider":provider,"sources":set(),"public_ips":[],"hosts":[],"count":0,"latency_ms":None,"jitter_ms":None,"loss_percent":None,"down_mbps":None,"up_mbps":None,"meta":meta,"interface_name":interface_name,"vlan_id":vlan_id,"has_probe":False})
    g["sources"].add(source)
    g["count"] += 1
    if public_ip and public_ip not in g["public_ips"]:
        g["public_ips"].append(public_ip)
    if host and host not in g["hosts"]:
        g["hosts"].append(host)
    if interface_name and not g.get("interface_name"):
        g["interface_name"] = interface_name
    if vlan_id and not g.get("vlan_id"):
        g["vlan_id"] = vlan_id
    metrics = metrics or {}
    for k in ["latency_ms","jitter_ms","loss_percent","down_mbps","up_mbps"]:
        if g.get(k) is None and metrics.get(k) is not None:
            g[k] = metrics.get(k)
    if any(metrics.get(k) is not None for k in ["latency_ms","jitter_ms","loss_percent","down_mbps","up_mbps"]):
        g["has_probe"] = True

def sk_isp_client_probe_fields(m: Dict[str, Any]) -> Dict[str, Any]:
    h = m.get("internet_health") if isinstance(m.get("internet_health"), dict) else {}
    return {"latency_ms":sk_num_first(m.get("latency_ms"),m.get("avg_latency_ms"),h.get("latency_ms"),h.get("avg_latency_ms")),"jitter_ms":sk_num_first(m.get("jitter_ms"),h.get("jitter_ms")),"loss_percent":sk_num_first(m.get("loss_percent"),m.get("packet_loss_percent"),h.get("loss_percent"),h.get("packet_loss_percent")),"down_mbps":sk_num_first(m.get("probe_download_mbps"),m.get("download_mbps"),h.get("probe_download_mbps"),h.get("download_mbps")),"up_mbps":sk_num_first(m.get("probe_upload_mbps"),m.get("upload_mbps"),h.get("probe_upload_mbps"),h.get("upload_mbps"))}

def sk_isp_deep_status(force: bool = False) -> Dict[str, Any]:
    now = time.time()
    if not force and ISP_DEEP_CACHE.get("data") and now - float(ISP_DEEP_CACHE.get("ts") or 0) < 45:
        return ISP_DEEP_CACHE["data"]
    server_isp = server_public_internet_info(bool(force))
    try:
        health = server_internet_health(bool(force), True)
    except Exception:
        health = {}
    groups: Dict[str, Dict[str, Any]] = {}
    router_settings = router_isp_load_settings(include_secret=False) if "router_isp_load_settings" in globals() else {"isp_rows":[]}
    for r in router_settings.get("isp_rows") or []:
        sk_merge_isp_group(groups, r.get("provider"), r.get("public_ip"), "router_manual", r.get("notes") or r.get("source_label") or "Router manual", r, "router", r.get("interface_name"), r.get("vlan_id"))
    server_provider = server_isp.get("isp") or server_isp.get("org") or server_isp.get("as") or "Server ISP"
    server_ip = server_isp.get("public_ip") or ""
    sk_merge_isp_group(groups, server_provider, server_ip, "server_probe", server_isp.get("as") or server_isp.get("org") or "", {"latency_ms":health.get("avg_latency_ms") or health.get("latency_ms"),"jitter_ms":health.get("jitter_ms"),"loss_percent":health.get("loss_percent") or health.get("packet_loss_percent"),"down_mbps":health.get("probe_download_mbps"),"up_mbps":health.get("probe_upload_mbps")}, "server", "", "")
    try:
        machines = load_latest()
    except Exception:
        machines = []
    for m in machines[:1000]:
        provider = clean_str(m.get("isp_name") or m.get("isp") or m.get("public_isp"))
        public_ip = clean_str(m.get("public_ip") or m.get("wan_ip"))
        host = clean_str(m.get("hostname") or m.get("machine_id"))
        if provider or public_ip:
            sk_merge_isp_group(groups, provider or "Unknown ISP", public_ip, "client_discovery", host, sk_isp_client_probe_fields(m), host, "", "")
    isp_groups = []
    for g in groups.values():
        sources = sorted(list(g.pop("sources", set())))
        g["sources"] = sources
        g["source_label"] = "Router manual" if "router_manual" in sources else ("Server probe" if "server_probe" in sources else "Client discovery")
        g["public_ip"] = ", ".join(g["public_ips"][:3]) + (f" +{len(g['public_ips'])-3}" if len(g["public_ips"]) > 3 else "")
        g["host_count"] = len(g["hosts"])
        g["probe_note"] = "Probe OK" if g.get("has_probe") else "Manual/router probe pending"
        isp_groups.append(g)
    isp_groups.sort(key=lambda x: (0 if "router_manual" in x.get("sources", []) else (1 if "server_probe" in x.get("sources", []) else 2), clean_str(x.get("provider"))))
    data = {"ok":True,"checked_at":now_iso(),"provider":server_provider,"public_ip":server_ip,"latency_ms":health.get("avg_latency_ms") or health.get("latency_ms"),"jitter_ms":health.get("jitter_ms"),"loss_percent":health.get("loss_percent") or health.get("packet_loss_percent"),"down_mbps":health.get("probe_download_mbps"),"up_mbps":health.get("probe_upload_mbps"),"router_settings":router_isp_public_settings() if "router_isp_public_settings" in globals() else {},"isp_groups":isp_groups,"note":"Router manual settings support WAN/interface/VLAN rows. TP-Link ER8411 live web scraping connector can be added after router page/API inspection."}
    ISP_DEEP_CACHE["ts"] = now
    ISP_DEEP_CACHE["data"] = data
    return data
# ISP_DEEP_BOX_ONLY_END

# ROUTER_ISP_SETTINGS_ONLY_START
from pathlib import Path as _router_Path
ROUTER_ISP_LOCAL_PATH = _router_Path(__file__).resolve().parent / "config" / "router_isp_settings.local.json"

def router_isp_default_settings() -> Dict[str, Any]:
    return {"router":{"brand_model":"TP-Link ER8411","login_ip":"192.168.0.1","access_type":"web","username":"admin","password":"","notes":"Password is local-only and never committed to GitHub."},"updated_at":""}

def router_isp_s(v: Any) -> str:
    return clean_str(v).strip()

def router_isp_load_settings(include_secret: bool = False) -> Dict[str, Any]:
    data = router_isp_default_settings()
    try:
        if ROUTER_ISP_LOCAL_PATH.exists():
            raw = json.loads(ROUTER_ISP_LOCAL_PATH.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                data["router"].update(raw.get("router") or {})
                data["updated_at"] = raw.get("updated_at") or ""
    except Exception as e:
        data["load_error"] = str(e)
    if not include_secret:
        pwd = data.get("router", {}).get("password") or ""
        data["router"]["password"] = ""
        data["router"]["password_saved"] = bool(pwd)
    data["local_config_path"] = str(ROUTER_ISP_LOCAL_PATH)
    return data

def router_isp_save_settings(body: Dict[str, Any]) -> Dict[str, Any]:
    cur = router_isp_load_settings(include_secret=True)
    router = dict(cur.get("router") or {})
    inc = body.get("router") or {}
    for k in ["brand_model","login_ip","access_type","username","notes"]:
        if k in inc:
            router[k] = router_isp_s(inc.get(k))
    if inc.get("clear_password") in (True,1,"1","true","True","yes"):
        router["password"] = ""
    elif router_isp_s(inc.get("password")):
        router["password"] = router_isp_s(inc.get("password"))
    out = {"router":router, "updated_at":now_iso()}
    ROUTER_ISP_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    ROUTER_ISP_LOCAL_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        ISP_DEEP_CACHE["ts"] = 0
        ISP_DEEP_CACHE["data"] = {}
    except Exception:
        pass
    return router_isp_load_settings(False)

def router_isp_test_router() -> Dict[str, Any]:
    data = router_isp_load_settings(True)
    ip = router_isp_s((data.get("router") or {}).get("login_ip")) or "192.168.0.1"
    out = {"ok": False, "ip": ip, "checks": []}

    http_ok = False
    for scheme in ["http", "https"]:
        url = f"{scheme}://{ip}/"
        item = {"url": url, "ok": False, "status": "", "error": "", "note": ""}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SagarSystemMonitor/RouterCheck"})
            with urllib.request.urlopen(req, timeout=4) as r:
                item["ok"] = True
                item["status"] = str(getattr(r, "status", 200))
                if scheme == "http":
                    http_ok = True
                out["ok"] = True
        except Exception as e:
            err = str(e)
            item["error"] = err
            # TP-Link local routers commonly work on HTTP and fail HTTPS/TLS handshake.
            # If HTTP is OK, HTTPS handshake failure is not a router failure.
            if scheme == "https" and http_ok and ("SSL" in err.upper() or "HANDSHAKE" in err.upper() or "CERTIFICATE" in err.upper()):
                item["ok"] = True
                item["status"] = "HTTPS not supported/skipped"
                item["note"] = "HTTP router login is reachable. HTTPS/TLS failed, but this is normal for many local routers."
                item["error"] = ""
        out["checks"].append(item)

    out["ok"] = any(x.get("ok") for x in out["checks"])
    out["note"] = (
        "Router is reachable on HTTP. HTTPS/TLS may fail on local TP-Link router; this is not a problem. "
        "Automatic WAN/VLAN read still needs TP-Link ER8411 web/API connector after local page inspection."
        if out["ok"] else
        "Router is not reachable from this server. Check router IP, network, and firewall."
    )
    return out
# ROUTER_ISP_SETTINGS_ONLY_END

def overview() -> Dict[str, Any]:
    machines = load_latest()
    server_isp = server_public_internet_info(False)
    settings = get_settings()
    auto_speed_probe = str(settings.get("auto_speed_probe", "1")).lower() in ("1", "true", "yes", "on")
    internet_health = server_internet_health(False, auto_speed_probe)
    total = len(machines)
    online = sum(1 for m in machines if m.get("online"))
    offline = total - online
    critical = sum(1 for m in machines if (to_float(m.get("cpu_percent"),0) or 0) >= 90 or (to_float(m.get("ram_percent"),0) or 0) >= 90 or (to_float(m.get("disk_max_percent"),0) or 0) >= 90)
    today_down = sum(to_float(m.get("today_download_gb"),0) or 0 for m in machines)
    today_up = sum(to_float(m.get("today_upload_gb"),0) or 0 for m in machines)
    cur_down = sum(to_float(m.get("wan_download_mbps"),0) or 0 for m in machines)
    cur_up = sum(to_float(m.get("wan_upload_mbps"),0) or 0 for m in machines)
    client_isp_down = sum(to_float(m.get("isp_download_mbps"),0) or 0 for m in machines)
    client_isp_up = sum(to_float(m.get("isp_upload_mbps"),0) or 0 for m in machines)
    probe_down = to_float(internet_health.get("probe_download_mbps"), 0) or 0
    probe_up = to_float(internet_health.get("probe_upload_mbps"), 0) or 0
    # Home ISP speed should not stay 0 when clients are idle; show server live ISP probe as fallback.
    isp_down = max(client_isp_down, probe_down)
    isp_up = max(client_isp_up, probe_up)
    isp_counts: Dict[str, int] = {}
    public_ips: List[str] = []
    for m in machines:
        if m.get("isp_name"):
            isp_counts[m["isp_name"]] = isp_counts.get(m["isp_name"], 0) + 1
        if m.get("public_ip") and m.get("public_ip") not in public_ips:
            public_ips.append(m["public_ip"])
    top_isps = sorted(isp_counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
    # Fallback: if no updated client has sent ISP yet, show server ISP so home page is not blank after server start.
    if not top_isps and server_isp.get("isp"):
        top_isps = [(server_isp.get("isp", ""), 1)]
    if not public_ips and server_isp.get("public_ip"):
        public_ips.append(server_isp.get("public_ip", ""))
    with DB_LOCK, db_connect() as con:
        notif = con.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT 10").fetchall()
        changes = con.execute("SELECT * FROM change_events ORDER BY id DESC LIMIT 10").fetchall()
    return {
        "total": total, "online": online, "offline": offline, "critical": critical,
        "today_download_gb": round(today_down, 2), "today_upload_gb": round(today_up, 2),
        "current_download_mbps": round(cur_down, 2), "current_upload_mbps": round(cur_up, 2),
        "isp_download_mbps": round(isp_down, 2), "isp_upload_mbps": round(isp_up, 2),
        "isp_names": [name for name, count in top_isps], "public_ips": public_ips[:5],
        "server_isp": server_isp,
        "internet_health": internet_health,
        "isp_speed_note": internet_health.get("speed_note", ""),
        "isp_speed_source": "server_live_probe" if (probe_down or probe_up) else "client_live_usage",
        "machines": machines[:500], "notifications": [dict(r) for r in notif], "changes": [humanize_change_row(dict(r)) for r in changes], "settings": settings
    }


def daily_history(days: int = 30, machine_id: str = "", date_from: str = "", date_to: str = "", include_samples: bool = False) -> Dict[str, Any]:
    """Build daily traffic/history from stored heartbeats.
    User can select an exact date or date range and download all data.
    """
    days = max(1, min(int(days or 30), 3650))
    now_utc = dt.datetime.now(dt.timezone.utc)
    def parse_day(v: str) -> Optional[dt.date]:
        try:
            return dt.date.fromisoformat((v or "").strip()[:10])
        except Exception:
            return None
    df = parse_day(date_from)
    dt_to = parse_day(date_to)
    if df:
        start_dt = dt.datetime.combine(df, dt.time.min, tzinfo=dt.timezone.utc)
    else:
        start_dt = now_utc - dt.timedelta(days=days)
    if dt_to:
        end_dt = dt.datetime.combine(dt_to + dt.timedelta(days=1), dt.time.min, tzinfo=dt.timezone.utc)
    elif df:
        end_dt = dt.datetime.combine(df + dt.timedelta(days=1), dt.time.min, tzinfo=dt.timezone.utc)
    else:
        end_dt = now_utc + dt.timedelta(seconds=1)
    with DB_LOCK, db_connect() as con:
        if machine_id:
            rows = con.execute("SELECT machine_id,received_at,hostname,payload_json FROM heartbeats WHERE received_at>=? AND received_at<? AND machine_id=? ORDER BY received_at ASC", (start_dt.isoformat(), end_dt.isoformat(), machine_id)).fetchall()
        else:
            rows = con.execute("SELECT machine_id,received_at,hostname,payload_json FROM heartbeats WHERE received_at>=? AND received_at<? ORDER BY received_at ASC", (start_dt.isoformat(), end_dt.isoformat())).fetchall()
    buckets: Dict[str, Dict[str, Any]] = {}
    machines: Dict[str, Dict[str, Any]] = {}
    samples: List[Dict[str, Any]] = []
    for r in rows:
        try:
            day = dt.datetime.fromisoformat(str(r["received_at"]).replace("Z", "+00:00")).astimezone(dt.timezone.utc).date().isoformat()
        except Exception:
            day = str(r["received_at"])[:10]
        payload = normalize_payload_inplace(safe_json_loads(r["payload_json"], {}))
        summary = summarize_payload(payload)
        mid = summary.get("machine_id") or r["machine_id"]
        host = summary.get("hostname") or r["hostname"] or mid
        b = buckets.setdefault(day, {"date": day, "machines_seen": set(), "download_gb": 0.0, "upload_gb": 0.0, "max_current_download_mbps": 0.0, "max_current_upload_mbps": 0.0, "cpu_samples": [], "ram_samples": [], "usb_max": 0, "software_max": 0, "heartbeat_count": 0})
        b["machines_seen"].add(mid)
        b["heartbeat_count"] += 1
        b["usb_max"] = max(int(b["usb_max"]), int(to_float(summary.get("usb_count"), 0) or 0))
        b["software_max"] = max(int(b["software_max"]), int(to_float(summary.get("software_count"), 0) or 0))
        # Client counters are day-to-date, so for each machine/day take the max seen value.
        mkey = day + "|" + mid
        mm = machines.setdefault(mkey, {"date":day, "machine_id":mid, "hostname":host, "download_gb":0.0, "upload_gb":0.0, "max_current_download_mbps":0.0, "max_current_upload_mbps":0.0, "cpu_max":0.0, "ram_max":0.0, "ram_total_gb":summary.get("ram_total_gb") or 0, "usb_count":0, "software_count":0, "public_ip":"", "isp_name":"", "last_seen":r["received_at"], "heartbeat_count":0})
        mm["download_gb"] = max(float(mm["download_gb"]), float(to_float(summary.get("today_download_gb"), 0) or 0))
        mm["upload_gb"] = max(float(mm["upload_gb"]), float(to_float(summary.get("today_upload_gb"), 0) or 0))
        mm["max_current_download_mbps"] = max(float(mm["max_current_download_mbps"]), float(to_float(summary.get("wan_download_mbps"), 0) or 0))
        mm["max_current_upload_mbps"] = max(float(mm["max_current_upload_mbps"]), float(to_float(summary.get("wan_upload_mbps"), 0) or 0))
        mm["cpu_max"] = max(float(mm["cpu_max"]), float(to_float(summary.get("cpu_percent"), 0) or 0))
        mm["ram_max"] = max(float(mm["ram_max"]), float(to_float(summary.get("ram_percent"), 0) or 0))
        mm["ram_total_gb"] = summary.get("ram_total_gb") or mm.get("ram_total_gb") or 0
        mm["usb_count"] = max(int(mm.get("usb_count") or 0), int(to_float(summary.get("usb_count"), 0) or 0))
        mm["software_count"] = max(int(mm.get("software_count") or 0), int(to_float(summary.get("software_count"), 0) or 0))
        if summary.get("public_ip"): mm["public_ip"] = summary.get("public_ip")
        if summary.get("isp_name"): mm["isp_name"] = summary.get("isp_name")
        mm["last_seen"] = r["received_at"]
        mm["heartbeat_count"] += 1
        b["max_current_download_mbps"] = max(float(b["max_current_download_mbps"]), float(to_float(summary.get("wan_download_mbps"), 0) or 0))
        b["max_current_upload_mbps"] = max(float(b["max_current_upload_mbps"]), float(to_float(summary.get("wan_upload_mbps"), 0) or 0))
        cp = to_float(summary.get("cpu_percent"))
        rp = to_float(summary.get("ram_percent"))
        if cp is not None: b["cpu_samples"].append(cp)
        if rp is not None: b["ram_samples"].append(rp)
        if include_samples:
            samples.append({
                "received_at": r["received_at"], "date": day, "machine_id": mid, "hostname": host,
                "primary_ip": summary.get("primary_ip"), "public_ip": summary.get("public_ip"), "isp_name": summary.get("isp_name"),
                "cpu_percent": summary.get("cpu_percent"), "cpu_temp_c": summary.get("cpu_temp_c"),
                "ram_percent": summary.get("ram_percent"), "ram_total_gb": summary.get("ram_total_gb"), "ram_used_gb": summary.get("ram_used_gb"),
                "disk_max_percent": summary.get("disk_max_percent"), "current_download_mbps": summary.get("wan_download_mbps"), "current_upload_mbps": summary.get("wan_upload_mbps"),
                "today_download_gb": summary.get("today_download_gb"), "today_upload_gb": summary.get("today_upload_gb"), "gpu_count": summary.get("gpu_count"),
                "gpu_names": ", ".join(summary.get("gpu_names") or []), "gpu_temp_c": summary.get("gpu_max_temp_c"), "vpn_active": summary.get("vpn_active"),
                "software_count": summary.get("software_count"), "usb_count": summary.get("usb_count"), "change_count": summary.get("change_count"),
            })
    for mm in machines.values():
        b = buckets[mm["date"]]
        b["download_gb"] += float(mm["download_gb"])
        b["upload_gb"] += float(mm["upload_gb"])
    daily = []
    for day in sorted(buckets.keys(), reverse=True):
        b = buckets[day]
        cpu_avg = round(sum(b["cpu_samples"])/len(b["cpu_samples"]), 2) if b["cpu_samples"] else 0
        ram_avg = round(sum(b["ram_samples"])/len(b["ram_samples"]), 2) if b["ram_samples"] else 0
        daily.append({"date": day, "machines_seen": len(b["machines_seen"]), "heartbeat_count": b["heartbeat_count"], "download_gb": round(float(b["download_gb"]), 2), "upload_gb": round(float(b["upload_gb"]), 2), "max_current_download_mbps": round(float(b["max_current_download_mbps"]), 2), "max_current_upload_mbps": round(float(b["max_current_upload_mbps"]), 2), "avg_cpu_percent": cpu_avg, "avg_ram_percent": ram_avg, "usb_max": b["usb_max"], "software_max": b["software_max"]})
    per_machine = list(machines.values())
    per_machine.sort(key=lambda x: (x["date"], x["hostname"]), reverse=True)
    return {"ok": True, "days": days, "date_from": start_dt.date().isoformat(), "date_to": (end_dt.date() - dt.timedelta(days=1)).isoformat(), "history_note": "History is available from heartbeats stored in this server database.", "daily": daily, "per_machine": per_machine[:5000], "samples": samples[:20000] if include_samples else []}


def csv_response(rows: List[Dict[str, Any]], filename: str) -> Tuple[bytes, Dict[str, str]]:
    out = io.StringIO()
    if rows:
        fields = list(rows[0].keys())
    else:
        fields = ["no_data"]
        rows = [{"no_data":"No rows for selected date/range"}]
    w = csv.DictWriter(out, fieldnames=fields)
    w.writeheader()
    for row in rows:
        w.writerow({k: row.get(k, "") for k in fields})
    return out.getvalue().encode("utf-8"), {"Content-Disposition": f"attachment; filename={filename}"}


class Handler(BaseHTTPRequestHandler):
    server_version = "SagarSystemMonitor/6.4"

    def log_message(self, fmt: str, *args: Any) -> None:
        log(f"{self.address_string()} {fmt % args}")

    def current_session(self) -> Dict[str, Any]:
        cookies = parse_cookies(self.headers.get("Cookie", ""))
        return session_info(cookies.get("cmp_session", ""))

    def is_authenticated(self) -> bool:
        return bool(self.current_session())

    def current_role(self) -> str:
        return clean_str(self.current_session().get("role") or "")

    def current_username(self) -> str:
        return clean_str(self.current_session().get("username") or "")

    def is_admin(self) -> bool:
        return self.current_role() == "admin"

    def require_admin(self) -> bool:
        if not self.is_authenticated():
            return self.send_json({"error":"auth_required"}, 401) or False
        if not self.is_admin():
            return self.send_json({"error":"admin_required", "message":"This action is available only to admin users."}, 403) or False
        return True

    def require_auth(self, path: str, method: str) -> bool:
        if not auth_required_path(method, path):
            return True
        if self.is_authenticated():
            return True
        self.send_json({"error":"login_required", "message":"Admin login required"}, 401)
        return False

    def _send(self, status: int, body: bytes, content_type: str = "application/json; charset=utf-8", extra_headers: Optional[Dict[str,str]]=None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Old-CORS-Disabled", "REAL_FIX_V3")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if extra_headers:
            for k, v in extra_headers.items(): self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, obj: Any, status: int=200) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))

    def read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8", errors="replace") or "{}")

    def do_OPTIONS(self) -> None:
        self._send(204, b"")

    def do_GET(self) -> None:
        try:
            path = self.path.split("?", 1)[0]
            qs = {}
            if "?" in self.path:
                from urllib.parse import parse_qs
                qs = parse_qs(self.path.split("?",1)[1])
            if path == "/api/health":
                return self.send_json({"ok": True, "time": now_iso(), "db": str(DB_PATH), "app_name": APP_NAME, "version":"8.4"})
            if path == "/api/auth/status":
                return self.send_json({"ok": True, "authenticated": self.is_authenticated(), "app_name": APP_NAME, "local": is_local_request(self.client_address[0]), "username": self.current_username(), "role": self.current_role()})
            if not self.require_auth(path, "GET"):
                return
            if path == "/api/isp-check":
                server_isp = server_public_internet_info(True)
                machines = load_latest()
                client_isp = [m for m in machines if m.get("isp_name") or m.get("public_ip")]
                return self.send_json({"ok": True, "server_isp": server_isp, "machines_total": len(machines), "machines_with_client_isp": len(client_isp), "client_isp_samples": client_isp[:10]})
            if path == "/api/server-speed-test":
                full = (qs.get("full") or ["0"])[0] in ("1", "true", "yes", "on")
                try:
                    down_mb = int(float((qs.get("download_mb") or ["0"])[0] or 0))
                except Exception:
                    down_mb = 0
                try:
                    up_mb = int(float((qs.get("upload_mb") or ["0"])[0] or 0))
                except Exception:
                    up_mb = 0
                if full:
                    down_b = (down_mb if down_mb else 50) * 1000 * 1000
                    up_b = (up_mb if up_mb else 10) * 1000 * 1000
                else:
                    down_b = (down_mb if down_mb else 5) * 1000 * 1000
                    up_b = (up_mb if up_mb else 1) * 1000 * 1000
                out = server_cloudflare_speed_test(down_b, up_b)
                out["mode"] = "full_capacity" if full else "quick_probe"
                out["download_mb_requested"] = round(down_b/1000/1000, 1)
                out["upload_mb_requested"] = round(up_b/1000/1000, 1)
                out["isp"] = server_public_internet_info(False)
                return self.send_json(out)
            if path == "/api/internet-health":
                force = (qs.get("force") or ["0"])[0] in ("1", "true", "yes")
                speed = (qs.get("speed") or ["1"])[0] in ("1", "true", "yes")
                return self.send_json(server_internet_health(force, speed))
            if path == "/api/isp-deep":
                force = (qs.get("force") or ["0"])[0] in ("1", "true", "yes", "on")
                return self.send_json(sk_isp_deep_status(force))
            if path == "/api/router-isp-settings":
                if not self.require_admin(): return
                return self.send_json(router_isp_public_settings())
            if path == "/api/users":
                if not self.require_admin():
                    return
                return self.send_json({"users": list_users_public()})
            if path == "/api/messages":
                return self.send_json({"messages": list_client_messages(300)})
            if path == "/api/overview":
                return self.send_json(overview())
            if path == "/api/machines":
                return self.send_json({"machines": load_latest()})
            if path == "/api/history":
                days = int((qs.get("days") or ["30"])[0] or 30)
                mid = (qs.get("machine_id") or [""])[0]
                date_from = (qs.get("date_from") or [""])[0]
                date_to = (qs.get("date_to") or [""])[0]
                include_samples = (qs.get("samples") or ["0"])[0] in ("1", "true", "yes")
                return self.send_json(daily_history(days, mid, date_from, date_to, include_samples))
            if path == "/api/machine":
                mid = (qs.get("id") or [""])[0]
                machines = load_latest()
                for m in machines:
                    if m.get("machine_id") == mid:
                        return self.send_json(m)
                return self.send_json({"error":"Machine not found"}, 404)
            if path == "/api/notifications/rules":
                return self.send_json({"rules": rules_list(), "settings": public_settings()})
            if path == "/api/notifications":
                with DB_LOCK, db_connect() as con:
                    rows = con.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT 200").fetchall()
                return self.send_json({"notifications": [dict(r) for r in rows]})
            # SK_HRCL_INLINE_RANGE_ROUTE_START
            if path == "/api/changes-range":
                import json, sqlite3, pathlib, urllib.parse
                def _hrcl_send(payload, code=200):
                    raw = json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8')
                    self.send_response(code)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Content-Length', str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                def _hrcl_q(name, default=''):
                    return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get(name, [default])[0]
                def _hrcl_day_start(v):
                    v = (v or '').strip()
                    return v + 'T00:00:00' if len(v) == 10 and v[4] == '-' and v[7] == '-' else v
                def _hrcl_day_end(v):
                    v = (v or '').strip()
                    return v + 'T23:59:59.999999' if len(v) == 10 and v[4] == '-' and v[7] == '-' else v
                def _hrcl_limit(v):
                    try:
                        n = int(v)
                    except Exception:
                        n = 5000
                    return max(1, min(n, 20000))
                try:
                    _base = pathlib.Path(__file__).resolve().parent
                    _db = pathlib.Path(globals().get('DB_PATH') or globals().get('DATABASE') or globals().get('DB_FILE') or (_base / 'data' / 'monitor.db'))
                    _mid = (_hrcl_q('machine_id', '') or '').strip()
                    _from = _hrcl_day_start(_hrcl_q('from', ''))
                    _to = _hrcl_day_end(_hrcl_q('to', ''))
                    _limit = _hrcl_limit(_hrcl_q('limit', '5000'))
                    if not _db.exists():
                        return _hrcl_send({'ok': False, 'error': 'monitor.db not found', 'db': str(_db), 'changes': []}, 404)
                    con = sqlite3.connect(str(_db), timeout=10)
                    con.row_factory = sqlite3.Row
                    cur = con.cursor()
                    where = []
                    params = []
                    if _mid:
                        where.append('machine_id = ?')
                        params.append(_mid)
                    if _from:
                        where.append('created_at >= ?')
                        params.append(_from)
                    if _to:
                        where.append('created_at <= ?')
                        params.append(_to)
                    sql = 'SELECT id, created_at, machine_id, hostname, change_type, title, message, detail_json FROM change_events'
                    if where:
                        sql += ' WHERE ' + ' AND '.join(where)
                    sql += ' ORDER BY created_at DESC, id DESC LIMIT ?'
                    params.append(_limit)
                    rows = cur.execute(sql, params).fetchall()
                    changes = []
                    for r in rows:
                        d = dict(r)
                        detail = {}
                        try:
                            detail = json.loads(d.get('detail_json') or '{}')
                        except Exception:
                            detail = {}
                        added = detail.get('added', [])
                        removed = detail.get('removed', [])
                        if not isinstance(added, list):
                            added = [added]
                        if not isinstance(removed, list):
                            removed = [removed]
                        d['human_title'] = d.get('title') or detail.get('title') or d.get('change_type') or 'Change'
                        d['human_message'] = d.get('message') or detail.get('message') or d['human_title']
                        d['summary'] = d['human_message']
                        d['added'] = added
                        d['removed'] = removed
                        d['added_items'] = added
                        d['removed_items'] = removed
                        d['type'] = d.get('change_type') or detail.get('type') or ''
                        changes.append(d)
                    con.close()
                    return _hrcl_send({'ok': True, 'changes': changes, 'count': len(changes), 'machine_id': _mid, 'from': _from, 'to': _to, 'limit': _limit})
                except Exception as e:
                    try:
                        con.close()
                    except Exception:
                        pass
                    return _hrcl_send({'ok': False, 'error': str(e), 'changes': []}, 500)
            # SK_HRCL_INLINE_RANGE_ROUTE_END
            # SK_HISTORY_FAST_ROUTE_START
            if path == "/api/history-fast":
                import json, sqlite3, pathlib, urllib.parse
                def _hist_send(payload, code=200):
                    raw = json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8')
                    self.send_response(code)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Content-Length', str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                def _hist_q(name, default=''):
                    try:
                        return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get(name, [default])[0]
                    except Exception:
                        return default
                def _hist_limit(v, default, hi):
                    try:
                        n = int(v)
                    except Exception:
                        n = default
                    return max(1, min(n, hi))
                def _day_start(v):
                    v=(v or '').strip()
                    return v + 'T00:00:00' if len(v)==10 and v[4]=='-' and v[7]=='-' else v
                def _day_end(v):
                    v=(v or '').strip()
                    return v + 'T23:59:59.999999' if len(v)==10 and v[4]=='-' and v[7]=='-' else v
                def _cat_sql(expr):
                    low = 'lower(' + expr + ')'
                    return {
                      'hardware': "("+low+" LIKE '%hardware%' OR "+low+" LIKE '%cpu%' OR "+low+" LIKE '%ram%' OR "+low+" LIKE '%disk%' OR "+low+" LIKE '%gpu%')",
                      'usb': "("+low+" LIKE '%usb%' OR "+low+" LIKE '%peripheral%' OR "+low+" LIKE '%keyboard%' OR "+low+" LIKE '%mouse%' OR "+low+" LIKE '%camera%' OR "+low+" LIKE '%printer%')",
                      'software': "("+low+" LIKE '%software%' OR "+low+" LIKE '%app%' OR "+low+" LIKE '%install%')",
                      'network': "("+low+" LIKE '%network%' OR "+low+" LIKE '%ip%' OR "+low+" LIKE '%wan%' OR "+low+" LIKE '%internet%' OR "+low+" LIKE '%latency%' OR "+low+" LIKE '%dns%')",
                      'vpn': "("+low+" LIKE '%vpn%')"
                    }
                try:
                    _base = pathlib.Path(__file__).resolve().parent
                    _db = pathlib.Path(globals().get('DB_PATH') or globals().get('DATABASE') or globals().get('DB_FILE') or (_base / 'data' / 'monitor.db'))
                    if not _db.exists():
                        return _hist_send({'ok': False, 'error': 'monitor.db not found', 'db': str(_db), 'days': [], 'events': []}, 404)
                    mode = (_hist_q('mode','days') or 'days').strip().lower()
                    mid = (_hist_q('machine_id','') or '').strip()
                    con = sqlite3.connect(str(_db), timeout=10)
                    con.row_factory = sqlite3.Row
                    cur = con.cursor()
                    try:
                        cur.execute('CREATE INDEX IF NOT EXISTS idx_history_fast_ce_day ON change_events(created_at)')
                        cur.execute('CREATE INDEX IF NOT EXISTS idx_history_fast_ce_machine_day ON change_events(machine_id, created_at)')
                        cur.execute('CREATE INDEX IF NOT EXISTS idx_history_fast_ce_type_day ON change_events(change_type, created_at)')
                    except Exception:
                        pass
                    cats = _cat_sql("coalesce(change_type,'') || ' ' || coalesce(title,'') || ' ' || coalesce(message,'')")
                    relevant = '(' + ' OR '.join(cats.values()) + ')'
                    where = [relevant]
                    params = []
                    if mid:
                        where.append('machine_id = ?')
                        params.append(mid)
                    if mode == 'days':
                        frm = _day_start(_hist_q('from',''))
                        to = _day_end(_hist_q('to',''))
                        if frm:
                            where.append('created_at >= ?')
                            params.append(frm)
                        if to:
                            where.append('created_at <= ?')
                            params.append(to)
                        limit_days = _hist_limit(_hist_q('limit_days','1200'), 1200, 5000)
                        sql = 'SELECT substr(created_at,1,10) AS day, COUNT(*) AS total_count, '
                        sql += 'SUM(CASE WHEN '+cats['hardware']+' THEN 1 ELSE 0 END) AS hardware_count, '
                        sql += 'SUM(CASE WHEN '+cats['usb']+' THEN 1 ELSE 0 END) AS usb_count, '
                        sql += 'SUM(CASE WHEN '+cats['software']+' THEN 1 ELSE 0 END) AS software_count, '
                        sql += 'SUM(CASE WHEN '+cats['network']+' THEN 1 ELSE 0 END) AS network_count, '
                        sql += 'SUM(CASE WHEN '+cats['vpn']+' THEN 1 ELSE 0 END) AS vpn_count '
                        sql += 'FROM change_events WHERE ' + ' AND '.join(where) + ' GROUP BY day ORDER BY day DESC LIMIT ?'
                        rows = cur.execute(sql, params + [limit_days]).fetchall()
                        days = [dict(r) for r in rows]
                        con.close()
                        return _hist_send({'ok': True, 'mode': 'days', 'days': days, 'count': len(days)})
                    else:
                        day = (_hist_q('date','') or '').strip()
                        if day:
                            where.append('created_at >= ?')
                            params.append(day + 'T00:00:00')
                            where.append('created_at <= ?')
                            params.append(day + 'T23:59:59.999999')
                        frm = _day_start(_hist_q('from',''))
                        to = _day_end(_hist_q('to',''))
                        if frm:
                            where.append('created_at >= ?')
                            params.append(frm)
                        if to:
                            where.append('created_at <= ?')
                            params.append(to)
                        limit = _hist_limit(_hist_q('limit','1000'), 1000, 10000)
                        sql = 'SELECT id, created_at, machine_id, hostname, change_type, title, message, detail_json FROM change_events WHERE ' + ' AND '.join(where) + ' ORDER BY created_at DESC, id DESC LIMIT ?'
                        rows = cur.execute(sql, params + [limit]).fetchall()
                        events = []
                        for r in rows:
                            d = dict(r)
                            detail = {}
                            try:
                                detail = json.loads(d.get('detail_json') or '{}')
                            except Exception:
                                detail = {}
                            added = detail.get('added', [])
                            removed = detail.get('removed', [])
                            if not isinstance(added, list): added = [added]
                            if not isinstance(removed, list): removed = [removed]
                            d['human_title'] = d.get('title') or detail.get('title') or d.get('change_type') or 'Change'
                            d['human_message'] = d.get('message') or detail.get('message') or d['human_title']
                            d['summary'] = d['human_message']
                            d['added_items'] = added
                            d['removed_items'] = removed
                            d['added'] = added
                            d['removed'] = removed
                            d['type'] = d.get('change_type') or detail.get('type') or ''
                            events.append(d)
                        con.close()
                        return _hist_send({'ok': True, 'mode': 'events', 'events': events, 'count': len(events)})
                except Exception as e:
                    try:
                        con.close()
                    except Exception:
                        pass
                    return _hist_send({'ok': False, 'error': str(e), 'days': [], 'events': []}, 500)
            # SK_HISTORY_FAST_ROUTE_END
            # SK_HW_INVENTORY_ROUTE_START
            if path == "/api/hardware-inventory":
                import json, sqlite3, pathlib, urllib.parse, datetime
                def _hw_send(payload, code=200):
                    raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                def _hw_q(name, default=""):
                    try:
                        return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get(name, [default])[0]
                    except Exception:
                        return default
                def _hw_db_path():
                    base = pathlib.Path(__file__).resolve().parent
                    return pathlib.Path(globals().get("DB_PATH") or globals().get("DATABASE") or globals().get("DB_FILE") or (base / "data" / "monitor.db"))
                def _hw_now():
                    return datetime.datetime.utcnow().isoformat() + "Z"
                def _hw_ensure(con):
                    cols = [
                        "sr_no","tagname_hostname","room_location","person_allocated_to","assets_type","oem_name","model_no","serial_no","configuration","vendor_name","po_invoice_bill_no","bill_path_google_drive_path","purchase_date","warranty_start_date","warranty_end_date","warranty_status","status","remark","source_sheet","source_row","original_section"
                    ]
                    con.execute("CREATE TABLE IF NOT EXISTS hardware_inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, updated_at TEXT)")
                    existing = {r[1] for r in con.execute("PRAGMA table_info(hardware_inventory)").fetchall()}
                    for c in cols:
                        if c not in existing:
                            con.execute("ALTER TABLE hardware_inventory ADD COLUMN " + c + " TEXT")
                    con.execute("CREATE INDEX IF NOT EXISTS idx_hw_inv_tag ON hardware_inventory(tagname_hostname)")
                    con.execute("CREATE INDEX IF NOT EXISTS idx_hw_inv_serial ON hardware_inventory(serial_no)")
                    con.execute("CREATE INDEX IF NOT EXISTS idx_hw_inv_type ON hardware_inventory(assets_type)")
                    con.execute("CREATE INDEX IF NOT EXISTS idx_hw_inv_status ON hardware_inventory(status)")
                    return cols
                def _hw_seed_if_empty(con, cols):
                    count = con.execute("SELECT COUNT(*) FROM hardware_inventory").fetchone()[0]
                    if count:
                        return False
                    seed_file = pathlib.Path(__file__).resolve().parent / "data" / "hardware_inventory_seed.json"
                    if not seed_file.exists():
                        return False
                    try:
                        rows = json.loads(seed_file.read_text(encoding="utf-8"))
                    except Exception:
                        rows = []
                    now = _hw_now()
                    for i, row in enumerate(rows, start=1):
                        values = []
                        row = dict(row or {})
                        row["sr_no"] = row.get("sr_no") or i
                        for c in cols:
                            values.append(str(row.get(c, "") or ""))
                        placeholders = ",".join(["?"] * (len(cols) + 2))
                        con.execute("INSERT INTO hardware_inventory(created_at, updated_at, " + ",".join(cols) + ") VALUES (" + placeholders + ")", [now, now] + values)
                    con.commit()
                    return bool(rows)
                def _hw_text(row):
                    return " ".join(str(v or "") for v in row.values()).lower()
                def _hw_live_rows(con):
                    out = []
                    try:
                        names = [r[1] for r in con.execute("PRAGMA table_info(latest)").fetchall()]
                        if not names:
                            return out
                        for rr in con.execute("SELECT * FROM latest LIMIT 5000").fetchall():
                            d = dict(zip(names, rr))
                            text = _hw_text(d)
                            host = d.get("hostname") or d.get("host") or d.get("machine_id") or d.get("name") or ""
                            ip = d.get("primary_ip") or d.get("ip") or ""
                            last_seen = d.get("last_seen") or d.get("updated_at") or d.get("created_at") or ""
                            out.append({"host": str(host or ""), "ip": str(ip or ""), "last_seen": str(last_seen or ""), "text": text})
                    except Exception:
                        return out
                    return out
                def _hw_rows(con, cols):
                    q = (_hw_q("q", "") or "").strip().lower()
                    asset_type = (_hw_q("asset_type", "") or "").strip().lower()
                    status = (_hw_q("status", "") or "").strip().lower()
                    try:
                        limit = max(1, min(int(_hw_q("limit", "2000") or "2000"), 10000))
                    except Exception:
                        limit = 2000
                    where = []
                    params = []
                    if q:
                        search_expr = "lower(coalesce(tagname_hostname,'')||' '||coalesce(serial_no,'')||' '||coalesce(person_allocated_to,'')||' '||coalesce(room_location,'')||' '||coalesce(configuration,'')||' '||coalesce(assets_type,'')||' '||coalesce(model_no,'')||' '||coalesce(oem_name,''))"
                        where.append(search_expr + " LIKE ?")
                        params.append("%" + q + "%")
                    if asset_type:
                        where.append("lower(coalesce(assets_type,'')) LIKE ?")
                        params.append("%" + asset_type + "%")
                    if status:
                        where.append("lower(coalesce(status,'')) LIKE ?")
                        params.append("%" + status + "%")
                    sql = "SELECT id, created_at, updated_at, " + ",".join(cols) + " FROM hardware_inventory"
                    if where:
                        sql += " WHERE " + " AND ".join(where)
                    sql += " ORDER BY CAST(NULLIF(sr_no,'') AS INTEGER), id LIMIT ?"
                    params.append(limit)
                    return [dict(r) for r in con.execute(sql, params).fetchall()]
                try:
                    db = _hw_db_path()
                    db.parent.mkdir(parents=True, exist_ok=True)
                    con = sqlite3.connect(str(db), timeout=20)
                    con.row_factory = sqlite3.Row
                    cols = _hw_ensure(con)
                    seeded = _hw_seed_if_empty(con, cols)
                    rows = _hw_rows(con, cols)
                    tag_counts = {}
                    serial_counts = {}
                    for r in con.execute("SELECT tagname_hostname, serial_no FROM hardware_inventory").fetchall():
                        tag = str(r[0] or "").strip().lower()
                        serial = str(r[1] or "").strip().lower()
                        if tag and tag not in ("na", "n/a", "-", "none"):
                            tag_counts[tag] = tag_counts.get(tag, 0) + 1
                        if serial and serial not in ("na", "n/a", "-", "none"):
                            serial_counts[serial] = serial_counts.get(serial, 0) + 1
                    live = _hw_live_rows(con)
                    for r in rows:
                        tag = str(r.get("tagname_hostname") or "").strip().lower()
                        serial = str(r.get("serial_no") or "").strip().lower()
                        r["duplicate_tag"] = bool(tag and tag_counts.get(tag, 0) > 1)
                        r["duplicate_serial"] = bool(serial and serial_counts.get(serial, 0) > 1)
                        r["live_sync_status"] = "Not matched"
                        r["live_machine"] = ""
                        r["live_ip"] = ""
                        r["live_last_seen"] = ""
                        if tag or serial:
                            for item in live:
                                text = item.get("text", "")
                                if (tag and len(tag) >= 3 and tag in text) or (serial and len(serial) >= 3 and serial in text):
                                    r["live_sync_status"] = "Live matched"
                                    r["live_machine"] = item.get("host", "")
                                    r["live_ip"] = item.get("ip", "")
                                    r["live_last_seen"] = item.get("last_seen", "")
                                    break
                    total = con.execute("SELECT COUNT(*) FROM hardware_inventory").fetchone()[0]
                    con.close()
                    return _hw_send({"ok": True, "seeded": seeded, "total": total, "count": len(rows), "rows": rows, "columns": cols})
                except Exception as e:
                    try:
                        con.close()
                    except Exception:
                        pass
                    return _hw_send({"ok": False, "error": str(e), "rows": []}, 500)
            # SK_HW_INVENTORY_ROUTE_END

            # SK_HW_INVENTORY_SAVE_GET_ROUTE_START
            if path == "/api/hardware-inventory-save":
                import json, sqlite3, pathlib, urllib.parse, datetime
                def _hw_send(payload, code=200):
                    raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                def _hw_q(name, default=""):
                    try:
                        return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get(name, [default])[0]
                    except Exception:
                        return default
                def _hw_db_path():
                    base = pathlib.Path(__file__).resolve().parent
                    return pathlib.Path(globals().get("DB_PATH") or globals().get("DATABASE") or globals().get("DB_FILE") or (base / "data" / "monitor.db"))
                def _hw_now():
                    return datetime.datetime.utcnow().isoformat() + "Z"
                def _hw_ensure(con):
                    cols = [
                        "sr_no","tagname_hostname","room_location","person_allocated_to","assets_type","oem_name","model_no","serial_no","configuration","vendor_name","po_invoice_bill_no","bill_path_google_drive_path","purchase_date","warranty_start_date","warranty_end_date","warranty_status","status","remark","source_sheet","source_row","original_section"
                    ]
                    con.execute("CREATE TABLE IF NOT EXISTS hardware_inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, updated_at TEXT)")
                    existing = {r[1] for r in con.execute("PRAGMA table_info(hardware_inventory)").fetchall()}
                    for c in cols:
                        if c not in existing:
                            con.execute("ALTER TABLE hardware_inventory ADD COLUMN " + c + " TEXT")
                    con.execute("CREATE INDEX IF NOT EXISTS idx_hw_inv_tag ON hardware_inventory(tagname_hostname)")
                    con.execute("CREATE INDEX IF NOT EXISTS idx_hw_inv_serial ON hardware_inventory(serial_no)")
                    return cols
                try:
                    payload = _hw_q("payload", "{}")
                    try:
                        data = json.loads(payload or "{}")
                    except Exception:
                        data = {}
                    rows = data.get("rows")
                    if rows is None:
                        one = data.get("row") or data
                        rows = [one]
                    if not isinstance(rows, list):
                        rows = []
                    db = _hw_db_path()
                    db.parent.mkdir(parents=True, exist_ok=True)
                    con = sqlite3.connect(str(db), timeout=20)
                    con.row_factory = sqlite3.Row
                    cols = _hw_ensure(con)
                    now = _hw_now()
                    saved = 0
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        values = [str(row.get(c, "") or "") for c in cols]
                        rid = str(row.get("id", "") or "").strip()
                        if rid.isdigit():
                            set_sql = ",".join([c + "=?" for c in cols])
                            con.execute("UPDATE hardware_inventory SET updated_at=?, " + set_sql + " WHERE id=?", [now] + values + [int(rid)])
                            saved += 1
                        else:
                            placeholders = ",".join(["?"] * (len(cols) + 2))
                            con.execute("INSERT INTO hardware_inventory(created_at, updated_at, " + ",".join(cols) + ") VALUES (" + placeholders + ")", [now, now] + values)
                            saved += 1
                    con.commit()
                    total = con.execute("SELECT COUNT(*) FROM hardware_inventory").fetchone()[0]
                    con.close()
                    return _hw_send({"ok": True, "saved": saved, "total": total})
                except Exception as e:
                    try:
                        con.close()
                    except Exception:
                        pass
                    return _hw_send({"ok": False, "error": str(e)}, 500)
            # SK_HW_INVENTORY_SAVE_GET_ROUTE_END
            # SK_HW_INVENTORY_DELETE_GET_ROUTE_START
            if path == "/api/hardware-inventory-delete":
                import json, sqlite3, pathlib, urllib.parse
                def _hw_del_send(payload, code=200):
                    raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                def _hw_del_q(name, default=""):
                    try:
                        return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get(name, [default])[0]
                    except Exception:
                        return default
                try:
                    ids_raw = _hw_del_q("ids", "")
                    ids = []
                    for x in ids_raw.split(","):
                        x = x.strip()
                        if x.isdigit():
                            ids.append(int(x))
                    if not ids:
                        return _hw_del_send({"ok": False, "error": "No valid id supplied"}, 400)
                    base = pathlib.Path(__file__).resolve().parent
                    db = pathlib.Path(globals().get("DB_PATH") or globals().get("DATABASE") or globals().get("DB_FILE") or (base / "data" / "monitor.db"))
                    con = sqlite3.connect(str(db), timeout=20)
                    placeholders = ",".join(["?"] * len(ids))
                    cur = con.execute("DELETE FROM hardware_inventory WHERE id IN (" + placeholders + ")", ids)
                    con.commit()
                    deleted = cur.rowcount
                    total = con.execute("SELECT COUNT(*) FROM hardware_inventory").fetchone()[0]
                    con.close()
                    return _hw_del_send({"ok": True, "deleted": deleted, "total": total})
                except Exception as e:
                    try:
                        con.close()
                    except Exception:
                        pass
                    return _hw_del_send({"ok": False, "error": str(e)}, 500)
            # SK_HW_INVENTORY_DELETE_GET_ROUTE_END
            # SK_SW_INVENTORY_ROUTES_START
            if path == "/api/software-inventory":
                import json, sqlite3, pathlib, urllib.parse
                def _sw_send(payload, code=200):
                    raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                def _sw_q(name, default=""):
                    try:
                        return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get(name, [default])[0]
                    except Exception:
                        return default
                def _sw_db():
                    base = pathlib.Path(__file__).resolve().parent
                    return pathlib.Path(globals().get("DB_PATH") or globals().get("DATABASE") or globals().get("DB_FILE") or (base / "data" / "monitor.db"))
                def _sw_cols():
                    return ["software_name","category","login_url","username","password_value","license_key","mfa_recovery","machine_asset","allocated_to","vendor_name","po_invoice_bill_no","bill_path_google_drive_path","purchase_date","renewal_expiry_date","status","notes"]
                def _sw_ensure(con):
                    con.execute("CREATE TABLE IF NOT EXISTS software_inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, updated_at TEXT)")
                    existing = {r[1] for r in con.execute("PRAGMA table_info(software_inventory)").fetchall()}
                    for c in _sw_cols():
                        if c not in existing:
                            con.execute("ALTER TABLE software_inventory ADD COLUMN " + c + " TEXT")
                    con.execute("CREATE INDEX IF NOT EXISTS idx_sw_inv_name ON software_inventory(software_name)")
                    con.execute("CREATE INDEX IF NOT EXISTS idx_sw_inv_user ON software_inventory(username)")
                    con.execute("CREATE INDEX IF NOT EXISTS idx_sw_inv_status ON software_inventory(status)")
                try:
                    db = _sw_db()
                    db.parent.mkdir(parents=True, exist_ok=True)
                    con = sqlite3.connect(str(db), timeout=20)
                    con.row_factory = sqlite3.Row
                    _sw_ensure(con)
                    search = (_sw_q("search","") or "").strip().lower()
                    status = (_sw_q("status","") or "").strip()
                    category = (_sw_q("category","") or "").strip()
                    try:
                        limit = max(1, min(int(_sw_q("limit","20000")), 50000))
                    except Exception:
                        limit = 20000
                    where = []
                    params = []
                    if search:
                        where.append("lower(coalesce(software_name,'') || ' ' || coalesce(category,'') || ' ' || coalesce(login_url,'') || ' ' || coalesce(username,'') || ' ' || coalesce(machine_asset,'') || ' ' || coalesce(allocated_to,'') || ' ' || coalesce(vendor_name,'') || ' ' || coalesce(license_key,'') || ' ' || coalesce(notes,'')) LIKE ?")
                        params.append("%" + search + "%")
                    if status:
                        where.append("status = ?")
                        params.append(status)
                    if category:
                        where.append("category = ?")
                        params.append(category)
                    sql = "SELECT * FROM software_inventory"
                    if where:
                        sql += " WHERE " + " AND ".join(where)
                    sql += " ORDER BY id DESC LIMIT ?"
                    params.append(limit)
                    rows = [dict(r) for r in con.execute(sql, params).fetchall()]
                    for r in rows:
                        r["password"] = r.get("password_value") or ""
                    total = con.execute("SELECT COUNT(*) FROM software_inventory").fetchone()[0]
                    con.close()
                    return _sw_send({"ok": True, "rows": rows, "total": total})
                except Exception as e:
                    try:
                        con.close()
                    except Exception:
                        pass
                    return _sw_send({"ok": False, "error": str(e), "rows": []}, 500)

            if path == "/api/software-inventory-save":
                import json, sqlite3, pathlib, urllib.parse, datetime
                def _sw_save_send(payload, code=200):
                    raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                def _sw_save_q(name, default=""):
                    try:
                        return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get(name, [default])[0]
                    except Exception:
                        return default
                def _sw_save_db():
                    base = pathlib.Path(__file__).resolve().parent
                    return pathlib.Path(globals().get("DB_PATH") or globals().get("DATABASE") or globals().get("DB_FILE") or (base / "data" / "monitor.db"))
                def _sw_cols():
                    return ["software_name","category","login_url","username","password_value","license_key","mfa_recovery","machine_asset","allocated_to","vendor_name","po_invoice_bill_no","bill_path_google_drive_path","purchase_date","renewal_expiry_date","status","notes"]
                def _sw_ensure(con):
                    con.execute("CREATE TABLE IF NOT EXISTS software_inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, updated_at TEXT)")
                    existing = {r[1] for r in con.execute("PRAGMA table_info(software_inventory)").fetchall()}
                    for c in _sw_cols():
                        if c not in existing:
                            con.execute("ALTER TABLE software_inventory ADD COLUMN " + c + " TEXT")
                    con.execute("CREATE INDEX IF NOT EXISTS idx_sw_inv_name ON software_inventory(software_name)")
                    con.execute("CREATE INDEX IF NOT EXISTS idx_sw_inv_user ON software_inventory(username)")
                    con.execute("CREATE INDEX IF NOT EXISTS idx_sw_inv_status ON software_inventory(status)")
                try:
                    payload = _sw_save_q("payload","{}")
                    try:
                        data = json.loads(payload or "{}")
                    except Exception:
                        data = {}
                    rows = data.get("rows")
                    if rows is None:
                        rows = [data.get("row") or data]
                    if not isinstance(rows, list):
                        rows = []
                    db = _sw_save_db()
                    db.parent.mkdir(parents=True, exist_ok=True)
                    con = sqlite3.connect(str(db), timeout=20)
                    con.row_factory = sqlite3.Row
                    _sw_ensure(con)
                    now = datetime.datetime.utcnow().isoformat() + "Z"
                    cols = _sw_cols()
                    saved = 0
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        if "password" in row and "password_value" not in row:
                            row["password_value"] = row.get("password")
                        values = [str(row.get(c, "") or "") for c in cols]
                        rid = str(row.get("id","") or "").strip()
                        if rid.isdigit():
                            set_sql = ",".join([c + "=?" for c in cols])
                            con.execute("UPDATE software_inventory SET updated_at=?, " + set_sql + " WHERE id=?", [now] + values + [int(rid)])
                            saved += 1
                        else:
                            placeholders = ",".join(["?"] * (len(cols) + 2))
                            con.execute("INSERT INTO software_inventory(created_at, updated_at, " + ",".join(cols) + ") VALUES (" + placeholders + ")", [now, now] + values)
                            saved += 1
                    con.commit()
                    total = con.execute("SELECT COUNT(*) FROM software_inventory").fetchone()[0]
                    con.close()
                    return _sw_save_send({"ok": True, "saved": saved, "total": total})
                except Exception as e:
                    try:
                        con.close()
                    except Exception:
                        pass
                    return _sw_save_send({"ok": False, "error": str(e)}, 500)

            if path == "/api/software-inventory-delete":
                import json, sqlite3, pathlib, urllib.parse
                def _sw_del_send(payload, code=200):
                    raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                def _sw_del_q(name, default=""):
                    try:
                        return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get(name, [default])[0]
                    except Exception:
                        return default
                try:
                    ids = []
                    for x in (_sw_del_q("ids","") or "").split(","):
                        x = x.strip()
                        if x.isdigit():
                            ids.append(int(x))
                    if not ids:
                        return _sw_del_send({"ok": False, "error": "No valid id supplied"}, 400)
                    base = pathlib.Path(__file__).resolve().parent
                    db = pathlib.Path(globals().get("DB_PATH") or globals().get("DATABASE") or globals().get("DB_FILE") or (base / "data" / "monitor.db"))
                    con = sqlite3.connect(str(db), timeout=20)
                    ph = ",".join(["?"] * len(ids))
                    cur = con.execute("DELETE FROM software_inventory WHERE id IN (" + ph + ")", ids)
                    con.commit()
                    deleted = cur.rowcount
                    total = con.execute("SELECT COUNT(*) FROM software_inventory").fetchone()[0]
                    con.close()
                    return _sw_del_send({"ok": True, "deleted": deleted, "total": total})
                except Exception as e:
                    try:
                        con.close()
                    except Exception:
                        pass
                    return _sw_del_send({"ok": False, "error": str(e)}, 500)
            # SK_SW_INVENTORY_ROUTES_END
            # SK_NOTIFICATION_EXTRA_RULES_ROUTE_START
            if path == "/api/notification-extra-rules-seed":
                import json, sqlite3, pathlib, urllib.parse, time
                def _sk_notif_send(payload, code=200):
                    raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                try:
                    base = pathlib.Path(__file__).resolve().parent
                    db = pathlib.Path(globals().get("DB_PATH") or globals().get("DATABASE") or globals().get("DB_FILE") or (base / "data" / "monitor.db"))
                    db.parent.mkdir(parents=True, exist_ok=True)
                    con = sqlite3.connect(str(db), timeout=20)
                    con.row_factory = sqlite3.Row

                    # Works with existing notification_rules table. Creates only if missing.
                    con.execute("""CREATE TABLE IF NOT EXISTS notification_rules (
                        id TEXT PRIMARY KEY,
                        name TEXT,
                        metric TEXT,
                        op TEXT,
                        threshold REAL,
                        enabled INTEGER DEFAULT 0,
                        severity TEXT DEFAULT 'warning',
                        cooldown_minutes INTEGER DEFAULT 15
                    )""")

                    cols = {r[1] for r in con.execute("PRAGMA table_info(notification_rules)").fetchall()}
                    needed = {
                        "id": "TEXT PRIMARY KEY",
                        "name": "TEXT",
                        "metric": "TEXT",
                        "op": "TEXT",
                        "threshold": "REAL",
                        "enabled": "INTEGER DEFAULT 0",
                        "severity": "TEXT DEFAULT 'warning'",
                        "cooldown_minutes": "INTEGER DEFAULT 15"
                    }
                    for c, typ in needed.items():
                        if c not in cols and c != "id":
                            try:
                                con.execute("ALTER TABLE notification_rules ADD COLUMN " + c + " " + typ)
                            except Exception:
                                pass

                    rules = [
                        {
                            "id": "disk_usage_high",
                            "name": "SSD/HDD usage high",
                            "metric": "max_disk_used_percent",
                            "op": ">=",
                            "threshold": 90,
                            "enabled": 0,
                            "severity": "critical",
                            "cooldown_minutes": 15
                        },
                        {
                            "id": "cpu_ram_combo_high",
                            "name": "CPU + RAM combined high",
                            "metric": "cpu_ram_combined_percent",
                            "op": ">=",
                            "threshold": 85,
                            "enabled": 0,
                            "severity": "critical",
                            "cooldown_minutes": 10
                        },
                        {
                            "id": "cpu_gpu_temp_high",
                            "name": "CPU/GPU temperature high",
                            "metric": "cpu_gpu_temp_max_c",
                            "op": ">=",
                            "threshold": 80,
                            "enabled": 0,
                            "severity": "critical",
                            "cooldown_minutes": 10
                        },
                        {
                            "id": "thread_core_usage_high",
                            "name": "Thread/Core usage high",
                            "metric": "thread_core_usage_percent",
                            "op": ">=",
                            "threshold": 90,
                            "enabled": 0,
                            "severity": "warning",
                            "cooldown_minutes": 10
                        }
                    ]

                    inserted = 0
                    updated = 0
                    for r in rules:
                        exists = con.execute("SELECT id FROM notification_rules WHERE id=?", (r["id"],)).fetchone()
                        if exists:
                            con.execute("""UPDATE notification_rules
                                           SET name=?, metric=?, op=?, threshold=?, severity=?, cooldown_minutes=?
                                           WHERE id=?""",
                                        (r["name"], r["metric"], r["op"], r["threshold"], r["severity"], r["cooldown_minutes"], r["id"]))
                            updated += 1
                        else:
                            con.execute("""INSERT INTO notification_rules(id,name,metric,op,threshold,enabled,severity,cooldown_minutes)
                                           VALUES(?,?,?,?,?,?,?,?)""",
                                        (r["id"], r["name"], r["metric"], r["op"], r["threshold"], r["enabled"], r["severity"], r["cooldown_minutes"]))
                            inserted += 1

                    con.commit()
                    total = con.execute("SELECT COUNT(*) FROM notification_rules").fetchone()[0]
                    con.close()
                    return _sk_notif_send({"ok": True, "inserted": inserted, "updated": updated, "total": total, "rules": rules})
                except Exception as e:
                    try:
                        con.close()
                    except Exception:
                        pass
                    return _sk_notif_send({"ok": False, "error": str(e)}, 500)
            # SK_NOTIFICATION_EXTRA_RULES_ROUTE_END
            if path == "/api/changes":
                return self.send_json({"changes": latest_change_events(300, human=True)})
            if path == "/api/export/changes.csv":
                if not self.is_admin():
                    return self.send_json({"error":"admin_required", "message":"Downloads are available only to admin users."}, 403)
                mid = (qs.get("machine_id") or [""])[0]
                rows = change_events_for_export(5000, mid)
                body, headers = csv_response(rows, "human_change_log.csv" if not mid else "human_change_log_selected_machine.csv")
                return self._send(200, body, "text/csv; charset=utf-8", headers)
            if path == "/api/export/software.csv":
                if not self.is_admin():
                    return self.send_json({"error":"admin_required", "message":"Downloads are available only to admin users."}, 403)
                mid = (qs.get("machine_id") or [""])[0]
                rows = export_software_rows(mid)
                body, headers = csv_response(rows, "software_inventory.csv" if not mid else "software_selected_machine.csv")
                return self._send(200, body, "text/csv; charset=utf-8", headers)
            if path == "/api/export/usb.csv":
                if not self.is_admin():
                    return self.send_json({"error":"admin_required", "message":"Downloads are available only to admin users."}, 403)
                mid = (qs.get("machine_id") or [""])[0]
                rows = export_usb_rows(mid)
                body, headers = csv_response(rows, "usb_peripherals.csv" if not mid else "usb_selected_machine.csv")
                return self._send(200, body, "text/csv; charset=utf-8", headers)
            if path == "/api/export/history_daily.csv":
                if not self.is_admin():
                    return self.send_json({"error":"admin_required", "message":"Downloads are available only to admin users."}, 403)
                days = int((qs.get("days") or ["30"])[0] or 30)
                mid = (qs.get("machine_id") or [""])[0]
                date_from = (qs.get("date_from") or [""])[0]
                date_to = (qs.get("date_to") or [""])[0]
                data = daily_history(days, mid, date_from, date_to, False)
                body, headers = csv_response(data.get("daily") or [], "day_summary.csv")
                return self._send(200, body, "text/csv; charset=utf-8", headers)
            if path == "/api/export/history_machine.csv":
                if not self.is_admin():
                    return self.send_json({"error":"admin_required", "message":"Downloads are available only to admin users."}, 403)
                days = int((qs.get("days") or ["30"])[0] or 30)
                mid = (qs.get("machine_id") or [""])[0]
                date_from = (qs.get("date_from") or [""])[0]
                date_to = (qs.get("date_to") or [""])[0]
                data = daily_history(days, mid, date_from, date_to, False)
                body, headers = csv_response(data.get("per_machine") or [], "system_wise_day_history.csv")
                return self._send(200, body, "text/csv; charset=utf-8", headers)
            if path.startswith("/api/export/") and not self.is_admin():
                return self.send_json({"error":"admin_required", "message":"Downloads are available only to admin users."}, 403)
            if path == "/api/export/history.csv":
                days = int((qs.get("days") or ["30"])[0] or 30)
                mid = (qs.get("machine_id") or [""])[0]
                date_from = (qs.get("date_from") or [""])[0]
                date_to = (qs.get("date_to") or [""])[0]
                data = daily_history(days, mid, date_from, date_to, False)
                rows = data.get("per_machine") or data.get("daily") or []
                body, headers = csv_response(rows, "history_per_machine.csv")
                return self._send(200, body, "text/csv; charset=utf-8", headers)
            if path == "/api/export/history_samples.csv":
                days = int((qs.get("days") or ["30"])[0] or 30)
                mid = (qs.get("machine_id") or [""])[0]
                date_from = (qs.get("date_from") or [""])[0]
                date_to = (qs.get("date_to") or [""])[0]
                data = daily_history(days, mid, date_from, date_to, True)
                body, headers = csv_response(data.get("samples") or [], "history_all_heartbeats.csv")
                return self._send(200, body, "text/csv; charset=utf-8", headers)
            if path == "/api/export/machine_current.csv":
                if not self.is_admin():
                    return self.send_json({"error":"admin_required", "message":"Downloads are available only to admin users."}, 403)
                mid = (qs.get("machine_id") or [""])[0]
                machines = load_latest()
                if mid:
                    machines = [m for m in machines if m.get("machine_id") == mid]
                fields = ["hostname","machine_id","os","primary_ip","public_ip","isp_name","online","cpu_percent","cpu_temp_c","ram_percent","ram_total_gb","ram_used_gb","disk_max_percent","wan_download_mbps","wan_upload_mbps","today_download_gb","today_upload_gb","gpu_count","gpu_names","vpn_active","software_count","usb_count","updated_at"]
                out = io.StringIO(); w = csv.DictWriter(out, fieldnames=fields); w.writeheader()
                for m in machines:
                    row = {k: m.get(k, "") for k in fields}
                    if isinstance(row.get("gpu_names"), list): row["gpu_names"] = "; ".join(row["gpu_names"])
                    w.writerow(row)
                return self._send(200, out.getvalue().encode("utf-8"), "text/csv; charset=utf-8", {"Content-Disposition":"attachment; filename=machine_current.csv"})
            if path == "/api/export/machines.csv":
                if not self.is_admin():
                    return self.send_json({"error":"admin_required", "message":"Downloads are available only to admin users."}, 403)
                machines = load_latest()
                out = io.StringIO()
                fields = ["hostname","machine_id","id_source","os","primary_ip","public_ip","isp_name","online","cpu_percent","cpu_temp_c","ram_percent","ram_total_gb","ram_used_gb","disk_max_percent","wan_download_mbps","wan_upload_mbps","isp_download_mbps","isp_upload_mbps","today_download_gb","today_upload_gb","gpu_count","gpu_max_usage","gpu_max_temp_c","vpn_active","software_count","usb_count","change_count","updated_at"]
                w = csv.DictWriter(out, fieldnames=fields)
                w.writeheader()
                for m in machines:
                    w.writerow({k: m.get(k, "") for k in fields})
                return self._send(200, out.getvalue().encode("utf-8"), "text/csv; charset=utf-8", {"Content-Disposition":"attachment; filename=machines.csv"})
            return self.serve_static(path)
        except Exception as e:
            log(traceback.format_exc())
            return self.send_json({"error": str(e)}, 500)

    def serve_static(self, path: str) -> None:
        if path in ("", "/"):
            path = "/index.html"
        rel = path.lstrip("/")
        if ".." in rel or rel.startswith("/"):
            return self.send_json({"error":"bad path"}, 400)

        # Single-port client update system:
        # The main server on 2278 also serves scripts, so no separate 8511 file-server window is required.
        if rel == "scripts" or rel.startswith("scripts/"):
            script_rel = rel[len("scripts/"): ] if rel.startswith("scripts/") else ""
            file_path = SCRIPTS_DIR / script_rel
            if file_path.exists() and file_path.is_file():
                data = file_path.read_bytes()
                return self._send(200, data, MIME.get(file_path.suffix.lower(), "application/octet-stream"), {"Cache-Control":"no-store"})
            return self.send_json({"error":"script not found"}, 404)

        if rel == "dist" or rel.startswith("dist/"):
            dist_rel = rel[len("dist/"): ] if rel.startswith("dist/") else ""
            dist_path = BASE_DIR / "dist" / dist_rel
            if dist_path.exists() and dist_path.is_file():
                data = dist_path.read_bytes()
                return self._send(200, data, MIME.get(dist_path.suffix.lower(), "application/octet-stream"), {"Cache-Control":"no-store"})
            return self.send_json({"error":"file not found"}, 404)

        file_path = PUBLIC_DIR / rel
        if not file_path.exists() or not file_path.is_file():
            file_path = PUBLIC_DIR / "index.html"
        data = file_path.read_bytes()
        self._send(200, data, MIME.get(file_path.suffix.lower(), "application/octet-stream"), {"Cache-Control":"no-store, max-age=0"})

    def do_POST(self) -> None:
        try:
            path = self.path.split("?",1)[0]
            body = self.read_json()
            if path == "/api/auth/login":
                username = clean_str(body.get("username") or "admin").strip() or "admin"
                password = clean_str(body.get("password"))
                row = get_user_row(username)
                if row and verify_password(password, row["password_hash"]):
                    token = new_session(row["username"], row["role"])
                    data = json.dumps({"ok": True, "app_name": APP_NAME, "version":"8.4", "username": row["username"], "role": row["role"]}).encode("utf-8")
                    self._send(200, data, "application/json; charset=utf-8", {"Set-Cookie": f"cmp_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={SESSION_TTL_SECONDS}"})
                    return
                settings = get_settings()
                stored = settings.get("admin_password_hash", "")
                if username.lower() == "admin" and verify_password(password, stored):
                    token = new_session("admin", "admin")
                    data = json.dumps({"ok": True, "app_name": APP_NAME, "version":"8.4", "username":"admin", "role":"admin"}).encode("utf-8")
                    self._send(200, data, "application/json; charset=utf-8", {"Set-Cookie": f"cmp_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={SESSION_TTL_SECONDS}"})
                    return
                return self.send_json({"ok": False, "error":"bad_password"}, 403)
            if path in ("/api/heartbeat", "/heartbeat", "/submit"):
                return self.send_json(upsert_heartbeat(body, self.client_address[0]))
            if not self.require_auth(path, "POST"):
                return
            if path == "/api/auth/logout":
                cookies = parse_cookies(self.headers.get("Cookie", "")); SESSIONS.pop(cookies.get("cmp_session", ""), None)
                return self._send(200, b'{"ok": true}', "application/json; charset=utf-8", {"Set-Cookie":"cmp_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"})
            if path == "/api/auth/change-password":
                oldp = clean_str(body.get("old_password")); newp = clean_str(body.get("new_password"))
                if len(newp) < 8:
                    return self.send_json({"ok": False, "error":"Password must be at least 8 characters"}, 400)
                stored = get_settings().get("admin_password_hash", "")
                if not verify_password(oldp, stored):
                    return self.send_json({"ok": False, "error":"Old password wrong"}, 403)
                new_hash = hash_password(newp)
                set_settings({"admin_password_hash": new_hash})
                with DB_LOCK, db_connect() as con:
                    con.execute("UPDATE users SET password_hash=?, updated_at=? WHERE username=?", (new_hash, now_iso(), self.current_username() or 'admin'))
                    if (self.current_username() or 'admin').lower() == 'admin':
                        con.execute("UPDATE users SET password_hash=?, updated_at=? WHERE username='admin'", (new_hash, now_iso()))
                    con.commit()
                return self.send_json({"ok": True})
            if path == "/api/settings":
                if not self.require_admin(): return
                set_settings(body)
                return self.send_json({"ok": True, "settings": public_settings()})
            if path == "/api/router-isp-settings":
                if not self.require_admin(): return
                return self.send_json(router_isp_save_settings(body))
            if path == "/api/router-isp-test":
                if not self.require_admin(): return
                return self.send_json(router_isp_test_router())
            if path == "/api/users":
                if not self.require_admin(): return
                return self.send_json(upsert_user(clean_str(body.get("username")), clean_str(body.get("password")), clean_str(body.get("role") or "viewer"), body.get("enabled", True) not in (False, 0, "0", "false", "False")))
            if path == "/api/notifications/rule":
                if not self.require_admin(): return
                rid = clean_str(body.get("id")) or ("rule_" + str(int(time.time()*1000)))
                name = clean_str(body.get("name")) or rid
                metric = clean_str(body.get("metric")) or "cpu_percent"
                op = clean_str(body.get("op")) or ">="
                threshold = to_float(body.get("threshold"), 0) or 0
                enabled = 1 if body.get("enabled") in (True, 1, "1", "true", "True", "on") else 0
                severity = clean_str(body.get("severity")) or "warning"
                cooldown = int(to_float(body.get("cooldown_minutes"), 15) or 15)
                with DB_LOCK, db_connect() as con:
                    con.execute("""INSERT OR REPLACE INTO notification_rules(id,name,metric,op,threshold,enabled,severity,cooldown_minutes)
                        VALUES(?,?,?,?,?,?,?,?)""", (rid,name,metric,op,threshold,enabled,severity,cooldown))
                    con.commit()
                return self.send_json({"ok": True, "rules": rules_list()})
            if path == "/api/messages":
                if not self.require_admin(): return
                return self.send_json(create_client_message(clean_str(body.get("target_machine_id")), clean_str(body.get("target_hostname")), clean_str(body.get("title") or "Admin message"), clean_str(body.get("message")), clean_str(body.get("priority") or "normal")))
            if path == "/api/notifications/test":
                if not self.require_admin(): return
                message = clean_str(body.get("message")) or "Test notification from Commercial Monitor Pro"
                with DB_LOCK, db_connect() as con:
                    record_notification(con, "info", "SERVER", "SERVER", "Test notification", message, "test")
                    con.commit()
                return self.send_json({"ok": True})
            if path == "/api/notifications/clear":
                if not self.require_admin(): return
                with DB_LOCK, db_connect() as con:
                    con.execute("DELETE FROM notifications")
                    con.commit()
                return self.send_json({"ok": True})
            return self.send_json({"error":"not found"}, 404)
        except Exception as e:
            log(traceback.format_exc())
            return self.send_json({"error": str(e)}, 500)

    def do_DELETE(self) -> None:
        try:
            path = self.path.split("?",1)[0]
            from urllib.parse import parse_qs
            qs = parse_qs(self.path.split("?",1)[1]) if "?" in self.path else {}
            if not self.require_auth(path, "DELETE"):
                return
            if path == "/api/notifications/rule":
                if not self.require_admin(): return
                rid = (qs.get("id") or [""])[0]
                if rid:
                    with DB_LOCK, db_connect() as con:
                        con.execute("DELETE FROM notification_rules WHERE id=?", (rid,))
                        con.commit()
                return self.send_json({"ok": True, "rules": rules_list()})
            if path == "/api/users":
                if not self.require_admin(): return
                username = (qs.get("username") or [""])[0]
                return self.send_json(delete_user(username))
            return self.send_json({"error":"not found"}, 404)
        except Exception as e:
            return self.send_json({"error": str(e)}, 500)


# STABILITY_AUDIT_TESTED_V2_START
try:
    import urllib.parse as _stab2_urlparse
    import datetime as _stab2_dt
    import sqlite3 as _stab2_sqlite3
    import json as _stab2_json
    from pathlib import Path as _stab2_Path

    def cleanup_duplicate_latest_rows(con, summary, payload):
        """V2 safety: never delete/merge latest rows automatically.
        Wrong client count/details came from aggressive cleanup. Keep rows visible; admins can audit manually.
        """
        return []

    def _stab2_num(v, default=0.0):
        try:
            if v is None or v == "":
                return default
            return float(str(v).replace("%", "").strip())
        except Exception:
            return default

    def _stab2_json_load(v, default=None):
        try:
            return _stab2_json.loads(v or "{}")
        except Exception:
            return default if default is not None else {}

    def _stab2_db():
        try:
            return _stab2_Path(globals().get("DB_PATH") or (_stab2_Path(__file__).resolve().parent / "data" / "monitor.db"))
        except Exception:
            return _stab2_Path(__file__).resolve().parent / "data" / "monitor.db"

    def load_latest() -> List[Dict[str, Any]]:
        """V2 read-only latest loader.
        It never deletes latest rows, so dashboard count and client details do not disappear.
        """
        try:
            check_offline_notifications()
        except Exception as e:
            try: log(f"stability_v2 offline notification check skipped: {e}")
            except Exception: pass
        try:
            settings = get_settings()
        except Exception:
            settings = {}
        try:
            timeout = float(settings.get("offline_timeout_minutes", "0.25"))
        except Exception:
            timeout = 0.25
        try:
            with DB_LOCK, db_connect() as con:
                rows = con.execute("SELECT * FROM latest ORDER BY updated_at DESC").fetchall()
        except Exception as e:
            try: log(f"stability_v2 load_latest failed: {e}")
            except Exception: pass
            return []
        now_ts = _stab2_dt.datetime.now(_stab2_dt.timezone.utc).timestamp()
        out = []
        for r in rows:
            try:
                d = dict(r)
                summary = safe_json_loads(d.get("summary_json", "{}"), {})
                if not isinstance(summary, dict):
                    summary = {}
                payload = safe_json_loads(d.get("payload_json", "{}"), {})
                if not isinstance(payload, dict):
                    payload = {}
                try:
                    payload = normalize_payload_inplace(payload)
                except Exception:
                    pass
                if isinstance(payload, dict):
                    try:
                        summary["usb_count"] = int((payload.get("usb") or {}).get("count") or len(normalize_usb_list(get_nested(payload, ["usb.devices", "usb", "peripherals"], []))))
                    except Exception:
                        summary["usb_count"] = summary.get("usb_count", 0)
                    try:
                        summary["software_count"] = len(listify(get_nested(payload, ["software.installed", "software", "apps"], [])))
                    except Exception:
                        pass
                summary.update({
                    "machine_id": d.get("machine_id") or summary.get("machine_id") or "",
                    "hostname": d.get("hostname") or summary.get("hostname", ""),
                    "id_source": d.get("id_source") or summary.get("id_source", ""),
                    "id_value": d.get("id_value") or summary.get("id_value", ""),
                    "updated_at": d.get("updated_at"),
                    "payload": payload,
                })
                try:
                    updated = _stab2_dt.datetime.fromisoformat((d.get("updated_at") or "").replace("Z", "+00:00")).timestamp()
                    mins = max(0.0, (now_ts - updated) / 60.0)
                except Exception:
                    mins = 9999.0
                summary["offline_minutes"] = round(mins, 2)
                summary["online"] = mins <= timeout
                summary["duplicate_cleanup_disabled"] = True
                out.append(summary)
            except Exception as e:
                try: log(f"stability_v2 load_latest row skipped: {e}")
                except Exception: pass
        return out

    def _stab2_metric_value(summary, metric):
        cpu = _stab2_num(summary.get("cpu_percent"))
        ram = _stab2_num(summary.get("ram_percent"))
        gpu_usage = _stab2_num(summary.get("gpu_max_usage"))
        cpu_temp = _stab2_num(summary.get("cpu_temp_c"))
        gpu_temp = _stab2_num(summary.get("gpu_max_temp_c"))
        if metric == "cpu_ram_combined_percent":
            return min(cpu, ram)
        if metric == "cpu_ram_peak_percent":
            return max(cpu, ram)
        if metric == "cpu_gpu_temp_combined_c":
            vals = [x for x in [cpu_temp, gpu_temp] if x > 0]
            return min(vals) if len(vals) == 2 else 0
        if metric == "cpu_gpu_temp_peak_c":
            return max(cpu_temp, gpu_temp)
        if metric == "ram_gpu_usage_combined_percent":
            vals = [ram, gpu_usage]
            return min(vals) if all(x > 0 for x in vals) else 0
        if metric == "ram_gpu_usage_peak_percent":
            return max(ram, gpu_usage)
        return to_float(summary.get(metric))

    def evaluate_notifications(summary):
        try:
            if not isinstance(summary, dict):
                return
            summary["cpu_ram_combined_percent"] = round(min(_stab2_num(summary.get("cpu_percent")), _stab2_num(summary.get("ram_percent"))), 2)
            summary["cpu_ram_peak_percent"] = round(max(_stab2_num(summary.get("cpu_percent")), _stab2_num(summary.get("ram_percent"))), 2)
            summary["cpu_gpu_temp_combined_c"] = round(_stab2_metric_value(summary, "cpu_gpu_temp_combined_c"), 2)
            summary["cpu_gpu_temp_peak_c"] = round(_stab2_metric_value(summary, "cpu_gpu_temp_peak_c"), 2)
            summary["ram_gpu_usage_combined_percent"] = round(_stab2_metric_value(summary, "ram_gpu_usage_combined_percent"), 2)
            summary["ram_gpu_usage_peak_percent"] = round(_stab2_metric_value(summary, "ram_gpu_usage_peak_percent"), 2)
            with DB_LOCK, db_connect() as con:
                rows = con.execute("SELECT * FROM notification_rules WHERE enabled=1 AND metric!='offline_minutes' AND metric NOT LIKE 'change_%'").fetchall()
                for r in rows:
                    value = _stab2_metric_value(summary, r["metric"])
                    if eval_rule(value, r["op"], float(r["threshold"])):
                        if can_send_alert(con, r["id"], summary["machine_id"], int(r["cooldown_minutes"])):
                            host = summary.get("hostname") or summary["machine_id"]
                            msg = f"{host}: {r['metric']} is {value} {r['op']} {r['threshold']}"
                            record_notification(con, r["severity"], summary["machine_id"], host, r["name"], msg, r["id"])
                con.commit()
        except Exception as e:
            try: log(f"stability_v2 evaluate_notifications failed: {e}")
            except Exception: pass

    def _stab2_day(full_path, name):
        try:
            s = _stab2_urlparse.parse_qs(_stab2_urlparse.urlparse(full_path).query).get(name, [""])[0]
            s = str(s or "").strip()[:10]
            if len(s) == 10 and s[4] == "-" and s[7] == "-":
                return _stab2_dt.date.fromisoformat(s)
        except Exception:
            pass
        return None

    def _stab2_q(full_path, name, default=""):
        try:
            return _stab2_urlparse.parse_qs(_stab2_urlparse.urlparse(full_path).query).get(name, [default])[0]
        except Exception:
            return default

    def _stab2_int(v, default=30, lo=1, hi=3650):
        try:
            n = int(str(v or default).strip())
        except Exception:
            n = default
        return max(lo, min(n, hi))

    def _stab2_expr(paths, default="0"):
        return "CAST(COALESCE(" + ",".join(["json_extract(payload_json, '%s')" % p for p in paths]) + ", " + default + ") AS REAL)"

    def _stab2_txt(paths):
        return "COALESCE(" + ",".join(["NULLIF(json_extract(payload_json, '%s'), '')" % p for p in paths]) + ", '')"

    def _stab2_history_usage_fast(full_path):
        days = _stab2_int(_stab2_q(full_path, "days", "30"), 30, 1, 3650)
        mid = str(_stab2_q(full_path, "machine_id", "") or "").strip()
        date_from = _stab2_day(full_path, "date_from")
        date_to = _stab2_day(full_path, "date_to")
        now_utc = _stab2_dt.datetime.now(_stab2_dt.timezone.utc)
        if date_from:
            start_dt = _stab2_dt.datetime.combine(date_from, _stab2_dt.time.min, tzinfo=_stab2_dt.timezone.utc)
        else:
            start_dt = now_utc - _stab2_dt.timedelta(days=days)
        if date_to:
            end_dt = _stab2_dt.datetime.combine(date_to + _stab2_dt.timedelta(days=1), _stab2_dt.time.min, tzinfo=_stab2_dt.timezone.utc)
        elif date_from:
            end_dt = _stab2_dt.datetime.combine(date_from + _stab2_dt.timedelta(days=1), _stab2_dt.time.min, tzinfo=_stab2_dt.timezone.utc)
        else:
            end_dt = now_utc + _stab2_dt.timedelta(seconds=1)
        db = _stab2_db()
        if not db.exists():
            return {"ok": False, "error": "monitor.db not found", "machines": [], "daily": []}
        down = _stab2_expr(["$.network.traffic.today_download_gb","$.network.today_download_gb","$.today_download_gb"])
        up = _stab2_expr(["$.network.traffic.today_upload_gb","$.network.today_upload_gb","$.today_upload_gb"])
        cur_down = _stab2_expr(["$.network.traffic.current_download_mbps","$.network.current_download_mbps","$.current_download_mbps","$.download_mbps","$.wan_download_mbps"])
        cur_up = _stab2_expr(["$.network.traffic.current_upload_mbps","$.network.current_upload_mbps","$.current_upload_mbps","$.upload_mbps","$.wan_upload_mbps"])
        primary_ip = _stab2_txt(["$.network.primary_ip","$.primary_ip","$.ip"])
        public_ip = _stab2_txt(["$.network.public_internet.public_ip","$.network.public_internet.query","$.network.public_internet.ip","$.public_ip"])
        isp = _stab2_txt(["$.network.public_internet.isp","$.network.public_internet.org","$.network.public_internet.as","$.isp_name"])
        con = None
        try:
            con = _stab2_sqlite3.connect(str(db), timeout=20)
            con.row_factory = _stab2_sqlite3.Row
            try:
                con.execute("CREATE INDEX IF NOT EXISTS idx_stab2_history_time ON heartbeats(received_at)")
                con.execute("CREATE INDEX IF NOT EXISTS idx_stab2_history_machine_time ON heartbeats(machine_id, received_at)")
            except Exception:
                pass
            where = ["received_at >= ?", "received_at < ?"]
            params = [start_dt.isoformat(), end_dt.isoformat()]
            if mid:
                where.append("machine_id = ?")
                params.append(mid)
            sql = """
                SELECT machine_id, substr(received_at,1,10) AS day,
                       COALESCE(MAX(NULLIF(hostname,'')), machine_id) AS hostname,
                       COUNT(*) AS heartbeat_count,
                       MAX(%s) AS download_gb, MAX(%s) AS upload_gb,
                       MAX(%s) AS max_down_mbps, MAX(%s) AS max_up_mbps,
                       MAX(%s) AS primary_ip, MAX(%s) AS public_ip, MAX(%s) AS isp_name,
                       MAX(received_at) AS last_seen
                FROM heartbeats WHERE %s
                GROUP BY machine_id, day
                ORDER BY day DESC, hostname ASC
                LIMIT 50000
            """ % (down, up, cur_down, cur_up, primary_ip, public_ip, isp, " AND ".join(where))
            raw = [dict(r) for r in con.execute(sql, params).fetchall()]
            con.close(); con = None
            machines = {}; daily = {}
            for r in raw:
                machine_id = str(r.get("machine_id") or "")
                day = str(r.get("day") or "")
                dg = _stab2_num(r.get("download_gb")); ug = _stab2_num(r.get("upload_gb"))
                h = int(_stab2_num(r.get("heartbeat_count")))
                md = _stab2_num(r.get("max_down_mbps")); mu = _stab2_num(r.get("max_up_mbps"))
                m = machines.setdefault(machine_id, {"machine_id": machine_id, "hostname": str(r.get("hostname") or machine_id), "primary_ip": "", "public_ip": "", "isp_name": "", "days": 0, "heartbeat_count": 0, "download_gb": 0.0, "upload_gb": 0.0, "total_gb": 0.0, "max_down_mbps": 0.0, "max_up_mbps": 0.0, "last_seen": ""})
                if r.get("hostname"): m["hostname"] = str(r.get("hostname"))
                if r.get("primary_ip"): m["primary_ip"] = str(r.get("primary_ip"))
                if r.get("public_ip"): m["public_ip"] = str(r.get("public_ip"))
                if r.get("isp_name"): m["isp_name"] = str(r.get("isp_name"))
                m["days"] += 1; m["heartbeat_count"] += h; m["download_gb"] += dg; m["upload_gb"] += ug
                m["max_down_mbps"] = max(m["max_down_mbps"], md); m["max_up_mbps"] = max(m["max_up_mbps"], mu)
                if str(r.get("last_seen") or "") > str(m.get("last_seen") or ""):
                    m["last_seen"] = str(r.get("last_seen") or "")
                d = daily.setdefault(day, {"date": day, "machines_seen": set(), "heartbeat_count": 0, "download_gb": 0.0, "upload_gb": 0.0, "total_gb": 0.0, "max_down_mbps": 0.0, "max_up_mbps": 0.0})
                d["machines_seen"].add(machine_id); d["heartbeat_count"] += h; d["download_gb"] += dg; d["upload_gb"] += ug
                d["max_down_mbps"] = max(d["max_down_mbps"], md); d["max_up_mbps"] = max(d["max_up_mbps"], mu)
            out_m = []
            for m in machines.values():
                m["download_gb"] = round(float(m["download_gb"]), 3); m["upload_gb"] = round(float(m["upload_gb"]), 3)
                m["total_gb"] = round(float(m["download_gb"]) + float(m["upload_gb"]), 3)
                m["max_down_mbps"] = round(float(m["max_down_mbps"]), 3); m["max_up_mbps"] = round(float(m["max_up_mbps"]), 3)
                out_m.append(m)
            out_m.sort(key=lambda x: x.get("total_gb", 0), reverse=True)
            out_d = []
            for d in daily.values():
                d["machines_seen"] = len(d["machines_seen"]); d["download_gb"] = round(float(d["download_gb"]), 3); d["upload_gb"] = round(float(d["upload_gb"]), 3)
                d["total_gb"] = round(float(d["download_gb"]) + float(d["upload_gb"]), 3); d["max_down_mbps"] = round(float(d["max_down_mbps"]), 3); d["max_up_mbps"] = round(float(d["max_up_mbps"]), 3)
                out_d.append(d)
            out_d.sort(key=lambda x: x.get("date", ""), reverse=True)
            return {"ok": True, "source": "stability_v2_fast_sql", "date_from": start_dt.date().isoformat(), "date_to": (end_dt.date() - _stab2_dt.timedelta(days=1)).isoformat(), "machine_id": mid, "machines": out_m, "daily": out_d, "count": len(out_m), "daily_count": len(out_d)}
        except Exception as e:
            try:
                if con: con.close()
            except Exception: pass
            return {"ok": False, "error": str(e), "machines": [], "daily": []}

    def _stab2_hw_cols():
        return ["sr_no","tagname_hostname","room_location","person_allocated_to","assets_type","oem_name","model_no","serial_no","configuration","vendor_name","po_invoice_bill_no","bill_path_google_drive_path","purchase_date","warranty_start_date","warranty_end_date","warranty_status","status","remark","source_sheet","source_row","original_section"]

    def _stab2_sw_cols():
        return ["software_name","category","login_url","username","password_value","license_key","mfa_recovery","machine_asset","allocated_to","vendor_name","po_invoice_bill_no","bill_path_google_drive_path","purchase_date","renewal_expiry_date","status","notes"]

    def _stab2_ensure_table(con, table, cols):
        con.execute(f"CREATE TABLE IF NOT EXISTS {table} (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, updated_at TEXT)")
        existing = {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
        for c in cols:
            if c not in existing:
                con.execute(f"ALTER TABLE {table} ADD COLUMN " + c + " TEXT")

    def _stab2_save_rows(table, cols, data):
        if not isinstance(data, dict): data = {}
        rows = data.get("rows")
        if rows is None: rows = [data.get("row") or data]
        if not isinstance(rows, list): rows = []
        db = _stab2_db(); db.parent.mkdir(parents=True, exist_ok=True)
        con = _stab2_sqlite3.connect(str(db), timeout=20); con.row_factory = _stab2_sqlite3.Row
        _stab2_ensure_table(con, table, cols)
        now = _stab2_dt.datetime.utcnow().isoformat() + "Z"
        saved = 0
        for row in rows:
            if not isinstance(row, dict): continue
            if table == "software_inventory" and "password" in row and "password_value" not in row:
                row["password_value"] = row.get("password")
            values = [str(row.get(c, "") or "") for c in cols]
            rid = str(row.get("id", "") or "").strip()
            if rid.isdigit() and int(rid) > 0:
                set_sql = ",".join([c + "=?" for c in cols])
                cur = con.execute(f"UPDATE {table} SET updated_at=?, " + set_sql + " WHERE id=?", [now] + values + [int(rid)])
                if cur.rowcount <= 0:
                    placeholders = ",".join(["?"] * (len(cols) + 2))
                    con.execute(f"INSERT INTO {table}(created_at, updated_at, " + ",".join(cols) + ") VALUES (" + placeholders + ")", [now, now] + values)
            else:
                placeholders = ",".join(["?"] * (len(cols) + 2))
                con.execute(f"INSERT INTO {table}(created_at, updated_at, " + ",".join(cols) + ") VALUES (" + placeholders + ")", [now, now] + values)
            saved += 1
        con.commit(); total = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]; con.close()
        return {"ok": True, "saved": saved, "total": total}

    _STAB2_OLD_GET = Handler.do_GET
    _STAB2_OLD_POST = Handler.do_POST

    def _stab2_read_body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            return _stab2_json.loads(raw.decode("utf-8-sig") or "{}")
        except Exception:
            return {}

    def _stab2_get(self):
        try:
            path = self.path.split("?", 1)[0]
            if path == "/api/history-usage-fast":
                if not self.require_auth(path, "GET"): return
                return self.send_json(_stab2_history_usage_fast(self.path))
            return _STAB2_OLD_GET(self)
        except Exception as e:
            return self.send_json({"ok": False, "error": str(e)}, 500)

    def _stab2_post(self):
        try:
            path = self.path.split("?", 1)[0]
            if path == "/api/hardware-inventory-save":
                if not self.require_admin(): return
                return self.send_json(_stab2_save_rows("hardware_inventory", _stab2_hw_cols(), _stab2_read_body(self)))
            if path == "/api/software-inventory-save":
                if not self.require_admin(): return
                return self.send_json(_stab2_save_rows("software_inventory", _stab2_sw_cols(), _stab2_read_body(self)))
            return _STAB2_OLD_POST(self)
        except Exception as e:
            return self.send_json({"ok": False, "error": str(e)}, 500)

    Handler.do_GET = _stab2_get
    Handler.do_POST = _stab2_post
    print("STABILITY_AUDIT_TESTED_V2_LOADED")
except Exception as _stab2_e:
    print("STABILITY_AUDIT_TESTED_V2_FAILED", _stab2_e)
# STABILITY_AUDIT_TESTED_V2_END

# REAL_FIX_V3_START
try:
    import urllib.parse as _rf3_urlparse
    import datetime as _rf3_dt
    import sqlite3 as _rf3_sqlite3
    import json as _rf3_json

    def cleanup_duplicate_latest_rows(con, summary, payload):
        # Safety: never delete/hide live client rows from latest.
        return []

    def _rf3_to_float(v, default=0.0):
        try:
            if v is None or v == "":
                return default
            return float(str(v).replace("%", "").strip())
        except Exception:
            return default

    def load_latest():
        # Safe current-client loader: read every latest row, do not delete and do not hide.
        try:
            check_offline_notifications()
        except Exception:
            pass
        settings = get_settings()
        try:
            timeout = float(settings.get("offline_timeout_minutes", "0.25"))
        except Exception:
            timeout = 0.25
        with DB_LOCK, db_connect() as con:
            rows = con.execute("SELECT * FROM latest ORDER BY updated_at DESC").fetchall()
        now_ts = _rf3_dt.datetime.now(_rf3_dt.timezone.utc).timestamp()
        out = []
        for r in rows:
            try:
                d = dict(r)
                summary = safe_json_loads(d.get("summary_json", "{}"), {})
                payload = safe_json_loads(d.get("payload_json", "{}"), {})
                if not isinstance(summary, dict):
                    summary = {}
                if isinstance(payload, dict):
                    try:
                        payload = normalize_payload_inplace(payload)
                    except Exception:
                        pass
                    try:
                        summary["usb_count"] = int((payload.get("usb") or {}).get("count") or len(normalize_usb_list(get_nested(payload, ["usb.devices", "usb", "peripherals"], []))))
                    except Exception:
                        summary["usb_count"] = summary.get("usb_count", 0)
                    try:
                        summary["software_count"] = len(listify(get_nested(payload, ["software.installed", "software", "apps"], [])))
                    except Exception:
                        pass
                summary.update({
                    "machine_id": d.get("machine_id", ""),
                    "hostname": d.get("hostname") or summary.get("hostname", ""),
                    "id_source": d.get("id_source") or summary.get("id_source", ""),
                    "id_value": d.get("id_value") or summary.get("id_value", ""),
                    "updated_at": d.get("updated_at"),
                    "payload": payload if isinstance(payload, dict) else {}
                })
                try:
                    updated = _rf3_dt.datetime.fromisoformat((d.get("updated_at") or "").replace("Z", "+00:00")).timestamp()
                    mins = max(0.0, (now_ts - updated) / 60.0)
                except Exception:
                    mins = 9999.0
                summary["offline_minutes"] = round(mins, 2)
                summary["online"] = mins <= timeout
                out.append(summary)
            except Exception:
                continue
        return out

    def _rf3_origin_allowed(self):
        origin = self.headers.get("Origin", "")
        if not origin:
            return ""
        try:
            o = _rf3_urlparse.urlparse(origin)
            host = (self.headers.get("Host", "") or "").split(":")[0].lower()
            oh = (o.hostname or "").lower()
            if oh == host or oh in {"localhost", "127.0.0.1", "monitor.sagarkerhalkar.com"}:
                return origin
            if oh.startswith("192.168.") or oh.startswith("10.") or oh.startswith("156.156."):
                return origin
        except Exception:
            return ""
        return ""

    def _rf3_send(self, status, body, content_type="application/json; charset=utf-8", extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        origin = _rf3_origin_allowed(self)
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    Handler._send = _rf3_send

    def _rf3_q(full_path, name, default=""):
        try:
            return _rf3_urlparse.parse_qs(_rf3_urlparse.urlparse(full_path).query).get(name, [default])[0]
        except Exception:
            return default

    def _rf3_int(v, default=30, lo=1, hi=3650):
        try:
            n = int(str(v or default).strip())
        except Exception:
            n = default
        return max(lo, min(n, hi))

    def _rf3_day(v):
        try:
            s = str(v or "").strip()[:10]
            if len(s) == 10 and s[4] == "-" and s[7] == "-":
                return _rf3_dt.date.fromisoformat(s)
        except Exception:
            pass
        return None

    def _rf3_expr(paths):
        inner = ",".join(["json_extract(payload_json, '%s')" % p for p in paths])
        return "CAST(COALESCE(" + inner + ", 0) AS REAL)"

    def _rf3_text_expr(paths):
        inner = ",".join(["NULLIF(json_extract(payload_json, '%s'), '')" % p for p in paths])
        return "COALESCE(" + inner + ", '')"

    def _rf3_history_usage_fast(full_path):
        days = _rf3_int(_rf3_q(full_path, "days", "30"), 30, 1, 3650)
        machine_id = str(_rf3_q(full_path, "machine_id", "") or "").strip()
        date_from = _rf3_day(_rf3_q(full_path, "date_from", ""))
        date_to = _rf3_day(_rf3_q(full_path, "date_to", ""))
        now_utc = _rf3_dt.datetime.now(_rf3_dt.timezone.utc)
        if date_from:
            start_dt = _rf3_dt.datetime.combine(date_from, _rf3_dt.time.min, tzinfo=_rf3_dt.timezone.utc)
        else:
            start_dt = now_utc - _rf3_dt.timedelta(days=days)
        if date_to:
            end_dt = _rf3_dt.datetime.combine(date_to + _rf3_dt.timedelta(days=1), _rf3_dt.time.min, tzinfo=_rf3_dt.timezone.utc)
        elif date_from:
            end_dt = _rf3_dt.datetime.combine(date_from + _rf3_dt.timedelta(days=1), _rf3_dt.time.min, tzinfo=_rf3_dt.timezone.utc)
        else:
            end_dt = now_utc + _rf3_dt.timedelta(seconds=1)
        down_expr = _rf3_expr(["$.network.traffic.today_download_gb", "$.network.today_download_gb", "$.today_download_gb"])
        up_expr = _rf3_expr(["$.network.traffic.today_upload_gb", "$.network.today_upload_gb", "$.today_upload_gb"])
        cur_down_expr = _rf3_expr(["$.network.traffic.current_download_mbps", "$.network.current_download_mbps", "$.current_download_mbps", "$.download_mbps", "$.wan_download_mbps"])
        cur_up_expr = _rf3_expr(["$.network.traffic.current_upload_mbps", "$.network.current_upload_mbps", "$.current_upload_mbps", "$.upload_mbps", "$.wan_upload_mbps"])
        primary_ip_expr = _rf3_text_expr(["$.network.primary_ip", "$.primary_ip", "$.ip"])
        public_ip_expr = _rf3_text_expr(["$.network.public_internet.public_ip", "$.network.public_internet.query", "$.network.public_internet.ip", "$.public_internet.public_ip", "$.public_ip"])
        isp_expr = _rf3_text_expr(["$.network.public_internet.isp", "$.network.public_internet.org", "$.network.public_internet.as", "$.public_internet.isp", "$.isp_name"])
        where = ["received_at >= ?", "received_at < ?"]
        params = [start_dt.isoformat(), end_dt.isoformat()]
        if machine_id:
            where.append("machine_id = ?")
            params.append(machine_id)
        with DB_LOCK, db_connect() as con:
            try:
                con.execute("CREATE INDEX IF NOT EXISTS idx_rf3_hb_time ON heartbeats(received_at)")
                con.execute("CREATE INDEX IF NOT EXISTS idx_rf3_hb_machine_time ON heartbeats(machine_id, received_at)")
            except Exception:
                pass
            sql = """
                SELECT machine_id, substr(received_at,1,10) AS day,
                       COALESCE(MAX(NULLIF(hostname,'')), machine_id) AS hostname,
                       COUNT(*) AS heartbeat_count,
                       MAX(%s) AS download_gb,
                       MAX(%s) AS upload_gb,
                       MAX(%s) AS max_down_mbps,
                       MAX(%s) AS max_up_mbps,
                       MAX(%s) AS primary_ip,
                       MAX(%s) AS public_ip,
                       MAX(%s) AS isp_name,
                       MAX(received_at) AS last_seen
                FROM heartbeats WHERE %s
                GROUP BY machine_id, day
                ORDER BY day DESC, hostname ASC
                LIMIT 100000
            """ % (down_expr, up_expr, cur_down_expr, cur_up_expr, primary_ip_expr, public_ip_expr, isp_expr, " AND ".join(where))
            rows = [dict(r) for r in con.execute(sql, params).fetchall()]
        machine_map = {}
        daily_map = {}
        for r in rows:
            mid = str(r.get("machine_id") or "")
            day = str(r.get("day") or "")
            down = _rf3_to_float(r.get("download_gb"))
            up = _rf3_to_float(r.get("upload_gb"))
            hbc = int(_rf3_to_float(r.get("heartbeat_count")))
            md = _rf3_to_float(r.get("max_down_mbps"))
            mu = _rf3_to_float(r.get("max_up_mbps"))
            m = machine_map.setdefault(mid, {"machine_id": mid, "hostname": str(r.get("hostname") or mid), "primary_ip":"", "public_ip":"", "isp_name":"", "days":0, "heartbeat_count":0, "download_gb":0.0, "upload_gb":0.0, "total_gb":0.0, "max_down_mbps":0.0, "max_up_mbps":0.0, "last_seen":""})
            if r.get("hostname"): m["hostname"] = str(r.get("hostname"))
            if r.get("primary_ip"): m["primary_ip"] = str(r.get("primary_ip"))
            if r.get("public_ip"): m["public_ip"] = str(r.get("public_ip"))
            if r.get("isp_name"): m["isp_name"] = str(r.get("isp_name"))
            m["days"] += 1
            m["heartbeat_count"] += hbc
            m["download_gb"] += down
            m["upload_gb"] += up
            m["max_down_mbps"] = max(m["max_down_mbps"], md)
            m["max_up_mbps"] = max(m["max_up_mbps"], mu)
            if str(r.get("last_seen") or "") > str(m.get("last_seen") or ""):
                m["last_seen"] = str(r.get("last_seen") or "")
            d = daily_map.setdefault(day, {"date":day, "machines_seen":set(), "heartbeat_count":0, "download_gb":0.0, "upload_gb":0.0, "total_gb":0.0, "max_down_mbps":0.0, "max_up_mbps":0.0})
            d["machines_seen"].add(mid); d["heartbeat_count"] += hbc; d["download_gb"] += down; d["upload_gb"] += up; d["max_down_mbps"] = max(d["max_down_mbps"], md); d["max_up_mbps"] = max(d["max_up_mbps"], mu)
        machines = []
        for m in machine_map.values():
            m["download_gb"] = round(float(m["download_gb"]), 3)
            m["upload_gb"] = round(float(m["upload_gb"]), 3)
            m["total_gb"] = round(m["download_gb"] + m["upload_gb"], 3)
            m["max_down_mbps"] = round(float(m["max_down_mbps"]), 3)
            m["max_up_mbps"] = round(float(m["max_up_mbps"]), 3)
            machines.append(m)
        machines.sort(key=lambda x: x.get("total_gb", 0), reverse=True)
        daily = []
        for d in daily_map.values():
            d["machines_seen"] = len(d["machines_seen"])
            d["download_gb"] = round(float(d["download_gb"]), 3)
            d["upload_gb"] = round(float(d["upload_gb"]), 3)
            d["total_gb"] = round(d["download_gb"] + d["upload_gb"], 3)
            d["max_down_mbps"] = round(float(d["max_down_mbps"]), 3)
            d["max_up_mbps"] = round(float(d["max_up_mbps"]), 3)
            daily.append(d)
        daily.sort(key=lambda x: x.get("date", ""), reverse=True)
        return {"ok": True, "source":"real_fix_v3_fast_sql", "date_from": start_dt.date().isoformat(), "date_to": (end_dt.date() - _rf3_dt.timedelta(days=1)).isoformat(), "machine_id": machine_id, "machines": machines, "daily": daily, "count": len(machines), "daily_count": len(daily), "generated_at": now_iso()}

    def _rf3_read_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            return _rf3_json.loads(raw.decode("utf-8-sig", errors="replace") or "{}")
        except Exception:
            return {}

    def _rf3_hw_cols():
        return ["sr_no","tagname_hostname","room_location","person_allocated_to","assets_type","oem_name","model_no","serial_no","configuration","vendor_name","po_invoice_bill_no","bill_path_google_drive_path","purchase_date","warranty_start_date","warranty_end_date","warranty_status","status","remark","source_sheet","source_row","original_section"]

    def _rf3_sw_cols():
        return ["category","name","version","publisher","install_date","owner","license_key","license_expiry","machine_name","machine_id","ip","source","status","remark"]

    def _rf3_ensure_table(con, table, cols):
        con.execute("CREATE TABLE IF NOT EXISTS " + table + " (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, updated_at TEXT)")
        existing = {r[1] for r in con.execute("PRAGMA table_info(" + table + ")").fetchall()}
        for c in cols:
            if c not in existing:
                con.execute("ALTER TABLE " + table + " ADD COLUMN " + c + " TEXT")
        return cols

    def _rf3_save_rows(table, cols, body):
        rows = body.get("rows")
        if rows is None:
            one = body.get("row") or body
            rows = [one]
        if not isinstance(rows, list):
            rows = []
        now = now_iso()
        saved = 0
        with DB_LOCK, db_connect() as con:
            _rf3_ensure_table(con, table, cols)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                # Skip fully empty rows.
                if not any(str(row.get(c, "") or "").strip() for c in cols):
                    continue
                values = [str(row.get(c, "") or "") for c in cols]
                rid = str(row.get("id", "") or "").strip()
                if rid.isdigit():
                    set_sql = ",".join([c + "=?" for c in cols])
                    con.execute("UPDATE " + table + " SET updated_at=?, " + set_sql + " WHERE id=?", [now] + values + [int(rid)])
                    saved += 1
                else:
                    placeholders = ",".join(["?"] * (len(cols) + 2))
                    con.execute("INSERT INTO " + table + "(created_at, updated_at, " + ",".join(cols) + ") VALUES (" + placeholders + ")", [now, now] + values)
                    saved += 1
            con.commit()
            total = con.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
        return {"ok": True, "saved": saved, "total": total, "table": table}

    _RF3_OLD_GET = Handler.do_GET
    _RF3_OLD_POST = Handler.do_POST

    def _rf3_get(self):
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/history-usage-fast":
                if not self.require_auth(path, "GET"):
                    return
                return self.send_json(_rf3_history_usage_fast(self.path))
            if path in {"/api/hardware-inventory-save", "/api/software-inventory-save"}:
                return self.send_json({"ok": False, "error": "GET save disabled for security. Use POST.", "real_fix_v3": True}, 405)
            return _RF3_OLD_GET(self)
        except Exception as e:
            return self.send_json({"ok": False, "error": str(e), "real_fix_v3": True}, 500)

    def _rf3_post(self):
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/hardware-inventory-save":
                if not self.require_admin():
                    return
                return self.send_json(_rf3_save_rows("hardware_inventory", _rf3_hw_cols(), _rf3_read_body(self)))
            if path == "/api/software-inventory-save":
                if not self.require_admin():
                    return
                return self.send_json(_rf3_save_rows("software_inventory", _rf3_sw_cols(), _rf3_read_body(self)))
            return _RF3_OLD_POST(self)
        except Exception as e:
            return self.send_json({"ok": False, "error": str(e), "real_fix_v3": True}, 500)

    Handler.do_GET = _rf3_get
    Handler.do_POST = _rf3_post
    print("REAL_FIX_V3_LOADED")
except Exception as _rf3_e:
    print("REAL_FIX_V3_FAILED", _rf3_e)
# REAL_FIX_V3_END

# === MAIN_2278_RETENTION_MANAGER_START ===
try:
    import os as _ret_os, json as _ret_json, sqlite3 as _ret_sqlite3, subprocess as _ret_subprocess, datetime as _ret_dt
    from pathlib import Path as _ret_Path
    import urllib.parse as _ret_urlparse

    _RET_BASE = BASE_DIR if "BASE_DIR" in globals() else _ret_Path(__file__).resolve().parent
    _RET_DATA = _RET_BASE / "data"
    _RET_SETTINGS = _RET_DATA / "retention_settings.json"
    _RET_DB = _RET_DATA / "monitor.db"

    def _ret_s(v):
        return "" if v is None else str(v).strip()

    def _ret_load_settings():
        try:
            if _RET_SETTINGS.exists():
                obj = _ret_json.loads(_RET_SETTINGS.read_text(encoding="utf-8-sig"))
                if isinstance(obj, dict):
                    obj["keep_days"] = int(obj.get("keep_days") or 5)
                    return obj
        except Exception:
            pass
        return {"keep_days": 5}

    def _ret_save_settings(obj):
        keep = int(obj.get("keep_days") or 5)
        if keep < 1: keep = 1
        if keep > 365: keep = 365
        out = {"keep_days": keep, "updated_at": _ret_dt.datetime.now(_ret_dt.timezone.utc).isoformat()}
        _RET_SETTINGS.write_text(_ret_json.dumps(out, indent=2), encoding="utf-8")
        return out

    def _ret_drive_free_bytes(path):
        try:
            import shutil as _ret_shutil
            return _ret_shutil.disk_usage(str(path)).free
        except Exception:
            return 0

    def _ret_table_count(cur, table, col, cutoff):
        try:
            total = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            old = cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} < ?", (cutoff,)).fetchone()[0]
            newest = cur.execute(f"SELECT MAX({col}) FROM {table}").fetchone()[0]
            return {"total": total, "older_than_keep_days": old, "newest": newest}
        except Exception as e:
            return {"error": str(e)}

    def _ret_status():
        settings = _ret_load_settings()
        keep = int(settings.get("keep_days") or 5)
        cutoff = (_ret_dt.datetime.now(_ret_dt.timezone.utc) - _ret_dt.timedelta(days=keep)).isoformat()
        out = {"ok": True, "settings": settings, "db": str(_RET_DB), "cutoff_utc": cutoff}
        try:
            out["db_size_gb"] = round(_RET_DB.stat().st_size / 1024 / 1024 / 1024, 2)
        except Exception:
            out["db_size_gb"] = 0
        out["db_drive_free_gb"] = round(_ret_drive_free_bytes(_RET_DB.parent) / 1024 / 1024 / 1024, 2)
        out["old_rows"] = {}
        try:
            con = _ret_sqlite3.connect("file:" + str(_RET_DB) + "?mode=ro", uri=True, timeout=20)
            cur = con.cursor()
            page_size = cur.execute("PRAGMA page_size").fetchone()[0]
            freelist = cur.execute("PRAGMA freelist_count").fetchone()[0]
            internal_free = page_size * freelist
            physical = _RET_DB.stat().st_size
            out["sqlite_internal_free_gb"] = round(internal_free / 1024 / 1024 / 1024, 2)
            out["estimated_compact_db_gb"] = round((physical - internal_free) / 1024 / 1024 / 1024, 2)
            out["old_rows"]["heartbeats"] = _ret_table_count(cur, "heartbeats", "received_at", cutoff).get("older_than_keep_days", 0)
            out["tables"] = {
                "heartbeats": _ret_table_count(cur, "heartbeats", "received_at", cutoff),
                "notifications": _ret_table_count(cur, "notifications", "created_at", cutoff),
                "change_events": _ret_table_count(cur, "change_events", "created_at", cutoff),
                "client_messages": _ret_table_count(cur, "client_messages", "created_at", cutoff),
                "client_message_receipts": _ret_table_count(cur, "client_message_receipts", "delivered_at", cutoff),
            }
            out["newest_heartbeat"] = out["tables"]["heartbeats"].get("newest")
            con.close()
        except Exception as e:
            out["status_error"] = str(e)
        return out

    _RET_OLD_GET = Handler.do_GET
    _RET_OLD_POST = Handler.do_POST

    def _ret_read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        return _ret_json.loads(raw.decode("utf-8-sig") or "{}")

    def _ret_get(self):
        try:
            path = self.path.split("?", 1)[0]
            if path == "/api/retention/status":
                return self.send_json(_ret_status())
            if path == "/api/retention/settings":
                return self.send_json({"ok": True, "settings": _ret_load_settings()})
            return _RET_OLD_GET(self)
        except Exception as e:
            return self.send_json({"ok": False, "error": str(e)}, 500)

    def _ret_post(self):
        try:
            path = self.path.split("?", 1)[0]
            if path == "/api/retention/settings":
                body = _ret_read_body(self)
                return self.send_json({"ok": True, "settings": _ret_save_settings(body)})
            if path == "/api/retention/run-incremental-backup":
                ps1 = str(_RET_BASE / "scripts" / "INCREMENTAL_SOURCE_BACKUP_MAIN_2278.ps1")
                cp = _ret_subprocess.run(["powershell.exe","-ExecutionPolicy","Bypass","-File",ps1,"-App",str(_RET_BASE)], capture_output=True, text=True, timeout=300)
                return self.send_json({"ok": cp.returncode == 0, "returncode": cp.returncode, "stdout": cp.stdout[-4000:], "stderr": cp.stderr[-4000:]})
            return _RET_OLD_POST(self)
        except Exception as e:
            return self.send_json({"ok": False, "error": str(e)}, 500)

    Handler.do_GET = _ret_get
    Handler.do_POST = _ret_post
    print("MAIN_2278_RETENTION_MANAGER_LOADED")
except Exception as _ret_e:
    print("MAIN_2278_RETENTION_MANAGER_FAILED", _ret_e)
# === MAIN_2278_RETENTION_MANAGER_END ===



# DB_COMPACT_NO_REPEATED_HEARTBEATS_V1_START
try:
    import json as _dbc_json
    import datetime as _dbc_dt

    _DBC_SETTINGS_FILE = DATA_DIR / "db_compact_settings.json"

    def _dbc_load_settings():
        default = {"enabled": True, "heartbeat_min_seconds": 900, "traffic_delta_gb": 0.02, "compact_history_payload": True}
        try:
            if _DBC_SETTINGS_FILE.exists():
                obj = _dbc_json.loads(_DBC_SETTINGS_FILE.read_text(encoding="utf-8-sig"))
                if isinstance(obj, dict):
                    default.update(obj)
        except Exception:
            pass
        try:
            default["heartbeat_min_seconds"] = max(60, min(int(default.get("heartbeat_min_seconds") or 900), 86400))
        except Exception:
            default["heartbeat_min_seconds"] = 900
        try:
            default["traffic_delta_gb"] = max(0.001, float(default.get("traffic_delta_gb") or 0.02))
        except Exception:
            default["traffic_delta_gb"] = 0.02
        default["enabled"] = bool(default.get("enabled", True))
        default["compact_history_payload"] = bool(default.get("compact_history_payload", True))
        return default

    def _dbc_ts(v):
        try:
            return _dbc_dt.datetime.fromisoformat(str(v or "").replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    def _dbc_num(v):
        try:
            if v is None or v == "":
                return 0.0
            return float(v)
        except Exception:
            return 0.0

    def _dbc_changed_text(a, b):
        return str(a or "").strip() != str(b or "").strip()

    def _dbc_should_store_history(con, summary, previous_summary, now_iso_value, settings):
        if not settings.get("enabled", True):
            return True, "compact_disabled"
        if not previous_summary:
            return True, "first_seen"

        mid = summary.get("machine_id") or ""
        last = None
        try:
            row = con.execute("SELECT received_at FROM heartbeats WHERE machine_id=? ORDER BY id DESC LIMIT 1", (mid,)).fetchone()
            if row:
                last = row["received_at"] if hasattr(row, "keys") else row[0]
        except Exception:
            last = None

        if not last:
            return True, "first_history_sample"

        age = max(0, _dbc_ts(now_iso_value) - _dbc_ts(last))
        if age >= int(settings.get("heartbeat_min_seconds") or 900):
            return True, "time_sample"

        down_delta = abs(_dbc_num(summary.get("today_download_gb")) - _dbc_num(previous_summary.get("today_download_gb")))
        up_delta = abs(_dbc_num(summary.get("today_upload_gb")) - _dbc_num(previous_summary.get("today_upload_gb")))
        if (down_delta + up_delta) >= float(settings.get("traffic_delta_gb") or 0.02):
            return True, "traffic_delta"

        for f in ["traffic_date", "primary_ip", "public_ip", "isp_name", "vpn_active", "usb_count", "software_count"]:
            if _dbc_changed_text(summary.get(f), previous_summary.get(f)):
                return True, "changed_" + f

        return False, "repeated_skipped"

    def _dbc_small_list_count(n, limit=300):
        try:
            n = int(n or 0)
        except Exception:
            n = 0
        n = max(0, min(n, limit))
        return [{} for _ in range(n)]

    def _dbc_compact_history_payload(summary, payload):
        try:
            p = payload if isinstance(payload, dict) else {}
            disks = []
            try:
                raw_disks = listify(get_nested(p, ["storage.disks", "disks"], []))
                for d in raw_disks[:20]:
                    if isinstance(d, dict):
                        disks.append({
                            "mount": clean_str(d.get("mount") or d.get("name") or d.get("drive")),
                            "used_percent": to_float(d.get("used_percent") or d.get("usage_percent"), 0)
                        })
            except Exception:
                disks = []
            return {
                "identity": {"hostname": summary.get("hostname") or "", "machine_id": summary.get("machine_id") or ""},
                "os": {"name": summary.get("os") or ""},
                "network": {
                    "primary_ip": summary.get("primary_ip") or "",
                    "public_internet": {"public_ip": summary.get("public_ip") or "", "isp": summary.get("isp_name") or ""},
                    "traffic": {
                        "today_download_gb": _dbc_num(summary.get("today_download_gb")),
                        "today_upload_gb": _dbc_num(summary.get("today_upload_gb")),
                        "current_download_mbps": _dbc_num(summary.get("wan_download_mbps")),
                        "current_upload_mbps": _dbc_num(summary.get("wan_upload_mbps")),
                        "date": summary.get("traffic_date") or ""
                    },
                    "vpn": {"active": bool(summary.get("vpn_active"))}
                },
                "hardware": {
                    "cpu": {"usage_percent": _dbc_num(summary.get("cpu_percent")), "temperature_c": summary.get("cpu_temp_c")},
                    "memory": {
                        "used_percent": _dbc_num(summary.get("ram_percent")),
                        "total_gb": _dbc_num(summary.get("ram_total_gb")),
                        "used_gb": _dbc_num(summary.get("ram_used_gb")),
                        "free_gb": _dbc_num(summary.get("ram_free_gb"))
                    },
                    "gpus": [{"name": n} for n in (summary.get("gpu_names") or [])[:20]]
                },
                "storage": {"disks": disks},
                "software": {"installed": _dbc_small_list_count(summary.get("software_count"), 500)},
                "usb": {"devices": _dbc_small_list_count(summary.get("usb_count"), 100)}
            }
        except Exception:
            return payload if isinstance(payload, dict) else {}

    _DBC_OLD_UPSERT_HEARTBEAT = upsert_heartbeat

    def upsert_heartbeat(payload: Dict[str, Any], client_ip: str) -> Dict[str, Any]:
        settings = _dbc_load_settings()
        payload = normalize_payload_inplace(payload)
        if not isinstance(payload.get("network"), dict):
            payload["network"] = {}
        if not payload["network"].get("receiver_seen_ip"):
            payload["network"]["receiver_seen_ip"] = client_ip

        summary = summarize_payload(payload)
        received_at = now_iso()
        history_saved = False
        history_reason = "not_checked"

        with DB_LOCK, db_connect() as con:
            cleanup_duplicate_latest_rows(con, summary, payload)
            previous_summary = {}
            try:
                old = con.execute("SELECT summary_json FROM latest WHERE machine_id=?", (summary["machine_id"],)).fetchone()
                if old:
                    previous_summary = safe_json_loads(old["summary_json"], {})
                    if not isinstance(previous_summary, dict):
                        previous_summary = {}
            except Exception:
                previous_summary = {}

            history_saved, history_reason = _dbc_should_store_history(con, summary, previous_summary, received_at, settings)

            if history_saved:
                history_payload = _dbc_compact_history_payload(summary, payload) if settings.get("compact_history_payload", True) else payload
                con.execute("INSERT INTO heartbeats(machine_id,received_at,hostname,payload_json) VALUES(?,?,?,?)",
                            (summary["machine_id"], received_at, summary.get("hostname", ""), _dbc_json.dumps(history_payload, ensure_ascii=False, separators=(",", ":"))))

            con.execute("""INSERT OR REPLACE INTO latest(machine_id,hostname,id_source,id_value,updated_at,summary_json,payload_json)
                VALUES(?,?,?,?,?,?,?)""",
                (summary["machine_id"], summary.get("hostname", ""), summary.get("id_source", ""), summary.get("id_value", ""), received_at,
                 _dbc_json.dumps(summary, ensure_ascii=False, separators=(",", ":")), _dbc_json.dumps(payload, ensure_ascii=False, separators=(",", ":"))))

            pending_messages = take_pending_messages(con, summary["machine_id"], summary.get("hostname", ""))
            con.commit()

        evaluate_notifications(summary)
        try:
            _sk_enrich_notification_metrics(summary, payload)
        except Exception:
            pass
        process_change_events(summary, payload)

        return {"ok": True, "machine_id": summary["machine_id"], "id_source": summary["id_source"], "received_at": received_at, "changes_received": len(payload.get("changes") or []), "pending_messages": pending_messages, "history_saved": bool(history_saved), "history_reason": history_reason, "db_compact": "enabled"}

    print("DB_COMPACT_NO_REPEATED_HEARTBEATS_V1_LOADED")
except Exception as _dbc_e:
    print("DB_COMPACT_NO_REPEATED_HEARTBEATS_V1_FAILED", _dbc_e)
# DB_COMPACT_NO_REPEATED_HEARTBEATS_V1_END





# FINAL_ONE_SEARCH_INVENTORY_NOTIFICATION_CLIENT_V4_START
try:
    import json as _f4_json
    import datetime as _f4_dt
    import re as _f4_re

    _F4_HW_DEFAULT_COLS = ["sr_no","tagname_hostname","room_location","person_allocated_to","assets_type","oem_name","model_no","serial_no","configuration","vendor_name","po_invoice_bill_no","bill_path_google_drive_path","purchase_date","warranty_start_date","warranty_end_date","warranty_status","status","remark","source_sheet","source_row","original_section","live_sync_status","live_match_score","live_hostname","live_ip","last_seen"]
    _F4_SW_DEFAULT_COLS = ["software_name","category","login_url","username","password_value","license_key","mfa_recovery","machine_asset","allocated_to","vendor_name","po_invoice_bill_no","bill_path_google_drive_path","purchase_date","renewal_expiry_date","status","notes"]

    def _f4_col(name):
        s = _f4_re.sub(r"[^A-Za-z0-9_]+", "_", str(name or "").strip().lower()).strip("_")
        if not s:
            s = "field"
        if s[0].isdigit():
            s = "f_" + s
        return s[:60]

    def _f4_norm_row(row):
        out = {}
        if not isinstance(row, dict):
            return out
        alias = {"name":"software_name", "display_name":"software_name", "asset":"tagname_hostname", "tag":"tagname_hostname"}
        for k, v in row.items():
            ck = _f4_col(alias.get(str(k), k))
            if ck == "id":
                out[ck] = str(v or "").strip()
            else:
                out[ck] = "" if v is None else str(v)
        return out

    def _f4_extract_rows(data):
        if not isinstance(data, dict):
            return []
        if isinstance(data.get("row"), dict):
            return [_f4_norm_row(data.get("row"))]
        rows = data.get("rows") or data.get("items") or data.get("data")
        if isinstance(rows, list):
            return [_f4_norm_row(r) for r in rows if isinstance(r, dict)]
        if any(k for k in data.keys() if k not in {"mode","action","ok"}):
            return [_f4_norm_row(data)]
        return []

    def _f4_read_body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            return _f4_json.loads((raw or b"{}").decode("utf-8-sig", errors="replace") or "{}")
        except Exception:
            return {}

    def _f4_ensure_table(con, table, default_cols, rows):
        con.execute("CREATE TABLE IF NOT EXISTS " + table + " (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, updated_at TEXT)")
        existing = {r[1] for r in con.execute("PRAGMA table_info(" + table + ")").fetchall()}
        cols = []
        for c in default_cols:
            cc = _f4_col(c)
            if cc != "id" and cc not in cols:
                cols.append(cc)
        for row in rows:
            for k in row.keys():
                ck = _f4_col(k)
                if ck != "id" and ck not in cols:
                    cols.append(ck)
        for c in cols:
            if c not in existing:
                con.execute("ALTER TABLE " + table + " ADD COLUMN " + c + " TEXT")
                existing.add(c)
        return cols

    def _f4_save_inventory(table, default_cols, data):
        rows = _f4_extract_rows(data)
        if not rows:
            return {"ok": False, "error":"No row data received", "saved":0, "table":table, "final_v4":True}
        with DB_LOCK, db_connect() as con:
            cols = _f4_ensure_table(con, table, default_cols, rows)
            now = _f4_dt.datetime.now(_f4_dt.timezone.utc).isoformat()
            saved = 0
            for row in rows:
                row_id = str(row.get("id") or "").strip()
                vals = {c: row.get(c, "") for c in cols}
                if row_id and con.execute("SELECT id FROM " + table + " WHERE id=?", (row_id,)).fetchone():
                    set_sql = ",".join([c + "=?" for c in cols]) + ",updated_at=?"
                    con.execute("UPDATE " + table + " SET " + set_sql + " WHERE id=?", list(vals.values()) + [now, int(row_id)])
                else:
                    insert_cols = ["created_at", "updated_at"] + cols
                    qs = ",".join(["?"] * len(insert_cols))
                    con.execute("INSERT INTO " + table + "(" + ",".join(insert_cols) + ") VALUES(" + qs + ")", [now, now] + list(vals.values()))
                saved += 1
            con.commit()
        return {"ok": True, "saved": saved, "table": table, "final_v4": True}

    def _f4_enrich(summary):
        try:
            cpu = to_float(summary.get("cpu_percent"), None)
            ram = to_float(summary.get("ram_percent"), None)
            gpu_usage = to_float(summary.get("gpu_max_usage"), None)
            cpu_temp = to_float(summary.get("cpu_temp_c"), None)
            gpu_temp = to_float(summary.get("gpu_max_temp_c"), None)
            if cpu is not None and ram is not None:
                summary["cpu_ram_combined_percent"] = min(cpu, ram)
                summary["cpu_ram_peak_percent"] = max(cpu, ram)
            if cpu_temp is not None and gpu_temp is not None:
                summary["cpu_gpu_temp_combined_c"] = min(cpu_temp, gpu_temp)
                summary["cpu_gpu_temp_peak_c"] = max(cpu_temp, gpu_temp)
            if ram is not None and gpu_usage is not None:
                summary["ram_gpu_usage_combined_percent"] = min(ram, gpu_usage)
                summary["ram_gpu_usage_peak_percent"] = max(ram, gpu_usage)
        except Exception:
            pass
        return summary

    _F4_OLD_POST = Handler.do_POST
    _F4_OLD_GET = Handler.do_GET

    def _f4_post(self):
        try:
            path = self.path.split("?", 1)[0]
            if path == "/api/hardware-inventory-save":
                if not self.require_admin(): return
                return self.send_json(_f4_save_inventory("hardware_inventory", _F4_HW_DEFAULT_COLS, _f4_read_body(self)))
            if path == "/api/software-inventory-save":
                if not self.require_admin(): return
                return self.send_json(_f4_save_inventory("software_inventory", _F4_SW_DEFAULT_COLS, _f4_read_body(self)))
            return _F4_OLD_POST(self)
        except Exception as e:
            return self.send_json({"ok": False, "error": str(e), "final_v4": True}, 500)

    def _f4_get(self):
        try:
            path = self.path.split("?", 1)[0]
            if path in ("/api/hardware-inventory-save", "/api/software-inventory-save"):
                return self.send_json({"ok": False, "error":"POST required. GET save is blocked for security.", "final_v4": True}, 405)
            return _F4_OLD_GET(self)
        except Exception as e:
            return self.send_json({"ok": False, "error": str(e), "final_v4": True}, 500)

    Handler.do_POST = _f4_post
    Handler.do_GET = _f4_get

    try:
        _F4_OLD_EVALUATE = evaluate_notifications
        def evaluate_notifications(summary):
            return _F4_OLD_EVALUATE(_f4_enrich(summary if isinstance(summary, dict) else {}))
    except Exception:
        pass

    print("FINAL_ONE_SEARCH_INVENTORY_NOTIFICATION_CLIENT_V4_LOADED")
except Exception as _f4_e:
    print("FINAL_ONE_SEARCH_INVENTORY_NOTIFICATION_CLIENT_V4_FAILED", _f4_e)
# FINAL_ONE_SEARCH_INVENTORY_NOTIFICATION_CLIENT_V4_END

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=2278)
    args = parser.parse_args()
    init_db()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"{APP_NAME} running: http://{args.host}:{args.port}")
    print("Default admin password: " + DEFAULT_ADMIN_PASSWORD + "  (change it from UI after login)")
    print(f"Open dashboard from server: http://localhost:{args.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Stopped")

if __name__ == "__main__":
    main()




