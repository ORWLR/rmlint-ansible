#!/usr/bin/env python3
"""Find near-duplicate documents using text embeddings.

Usage: doc_near_dupes.py <threshold> <output_json> <dir> [<dir> ...]

threshold is cosine similarity (0.0-1.0), e.g. 0.85
"""
import sys
import json
import subprocess
from pathlib import Path

from sentence_transformers import SentenceTransformer, util

EXTENSIONS = {'.pdf', '.txt', '.md', '.rst', '.doc', '.docx'}
MAX_CHARS = 2000


def _warn(msg):
    print(msg, file=sys.stderr)


def extract_text(path):
    if path.suffix.lower() == '.pdf':
        try:
            r = subprocess.run(
                ['pdftotext', str(path), '-'],
                capture_output=True, text=True, timeout=10
            )
            return r.stdout[:MAX_CHARS]
        except Exception as exc:
            _warn(f"Skipping {path}: {exc}")
            return ""
    else:
        try:
            return path.read_text(errors='ignore')[:MAX_CHARS]
        except Exception as exc:
            _warn(f"Skipping {path}: {exc}")
            return ""


def scan(directories, threshold):
    model = SentenceTransformer('all-MiniLM-L6-v2')
    files, texts = [], []

    for d in directories:
        for p in Path(d).rglob('*'):
            if p.suffix.lower() not in EXTENSIONS:
                continue
            text = extract_text(p)
            if len(text.strip()) < 50:
                continue
            files.append(str(p))
            texts.append(text)

    if not texts:
        return []

    embeddings = model.encode(texts, convert_to_tensor=True,
                              show_progress_bar=True)
    cosine_scores = util.cos_sim(embeddings, embeddings)

    used = set()
    groups = []
    for i in range(len(files)):
        if i in used:
            continue
        group = [files[i]]
        for j in range(i + 1, len(files)):
            if j in used:
                continue
            if float(cosine_scores[i][j]) >= threshold:
                group.append(files[j])
                used.add(j)
        if len(group) > 1:
            used.add(i)
            groups.append({
                "type": "document_near_duplicate",
                "similarity_threshold": threshold,
                "files": group
            })
    return groups


if __name__ == "__main__":
    threshold = float(sys.argv[1])
    output = sys.argv[2]
    dirs = sys.argv[3:]
    results = scan(dirs, threshold)
    with open(output, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Found {len(results)} near-duplicate document groups → {output}")
