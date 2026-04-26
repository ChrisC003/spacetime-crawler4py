import re
from urllib.parse import urlparse, urljoin, urldefrag
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
from tokenizer import tokenize

#frontier.py already has a thing checking if you've been to a page or not, could add a seen thing here to optimize it a bit more
seen = set() #Length of this is "unique pages" found
subdomains = dict()
robot_cache = {}


def scraper(url, resp):
    #Unsure if we need to check for robots since we are operating on a cache, and there is already system code 608 for not allowed
    links = extract_next_links(url, resp)
    return [link for link in links if is_valid(link)]

#Is robots already handled by 608 since we're on a cache server?

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
        return links

    if not resp.raw_response or not resp.raw_response.content: #If there's no raw response content nothing
        return links

    soup = BeautifulSoup(resp.raw_response.content, "html.parser")


    for obj in soup.find_all("a", href = True):
        link = urljoin(url, obj["href"])
        link, _ = urldefrag(link)
        links.append(link)
	
    tokenize(url, resp.raw_response.content)

    defrag = urldefrag(url)
    seen.add(defrag) #If it's proccessed a page, it should count as being visisted ig

    if defrag in subdomains: #Keeping track of the subdomain
        subdomains[defrag] += 1
    else:
        subdomains[defrag] = 1
    
    return links

def is_valid(url):
    # Decide whether to crawl this url or not. 
    # If you decide to crawl it, return True; otherwise return False.
    # There are already some conditions that return False.
    try:
		#Need to consider traps, I know the calender for sure is one

        allowed = ("ics.uci.edu", "cs.uci.edu", "informatics.uci.edu", "stat.uci.edu")
        parsed = urlparse(url)
        if parsed.scheme not in set(["http", "https"]):
            return False

        if not any(
            parsed.hostname.lower() == domain or parsed.hostname.lower().endswith("." + domain) #Either the domain directly contains it, or it ends with the domain
            for domain in allowed
        ):
            return False
        rp = get_robot_parser(url)

		if rp is not None:

		    if rp.disallow_all: #Kinda basic robot parser
                return False
            elif not rp.can_fetch("*", url):
                return False

        return not re.match(
            r".*\.(css|js|bmp|gif|jpe?g|ico"
            + r"|png|tiff?|mid|mp2|mp3|mp4"
            + r"|wav|avi|mov|mpeg|ram|m4v|mkv|ogg|ogv|pdf"
            + r"|ps|eps|tex|ppt|pptx|doc|docx|xls|xlsx|names"
            + r"|data|dat|exe|bz2|tar|msi|bin|7z|psd|dmg|iso"
            + r"|epub|dll|cnf|tgz|sha1"
            + r"|thmx|mso|arff|rtf|jar|csv"
            + r"|rm|smil|wmv|swf|wma|zip|rar|gz)$", parsed.path.lower())

    except TypeError:
        print ("TypeError for ", parsed)
        raise

def get_robot_parser(url):
    parsed = urlparse(url)
    if parsed.hostname.lower() in robot_cache:
        return robot_cache[parsed.hostname.lower()]
    rp = RobotFileParser()
    robot_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp.set_url(robot_url)
    rp.read()
    robot_cache[parsed.hostname.lower()] = rp
    return rp
