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

    for tag in soup(["script", "style", "meta", "link", "noscript"]): #Decompose tags that aren't text related
        tag.decompose()

    base_text = soup.get_text(separator = ' ', strip = True) #Get the actual text from remaining tags
    words = re.findall(r'\b[a-z0-9]+\b', base_text.lower()) #Seperate it based off of alphanumeric English
    
    tokens = [word for word in words if (word not in stopwords and len(word) > 1)] #Must not be a stopword for a single char
   
    computeWordFrequencies(tokens) #Add to dict

    return tokens #There's not really a need to return it now that I think about it


    

def computeWordFrequencies(file_tokens):
    for word in file_tokens: #simple iteration loop
        if word in word_count:
            word_count[word] += 1
        else:
            word_count[word] = 1
    #freq_print(word_count)

def freq_print(freqCount):

    freqCount = dict(sorted(freqCount.items(), key=lambda item: (-item[1], item[0]))) #sort it by frequency (high to low) then alphabetical
    counter = 0
    for key, value in freqCount.items():
        if(counter < 10):
            print(key + " - " + str(value))
        counter += 1
