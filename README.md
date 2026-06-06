# Job Automation Pipeline

Automatically scrapes, scores, and applies to remote jobs every 3 hours — completely free.

## How It Works

1. Scrapes jobs from 7 sources (RemoteOK, Remotive, WeWorkRemotely, Himalayas, Arbeitnow, Adzuna, JSearch)
2. AI scores each job against your profile (Groq + Gemini)
3. Generates a tailored resume + cover letter for each match
4. Auto-applies via LinkedIn Easy Apply & Indeed
5. Saves everything to Google Sheets

---

## Setup (5 Steps, ~30 minutes)

### Step 1 — Fork this repo
Click **Fork** at the top right of this page.

---

### Step 2 — Get your free API keys

| Key | Where to get it | Required? |
|-----|----------------|-----------|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) → API Keys | Yes |
| `GEMINI_API_KEY` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) → Create API key in new project | Yes (backup) |
| `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` | [developer.adzuna.com](https://developer.adzuna.com) → Free account | Optional |
| `RAPIDAPI_KEY` | [rapidapi.com](https://rapidapi.com) → Subscribe to JSearch free plan | Optional |

---

### Step 3 — Set up Google Sheets

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project → name it anything
3. Enable **Google Sheets API** and **Google Drive API**
4. Go to **IAM & Admin → Service Accounts → Create**
   - Name: `job-automation-bot` → Done
5. Click the service account → **Keys → Add Key → JSON → Download**
6. Create a Google Sheet named **"Job Automation Tracker"**
7. Share the sheet with the service account email (looks like `job-automation-bot@project.iam.gserviceaccount.com`) with **Editor** access

---

### Step 4 — Add GitHub Secrets

Go to your forked repo → **Settings → Secrets and variables → Actions → New repository secret**

Add these:

| Secret Name | Value |
|-------------|-------|
| `GROQ_API_KEY` | Your Groq key |
| `GEMINI_API_KEY` | Your Gemini key |
| `ADZUNA_APP_ID` | Your Adzuna app ID |
| `ADZUNA_APP_KEY` | Your Adzuna app key |
| `RAPIDAPI_KEY` | Your RapidAPI key |
| `LINKEDIN_EMAIL` | Your LinkedIn email |
| `LINKEDIN_PASSWORD` | Your LinkedIn password |
| `GOOGLE_SHEETS_CREDS` | Paste the entire contents of your downloaded `credentials.json` |

---

### Step 5 — Update your profile

Edit `.github/workflows/job-automation.yml` and update these lines with your details:

```yaml
CANDIDATE_NAME: Your Full Name
CANDIDATE_EMAIL: your@email.com
CANDIDATE_PHONE: +1-555-0100
CANDIDATE_SKILLS: Python,Docker,Kubernetes,AWS   # comma-separated
CANDIDATE_EXPERIENCE: "3"                         # years
SALARY_MIN: "80000"
SALARY_MAX: "120000"
MIN_SCORE: "40"    # 60 = strict, 30 = more volume
MAX_APPLY: "15"    # max applications per run
```

Also add your resume as `resume_base.docx` in the project root. Add a `[SUMMARY]` placeholder where your professional summary goes — the AI replaces it with a tailored version for each job.

---

## That's it!

Once secrets are added and profile is updated, the pipeline runs **automatically every 3 hours**.

Check your **Google Sheet** to see applied jobs, scores, and cover letters.

### Manual run (optional)
Go to **Actions → Job Automation → Run workflow** to trigger immediately.

---

## Tuning

| Setting | Effect |
|---------|--------|
| `MIN_SCORE: "60"` | Stricter — fewer but better matches |
| `MIN_SCORE: "30"` | More volume — applies to more jobs |
| `MAX_APPLY: "5"` | Conservative — 5 apps per run |
| `MAX_APPLY: "20"` | Aggressive — 20 apps per run |

Edit search queries in `main.py` under `CONFIG["search"]["queries"]` to target different roles.

---

## Job Sources

| Source | API Key | Notes |
|--------|---------|-------|
| RemoteOK | No | Remote only |
| Remotive | No | Remote only |
| We Work Remotely | No | Remote only |
| Himalayas | No | Remote only |
| Arbeitnow | No | Remote only |
| Adzuna | Yes (free) | US + Canada |
| JSearch (RapidAPI) | Yes (free) | LinkedIn + Indeed + more |

---

## Troubleshooting

**No jobs applied** — Check that Playwright installed correctly in the Actions log. LinkedIn/Indeed Easy Apply must be available on the job listing.

**Groq rate limit** — Free tier is 100K tokens/day. Resets at midnight UTC. Gemini kicks in as backup.

**Google Sheets error** — Make sure the sheet is shared with your service account email with Editor access.

**Adzuna returning 0 jobs** — Check your app_id and app_key are correct at developer.adzuna.com.
