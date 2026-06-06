"""
Multi-source Job Scraper
Aggregates listings from free APIs: RemoteOK, Adzuna, Arbeitnow, JSearch
"""
import logging
import os
import time

import requests

log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "JobAutomation/1.0 (contact@example.com)"}
REQUEST_TIMEOUT = 15


def _get_with_retry(url, params=None, headers=None, retries=3, backoff=2):
    """GET with exponential-backoff retry on transient failures."""
    h = {**HEADERS, **(headers or {})}
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=h, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            if attempt == retries - 1:
                raise
            wait = backoff ** attempt
            log.debug("  Retry %d/%d for %s after %ds (%s)", attempt + 1, retries, url, wait, exc)
            time.sleep(wait)


def scrape_remoteok(query: str) -> list[dict]:
    """RemoteOK — free, no auth required."""
    jobs = []
    try:
        resp = _get_with_retry("https://remoteok.com/api")
        data = resp.json()[1:]  # skip meta entry
        query_words = query.lower().split()
        for item in data:
            title = item.get("position", "").lower()
            tags = " ".join(item.get("tags", [])).lower()
            if any(w in title or w in tags for w in query_words):
                jobs.append({
                    "title": item.get("position", ""),
                    "company": item.get("company", ""),
                    "url": item.get("url") or f"https://remoteok.com/l/{item.get('id', '')}",
                    "description": item.get("description", ""),
                    "tags": item.get("tags", []),
                    "salary_min": item.get("salary_min"),
                    "salary_max": item.get("salary_max"),
                    "source": "RemoteOK",
                    "date": item.get("date", ""),
                })
    except Exception as exc:
        log.warning("  RemoteOK error: %s", exc)
    return jobs


def scrape_adzuna(query: str, country: str = "us") -> list[dict]:
    """Adzuna — free tier: 5,000 req/month."""
    app_id = os.getenv("ADZUNA_APP_ID", "")
    app_key = os.getenv("ADZUNA_APP_KEY", "")
    if not app_id or not app_key:
        log.debug("  Adzuna skipped: ADZUNA_APP_ID / ADZUNA_APP_KEY not set")
        return []

    jobs = []
    try:
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "what": query,
            "where": "remote",
            "results_per_page": 50,
            "content-type": "application/json",
        }
        data = _get_with_retry(url, params=params).json().get("results", [])
        for item in data:
            tags_raw = item.get("category", {}).get("tag", "")
            jobs.append({
                "title": item.get("title", ""),
                "company": item.get("company", {}).get("display_name", ""),
                "url": item.get("redirect_url", ""),
                "description": item.get("description", ""),
                "tags": [t.strip() for t in tags_raw.split(",") if t.strip()],
                "salary_min": item.get("salary_min"),
                "salary_max": item.get("salary_max"),
                "source": "Adzuna",
                "date": item.get("created", ""),
            })
    except Exception as exc:
        log.warning("  Adzuna error: %s", exc)
    return jobs


def scrape_arbeitnow(query: str) -> list[dict]:
    """Arbeitnow — free, no auth required."""
    jobs = []
    try:
        data = _get_with_retry("https://arbeitnow.com/api/job-board-api").json().get("data", [])
        query_words = query.lower().split()
        for item in data:
            title = item.get("title", "").lower()
            tags = " ".join(item.get("tags", [])).lower()
            if any(w in title or w in tags for w in query_words):
                jobs.append({
                    "title": item.get("title", ""),
                    "company": item.get("company_name", ""),
                    "url": item.get("url", ""),
                    "description": item.get("description", ""),
                    "tags": item.get("tags", []),
                    "salary_min": None,
                    "salary_max": None,
                    "source": "Arbeitnow",
                    "date": item.get("created_at", ""),
                })
    except Exception as exc:
        log.warning("  Arbeitnow error: %s", exc)
    return jobs


def scrape_jsearch(query: str) -> list[dict]:
    """JSearch via RapidAPI — free tier: 500 req/month."""
    api_key = os.getenv("RAPIDAPI_KEY", "")
    if not api_key:
        log.debug("  JSearch skipped: RAPIDAPI_KEY not set")
        return []

    jobs = []
    try:
        params = {"query": query, "page": "1", "num_pages": "2"}
        extra_headers = {
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }
        data = _get_with_retry(
            "https://jsearch.p.rapidapi.com/search",
            params=params,
            headers=extra_headers,
        ).json().get("data", [])

        for item in data:
            jobs.append({
                "title": item.get("job_title", ""),
                "company": item.get("employer_name", ""),
                "url": item.get("job_apply_link") or item.get("job_google_link", ""),
                "description": item.get("job_description", ""),
                "tags": item.get("job_required_skills") or [],
                "salary_min": item.get("job_min_salary"),
                "salary_max": item.get("job_max_salary"),
                "source": "JSearch",
                "date": item.get("job_posted_at_datetime_utc", ""),
            })
    except Exception as exc:
        log.warning("  JSearch error: %s", exc)
    return jobs


def scrape_all_sources(query: str) -> list[dict]:
    """Aggregate jobs from all free sources with polite rate limiting."""
    all_jobs: list[dict] = []
    scrapers = [
        ("RemoteOK", lambda: scrape_remoteok(query)),
        ("Adzuna", lambda: scrape_adzuna(query)),
        ("Arbeitnow", lambda: scrape_arbeitnow(query)),
        ("JSearch", lambda: scrape_jsearch(query)),
    ]

    for name, fn in scrapers:
        log.info("    Scraping %s...", name)
        jobs = fn()
        all_jobs.extend(jobs)
        log.info("    -> %d jobs found from %s", len(jobs), name)
        time.sleep(1)

    return all_jobs
