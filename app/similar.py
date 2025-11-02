import os, sys, csv, json, shutil, subprocess, time, logging
from pathlib import Path
from PIL import Image, UnidentifiedImageError
import imagehash

# Configure basic logging to stdout first; file handler will be added after OUT is known
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

ROOT = Path(os.environ.get("ROOT_DIR", "/data"))
MASTER = ROOT / os.environ.get("MASTER_DIR", "MobileBackup")
SOURCE = ROOT / os.environ.get("SOURCE_DIR", "Google Fotos")
OUT = Path(os.environ.get("OUT_DIR", "/out"))
QUAR = Path(os.environ.get("QUAR_DIR", "/quarantine"))
DRY_RUN = os.environ.get("DRY_RUN", "1") != "0"
PHASH_THRESHOLD = int(os.environ.get("PHASH_THRESHOLD", "8"))
EXTS = set(e.lower().strip() for e in os.environ.get("EXTS","").split(",") if e)
QUALITY_ORDER = [s.strip() for s in os.environ.get("QUALITY_ORDER","raw,heic,jpeg,png,other").split(",")]

PLAN_CSV = OUT / "plan_smart_merge.csv"
REPORT_JSON = OUT / "smart_merge_report.json"

# Ensure output dir exists and add a file handler for persistent logs there
try:
    OUT.mkdir(parents=True, exist_ok=True)
    log_file = OUT / "photo-merge.log"
    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    # get module logger and configure
    logger.setLevel(log_level)
    fh = logging.FileHandler(str(log_file))
    fh.setLevel(log_level)
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(fh)
    logger.info(f"Logging to {log_file} at level {log_level_name}")
except Exception as e:
    logger.warning(f"Could not create log file in OUT dir {OUT}: {e}")

# Log configuration
logger.info("=== Photo Smart Merge Starting ===")
logger.info(f"ROOT: {ROOT}")
logger.info(f"MASTER: {MASTER}")
logger.info(f"SOURCE: {SOURCE}")
logger.info(f"OUT: {OUT}")
logger.info(f"QUAR: {QUAR}")
logger.info(f"DRY_RUN: {DRY_RUN}")
logger.info(f"PHASH_THRESHOLD: {PHASH_THRESHOLD}")
logger.info(f"QUALITY_ORDER: {QUALITY_ORDER}")
logger.info(f"EXTS: {list(EXTS)[:10]}{'...' if len(EXTS) > 10 else ''}")

def is_media(p: Path):
    return p.is_file() and (p.suffix.lower().lstrip(".") in EXTS)

def scan_files(base: Path):
    logger.info(f"Scanning files in: {base}")
    count = 0
    for p in base.rglob("*"):
        if is_media(p):
            count += 1
            if count % 1000 == 0:
                logger.info(f"Scanned {count} files so far...")
            yield p
    logger.info(f"Completed scanning: {count} files found in {base}")

def file_type_rank(p: Path):
    ext = p.suffix.lower().lstrip(".")
    if ext in {"dng","cr2","cr3","nef","arw"}: t = "raw"
    elif ext in {"heic","heif"}: t = "heic"
    elif ext in {"jpg","jpeg"}: t = "jpeg"
    elif ext in {"png"}: t = "png"
    else: t = "other"
    return QUALITY_ORDER.index(t) if t in QUALITY_ORDER else len(QUALITY_ORDER)

def resolution(p: Path):
    try:
        with Image.open(p) as im:
            return im.width * im.height, im.width, im.height
    except Exception:
        return (0,0,0)

def has_exif_datetime(p: Path):
    try:
        res = subprocess.run(
            ["exiftool","-s3","-DateTimeOriginal","-CreateDate",str(p)],
            capture_output=True, text=True, check=False
        )
        txt = (res.stdout or "") + (res.stderr or "")
        return any(k in txt and ":" in txt for k in ["DateTimeOriginal","CreateDate"])
    except Exception:
        return False

def exif_yyyy_mm(p: Path):
    try:
        res = subprocess.run(
            ["exiftool","-s3","-d","%Y:%m","-DateTimeOriginal","-CreateDate",str(p)],
            capture_output=True, text=True, check=False
        )
        for line in res.stdout.splitlines():
            if line.strip() and ":" in line:
                y,m = line.strip().split(":")[:2]
                if len(y)==4 and len(m)==2: return f"{y}/{m}"
    except Exception:
        pass
    ts = p.stat().st_mtime
    return time.strftime("%Y/%m", time.localtime(ts))

def file_score(p: Path):
    t = file_type_rank(p)
    px, w, h = resolution(p)
    ex = has_exif_datetime(p)
    sz = p.stat().st_size
    # smaller tuple = better
    return (t, -px, 0 if not ex else -1, -sz)

def better(a: Path, b: Path):
    return a if file_score(a) < file_score(b) else b

def phash(p: Path):
    try:
        with Image.open(p) as im:
            return imagehash.phash(im)
    except (UnidentifiedImageError, OSError):
        return None

def hamming(a, b):
    return (a - b)

def collect_by_phash(paths):
    logger.info(f"Calculating perceptual hashes for {len(paths)} files...")
    out = {}
    processed = 0
    failed = 0
    for p in paths:
        processed += 1
        if processed % 500 == 0:
            logger.info(f"Processed {processed}/{len(paths)} hashes ({processed/len(paths)*100:.1f}%), failed: {failed}")
        
        hash_val = phash(p)
        if hash_val is None:
            failed += 1
        out[p] = hash_val
    
    logger.info(f"Hash calculation complete: {processed} processed, {failed} failed, {len([h for h in out.values() if h is not None])} successful")
    return out

def jdupes_groups(pathsA, pathsB):
    logger.info(f"Running jdupes to find exact duplicates between {pathsA} and {pathsB}")
    cmd = ["jdupes","-r","-j", str(pathsA), str(pathsB)]
    start_time = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    elapsed = time.time() - start_time
    logger.info(f"jdupes completed in {elapsed:.2f} seconds")
    
    js = json.loads(res.stdout or "{}")
    groups = []
    for g in js.get("matches", []):
        groups.append([Path(x["path"]) for x in g])
    
    logger.info(f"Found {len(groups)} duplicate groups with jdupes")
    return groups

def make_plan():
    logger.info("=== Starting plan generation ===")
    
    logger.info("Phase 1: Scanning files...")
    MASTER_FILES = list(scan_files(MASTER))
    SOURCE_FILES = list(scan_files(SOURCE))
    
    logger.info(f"Found {len(MASTER_FILES)} files in master directory")
    logger.info(f"Found {len(SOURCE_FILES)} files in source directory")

    # 1) Exakte Duplikate: gruppieren
    logger.info("Phase 2: Finding exact duplicates...")
    exact_groups = jdupes_groups(MASTER, SOURCE)

    exact_src_dups = set()
    pairs_exact = []  # (src, master, action, reason)
    logger.info(f"Processing {len(exact_groups)} exact duplicate groups...")
    
    for i, g in enumerate(exact_groups):
        if i % 100 == 0 and i > 0:
            logger.info(f"Processed {i}/{len(exact_groups)} exact duplicate groups...")
            
        has_master = [p for p in g if str(p).startswith(str(MASTER))]
        has_source = [p for p in g if str(p).startswith(str(SOURCE))]
        if not has_master or not has_source:
            continue
        for s in has_source:
            candidates = has_master + [s]
            best = candidates[0]
            for c in candidates[1:]:
                best = better(best, c)
            if best == s:
                # Source better -> replace worst master
                worst_m = has_master[0]
                for m in has_master[1:]:
                    worst_m = m if file_score(m) > file_score(worst_m) else worst_m
                pairs_exact.append((s, worst_m, "REPLACE_MASTER_WITH_SOURCE", "exact_dup_better_source"))
            else:
                pairs_exact.append((s, best, "KEEP_MASTER", "exact_dup_master_better"))
            exact_src_dups.add(s)

    logger.info(f"Exact duplicates processing complete: {len(pairs_exact)} pairs, {len(exact_src_dups)} source files matched")

    # 2) pHash für verbleibende
    remaining = [p for p in SOURCE_FILES if p not in exact_src_dups]
    logger.info(f"Phase 3: Calculating perceptual hashes for {len(remaining)} remaining source files and {len(MASTER_FILES)} master files...")
    
    master_hash = collect_by_phash(MASTER_FILES)
    source_hash = collect_by_phash(remaining)

    logger.info("Phase 4: Comparing perceptual hashes for similarity...")
    pairs_sim = []  # (src, master?, action, reason)
    processed_comparisons = 0
    total_comparisons = len(source_hash)
    
    for s, sh in source_hash.items():
        processed_comparisons += 1
        if processed_comparisons % 100 == 0:
            logger.info(f"Similarity comparison progress: {processed_comparisons}/{total_comparisons} ({processed_comparisons/total_comparisons*100:.1f}%)")
            
        if sh is None:
            pairs_sim.append((s, None, "MOVE_SOURCE", "no_phash"))
            continue
        best_m = None
        best_d = 999
        for m, mh in master_hash.items():
            if mh is None:
                continue
            d = hamming(sh, mh)
            if d < best_d:
                best_d, best_m = d, m
        if best_m is not None and best_d <= PHASH_THRESHOLD:
            winner = better(s, best_m)
            if winner == s:
                pairs_sim.append((s, best_m, "REPLACE_MASTER_WITH_SOURCE", f"phash_dup_d{best_d}_better_source"))
            else:
                pairs_sim.append((s, best_m, "KEEP_MASTER", f"phash_dup_d{best_d}_master_better"))
        else:
            pairs_sim.append((s, None, "MOVE_SOURCE", "unique_vs_master"))

    logger.info(f"Similarity comparison complete: {len(pairs_sim)} similarity pairs processed")
    logger.info("Phase 5: Writing plan and report files...")

    PLAN_CSV.parent.mkdir(parents=True, exist_ok=True)
    def filecmp(a: Path, b: Path):
        try:
            if os.path.getsize(a) != os.path.getsize(b):
                return False
            # quick partial compare
            with open(a, 'rb') as fa, open(b, 'rb') as fb:
                return fa.read(1024) == fb.read(1024)
        except Exception:
            return False

    def target_path_for(p: Path):
        rel = exif_yyyy_mm(p)
        dest_dir = MASTER / rel
        dest = dest_dir / p.name
        if dest.exists() and not filecmp(p, dest):
            ts = int(time.time())
            dest = dest_dir / f"{dest.stem}_{ts}{dest.suffix}"
        return dest_dir, dest

    with PLAN_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["action","src","master","target_dir","target_path","quarantine_path","reason",
                    "src_score","master_score"])
        rows = []
        for (s, m, act, why) in (pairs_exact + pairs_sim):
            tdir, tpath = target_path_for(s)
            qpath = None
            if act == "REPLACE_MASTER_WITH_SOURCE" and m:
                QUAR.mkdir(parents=True, exist_ok=True)
                qpath = QUAR / (m.name)
                if qpath.exists():
                    qpath = QUAR / f"{m.stem}_{int(time.time())}{m.suffix}"
            rows.append([
                act, str(s), (str(m) if m else ""), str(tdir), str(tpath), (str(qpath) if qpath else ""),
                why, json.dumps(file_score(s)), json.dumps(file_score(m) if m else None)
            ])
        w.writerows(rows)

    rep = {
        "root": str(ROOT), "master": str(MASTER), "source": str(SOURCE),
        "counts": {
            "source_total": len(SOURCE_FILES),
            "move_or_replace_planned": len([1 for _ in (pairs_exact + pairs_sim) if True])
        },
        "plan_csv": str(PLAN_CSV)
    }
    REPORT_JSON.write_text(json.dumps(rep, indent=2))
    
    logger.info(f"=== Plan Generation Complete ===")
    logger.info(f"Total actions planned: {len(pairs_exact + pairs_sim)}")
    logger.info(f"Plan written to: {PLAN_CSV}")
    logger.info(f"Report written to: {REPORT_JSON}")
    
    print(f"Plan created: {PLAN_CSV}")
    print(json.dumps(rep, indent=2))

def do_apply():
    if not PLAN_CSV.exists():
        print("Plan missing. Run 'plan' first.", file=sys.stderr)
        sys.exit(2)

    moved = replaced = kept = 0
    with PLAN_CSV.open() as f:
        r = csv.DictReader(f)
        for row in r:
            act = row["action"]
            src = Path(row["src"])
            tdir = Path(row["target_dir"])
            tpath = Path(row["target_path"])
            m = Path(row["master"]) if row["master"] else None
            qpath = Path(row["quarantine_path"]) if row["quarantine_path"] else None

            if act == "KEEP_MASTER":
                kept += 1
                continue

            tdir.mkdir(parents=True, exist_ok=True)

            if act == "MOVE_SOURCE":
                if not DRY_RUN and src.exists():
                    shutil.move(str(src), str(tpath))
                moved += 1

            elif act == "REPLACE_MASTER_WITH_SOURCE" and m:
                if not DRY_RUN:
                    if m.exists() and qpath:
                        QUAR.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(m), str(qpath))
                    if src.exists():
                        shutil.move(str(src), str(tpath))
                replaced += 1

    print(f"APPLY done. moved={moved}, replaced={replaced}, kept={kept}")

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "apply":
        do_apply()
    else:
        make_plan()
