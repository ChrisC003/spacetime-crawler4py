import hashlib
import re
from threading import RLock
from tokenizer import stopwords

# simhash is usually 64 bits so we just use the first 64 bits of the hash
SIMHASH_BITS = 64

# split the fingerprint into 8 bands
# we only compare a few candidates instead of every old page.
SIMHASH_BANDS = 8
SIMHASH_BAND_BITS = SIMHASH_BITS // SIMHASH_BANDS
# we first use 0.9 but too many pages was considered duplicates so we finally use 0.97
SIMHASH_THRESHOLD = 0.97
MAX_HAMMING_DISTANCE = int((1.0 - SIMHASH_THRESHOLD) * SIMHASH_BITS)

# if the page is too short, the simhash is noisy, so we justskip near-dup checks
MIN_SIMHASH_TOKENS = 50

# workers share this module
# so the sets must update together
_lock = RLock()
_exact_hashes = set()
_simhashes = set()
_band_index = {}


def check_page_similarity(soup):
    # same token idea as elsewhere in the project: lowercase alnum tokens only
    plain_text_lower = soup.get_text(" ", strip=True).lower()
    raw_alnum_tokens = re.findall(r"\b[a-z0-9]+\b", plain_text_lower)
    if len(raw_alnum_tokens) == 0:
        return None

    exact_sequence_fingerprint = _exact_hash(raw_alnum_tokens)

    filtered_words = []
    for word in raw_alnum_tokens:
        if word not in stopwords and len(word) > 1:
            filtered_words.append(word)

    simhash_fingerprint = _simhash(filtered_words)

    with _lock:
        if exact_sequence_fingerprint in _exact_hashes:
            return "similarity:exact_duplicate"

        if simhash_fingerprint is not None:
            if _is_near_duplicate(simhash_fingerprint):
                return "similarity:simhash_duplicate"

        _exact_hashes.add(exact_sequence_fingerprint)
        if simhash_fingerprint is not None:
            _add_simhash(simhash_fingerprint)

    return None


def _exact_hash(words):
    # whole word order matters for "exact" duplicate (cheap string check first)
    joined_words = " ".join(words)
    utf8_bytes = joined_words.encode("utf-8")
    hasher = hashlib.blake2b(utf8_bytes, digest_size=16)
    
    return hasher.hexdigest()



def _simhash(words):
    if len(words) < MIN_SIMHASH_TOKENS:
        return None

    # how many times each token shows up (weights the bit votes)
    token_frequencies = {}
    for word in words:
        if word in token_frequencies:
            token_frequencies[word] = token_frequencies[word] + 1
        else:
            token_frequencies[word] = 1

    bit_weight_totals = [0] * SIMHASH_BITS

    for token, weight in token_frequencies.items():
        blake_digest_bytes = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        hashed_token_bits = int.from_bytes(blake_digest_bytes, "big")
        bit_index = 0
        
        while bit_index < SIMHASH_BITS:
            if hashed_token_bits & (1 << bit_index):
                bit_weight_totals[bit_index] = bit_weight_totals[bit_index] + weight
            else:
                bit_weight_totals[bit_index] = bit_weight_totals[bit_index] - weight
            bit_index = bit_index + 1

    fingerprint = 0
    bit_position = 0
    
    while bit_position < SIMHASH_BITS:
        if bit_weight_totals[bit_position] >= 0:
            fingerprint = fingerprint | (1 << bit_position)
        
        bit_position = bit_position + 1

    return fingerprint


def _is_near_duplicate(simhash):
    # only compare fingerprints that landed in overlapping LSH buckets
    candidate_fingerprints = _candidate_simhashes(simhash)
    
    for existing_fingerprint in candidate_fingerprints:
        distance = _hamming_distance(simhash, existing_fingerprint)
        if distance <= MAX_HAMMING_DISTANCE:
            return True
    
    return False



def _hamming_distance(left_fp, right_fp):
    # count differing bits between two 64-bit simhashes
    xor_result = left_fp ^ right_fp
    differing_bits = 0
    bit_step = 0
    while bit_step < SIMHASH_BITS:
        differing_bits = differing_bits + (xor_result & 1)
        xor_result = xor_result >> 1
        bit_step = bit_step + 1
    return differing_bits


def _candidate_simhashes(simhash):
    all_candidates = set()
    band_index = 0
    
    while band_index < SIMHASH_BANDS:
        band_numeric_value = _band_value(simhash, band_index)
        bucket_key = (band_index, band_numeric_value)
        
        if bucket_key in _band_index:
            for stored_fingerprint in _band_index[bucket_key]:
                all_candidates.add(stored_fingerprint)
        
        band_index = band_index + 1
    
    return all_candidates



def _add_simhash(simhash):
    _simhashes.add(simhash)
    band_index = 0
    
    while band_index < SIMHASH_BANDS:
        band_numeric_value = _band_value(simhash, band_index)
        bucket_key = (band_index, band_numeric_value)
        
        if bucket_key not in _band_index:
            _band_index[bucket_key] = set()
        
        _band_index[bucket_key].add(simhash)
        band_index = band_index + 1



def _band_value(simhash, band_index):
    bit_offset = band_index * SIMHASH_BAND_BITS
    low_bits_mask = (1 << SIMHASH_BAND_BITS) - 1
    return (simhash >> bit_offset) & low_bits_mask