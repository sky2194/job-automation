"""
Resume & Cover Letter Generator
Creates tailored application documents using free LLMs.
Falls back to templates when no API key is available.
Uses python-docx for DOCX resume output when a base template exists.
"""
import logging
import os
import re

log = logging.getLogger(__name__)


# ── Cover Letter ─────────────────────────────────

def generate_cover_letter(job: dict, candidate: dict, api_config: dict) -> str:
    prompt = f"""Write a professional, concise cover letter (200 words max).

JOB DETAILS:
- Position: {job['title']}
- Company: {job['company']}
- Key Requirements: {', '.join(job.get('tags', [])[:5])}
- Why good fit: {job.get('reason', 'Strong skill alignment')}

CANDIDATE:
- Name: {candidate['name']}
- Skills: {', '.join(candidate['skills'])}
- Years Experience: {candidate['experience_years']}

RULES:
- Be specific about the candidate's matching skills
- Sound genuine, not generic
- No fluff or filler phrases
- End with a clear call to action
- Do NOT start with "Dear Hiring Manager" — address the company by name"""

    groq_key = api_config.get("groq_key", "")
    gemini_key = api_config.get("gemini_key", "")

    if groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500,
            )
            return resp.choices[0].message.content
        except Exception as exc:
            log.warning("  Groq cover letter failed: %s — trying Gemini", exc)

    if gemini_key:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            resp = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            return resp.text
        except Exception as exc:
            log.warning("  Gemini cover letter failed: %s — using template", exc)

    return _template_cover_letter(job, candidate)


def _template_cover_letter(job: dict, candidate: dict) -> str:
    matches = job.get("key_matches", candidate["skills"][:3])
    skills_str = ", ".join(matches[:3]) if matches else ", ".join(candidate["skills"][:3])
    return f"""Dear {job['company']} Team,

I'm writing to express my interest in the {job['title']} role. With {candidate['experience_years']} years \
of hands-on experience in {skills_str}, I can contribute from day one.

My background in {', '.join(candidate['skills'][:4])} maps directly to what this position requires. \
I'm excited about the opportunity to bring that experience to {job['company']} and would welcome \
the chance to discuss how I can help your team succeed.

Available for a call any time — reach me at {candidate['email']}.

Best regards,
{candidate['name']}"""


# ── Resume Generator ─────────────────────────────

def _generate_summary(job: dict, candidate: dict, api_config: dict) -> str:
    prompt = f"""Write a 3-line professional summary for a resume tailored to this role.
Role: {job['title']} at {job['company']}
Skills to highlight: {', '.join(job.get('key_matches', candidate['skills'][:4]))}
Experience level: {candidate['experience_years']} years
Be concise and impact-focused. No buzzwords."""

    groq_key = api_config.get("groq_key", "")
    if groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=150,
            )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            log.warning("  Groq resume summary failed: %s", exc)

    skills_str = ", ".join(candidate["skills"][:4])
    return (
        f"Software professional with {candidate['experience_years']} years of experience "
        f"in {skills_str}. Strong track record of building and delivering scalable, "
        f"maintainable solutions in fast-paced environments."
    )


def _safe_filename(text: str) -> str:
    return re.sub(r"[^\w\-]", "_", text)


def generate_resume(job: dict, candidate: dict, api_config: dict) -> str:
    """
    Generate a tailored resume for the given job.
    - If resume_base.docx exists: inject the AI summary into a copy using python-docx.
    - Otherwise: write a plain-text resume to resumes/.
    Returns the path to the generated file.
    """
    os.makedirs("resumes", exist_ok=True)
    summary = _generate_summary(job, candidate, api_config)
    company_slug = _safe_filename(job["company"])

    base_docx = candidate.get("base_resume", "resume_base.docx")
    if os.path.exists(base_docx):
        return _generate_docx_resume(base_docx, company_slug, summary, job, candidate)

    return _generate_text_resume(company_slug, summary, job, candidate)


def _generate_docx_resume(
    base_path: str, company_slug: str, summary: str, job: dict, candidate: dict
) -> str:
    """Inject AI summary into a DOCX template by replacing the [SUMMARY] placeholder."""
    try:
        from docx import Document

        doc = Document(base_path)
        for para in doc.paragraphs:
            if "[SUMMARY]" in para.text:
                for run in para.runs:
                    run.text = run.text.replace("[SUMMARY]", summary)

        out_path = f"resumes/resume_{company_slug}.docx"
        doc.save(out_path)
        log.debug("  DOCX resume saved: %s", out_path)
        return out_path
    except ImportError:
        log.warning("  python-docx not installed — falling back to text resume")
    except Exception as exc:
        log.warning("  DOCX resume generation failed: %s — falling back to text", exc)

    return _generate_text_resume(company_slug, summary, job, candidate)


def _generate_text_resume(
    company_slug: str, summary: str, job: dict, candidate: dict
) -> str:
    out_path = f"resumes/resume_{company_slug}.txt"
    content = (
        f"TAILORED RESUME SUMMARY\n"
        f"{'='*40}\n"
        f"{summary}\n\n"
        f"TARGET ROLE : {job['title']} @ {job['company']}\n"
        f"CANDIDATE   : {candidate['name']} | {candidate['email']} | {candidate['phone']}\n"
        f"SKILLS      : {', '.join(candidate['skills'])}\n"
        f"EXPERIENCE  : {candidate['experience_years']} years\n"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    log.debug("  Text resume saved: %s", out_path)
    return out_path
