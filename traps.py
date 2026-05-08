import re
from collections import Counter
from urllib.parse import parse_qsl, urlparse


PATH_TRAP_SEGMENTS = {
    "calendar",
    "login",
    "logout",
    "wp-login",
    "search",
    "share",
    "print",
    "feed"
}

QUERY_TRAP_KEYS = {
    "ical",
    "eventdate",
    "date",
    "month",
    "year",
    "reply",
    "replytocom",
    "sort",
    "orderby",
    "order",
    "filter",
    "search",
    "query",
    "session",
    "sid",
    "phpsessid",
    "login",
    "logout",
    "wp-login",
    "share",
    "print",
    "feed"
}



def check_url_traps(url):
    """
    Check if an URL is a trap
    Return a reason string for traps
    otherwise return None

    Also, we want to trace the reason why a URL is a trap
    so we can use it to check if we banned a URL that should not be banned
    that's why when a url is detected as a trap, we return the reason
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    query_pairs = parse_qsl(parsed.query, keep_blank_values=False)
    query_keys = {key.lower() for key, _ in query_pairs}

    trap_handlers = (
        _handle_trap_malformed_embedded_url,
        _handle_trap_generic_query_or_path,
        _handle_trap_url_length,
        _handle_trap_path_depth,
        _handle_trap_large_pagination,
        _handle_trap_query_fanout,
        _handle_trap_repeated_path,
        _handle_trap_directory_listing_sort,
        _handle_trap_wiki_attachment,
        _handle_trap_doku_php,
        _handle_trap_dokuwiki_media_endpoint,
        _handle_trap_format_query,
        _handle_trap_image_query_value,
        _handle_trap_event_archive,
        _handle_trap_grape_wiki_revision,
        _handle_trap_grape_timeline,
        _handle_trap_wics_events,
        _handle_trap_helpdesk_ticket,
    )

    for handler in trap_handlers:
        reason = handler(url, parsed, host, path, query_pairs, query_keys)
        if reason:
            return reason
    
    return None



def has_repeated_path_segments(path):
    """
    Check if a path has repeated segments
    If a URL has more than 3 repeated segments, we think it is a trap
    """
    segments = [segment for segment in path.lower().split("/") if segment]
    counts = Counter(segments)
    return any(count >= 3 for count in counts.values())



def has_event_archive_date(path, query_pairs):
    """
    Check if a path has an event archive date
    If a URL has an event archive date, we think it is a trap
    """
    # Check if the path has an events segment
    segments = [segment for segment in path.lower().split("/") if segment]
    if "events" not in segments:
        return False

    # Check if the path has a day segment
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for index, segment in enumerate(segments):
        if segment == "day" and index + 1 < len(segments):
            if date_pattern.match(segments[index + 1]):
                return True

    # Check if the path has an events segment
    if len(segments) >= 2 and segments[-2] == "events":
        if date_pattern.match(segments[-1]):
            return True

    # Check if the path has an archive segment
    archive_segments = {"month", "week", "list", "today"}
    if any(segment in archive_segments for segment in segments):
        return True

    # Also, if a url end with a date query, we think it is a trap
    date_query_keys = {
        "date",
        "day",
        "month",
        "year",
        "tribe-bar-date",
        "eventdate",
        "eventdisplay",
    }
    for key, value in query_pairs:
        if key.lower() in date_query_keys and re.search(r"\d{4}", value):
            return True

    return False



def has_directory_listing_sort_query(query_pairs):
    """
    Check if a query has a directory listing sort query
    If a URL has a directory listing sort query, we think it is a trap
    """
    for key, value in query_pairs:
        if key.lower() == "c" and re.fullmatch(r"[dmns];o=[ad]", value.lower()):
            return True
    
    return False



def has_large_pagination(parsed, query_pairs):
    """
    Check if a URL has a large pagination
    If a URL has a large pagination, we think it is a trap
    """
    segments = [segment.lower() for segment in parsed.path.split("/") if segment]
    for index, segment in enumerate(segments[:-1]):
        if segment == "page" and segments[index + 1].isdigit():
            if int(segments[index + 1]) > 1000:
                return True

    for key, value in query_pairs:
        if key.lower() == "page" and value.isdigit():
            if int(value) > 1000:
                return True

    return False



def _handle_trap_malformed_embedded_url(url, parsed, host, path, query_pairs, query_keys):
    """
    Reject bad relative links that accidentally embed another URL in the path.
    This happens when we find a log:
    [2026-04-30 08:48:50] Crawling: https://isg.ics.uci.edu/demo video: https:/www.youtube.com/watch?v=2gfPUZNsoBs
    """
    if re.search(r"https?:/{1,2}", path):
        return "malformed_embedded_url"

    return None



def _handle_trap_generic_query_or_path(url, parsed, host, path, query_pairs, query_keys):
    """
    Avoid common generated pages such as search, sort, login, feeds.
    """
    path_segments = {segment for segment in path.split("/") if segment}
    for segment in PATH_TRAP_SEGMENTS:
        if segment in path_segments:
            return f"trap_keyword:{segment}"

    for key in query_keys:
        if key in QUERY_TRAP_KEYS:
            return f"trap_keyword:{key}"
        
        if key.startswith("filter"):
            return "trap_keyword:filter"
        
        if key.startswith("utm_"):
            return "trap_keyword:tracking"

    return None



def _handle_trap_url_length(url, parsed, host, path, query_pairs, query_keys):
    """
    Very long URLs are usually generated paths or query traps.
    """
    if len(url) > 250:
        return "url_too_long"

    return None



def _handle_trap_path_depth(url, parsed, host, path, query_pairs, query_keys):
    """
    Very deep paths are often recursive archive or generated trees.
    """
    path_depth = len([segment for segment in parsed.path.split("/") if segment])
    if path_depth > 8:
        return "path_too_deep"

    return None



def _handle_trap_large_pagination(
    url, parsed, host, path, query_pairs, query_keys
):
    """
    Numeric page indexes above 1000 are pagination traps.
    """
    if has_large_pagination(parsed, query_pairs):
        return "trap_keyword:large_pagination"

    return None



def _handle_trap_query_fanout(url, parsed, host, path, query_pairs, query_keys):
    """
    Many query parameters often create large duplicate URL spaces.
    """
    if len(query_pairs) > 2:
        return "too_many_query_params"

    return None



def _handle_trap_repeated_path(url, parsed, host, path, query_pairs, query_keys):
    """
    Repeated path segments are a common recursive crawler trap.
    """
    if has_repeated_path_segments(parsed.path):
        return "repeated_path_segments"

    return None



def _handle_trap_directory_listing_sort(
    url, parsed, host, path, query_pairs, query_keys
):
    """
    Apache autoindex sort parameters create duplicate directory pages.
    """
    if has_directory_listing_sort_query(query_pairs):
        return "trap_keyword:directory_listing_sort"
    
    return None



def _handle_trap_wiki_attachment(url, parsed, host, path, query_pairs, query_keys):
    """
    Wiki raw attachments are downloads, not useful HTML pages.
    """
    if "raw-attachment" in path:
        return "trap_keyword:raw-attachment"
    
    return None



def _handle_trap_doku_php(url, parsed, host, path, query_pairs, query_keys):
    """
    Allow DokuWiki content pages, but reject generated action/history/export pages.
    """
    if "/doku.php" not in path:
        return None

    generated_keys = {
        "do", "rev", "idx", "sectok", "media", "image", "ns",
        "tab_files", "tab_details",
    }
    if query_keys.intersection(generated_keys):
        return "trap_keyword:dokuwiki_generated"
    return None



def _handle_trap_dokuwiki_media_endpoint(
    url, parsed, host, path, query_pairs, query_keys
):
    """
    DokuWiki media endpoints serve images/files, not useful HTML pages.
    """
    if "/lib/exe/detail.php" in path or "/lib/exe/fetch.php" in path:
        return "trap_keyword:dokuwiki_media_endpoint"
    
    return None


def _handle_trap_format_query(url, parsed, host, path, query_pairs, query_keys):
    """
    Format query parameters often request generated export views.
    """
    if "format" in query_keys:
        return "trap_keyword:format_query"
    
    return None



def _handle_trap_image_query_value(url, parsed, host, path, query_pairs, query_keys):
    """
    Query values pointing at images usually represent media detail pages.
    We do have similar checking in scraper.py but just in case we missed some, we check here again
    """
    image_extensions = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico", ".tiff",)
    for i, value in query_pairs:
        if value.lower().endswith(image_extensions):
            return "trap_keyword:image_query_value"
    
    return None



def _handle_trap_event_archive(url, parsed, host, path, query_pairs, query_keys):
    """
    Event calendars generate date/month/list archive pages.
    """
    if has_event_archive_date(path, query_pairs):
        return "trap_keyword:event_archive_date"
    
    return None



def _handle_trap_grape_wiki_revision(url, parsed, host, path, query_pairs, query_keys):
    """
    Grape wiki revision/diff/export query pages duplicate page history.
    """
    if "/wiki/public/wiki/" in path and query_keys.intersection({"action", "format", "version"}):
        return "trap_keyword:wiki_revision_query"
    
    return None



def _handle_trap_grape_timeline(url, parsed, host, path, query_pairs, query_keys):
    """
    Grape timeline URLs generate many timestamp navigation pages.
    """
    if "/wiki/public/timeline" in path:
        return "trap_keyword:wiki_timeline"
    
    return None



def _handle_trap_wics_events(url, parsed, host, path, query_pairs, query_keys):
    """
    WICS event pages are mostly calendar/archive trap pages.
    """
    if host == "wics.ics.uci.edu" and path.startswith("/events"):
        return "trap_keyword:wics_events"
    
    return None



def _handle_trap_helpdesk_ticket(url, parsed, host, path, query_pairs, query_keys):
    """
    Helpdesk ticket URLs resolve to repeated login pages.
    """
    if host == "helpdesk.ics.uci.edu" and path == "/ticket/display.html":
        if "id" in query_keys:
            return "trap_keyword:helpdesk_ticket_login"
    
    return None