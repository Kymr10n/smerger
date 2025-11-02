# photo-smart-merge

<div align="center">
  <img src="smerger.png" alt="Photo Smart Merge Logo" width="200"/>
</div>

**Purpose:** Intelligently merge photo collections while:
- detecting **exact duplicates** (jdupes) and **visual near-duplicates** (pHash),
- always keeping the **better** version (by type/quality/resolution/exif/size),
- filing results into **date-organized folders**: `YYYY/MM`,
- using a **dry-run plan** first, and offering **quarantine** for replaced files.

## Folder structure
```
/path/to/photos/
 ├─ master-collection     # MASTER (destination; compared against)
 ├─ source-collection     # SOURCE (import from; only uniques or better variants)
```

## Quick start (local build, remote deploy)

1. **Setup environment:**
   ```bash
   cp .env.example .env
   # Edit .env file with your specific paths and settings
   ```

2. **Setup remote SSH connection and Docker context:**
   ```bash
   ./setup-nas-connection.sh
   ```
   This script will:
   - Generate SSH keys if needed
   - Configure SSH client
   - Set up passwordless SSH access to your remote target
   - Create and test Docker context for remote deployment
   
   **Note:** Make sure your deployment target hostname is resolvable. If you have DNS issues, either:
   - Use the target IP address directly in your `.env` file (`NAS_HOST=192.168.1.100`)
   - Add the hostname to your `/etc/hosts` file
   - Configure your network/DNS properly

3. **Optional:** Manage Docker contexts easily:
   ```bash
   ./docker-context.sh remote  # Switch to remote target
   ./docker-context.sh local   # Switch to local
   ./docker-context.sh status  # Show current context
   ./docker-context.sh test    # Test remote connection
   ```

4. **Build & plan (dry-run):**
   ```bash
   docker build -t your-username/photo-smart-merge:latest .
   docker run --rm -it \
     --user 1000:121 \
     -e ROOT_DIR=/data \
     -e MASTER_DIR="master-collection" \
     -e SOURCE_DIR="source-collection" \
     -e DRY_RUN=1 \
     -e PHASH_THRESHOLD=8 \
     -e QUALITY_ORDER="raw,heic,jpeg,png,other" \
     -v /path/to/your/photos:/data:rw \
     -v /path/to/your/photos/.reports:/out:rw \
     -v /path/to/your/photos/.quarantine:/quarantine:rw \
     your-username/photo-smart-merge:latest
   ```

   Check outputs:
   - Plan CSV: `/path/to/your/photos/.reports/plan_smart_merge.csv`
   - Report JSON: `/path/to/your/photos/.reports/smart_merge_report.json`

5. **Execute plan (apply):**
   ```bash
   docker run --rm -it \
     --user 1000:121 \
     -e ROOT_DIR=/data \
     -e MASTER_DIR="master-collection" \
     -e SOURCE_DIR="source-collection" \
     -e DRY_RUN=0 \
     -e PHASH_THRESHOLD=8 \
     -v /path/to/your/photos:/data:rw \
     -v /path/to/your/photos/.reports:/out:rw \
     -v /path/to/your/photos/.quarantine:/quarantine:rw \
     your-username/photo-smart-merge:latest
   ```

## docker compose
First setup your environment:
```bash
cp .env.example .env
# Edit .env file with your specific settings
```

Then run:
```bash
docker compose up --build
```

## Configuration
All configuration is done via the `.env` file. Copy `.env.example` to `.env` and adjust the values:

- `TZ`: Timezone for date operations
- `ROOT_DIR`, `MASTER_DIR`, `SOURCE_DIR`: Directory structure inside container  
- `DRY_RUN`: Set to 0 to execute, 1 for dry-run only
- `PHASH_THRESHOLD`: Visual similarity threshold (0-64)
- `QUALITY_ORDER`: File type priority ranking
- `EXTS`: Supported file extensions
- `DOCKER_USER`: User ID and group ID for container
- `PHOTOS_PATH`, `REPORTS_PATH`, `QUARANTINE_PATH`: Host volume mount paths

## Quality rules (default)
1. RAW (`dng,cr2,cr3,nef,arw`) > HEIC/HEIF > JPEG > PNG > other  
2. Higher resolution (pixels) wins  
3. Image with **EXIF DateTime** preferred  
4. Larger file size as tiebreaker

All settings can be customized via the `.env` file.

## Notes
- Replaced master files go to **quarantine** (if mounted).
- Date-organized pathing uses EXIF `DateTimeOriginal` or `CreateDate`; fallback is file mtime.
- Always confirm the **dry-run** plan before applying.
