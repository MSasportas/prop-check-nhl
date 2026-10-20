"""common.py: paths, the clock, safe file writes, polite HTTP and secret scrubbing.

Everything else in scripts/ goes through this file for those five things, so there is
one place that knows where data lives, what time it is and how a key is kept out of sight.

Test / dry-run switches (environment):
  PC_NOW                 ISO time that replaces the real clock, e.g. 2026-10-11T18:26:00-04:00
  PC_DATA_DIR            use this directory instead of <repo>/data for every read and write
  PC_ODDS_FIXTURE_DIR    odds client reads saved payloads here, never the network
  PC_NHL_FIXTURE_DIR     NHL client reads saved payloads here, never the network
  PC_LINEUP_FIXTURE_DIR  lineup client reads saved pages here, never the network
"""
import gzip
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DATA = os.path.join(ROOT, "data")
CONFIG_PATH = os.path.join(ROOT, "config", "rules.json")
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"}


# ---------------------------------------------------------------- paths
def data_dir():
    return os.environ.get("PC_DATA_DIR") or REPO_DATA


def dpath(*parts):
    """A path inside the data directory (honours PC_DATA_DIR)."""
    return os.path.join(data_dir(), *parts)


# ---------------------------------------------------------------- clock (Eastern everywhere)
def now():
    raw = os.environ.get("PC_NOW")
    if raw:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ET)
        return dt.astimezone(ET).replace(microsecond=0)
    return datetime.now(ET).replace(microsecond=0)


def iso(dt):
    return dt.astimezone(ET).replace(microsecond=0).isoformat()


def parse_iso(s):
    if not s:
        return None
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ET)
    return dt.astimezone(ET)


def slate_date(at, rollover_hour=5):
    """The slate a moment belongs to: a new slate starts at 5:00 AM Eastern."""
    return (at.astimezone(ET) - timedelta(hours=rollover_hour)).date().isoformat()


def fmt_time(dt):
    """7:10 PM"""
    dt = dt.astimezone(ET)
    h = dt.hour % 12 or 12
    return "%d:%02d %s" % (h, dt.minute, "AM" if dt.hour < 12 else "PM")


def fmt_price(american):
    """Signed American price: -145, +120."""
    return ("+%d" % american) if american > 0 else ("%d" % american)


# ---------------------------------------------------------------- secrets
_SECRETS = set()


def register_secret(s):
    if s and len(s) >= 6:
        _SECRETS.add(s)


def scrub(text):
    """Replace every known key with ***. Used on anything printed or written."""
    if not isinstance(text, str):
        text = str(text)
    for s in _SECRETS:
        if s in text:
            text = text.replace(s, "***")
    return text


class _ScrubStream:
    """Wraps stdout / stderr so a key can never be printed, even by a traceback."""

    def __init__(self, inner):
        self._inner = inner

    def write(self, s):
        return self._inner.write(scrub(s) if isinstance(s, str) else s)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def install_scrubbers():
    if not isinstance(sys.stdout, _ScrubStream):
        sys.stdout = _ScrubStream(sys.stdout)
    if not isinstance(sys.stderr, _ScrubStream):
        sys.stderr = _ScrubStream(sys.stderr)


def log(msg):
    print(scrub("[%s] %s" % (fmt_time(now()), msg)), flush=True)


def short_err(e):
    """A short, key-free description of an exception for status files."""
    return scrub("%s: %s" % (type(e).__name__, e))[:160]


# ---------------------------------------------------------------- files (every write is temp + rename)
def write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_text(path, text):
    write_bytes(path, scrub(text).encode("utf-8"))


def dumps(obj, pretty=True):
    if pretty:
        return json.dumps(obj, indent=1, ensure_ascii=True) + "\n"
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)


def write_json(path, obj, pretty=True):
    write_text(path, dumps(obj, pretty))


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (ValueError, OSError):
        return default


def write_gz_json(path, obj):
    raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    import io
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:      # mtime=0: same data, same bytes
        g.write(raw)
    write_bytes(path, buf.getvalue())


def read_gz_json(path, default=None):
    try:
        with gzip.open(path, "rb") as g:
            return json.loads(g.read().decode("utf-8"))
    except FileNotFoundError:
        return default
    except (ValueError, OSError, EOFError):
        return default


def config_path():
    """config/rules.json; tests may point PC_CONFIG at a copy (never used by the timer)."""
    return os.environ.get("PC_CONFIG") or CONFIG_PATH


def load_config():
    with open(config_path(), "r", encoding="utf-8") as f:
        return json.load(f)


def gap_guard(cfg):
    """ops.gap_guard: THE live rule (TEAM.md section 4). {} when the config has none."""
    return (cfg.get("ops") or {}).get("gap_guard") or {}


def gap_guard_active(cfg, slate=None):
    """ops.gap_guard.active and the slate on or after live_from (2026-10-20, the first slate it covers). Nothing is
    shown, flagged or appended for an earlier slate."""
    p = gap_guard(cfg)
    if not p.get("active"):
        return False
    if slate and p.get("live_from") and slate < p["live_from"]:
        return False
    return True


# ---------------------------------------------------------------- HTTP (polite: timeout, 2 retries, never raises)
class Http:
    """Result of one request. ok means HTTP 200 with a body."""

    def __init__(self, status, headers, body, error=None):
        self.status, self.headers, self.body, self.error = status, headers, body, error

    @property
    def ok(self):
        return self.status == 200 and self.body is not None

    def json(self):
        try:
            return json.loads(self.body.decode("utf-8"))
        except Exception:
            return None

    def text(self):
        try:
            return self.body.decode("utf-8", "replace")
        except Exception:
            return ""


def http_get(url, timeout=25, retries=2, headers=None, retry_statuses=(500, 502, 503, 504)):
    """GET with a timeout and up to `retries` extra tries. Never raises. Never logs the URL."""
    last = Http(0, {}, None, "not tried")
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers or UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return Http(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read())
        except urllib.error.HTTPError as e:
            try:
                body = e.read()
            except Exception:
                body = b""
            last = Http(e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, body, "HTTP %d" % e.code)
            if e.code not in retry_statuses:
                return last
        except Exception as e:                       # timeouts, DNS, TLS, reset
            last = Http(0, {}, None, type(e).__name__)
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))
    return last
