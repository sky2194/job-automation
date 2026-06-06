"""
AI Job Scorer
Scores each job 0-100 using Groq (primary), Gemini (fallback), or keyword matching.
"""
import json
import logging
import re
import time

log = logging.getLogger(__name__)


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response that may have markdown fences."""
    text = text.strip()
    # Strip ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        text = match.group(1)
    return json.loads(text)


def _call_groq_with_retry(client, model, messages, retries=3, **kwargs):
    for attempt in range(retries):
        try:
            return client.chat.completions.create(
                model=model, messages=messages, **kwargs
            )
        except Exception as exc:
            if attempt == retries - 1:
                raise
            wait = 2 ** attempt
            log.debug("  Groq retry %d/%d after %ds (%s)", attempt + 1, retries, wait, exc)
            time.sleep(wait)


def get_groq_score(job: dict, candidate: dict, api_key: str) -> dict:
    """Score using Groq (Llama 3.3 70B — free tier)."""
    from groq import Groq
    client = Groq(api_key=api_key)

    prompt = f"""You are a job matching expert. Score this job's fit for the candidate (0-100).

JOB:
- Title: {job['title']}
- Company: {job['company']}
- Description: {job.get('description', 'N/A')[:1200]}
- Tags: {', '.join(job.get('tags', []))}
- Salary: {job.get('salary_min', 'N/A')} - {job.get('salary_max', 'N/A')}

CANDIDATE:
- Skills: {', '.join(candidate['skills'])}
- Experience: {candidate['experience_years']} years
- Industries: {', '.join(candidate['preferred_industries'])}
- Salary Range: ${candidate['salary_min']:,} - ${candidate['salary_max']:,}

Return ONLY valid JSON:
{{"score": <0-100>, "reason": "<1-2 sentence explanation>", "key_matches": ["skill1", "skill2"]}}"""

    resp = _call_groq_with_retry(
        client,
        "llama-3.3-70b-versatile",
        [{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=200,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


def get_gemini_score(job: dict, candidate: dict, api_key: str) -> dict:
    """Fallback: Score using Google Gemini 2.0 Flash (free tier)."""
    from google import genai

    client = genai.Client(api_key=api_key)
    prompt = f"""Score job fit 0-100 for this candidate. Return ONLY JSON.
Job: {job['title']} at {job['company']}. Tags: {', '.join(job.get('tags', []))}
Description snippet: {job.get('description', '')[:500]}
Candidate skills: {', '.join(candidate['skills'])}
Return: {{"score": <int>, "reason": "<brief>", "key_matches": ["skill1"]}}"""

    resp = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    return _extract_json(resp.text)


def keyword_score(job: dict, candidate: dict) -> dict:
    """Simple keyword matching — no API needed."""
    text = f"{job['title']} {job.get('description', '')} {' '.join(job.get('tags', []))}".lower()
    matches = [s for s in candidate["skills"] if s.lower() in text]
    score = min(100, len(matches) * 20)
    return {
        "score": score,
        "reason": f"Keyword match: {len(matches)} skills found ({', '.join(matches[:3])})",
        "key_matches": matches,
    }


def score_jobs(jobs: list[dict], candidate: dict, api_config: dict) -> list[dict]:
    """Score all jobs with AI; fall back gracefully on any error."""
    scored = []
    groq_key = api_config.get("groq_key", "")
    gemini_key = api_config.get("gemini_key", "")

    for i, job in enumerate(jobs):
        try:
            if groq_key:
                result = get_groq_score(job, candidate, groq_key)
            elif gemini_key:
                result = get_gemini_score(job, candidate, gemini_key)
            else:
                result = keyword_score(job, candidate)

            job["score"] = int(result.get("score", 0))
            job["reason"] = result.get("reason", "")
            job["key_matches"] = result.get("key_matches", [])

        except Exception as exc:
            log.warning("  Score failed for '%s' (%s) — using keyword fallback", job.get("title"), exc)
            result = keyword_score(job, candidate)
            job.update(result)

        scored.append(job)

        if (i + 1) % 10 == 0:
            log.info("    Scored %d/%d jobs...", i + 1, len(jobs))

    return scored
