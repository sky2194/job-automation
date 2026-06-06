"""
Job Automation Pipeline
Runs every 3 hours: scrape -> score -> generate docs -> apply -> store
"""
import argparse
import logging
import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from scraper import scrape_all_sources
from scorer import score_jobs
from doc_generator import generate_resume, generate_cover_letter
from auto_apply import apply_to_job
from storage import save_to_sheets, get_applied_urls, save_local_backup, log_run
from notifier import send_summary_email

# ── Logging setup ─────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pipeline.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────
CONFIG = {
    "candidate": {
        "name": os.getenv("CANDIDATE_NAME", "Your Name"),
        "email": os.getenv("CANDIDATE_EMAIL", "you@email.com"),
        "phone": os.getenv("CANDIDATE_PHONE", "+1-555-0100"),
        "skills": os.getenv("CANDIDATE_SKILLS", "Python,JavaScript,React,AWS,Docker").split(","),
        "experience_years": int(os.getenv("CANDIDATE_EXPERIENCE", "3")),
        "preferred_industries": ["fintech", "banking", "enterprise tech", "cloud", "saas"],
        "salary_min": int(os.getenv("SALARY_MIN", "70000")),
        "salary_max": int(os.getenv("SALARY_MAX", "120000")),
        "base_resume": os.getenv("BASE_RESUME", "resume_base.docx"),
    },
    "search": {
        "queries": [
            "DevOps engineer remote",
            "Site reliability engineer remote",
            "platform engineer remote",
            "Kubernetes engineer remote",
        ],
        "min_score": int(os.getenv("MIN_SCORE", "40")),
        "max_apply_per_run": int(os.getenv("MAX_APPLY", "15")),
    },
    "apis": {
        "groq_key": os.getenv("GROQ_API_KEY", ""),
        "gemini_key": os.getenv("GEMINI_API_KEY", ""),
        "sheets_creds": os.getenv("GOOGLE_SHEETS_CREDS", "credentials.json"),
        "sheet_name": os.getenv("SHEET_NAME", "Job Automation Tracker"),
    },
    "notify": {
        "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "smtp_port": int(os.getenv("SMTP_PORT", "587")),
        "smtp_user": os.getenv("SMTP_USER", ""),
        "smtp_pass": os.getenv("SMTP_PASS", ""),
        "notify_email": os.getenv("NOTIFY_EMAIL", ""),
    },
}


def run_pipeline(args):
    run_number = os.getenv("GITHUB_RUN_NUMBER", "local")
    log.info("=" * 60)
    log.info("  Job Automation Pipeline — %s  [Run #%s]", datetime.now().strftime("%Y-%m-%d %H:%M"), run_number)
    if args.dry_run:
        log.info("  DRY RUN MODE — no applications will be submitted")
    log.info("=" * 60)

    min_score = args.min_score if args.min_score is not None else CONFIG["search"]["min_score"]
    max_apply = args.max_jobs if args.max_jobs else CONFIG["search"]["max_apply_per_run"]
    queries = [args.query] if args.query else CONFIG["search"]["queries"]
    candidate = CONFIG["candidate"]
    api_cfg = CONFIG["apis"]

    # Step 1: Scrape
    log.info("Step 1: Scraping job listings...")
    all_jobs = []
    for query in queries:
        log.info("  Query: '%s'", query)
        jobs = scrape_all_sources(query)
        all_jobs.extend(jobs)

    seen_urls: set = set()
    unique_jobs = []
    for job in all_jobs:
        url = job.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_jobs.append(job)

    log.info("  Found %d unique jobs across all sources", len(unique_jobs))

    # Step 2: Skip already-applied jobs
    log.info("Step 2: Checking for previously applied jobs...")
    applied_urls = get_applied_urls(api_cfg)
    new_jobs = [j for j in unique_jobs if j.get("url", "") not in applied_urls]
    skipped = len(unique_jobs) - len(new_jobs)
    log.info("  %d new jobs (skipped %d already applied)", len(new_jobs), skipped)

    if not new_jobs:
        log.info("  No new jobs to process. Exiting.")
        return

    # Step 3: AI Scoring
    log.info("Step 3: Scoring jobs with AI...")
    scored_jobs = score_jobs(new_jobs, candidate, api_cfg)
    qualified = sorted(
        [j for j in scored_jobs if j.get("score", 0) >= min_score],
        key=lambda x: x["score"],
        reverse=True,
    )
    log.info("  %d jobs scored >= %d", len(qualified), min_score)

    if args.score_only:
        log.info("\nTop qualifying jobs:")
        for i, job in enumerate(qualified[:20], 1):
            log.info(
                "  %2d. [%3d] %s @ %s (%s)",
                i, job["score"], job["title"], job["company"], job["source"],
            )
            log.info("       %s", job.get("reason", ""))
        return

    # Step 4: Generate docs & apply
    log.info("Step 4: Generating docs & applying...")
    applied_count = 0
    results = []

    for job in qualified[:max_apply]:
        log.info(
            "  Processing: %s @ %s (score: %d)",
            job["title"], job["company"], job["score"],
        )
        try:
            resume_path = generate_resume(job, candidate, api_cfg)
            cover_letter = generate_cover_letter(job, candidate, api_cfg)

            if args.dry_run:
                log.info("    [DRY RUN] Skipping submission")
                success = False
                job["status"] = "dry_run"
            else:
                success = apply_to_job(job, resume_path, cover_letter, candidate)
                job["status"] = "applied" if success else "failed"

            job["applied_date"] = datetime.now().isoformat()
            job["cover_letter"] = cover_letter
            job["run_number"] = run_number
            results.append(job)

            save_to_sheets(job, api_cfg)

            if success:
                applied_count += 1
                log.info("    Applied successfully")
            else:
                log.info("    Application failed or skipped")

            if not args.dry_run:
                time.sleep(5)

        except Exception as exc:
            log.exception("    Error processing job: %s", exc)
            job["status"] = "error"
            save_local_backup(job)

    # Step 5: Summary
    log.info("=" * 60)
    log.info("  Done! Applied to %d/%d qualifying jobs", applied_count, len(qualified))
    log.info("=" * 60)

    if not args.dry_run:
        log_run(api_cfg, run_number, len(unique_jobs), len(qualified), applied_count)

    notify_cfg = CONFIG["notify"]
    if notify_cfg.get("notify_email") and results and not args.dry_run:
        try:
            send_summary_email(results, applied_count, notify_cfg)
            log.info("  Summary email sent to %s", notify_cfg["notify_email"])
        except Exception as exc:
            log.warning("  Email notification failed: %s", exc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Automated job application pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                         # Full pipeline run
  python main.py --dry-run              # Scrape + score, no submissions
  python main.py --score-only           # Print top matches, exit
  python main.py --max-jobs 5           # Limit to 5 applications
  python main.py --query "ML engineer"  # Override search query
  python main.py --min-score 70         # Stricter filter
        """,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Run without submitting any applications")
    parser.add_argument("--score-only", action="store_true",
                        help="Scrape and score, print top matches, then exit")
    parser.add_argument("--max-jobs", type=int, default=None,
                        help="Maximum applications per run (overrides config)")
    parser.add_argument("--query", type=str, default=None,
                        help="Override search query (single query only)")
    parser.add_argument("--min-score", type=int, default=None,
                        help="Minimum score threshold (overrides config)")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable DEBUG-level logging")
    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    run_pipeline(args)
