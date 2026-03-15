# rmlint-ansible

Two-phase deduplication for ZFS filesystems:

1. **Exact duplicates** — `rmlint` with ZFS `xattr=sa` caching for fast repeated runs
2. **Near-duplicates** — perceptual hashing for images, sentence-transformer embeddings for documents

Neither playbook deletes anything. Both produce reports you review before acting.

---

## Prerequisites

- Ubuntu/Debian target host with ZFS already installed and a pool/dataset provisioned
- Ansible ≥ 2.14 on the control node
- `community.general` collection (installed via `requirements.yml`)

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/ORWLR/rmlint-ansible.git
cd rmlint-ansible

# 2. Install the required Ansible collection
ansible-galaxy collection install -r requirements.yml

# 3. Edit inventory.yml — point it at your target host(s)
#    For localhost testing, the default works as-is.

# 4. Run Playbook 1: ZFS xattr setup + rmlint exact-dupe scan
ansible-playbook rmlint_setup.yml

# 5. Run Playbook 2: near-duplicate detection (images + documents)
ansible-playbook near_dupes_setup.yml
```

---

## Configuration

### Playbook 1 — `rmlint_setup.yml`

| Variable | Default | Description |
|---|---|---|
| `zfs_dataset` | `pool/data` | ZFS dataset to configure with `xattr=sa` |
| `zfs_mountpoint` | `/pool/data` | Filesystem mount point for the dataset |
| `rmlint_keep_path` | `/pool/keep` | Files here are treated as originals (never marked for removal) |
| `rmlint_clean_path` | `/pool/clean` | Files here are candidates if they duplicate something in `keep` |
| `rmlint_output_dir` | `/var/lib/rmlint` | Where `results.json` and `rmlint.sh` are written |
| `rmlint_min_size` | `1M` | Ignore files smaller than this — cuts noise dramatically |

Override on the command line:

```bash
ansible-playbook rmlint_setup.yml \
  -e zfs_dataset=tank/media \
  -e zfs_mountpoint=/mnt/media \
  -e rmlint_keep_path=/mnt/media/masters \
  -e rmlint_clean_path=/mnt/media/inbox \
  -e rmlint_min_size=10M
```

### Playbook 2 — `near_dupes_setup.yml`

| Variable | Default | Description |
|---|---|---|
| `scan_paths` | `[/pool/data/photos, /pool/data/documents]` | Directories to scan |
| `output_dir` | `/var/lib/rmlint/near_dupes` | Where result JSON files are written |
| `venv_path` | `/opt/near_dupes_venv` | Python virtualenv for `imagehash` and `sentence-transformers` |
| `scripts_dir` | `/opt/near_dupes` | Where the Python scripts are deployed on the target |
| `phash_threshold` | `5` | Perceptual hash distance for images (see below) |
| `text_sim_threshold` | `0.85` | Cosine similarity threshold for documents (see below) |
| `exiftool_parallel` | `{{ ansible_processor_vcpus }}` | Parallel exiftool workers — defaults to vCPU count |

---

## What's idempotent

Every task is safe to re-run:

| Task | Why it's idempotent |
|---|---|
| Install packages | `state: present` — no-op if already installed |
| Set `xattr=sa` on ZFS dataset | `community.general.zfs` sets property only if it differs |
| Create xattr test file | `changed_when: false` — never reports a change |
| Write/read/clean up test xattr | `changed_when: false` — verification only |
| Create output directories | `state: directory` — no-op if they already exist |
| Create virtualenv | `creates:` guard — skipped if already exists |
| Install Python packages | `state: present` — no-op if already at that version |
| Deploy Python scripts | `copy` module — no-op if file content matches |
| Run rmlint scan | `changed_when: false` — scan result overwrites previous output |
| Run image/doc near-dupe detection | `changed_when: false` — output overwrites previous run |

---

## What's non-destructive

Both playbooks are **read-only with respect to your data**:

- `rmlint_setup.yml` writes `results.json` and `rmlint.sh` to `/var/lib/rmlint`. The shell script is generated but **never executed** by the playbook. You execute it manually after review.
- `near_dupes_setup.yml` writes three JSON report files to `/var/lib/rmlint/near_dupes`. Nothing is moved, renamed, or deleted.
- xattr writes (`--xattr-write`) store checksums as file metadata, not file content. Your data is untouched.

---

## Review workflow

### Exact duplicates (rmlint)

```bash
# Top 20 duplicates by size — start here
jq '.[:-1] | sort_by(-.size) | .[:20]' /var/lib/rmlint/results.json

# Show only files over 100MB
jq '[.[:-1][] | select(.size > 104857600)]' /var/lib/rmlint/results.json

# Review the generated removal script before running it
less /var/lib/rmlint/rmlint.sh

# When you're ready — runs with --dry-run first by default
bash /var/lib/rmlint/rmlint.sh --dry-run

# Actually execute (removes duplicates, keeps originals)
bash /var/lib/rmlint/rmlint.sh
```

### Near-duplicate images

```bash
# All clusters
jq '.[] | .files' /var/lib/rmlint/near_dupes/image_near_dupes.json

# Count clusters
jq 'length' /var/lib/rmlint/near_dupes/image_near_dupes.json

# Clusters with more than 2 files
jq '[.[] | select(.files | length > 2)]' /var/lib/rmlint/near_dupes/image_near_dupes.json
```

### Near-duplicate documents

```bash
# All clusters
jq '.[] | .files' /var/lib/rmlint/near_dupes/doc_near_dupes.json

# Pairs only
jq '[.[] | select(.files | length == 2) | .files]' /var/lib/rmlint/near_dupes/doc_near_dupes.json
```

---

## Clearing the xattr cache

If you want rmlint to rehash everything from scratch:

```bash
# Find the exact attribute name rmlint used
getfattr -d -m '.*' /pool/data/somefile

# Clear all rmlint xattrs (adjust attribute name if different)
find /pool/clean -type f -print0 | \
  xargs -0 -P"$(nproc)" setfattr -x user.rmlint.checksum 2>/dev/null

find /pool/keep -type f -print0 | \
  xargs -0 -P"$(nproc)" setfattr -x user.rmlint.checksum 2>/dev/null
```

---

## Customizing thresholds

### `phash_threshold` (images)

Perceptual hash distance between two images. Lower is stricter.

| Value | Matches |
|---|---|
| `0` | Byte-for-byte identical images (same as rmlint) |
| `3` | Same image, minor JPEG recompression |
| `5` | Same image, light crop or resize ← default |
| `10` | Visually similar but not the same shot |

Start at 5. If you're seeing false positives (unrelated images grouped together), lower it to 3.

### `text_sim_threshold` (documents)

Cosine similarity between sentence-transformer embeddings. Higher is stricter.

| Value | Matches |
|---|---|
| `0.95` | Near-identical text, minor edits only |
| `0.85` | Same document with substantive edits ← default |
| `0.75` | Same topic, different content |
| `0.60` | Thematically related |

Start at 0.85. If you're seeing unrelated documents grouped together, raise it to 0.90.
