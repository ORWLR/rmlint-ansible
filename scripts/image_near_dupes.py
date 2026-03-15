#!/usr/bin/env python3
"""Find near-duplicate images using perceptual hashing.

Usage: image_near_dupes.py <threshold> <output_json> <dir> [<dir> ...]
"""
import sys
import json
from pathlib import Path

import imagehash
from PIL import Image

def _warn(msg):
    print(msg, file=sys.stderr)

EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.webp', '.heic'}


def scan(directories, threshold):
    hashes = []
    for d in directories:
        for p in Path(d).rglob('*'):
            if p.suffix.lower() not in EXTENSIONS:
                continue
            try:
                h = imagehash.phash(Image.open(p))
                hashes.append((h, str(p)))
            except Exception as exc:
                _warn(f"Skipping {p}: {exc}")
                continue

    groups = []
    used = set()
    for i, (h1, f1) in enumerate(hashes):
        if i in used:
            continue
        group = [f1]
        for j, (h2, f2) in enumerate(hashes[i + 1:], start=i + 1):
            if j in used:
                continue
            if abs(h1 - h2) <= threshold:
                group.append(f2)
                used.add(j)
        if len(group) > 1:
            used.add(i)
            groups.append({
                "type": "image_near_duplicate",
                "distance": int(threshold),
                "files": group
            })
    return groups


if __name__ == "__main__":
    threshold = int(sys.argv[1])
    output = sys.argv[2]
    dirs = sys.argv[3:]
    results = scan(dirs, threshold)
    with open(output, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Found {len(results)} near-duplicate image groups → {output}")
