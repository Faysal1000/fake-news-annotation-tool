"""
Text cleaning and similarity metrics.

Provides functions to compute word overlap, Jaccard similarity,
difflib SequenceMatcher ratio, containment similarity, and word positions.
"""

import re
import difflib

def clean_text(text):
    """
    Cleans Bengali and English text by converting to lowercase, 
    removing punctuation (including Bengali danda '।'), and splitting into words.
    """
    if not text:
        return []
    # Replace punctuation characters with spaces
    cleaned = re.sub(r'[।\.,\?!\(\)\"\'\-\:\;\@\#\$\%\^\&\*\_\+\[\]\{\}\<\>\/\\\|`~]', ' ', text.lower())
    # Split by whitespace to get words
    return [word for word in cleaned.split() if word]

def calculate_jaccard_similarity(text1, text2):
    """
    Calculates the Jaccard similarity of two texts based on word sets.
    Returns a float between 0.0 and 1.0.
    """
    words1 = set(clean_text(text1))
    words2 = set(clean_text(text2))
    if not words1 and not words2:
        return 1.0
    if not words1 or not words2:
        return 0.0
    return len(words1.intersection(words2)) / len(words1.union(words2))

def calculate_heading_similarity(head1, head2):
    """
    Calculates heading similarity using a combination of difflib SequenceMatcher 
    and Jaccard similarity.
    """
    h1 = (head1 or "").strip().lower()
    h2 = (head2 or "").strip().lower()
    if not h1 and not h2:
        return 1.0
    if not h1 or not h2:
        return 0.0
    ratio = difflib.SequenceMatcher(None, h1, h2).ratio()
    jaccard = calculate_jaccard_similarity(h1, h2)
    return max(ratio, jaccard)

def get_words_with_positions(text):
    """
    Splits text into words and returns a list of dicts with word, start, and end char positions.
    """
    if not text:
        return []
    # Match any alphanumeric sequence, ignoring standard punctuation symbols.
    pattern = r'[^\s।\.,\?!\(\)\"\'\-\:\;\@\#\$\%\^\&\*\_\+\[\]\{\}\<\>\/\\\|`~]+'
    words = []
    for match in re.finditer(pattern, text):
        words.append({
            'word': match.group(0).lower(),
            'start': match.start(),
            'end': match.end()
        })
    return words

def calculate_containment_similarity(text_a, text_b):
    """What fraction of text_a's words appear in text_b?"""
    words_a = set(clean_text(text_a))
    words_b = set(clean_text(text_b))
    if not words_a:
        return 0.0
    return len(words_a.intersection(words_b)) / len(words_a)

def find_matching_word_ranges(new_text, existing_text, n=4):
    """
    Finds character ranges in existing_text that match new_text using n-gram shingles.
    Returns a list of tuples (start_char, end_char).
    """
    words_new = [w['word'] for w in get_words_with_positions(new_text)]
    words_existing = get_words_with_positions(existing_text)
    
    if not words_new or not words_existing:
        return []
    
    # Adaptive shingle size if either text is shorter than n
    actual_n = min(n, len(words_new), len(words_existing))
    if actual_n <= 0:
        return []
        
    # Build shingles for new_text
    shingles_new = set()
    for i in range(len(words_new) - actual_n + 1):
        shingles_new.add(tuple(words_new[i:i+actual_n]))
        
    # Track which word indices in existing_text are matched
    matched_indices = set()
    for i in range(len(words_existing) - actual_n + 1):
        shingle = tuple(words_existing[i+k]['word'] for k in range(actual_n))
        if shingle in shingles_new:
            for k in range(actual_n):
                matched_indices.add(i + k)
                
    if not matched_indices:
        return []
        
    # Group consecutive matched word indices into character ranges
    ranges = []
    sorted_indices = sorted(list(matched_indices))
    
    current_start = words_existing[sorted_indices[0]]['start']
    current_end = words_existing[sorted_indices[0]]['end']
    
    for idx in sorted_indices[1:]:
        word_info = words_existing[idx]
        if word_info['start'] <= current_end + 3:  # allow small gap (punctuation/space)
            current_end = word_info['end']
        else:
            ranges.append((current_start, current_end))
            current_start = word_info['start']
            current_end = word_info['end']
            
    ranges.append((current_start, current_end))
    return ranges
