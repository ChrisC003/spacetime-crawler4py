import re
from collections import defaultdict
from urllib.parse import urlparse, urljoin, urldefrag
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
from threading import RLock
import record
import similarity
from tokenizer import tokenize
from traps import check_url_traps
from utils.download import download

#frontier.py already has a thing checking if you've been to a page or not, could add a seen thing here to optimize it a bit more
seen = set() #Length of this is "unique pages" found
subdomains = {"ics.uci.edu":1, "cs.uci.edu":1, "informatics.uci.edu":1, "stat.uci.edu":1}
robot_cache = {}

crawler_config = None
politeness_waiter = None
robot_cache_lock = RLock()
robots_deny_lock = RLock()


ALLOWED_SUFFIXES = (
    "ics.uci.edu",
    "cs.uci.edu",
    "informatics.uci.edu",
    "stat.uci.edu",
)


# Some subdomain return 608 for robots.txt
# we don't know how this happens so just manually block them
ROBOTS_DENIED_HOSTS = {
    "circadiomics.ics.uci.edu",
    "cyberclub.ics.uci.edu",
    "kdd.ics.uci.edu",
    "labbie.ics.uci.edu",
    "observium.ics.uci.edu",
    "pastebin.ics.uci.edu",
    "phpmyadmin.ics.uci.edu",
}


ROBOTS_DENIED_DYNAMIC_HOSTS = set()
ROBOTS_DENIED_DYNAMIC_PATH_PREFIXES = defaultdict(set)
CONTENT_REJECTION_EXTENSIONS = {
    ".css", ".js", ".bmp", ".gif", ".jpg", ".jpeg", ".ico", ".png",
    ".tif", ".tiff", ".mid", ".mp2", ".mp3", ".mp4", ".wav", ".avi",
    ".mov", ".mpeg", ".mpg", ".m4v", ".mkv", ".ogg", ".ogv", ".pdf",
    ".ps", ".eps", ".tex", ".ppt", ".pptx", ".pps", ".ppsx", ".doc",
    ".docx", ".xls", ".xlsx", ".names", ".data", ".dat", ".exe",
    ".bz2", ".tar", ".msi", ".bin", ".7z", ".psd", ".dmg", ".iso",
    ".epub", ".dll", ".cnf", ".tgz", ".sha1", ".thmx", ".mso",
    ".arff", ".rtf", ".jar", ".csv", ".ipynb", ".rm", ".ram",
    ".smil", ".wmv", ".swf", ".wma", ".zip", ".rar", ".gz",
    ".txt", ".ipynb", ".webp", ".py", ".cpp", ".java", ".h", ".c", ".hpp"
}


def set_crawler_config(config):
    global crawler_config
    crawler_config = config


def set_politeness_waiter(waiter):
    global politeness_waiter
    politeness_waiter = waiter


def scraper(url, resp):
    links = extract_next_links(url, resp)
   # print(subdomains)
    return [link for link in links if is_valid(link)]

def extract_next_links(url, resp):
    # Implementation required.
    # url: the URL that was used to get the page
    # resp.url: the actual url of the page
    # resp.status: the status code returned by the server. 200 is OK, you got the page. Other numbers mean that there was some kind of problem.
    # resp.error: when status is not 200, you can check the error here, if needed.
    # resp.raw_response: this is where the page actually is. More specifically, the raw_response has two parts:c
    #         resp.raw_response.url: the url, again
    #         resp.raw_response.content: the content of the page!
    # Return a list with the hyperlinks (as strings) scrapped from resp.raw_response.content
    links = []

    if resp.status != 200:
        if resp.status == 608:
            register_robots_denied_from_url(url)
        record.record_fetch_result(url, resp.status)
        return links

    if not resp.raw_response or not resp.raw_response.content: #If there's no raw response content nothing
        record.record_trap(url, "empty_content", url)
        return links

    content_reason = content_type_rejection(url, resp.raw_response, resp.raw_response.content,)
    if content_reason:
        record.record_trap(url, content_reason, url)
        return links

    try:
        soup = BeautifulSoup(resp.raw_response.content, "html.parser")
    except Exception:
        record.record_trap(url, "parser_rejected_markup", url)
        return links

    for obj in soup.find_all("a", href = True):
        link = urljoin(url, obj["href"])
        link, _ = urldefrag(link)
        seen.add(link) #Once you've seen and defragged it add it into seen
        links.append(link)
        parsed = urlparse(link)

        hostname = parsed.hostname
        if hostname is None: #If not a parsable link
            continue
        else:
            hostname = hostname.lower()
            if hostname.endswith(".uci.edu"):
                subdomains[hostname] = subdomains.get(hostname, 0) + 1

    low_info_reason = low_information_reason(soup)
    if low_info_reason:
        record.record_trap(url, low_info_reason, url)
        return links

    similarity_reason = similarity.check_page_similarity(soup)
    if similarity_reason:
        record.record_trap(url, similarity_reason, url)
        return links
    
    try:
        tokenize(url, resp.raw_response.content)
    except Exception:
        record.record_trap(url, "tokenization_failed", url)
        return links

    record.save_crawled_page(url, resp.status, resp.raw_response.content, len(links))
    defrag = urldefrag(url)
    seen.add(defrag) #Add the page you just scraped, msotly for the beginning few
    return links



def is_valid(url):
    """
    Our order of decisions:

    1. URL parses as http(s) and has a hostname on the allowed UC/Irvine-style
       suffix list.
    2. Static/dynamic robots blocklists from our crawler state (not HTML yet).
    3. Reject obviously non-HTML paths via extension / URL-only heuristics
       (content_type_rejection without a response body).
    4. URL trap rules (calendar traps, query keys, etc.).
    5. Parse robots.txt from cache for this host and enforce Disallow for our
       user agent (may record a trap if disallowed).

    Tokenization, similarity, and low-information filters run later in scraper()
    after we have the page body, not here
    """
    try:
        parsed = urlparse(url)

        if parsed.hostname is None:
            return False

        if parsed.scheme not in {"http", "https"}:
            return False

        if not is_allowed_host(parsed.hostname.lower()):
            return False

        robots_deny_reason = get_robots_deny_reason(url)
        if robots_deny_reason:
            record.record_trap(url, robots_deny_reason, None)
            return False

        content_reason = content_type_rejection(url)
        if content_reason:
            record.record_trap(url, content_reason, None)
            return False

        trap_reason = check_url_traps(url)
        if trap_reason:
            record.record_trap(url, trap_reason, None)
            return False

        rp = get_robot_parser(url)
        if rp is not None:
            if rp.disallow_all: #Kinda basic robot parser
                return False
            
            user_agent = crawler_config.user_agent if crawler_config else "*"
            if not rp.can_fetch(user_agent, url):
                record.record_trap(url, "robots_disallowed", None)
                return False

        return True
    except Exception as e:
        print("Exception when checking if URL is valid", url, e)
        return False


def is_allowed_host(host):
    return any(
        host == suffix or host.endswith("." + suffix)
        for suffix in ALLOWED_SUFFIXES
    )


def is_robots_denied_host(host):
    return host in ROBOTS_DENIED_HOSTS or host in ROBOTS_DENIED_DYNAMIC_HOSTS


def normalize_block_path(path):
    normalized = path or "/"
    
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    
    if normalized != "/":
        normalized = normalized.rstrip("/")
    
    return normalized


def get_robots_deny_reason(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    if not host:
        return None

    path = normalize_block_path(parsed.path)

    if host in ROBOTS_DENIED_HOSTS:
        return "robots_denied_host_blocklist"

    with robots_deny_lock:
        if host in ROBOTS_DENIED_DYNAMIC_HOSTS:
            return "robots_denied_host_blocklist"
        
        for prefix in ROBOTS_DENIED_DYNAMIC_PATH_PREFIXES.get(host, set()):
            if path == prefix or path.startswith(prefix + "/"):
                return "robots_denied_path_blocklist"
    
    return None


def register_robots_denied_host(host):
    normalized_host = (host or "").lower()
    if not normalized_host:
        return
    
    with robots_deny_lock:
        ROBOTS_DENIED_DYNAMIC_HOSTS.add(normalized_host)


def register_robots_denied_from_url(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    
    if not host:
        return
    
    path = normalize_block_path(parsed.path)
    if path == "/":
        register_robots_denied_host(host)
        return
    
    with robots_deny_lock:
        ROBOTS_DENIED_DYNAMIC_PATH_PREFIXES[host].add(path)


def is_robots_denied_url(url):
    return get_robots_deny_reason(url) is not None


def register_robots_denied_host_from_url(url):
    register_robots_denied_from_url(url)


def content_type_rejection(url, raw_response=None, content=None):
    parsed = urlparse(url)
    path = parsed.path.lower()
    if any(path.endswith(ext) for ext in CONTENT_REJECTION_EXTENSIONS):
        return "bad_file_extension"

    if raw_response is None or content is None:
        return None

    headers = getattr(raw_response, "headers", {}) or {}
    content_type = headers.get("content-type", "").lower()
    is_html_mime = (
        "text/html" in content_type
        or "application/xhtml" in content_type
    )
    
    if is_html_mime:
        return None

    if content_type:
        return f"low_value_content_type:{content_type.split(';')[0]}"

    # Check if the content is UTF-16 encoded HTML
    # since we sometimes find some pages are UTF-16 encoded HTML and cause errors
    sample = content[:2048]
    utf16_html = (
        sample.startswith((b"\xff\xfe", b"\xfe\xff"))
        and (b"<\x00h\x00t\x00m\x00l" in sample.lower()
             or b"\x00<\x00h\x00t\x00m\x00l" in sample.lower())
    )
    if utf16_html:
        return None

    if b"\x00" in sample:
        return "binary_content"

    return None


def low_information_reason(soup):
    """
    Flag pages that are directory listings, login shells, geo blocks, or too
    little real text. Title and h1 are checked first because Apache/Nginx style
    listings announce themselves there before the body; the rest uses
    script/style-stripped text so markup chrome does not inflate word counts,
    and the same alnum token regex used elsewhere for consistency.
    """
    # Explicit metadata and first heading: cheap hints for listing/login UIs.
    title_tag = soup.title
    if title_tag is not None:
        page_title_text = title_tag.get_text(" ", strip=True)
    else:
        page_title_text = ""

    first_h1_element = soup.find("h1")
    if first_h1_element is not None:
        main_heading_text = first_h1_element.get_text(" ", strip=True)
    else:
        main_heading_text = ""

    # Body text with scripts/styles removed
    visible_page_text = page_text(soup)
    lowercase_word_tokens = re.findall(
        r"\b[a-z0-9]+\b",
        visible_page_text.lower(),
    )
    number_of_anchor_tags = len(soup.find_all("a", href=True))

    if page_title_text.lower().startswith("index of "):
        return "low_information:directory_listing"

    if main_heading_text.lower().startswith("index of "):
        return "low_information:directory_listing"

    if "access restricted - ip location block" in visible_page_text.lower():
        return "low_information:access_restricted"

    if page_title_text.strip().lower() == "login":
        return "low_information:login_page"

    login_terms = {"username", "password", "login"}
    if login_terms.issubset(set(lowercase_word_tokens)):
        return "low_information:login_template"

    if len(lowercase_word_tokens) < 20 and number_of_anchor_tags <= 5:
        return "low_information:too_few_words"

    return None


def page_text(soup):
    for tag in soup(["script", "style", "meta", "link", "noscript"]):
        tag.decompose()
    
    return soup.get_text(" ", strip=True)


def get_robot_parser(url):
    if crawler_config is None or crawler_config.cache_server is None:
        return None

    parsed = urlparse(url)
    cache_key = (parsed.scheme.lower(), parsed.netloc.lower())
    with robot_cache_lock:
        if cache_key in robot_cache:
            return robot_cache[cache_key]

    rp = RobotFileParser()
    robot_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp.set_url(robot_url)
    
    try:
        if politeness_waiter is not None:
            politeness_waiter(robot_url)
        resp = download(robot_url, crawler_config)
        
        if resp.status == 200 and resp.raw_response and resp.raw_response.content:
            text = resp.raw_response.content.decode("utf-8", errors="ignore")
            rp.parse(text.splitlines())
        elif resp.status == 608:
            register_robots_denied_host(parsed.hostname)
            rp.parse(["User-agent: *", "Disallow: /"])
        else:
            rp.parse([])
    except Exception:
        rp.parse([])
    
    with robot_cache_lock:
        robot_cache[cache_key] = rp
    
    return rp
