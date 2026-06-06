"""
Auto-Apply Engine
Uses Playwright to submit job applications.
Supports: LinkedIn Easy Apply, Indeed, and generic job boards.
"""
import logging
import os
import time

log = logging.getLogger(__name__)

LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD", "")
INDEED_EMAIL = os.getenv("INDEED_EMAIL", "")

# Set HEADLESS=false in .env to watch the browser (useful for debugging CAPTCHAs)
HEADLESS = os.getenv("HEADLESS", "true").lower() != "false"


def apply_to_job(job: dict, resume_path: str, cover_letter: str, candidate: dict) -> bool:
    """Route to the correct applicator based on job URL."""
    url = job.get("url", "").lower()
    if "linkedin.com" in url:
        return apply_linkedin(job, resume_path, cover_letter, candidate)
    if "indeed.com" in url:
        return apply_indeed(job, resume_path, candidate)
    return apply_generic(job, resume_path, cover_letter, candidate)


def apply_linkedin(job: dict, resume_path: str, cover_letter: str, candidate: dict) -> bool:
    """Auto-apply via LinkedIn Easy Apply."""
    if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
        log.warning("  LinkedIn credentials not set — skipping")
        return False

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        try:
            # Login
            page.goto("https://www.linkedin.com/login")
            page.fill("#username", LINKEDIN_EMAIL)
            page.fill("#password", LINKEDIN_PASSWORD)
            page.click('[type="submit"]')
            page.wait_for_load_state("networkidle")
            time.sleep(3)

            # Navigate to job
            page.goto(job["url"])
            time.sleep(3)

            easy_apply = page.query_selector(
                'button.jobs-apply-button, button[aria-label*="Easy Apply"]'
            )
            if not easy_apply:
                log.debug("  No Easy Apply button found for %s", job["url"])
                return False

            easy_apply.click()
            time.sleep(2)

            for _ in range(10):
                # Upload resume
                file_input = page.query_selector(
                    'input[type="file"][accept*=".pdf"], input[type="file"][accept*=".doc"]'
                )
                if file_input and resume_path and os.path.exists(resume_path):
                    file_input.set_input_files(resume_path)
                    time.sleep(1)

                # Fill cover letter textarea
                for ta in page.query_selector_all("textarea"):
                    label = (
                        ta.get_attribute("aria-label") or
                        ta.get_attribute("placeholder") or ""
                    ).lower()
                    if any(k in label for k in ["cover", "letter", "additional", "message"]):
                        ta.fill(cover_letter[:500])

                _fill_form_fields(page, candidate)

                # Try to submit
                submit_btn = page.query_selector('[aria-label="Submit application"]')
                if submit_btn:
                    submit_btn.click()
                    time.sleep(2)
                    log.info("  LinkedIn: submitted %s @ %s", job["title"], job["company"])
                    return True

                next_btn = page.query_selector(
                    '[aria-label="Continue to next step"], '
                    'button:has-text("Next"), '
                    'button:has-text("Review")'
                )
                if next_btn:
                    next_btn.click()
                    time.sleep(2)
                else:
                    break

            return False

        except Exception as exc:
            log.warning("  LinkedIn apply error: %s", exc)
            return False
        finally:
            browser.close()


def apply_indeed(job: dict, resume_path: str, candidate: dict) -> bool:
    """Auto-apply via Indeed."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page()
        try:
            page.goto(job["url"])
            time.sleep(3)

            apply_btn = page.query_selector(
                "#indeedApplyButton, .ia-IndeedApplyButton, "
                "button[id*='apply'], a[href*='apply']"
            )
            if not apply_btn:
                return False

            apply_btn.click()
            time.sleep(3)

            file_input = page.query_selector('input[type="file"]')
            if file_input and resume_path and os.path.exists(resume_path):
                file_input.set_input_files(resume_path)
                time.sleep(2)

            _fill_form_fields(page, candidate)

            for _ in range(5):
                submit = page.query_selector(
                    'button:has-text("Submit"), '
                    'button:has-text("Apply"), '
                    'button[type="submit"]'
                )
                cont = page.query_selector('button:has-text("Continue")')

                if submit:
                    text = (submit.inner_text() or "").lower()
                    if "submit" in text or "apply" in text:
                        submit.click()
                        time.sleep(2)
                        log.info("  Indeed: submitted %s @ %s", job["title"], job["company"])
                        return True

                if cont:
                    cont.click()
                    time.sleep(2)
                else:
                    break

            return False

        except Exception as exc:
            log.warning("  Indeed apply error: %s", exc)
            return False
        finally:
            browser.close()


def apply_generic(job: dict, resume_path: str, cover_letter: str, candidate: dict) -> bool:
    """Best-effort apply on generic job board pages."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page()
        try:
            page.goto(job["url"])
            time.sleep(3)

            apply_btn = page.query_selector(
                'a:has-text("Apply"), button:has-text("Apply"), '
                'a[href*="apply"], button[class*="apply"]'
            )
            if apply_btn:
                apply_btn.click()
                time.sleep(3)
                _fill_form_fields(page, candidate)

            # Generic pages: return False (best-effort, no reliable submit detection)
            return False

        except Exception as exc:
            log.debug("  Generic apply error: %s", exc)
            return False
        finally:
            browser.close()


def _fill_form_fields(page, candidate: dict) -> None:
    """Detect and fill common form fields by label/placeholder/name."""
    inputs = page.query_selector_all(
        "input[type='text'], input[type='email'], input[type='tel']"
    )
    for inp in inputs:
        label = (
            inp.get_attribute("aria-label") or
            inp.get_attribute("placeholder") or
            inp.get_attribute("name") or ""
        ).lower()

        if any(k in label for k in ["full name", "your name", "first name", "name"]):
            try:
                inp.fill(candidate["name"])
            except Exception:
                pass
        elif "email" in label:
            try:
                inp.fill(candidate["email"])
            except Exception:
                pass
        elif any(k in label for k in ["phone", "mobile", "tel"]):
            try:
                inp.fill(candidate.get("phone", ""))
            except Exception:
                pass
