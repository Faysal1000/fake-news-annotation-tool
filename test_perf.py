import time
import os
import sys
import csv
import concurrent.futures

sys.path.insert(0, os.path.abspath('annotator/src'))

# Load data
csv_path = "/Users/faysalahmmed/Desktop/Fake News All/dataset.csv"
if not os.path.exists(csv_path):
    print("No dataset at", csv_path)
    sys.exit(1)

records = []
with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        records.append(row)

records = records[:1000] # Use 1000 data as user suggested
print(f"Loaded {len(records)} records")

from duplicates.duplicate_engine import _evaluate_duplicate_chunk, _init_worker
from analysis.text_similarity import clean_text

global_records_data = []
global_inverted_index = {}

print("Building index...")
for idx, rec in enumerate(records):
    h = rec.get("heading", "")
    t = rec.get("text", "")
    comb = f"{h} {t}".strip()
    words_comb = set(clean_text(comb))
    words_h = set(clean_text(h))
    
    global_records_data.append({
        "idx": idx,
        "record": rec,
        "heading": h,
        "text": t,
        "combined": comb,
        "words_combined": words_comb,
        "words_heading": words_h
    })
    
    for word in words_comb:
        if word not in global_inverted_index:
            global_inverted_index[word] = []
        global_inverted_index[word].append(idx)

# Single threaded
print("Testing single-threaded...")
start = time.time()
res1 = _evaluate_duplicate_chunk((0, len(records), global_records_data, global_inverted_index, 0.6))
st_time = time.time() - start
print(f"Single-threaded found {len(res1)} pairs in {st_time:.2f}s")

# Multi threaded
print("Testing multi-threaded...")
start = time.time()
num_cores = os.cpu_count() or 4
num_chunks = 100
chunk_size = max(1, len(records) // num_chunks)

tasks = []
for start_idx in range(0, len(records), chunk_size):
    end_idx = min(start_idx + chunk_size, len(records))
    tasks.append((start_idx, end_idx, 0.6))

res2 = []
with concurrent.futures.ProcessPoolExecutor(max_workers=num_cores, initializer=_init_worker, initargs=(global_records_data, global_inverted_index)) as executor:
    futures = [executor.submit(_evaluate_duplicate_chunk, t) for t in tasks]
    for future in concurrent.futures.as_completed(futures):
        res2.extend(future.result())

mt_time = time.time() - start
print(f"Multi-threaded found {len(res2)} pairs in {mt_time:.2f}s")
print(f"Speedup: {st_time / mt_time:.2f}x")
