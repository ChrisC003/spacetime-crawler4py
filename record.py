import re
import json
from datetime import datetime
from pathlib import Path
from threading import RLock
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# This module is just used to record the crawling process
# and save the pages and state of the crawling process
# just a test helper
# very good for debugging
# we appreciate our recorder! save us a lot of time!

_pages_run_dir = None
_state_run_dir = None
_tracking_state = None
_tracking_lock = RLock()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")



def ensure_tracking_run():
    global _pages_run_dir
    global _state_run_dir
    global _tracking_state

    with _tracking_lock:
        if _pages_run_dir is not None and _state_run_dir is not None:
            return _pages_run_dir

        pages_base_dir = Path("pages")
        states_base_dir = Path("states")
        pages_base_dir.mkdir(exist_ok=True)
        states_base_dir.mkdir(exist_ok=True)

        run_id = 1
        while (
            (pages_base_dir / f"run_{run_id}").exists()
            or (states_base_dir / f"run_{run_id}").exists()
        ):
            run_id += 1

        _pages_run_dir = pages_base_dir / f"run_{run_id}"
        _state_run_dir = states_base_dir / f"run_{run_id}"
        _pages_run_dir.mkdir(parents=True, exist_ok=True)
        _state_run_dir.mkdir(parents=True, exist_ok=True)

        _tracking_state = {
            "pages_run_dir": str(_pages_run_dir),
            "state_run_dir": str(_state_run_dir),
            "started_at": now(),
            "last_saved_at": None,
            "completed": [],
            "failed": {},
            "pages": {},
            "traps": {},
        }

        _save_tracking_state()
        return _pages_run_dir



def _save_tracking_state():
    if _state_run_dir is None or _tracking_state is None:
        return
    
    _tracking_state["last_saved_at"] = now()
    state_path = _state_run_dir / "state.json"
    
    with state_path.open("w", encoding="utf-8") as state_file:
        json.dump(_tracking_state, state_file, indent=2, sort_keys=True)



def current_state_path():
    if _state_run_dir is None:
        return None

    return _state_run_dir / "state.json"



def page_filename(index, url):
    parsed = urlparse(url)
    raw = f"{parsed.netloc}{parsed.path}" or f"page_{index}"
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", raw).strip("_")
    return f"{index:05d}_{slug or f'page_{index}'}.html"



def save_crawled_page(url, status, content, allowed_links_count):
    with _tracking_lock:
        run_dir = ensure_tracking_run()
        page_index = len(_tracking_state["pages"]) + 1
        saved_path = run_dir / page_filename(page_index, url)
        saved_path.write_bytes(content)

        words = extract_words(content)
        _tracking_state["completed"].append(url)
        _tracking_state["pages"][url] = {
            "status": status,
            "word_count": len(words),
            "allowed_links": allowed_links_count,
            "saved_path": str(saved_path),
            "time": now(),
        }

        _save_tracking_state()



def extract_words(content):
    try:
        soup = BeautifulSoup(content, "html.parser")
    except Exception:
        return []

    for tag in soup(["script", "style", "meta", "link", "noscript"]):
        tag.decompose()

    text = soup.get_text(" ", strip=True)
    return re.findall(r"\b[a-z0-9]+\b", text.lower())



def record_fetch_result(url, status):
    if status == 200:
        return

    with _tracking_lock:
        ensure_tracking_run()

        _tracking_state["failed"][url] = {
            "status": status,
            "time": now(),
        }

        _save_tracking_state()



def record_trap(url, reason, source_url):
    with _tracking_lock:
        ensure_tracking_run()
        traps = _tracking_state["traps"]

        if url in traps:
            return

        traps[url] = {
            "reason": reason,
            "source": source_url,
            "time": now(),
        }

        traps_path = (
            _state_run_dir / f"traps_{_state_run_dir.name.replace('_', '')}.txt"
        )

        with traps_path.open("a", encoding="utf-8") as traps_file:
            traps_file.write(
                f"[{now()}] reason={reason} source={source_url} url={url}\n"
            )

        _save_tracking_state()
