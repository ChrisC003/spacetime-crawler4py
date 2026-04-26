import re
from urllib.parse import urlparse, urljoin, urldefrag
from bs4 import BeautifulSoup
from tokenizer import tokenize

#This could be moved into another file maybe to have control over it
visited = set()
longest_file = list() #Probably an ordered pair containing the url, and the length as the second  unit


def scraper(url, resp):
    #Unsure if we need to check for robots since we are operating on a cache, and there is already system code 608 for not allowed
    if url not in visited:
        visited.add(url)
    else: #If already visited don't visit again
        return []
    links = extract_next_links(url, resp)
    return [link for link in links if is_valid(link)]

#Is robots already handled by 608 since we're on a cache server?

def extract_next_links(url, resp):
    # Implementation required.
    # url: the URL that was used to get the page
    # resp.url: the actual url of the page
    # resp.status: the status code returned by the server. 200 is OK, you got the page. Other numbers mean that there was some kind of problem.
    # resp.error: when status is not 200, you can check the error here, if needed.
    # resp.raw_response: this is where the page actually is. More specifically, the raw_response has two parts:
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
	
    tokenize(resp.raw_response.content)

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

        if parsed.hostname not in allowed:
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
