# rmlint-ansible

Three-playbook deduplication pipeline for ZFS filesystems:

1. **`zfs_tune.yml`** — ZFS tuning, pool health gate, SMART disk health, OOM protection, process monitoring tools
2. **`rmlint_setup.yml`** — Exact duplicates via `rmlint` with ZFS `xattr=sa` caching
3. **`near_dupes_setup.yml`** — Near-duplicates via perceptual hashing (images) and sentence-transformer embeddings (documents)

None of the playbooks delete anything. All three produce reports or apply configuration — no data is touched.

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

# 4. Run Playbook 0: ZFS tuning + health checks + monitoring tools
ansible-playbook zfs_tune.yml

# 5. Run Playbook 1: ZFS xattr setup + rmlint exact-dupe scan
ansible-playbook rmlint_setup.yml

# 6. Run Playbook 2: near-duplicate detection (images + documents)
ansible-playbook near_dupes_setup.yml
```

Run `zfs_tune.yml` at least once before either scan playbook. It is safe to re-run.

---

## Configuration

### Playbook 0 — `zfs_tune.yml`

| Variable | Default | Description |
|---|---|---|
| `zfs_dataset` | `pool/data` | Dataset to tune |
| `zfs_recordsize` | `128K` | ZFS record size — 128K suits photo/document archives; use `1M` for video |
| `zfs_arc_max_bytes` | 50% of total RAM | Maximum ZFS ARC size in bytes — caps memory use to leave headroom for scans |
| `zfs_arc_min_bytes` | 10% of total RAM | Minimum ARC that ZFS will always keep |
| `vm_swappiness` | `10` | Kernel swap eagerness (default 60 — reduced for scan workloads) |
| `vm_vfs_cache_pressure` | `50` | Kernel inode/dentry cache retention (default 100 — reduced for scan workloads) |
| `scan_min_free_mb` | `512` | Minimum free RAM (MB) required — playbook fails fast if below this |

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
| `scan_min_free_mb_ml` | `2048` | Minimum free RAM (MB) before running sentence-transformers |

---

## What `zfs_tune.yml` does

### Process monitoring tools

Installs and enables:

| Tool | What it does |
|---|---|
| `sysstat` | Records CPU/IO/memory samples every 10 min via `sa1`. Use `sar -d` to review disk I/O history after a scan. `iostat -x 2` for live disk stats during a scan. |
| `iotop` | Real-time per-process disk I/O. Run `sudo iotop -o` alongside a scan to watch rmlint's I/O. |
| `smartmontools` | S.M.A.R.T. disk health queries. The playbook runs `smartctl -H` on every discovered drive before scanning. |
| `htop` | Interactive process monitor — CPU, memory, and per-process stats. |

### Disk read error detection

The playbook checks health on two levels before scanning:

1. **ZFS pool health** (`zpool status -x`) — fails immediately if any pool is DEGRADED, FAULTED, or has uncleared errors. ZFS tracks read/write/checksum errors per vdev; these show up here.
2. **S.M.A.R.T.** (`smartctl -H`) — queries each physical disk's SMART overall health assessment. Fails if any drive reports FAILED. On VMs or NVMe devices where SMART is unavailable, this step reports but does not fail.

If either check fails, the playbook stops before any scan runs.

### OOM protection

rmlint on 500 GB / 100k files and sentence-transformers both compete for RAM. Without a cap, ZFS's ARC can grow to consume nearly all memory, leaving the scan processes to trigger the OOM killer.

The playbook sets `zfs_arc_max` to 50% of total RAM, both persistently (via `/etc/modprobe.d/zfs.conf`) and immediately (via `/sys/module/zfs/parameters/zfs_arc_max`). No reboot required.

The rmlint scan is also run under `nice -n 10 ionice -c 3` so it yields CPU and I/O to other processes, making the system less likely to become unresponsive during a long scan.

A memory assertion fails fast if free RAM is below the configured minimum — catching the problem before the scan starts rather than mid-run.

### ZFS dataset tuning

| Property | Value | Reason |
|---|---|---|
| `atime=off` | `off` | Eliminates a write for every file read during the scan traversal |
| `compression` | `lz4` | Compresses new data; near-zero CPU cost; doesn't affect existing data |
| `xattr` | `sa` | Stores xattrs in the inode (System Attributes), not a hidden directory — critical for rmlint's `--xattr-write` performance |
| `recordsize` | `128K` | Matches mixed photo/document archives; set to `1M` for video-only pools |

### ARC tuning

ZFS ARC default cap is 50% of RAM on Linux (with minimum 64 MB). The playbook makes this explicit and adjustable:

```bash
# Check current ARC usage at any time
cat /proc/spl/kstat/zfs/arcstats | grep -E '^(size|c_max|c_min|hits|misses) '
```

To tune from the command line without editing vars:

```bash
ansible-playbook zfs_tune.yml \
  -e "zfs_arc_max_bytes=$(python3 -c 'import os; print(os.sysconf(\"SC_PAGE_SIZE\") * os.sysconf(\"SC_PHYS_PAGES\") // 3)')"
```

(That sets ARC max to ⅓ of RAM — useful if running the full three-playbook pipeline in sequence on the same host.)

---

## What's idempotent

Every task is safe to re-run:

| Task | Why it's idempotent |
|---|---|
| Install packages | `state: present` — no-op if already installed |
| Enable sysstat | `state: started, enabled: true` — no-op if already running |
| Pool health check | read-only, `changed_when: false` |
| SMART health check | read-only, `changed_when: false` |
| ZFS dataset properties | `community.general.zfs` sets only properties that differ |
| Write ARC modprobe config | `copy` module — no-op if file content matches |
| Apply ARC limits to `/sys` | `changed_when: false` — write is idempotent at the OS level |
| Write sysctl config | `copy` module — no-op if file content matches |
| Apply sysctl | `sysctl --system` — sets only values that differ |
| Memory assertion | read-only check |
| Set `xattr=sa` on ZFS dataset | `community.general.zfs` — no-op if already set |
| Create xattr test file | `changed_when: false` — verification only |
| Create output directories | `state: directory` — no-op if they already exist |
| Create virtualenv | `creates:` guard — skipped if already exists |
| Install Python packages | `state: present` — no-op if already at that version |
| Deploy Python scripts | `copy` module — no-op if file content matches |
| Run rmlint scan | `changed_when: false` — scan result overwrites previous output |
| Run image/doc near-dupe detection | `changed_when: false` — output overwrites previous run |

---

## What's non-destructive

All three playbooks are read-only with respect to your data:

- `zfs_tune.yml` modifies ZFS properties and system configuration files — it does not touch any files in your pool.
- `rmlint_setup.yml` writes `results.json` and `rmlint.sh` to `/var/lib/rmlint`. The shell script is generated but **never executed** by the playbook. You execute it manually after review.
- `near_dupes_setup.yml` writes three JSON report files to `/var/lib/rmlint/near_dupes`. Nothing is moved, renamed, or deleted.
- xattr writes (`--xattr-write`) store checksums as file metadata, not file content.

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

# Dry run
bash /var/lib/rmlint/rmlint.sh --dry-run

# Execute when ready
bash /var/lib/rmlint/rmlint.sh
```

### Near-duplicate images

```bash
jq '.[] | .files' /var/lib/rmlint/near_dupes/image_near_dupes.json
jq 'length' /var/lib/rmlint/near_dupes/image_near_dupes.json
jq '[.[] | select(.files | length > 2)]' /var/lib/rmlint/near_dupes/image_near_dupes.json
```

### Near-duplicate documents

```bash
jq '.[] | .files' /var/lib/rmlint/near_dupes/doc_near_dupes.json
jq '[.[] | select(.files | length == 2) | .files]' /var/lib/rmlint/near_dupes/doc_near_dupes.json
```

### Monitoring a running scan

```bash
# Watch rmlint's disk I/O in real time
sudo iotop -o -p $(pgrep rmlint)

# Live disk throughput
iostat -x 2

# Review system metrics from the scan window afterward
sar -d -f /var/log/sysstat/sa$(date +%d)
```

---

## Clearing the xattr cache

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
