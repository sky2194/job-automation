"""
Email Notifier
Sends a summary email after each pipeline run using smtplib (no extra packages needed).
"""
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger(__name__)


def send_summary_email(results: list[dict], applied_count: int, notify_cfg: dict) -> None:
    """
    Send a plain-text + HTML summary email via SMTP.
    notify_cfg keys: smtp_host, smtp_port, smtp_user, smtp_pass, notify_email
    """
    smtp_host = notify_cfg.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(notify_cfg.get("smtp_port", 587))
    smtp_user = notify_cfg.get("smtp_user", "")
    smtp_pass = notify_cfg.get("smtp_pass", "")
    to_addr = notify_cfg.get("notify_email", smtp_user)

    if not smtp_user or not smtp_pass:
        log.warning("  SMTP credentials not set — skipping email notification")
        return

    applied = [j for j in results if j.get("status") == "applied"]
    failed = [j for j in results if j.get("status") not in ("applied", "dry_run")]

    subject = (
        f"[Job Bot] {applied_count} application(s) submitted — "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

    plain = _build_plain(applied, failed, applied_count)
    html = _build_html(applied, failed, applied_count)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_addr
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, to_addr, msg.as_string())


def _build_plain(applied: list[dict], failed: list[dict], count: int) -> str:
    lines = [
        f"Job Automation Run — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Applied: {count}  |  Failed/skipped: {len(failed)}",
        "",
    ]
    if applied:
        lines.append("APPLIED:")
        for j in applied:
            lines.append(f"  [{j.get('score', 0):3d}] {j['title']} @ {j['company']}")
            lines.append(f"        {j.get('url', '')}")
    if failed:
        lines.append("\nFAILED / SKIPPED:")
        for j in failed:
            lines.append(f"  {j['title']} @ {j['company']} — {j.get('status', '')}")
    return "\n".join(lines)


def _build_html(applied: list[dict], failed: list[dict], count: int) -> str:
    rows_applied = "".join(
        f"<tr>"
        f"<td style='padding:8px;'><b>{j['title']}</b><br><small>{j['company']}</small></td>"
        f"<td style='padding:8px;text-align:center;color:{'#22c55e' if j.get('score',0)>=70 else '#f59e0b'}'>"
        f"<b>{j.get('score', 0)}</b></td>"
        f"<td style='padding:8px;'><a href='{j.get('url','')}'>View Job</a></td>"
        f"</tr>"
        for j in applied
    )
    rows_failed = "".join(
        f"<tr><td style='padding:8px;color:#ef4444;'>{j['title']} @ {j['company']}</td>"
        f"<td style='padding:8px;'>{j.get('status','')}</td></tr>"
        for j in failed
    )
    return f"""<html><body style="font-family:sans-serif;max-width:600px;margin:auto;">
<h2 style="color:#6366f1;">Job Automation Run</h2>
<p style="color:#64748b;">{datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<p>Applied: <b>{count}</b> &nbsp;|&nbsp; Failed/skipped: <b>{len(failed)}</b></p>
{'<h3>Applied Successfully</h3><table style="width:100%;border-collapse:collapse;"><thead><tr><th style="text-align:left;padding:8px;background:#f8fafc;">Job</th><th style="padding:8px;background:#f8fafc;">Score</th><th style="padding:8px;background:#f8fafc;">Link</th></tr></thead><tbody>' + rows_applied + '</tbody></table>' if applied else ''}
{'<h3 style="color:#ef4444;">Failed / Skipped</h3><table style="width:100%;border-collapse:collapse;"><tbody>' + rows_failed + '</tbody></table>' if failed else ''}
<hr style="margin-top:32px;border:none;border-top:1px solid #e2e8f0;">
<p style="font-size:12px;color:#94a3b8;">Sent by Job Automation Bot</p>
</body></html>"""
