from bs4 import BeautifulSoup
import re
word_count = {}
stopwords = {'a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 'and', 'any',
             'are', 'as', 'at', 'be', 'because', 'been', 'before', 'being', 'below', 'between', 'both',
             'but', 'by', 'can', 'could', 'did', 'do', 'does', 'doing', 'down', 'during', 'each', 'few', 
             'for', 'from', 'further', 'had', 'has', 'have', 'having', 'he', 'her', 'here', 'hers', 'herself',
             'him', 'himself', 'his', 'how', 'i', 'if', 'in', 'into', 'is', 'it', 'its', 'itself', 'just', 'me', 
             'might', 'more', 'most', 'must', 'my', 'myself', 'no', 'nor', 'not', 'now', 'of', 'off', 'on', 'once', 
             'only', 'or', 'other', 'our', 'ours', 'ourselves', 'out', 'over', 'own', 's', 'same', 'she', 'should', 
             'so', 'some', 'such', 't', 'than', 'that', 'the', 'their', 'theirs', 'them', 'themselves',
             'then', 'there', 'these', 'they', 'this', 'those', 'through', 'to', 'too', 'under', 'until', 'up', 
             'very', 'was', 'we', 'were', 'what', 'when', 'where', 'which', 'while', 'who', 'whom', 'why', 'will', 
             'with', 'would', 'you', 'your', 'yours', 'yourself', 'yourselves'}

def tokenize(fileText):
    try:
        soup = BeautifulSoup(fileText, "lxml")
    except Exception:
        soup = BeautifulSoup(fileText, "html.parser")

    for a in soup(["script", "style", "meta", "link", "noscript"]):
        script.decompose()

    base_text = soup.get_text(separator = ' ', strip = True)
    words = re.findall(r'\b[a-z0-9]+\b', text.lower())
    
    tokens = [word for word in words if word not in stopwords and len(w) > 1)
    #At this point all this does is get all the words minus the tags, doesn't account for the dict yet
    
    computeWordFrequencies(tokens)

    return tokens


    

def computeWordFrequencies():
    for word in word_count: #simple iteration loop
        if word in return_dict:
            return_dict[word] += 1
        else:
            return_dict[word] = 1

def freq_print(freqCount):

    freqCount = dict(sorted(freqCount.items(), key=lambda item: (-item[1], item[0]))) #sort it by frequency (high to low) then alphabetical

    for key, value in freqCount.items():
        print(key + " - " + str(value))
