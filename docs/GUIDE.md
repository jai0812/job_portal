# SharmaJai Job Portal: full guide

A local portal for your job search:

1. **Jobs**: new postings from 13 GitHub job lists (SimplifyJobs, SpeedyApply SWE and AI/ML, JobRight's new-grad and internship lists for software, data and accounting/finance, NU Fintech quant internships, vanshb03, and any others you add), plus LinkedIn through Apify. One table shows how old each posting is (hours or days), where it came from, and an Apply link. You can filter by:
   - **Category**: Software Engineering · Finance & Banks · Data Science & ML
   - **Level**: Internship · Early career / New grad · Experienced
   - **H‑1B**: Sponsors · Likely (based on the company's filing history) · No sponsorship · US citizens only
   - **Cap‑exempt** employers (universities, hospitals, national labs, research nonprofits)
   - **★ Top companies**, source, and status (new / saved / applied / hidden)
   - **Other H‑1B sponsors, tech roles only**: Nike, Disney, Verizon, T‑Mobile, Medtronic, Pfizer, Moderna, Illumina, Motorola Solutions, Thomson Reuters, Warner Bros. Discovery, Experian, Intuitive and NBCUniversal: only their IT / software / data / ML roles are kept.
   - Each row also has a **JR** button that looks the job up on JobRight AI.
   - **FAANG / MAANG and top tech, direct from their career sites** (`config/more_companies.yaml`): Amazon, Microsoft, Netflix, NVIDIA; big tech such as Salesforce, Adobe, Intel, Cisco, TikTok, LinkedIn and ServiceNow; and about 60 top tech companies such as Airbnb, Databricks, Snowflake, DoorDash, Anthropic and Waymo. Every company in these groups has USCIS FY2023 H‑1B approvals, except a small "AI labs (H‑1B not verified)" group (OpenAI, xAI, Cursor…). Google, Meta, Apple and Uber can't be read directly; they come from the GitHub lists and a LinkedIn (Apify) company search.
   - **Finance firm** column: 107 finance firms in 11 categories (broad banks, global banks, investment banking, asset managers, private markets, hedge funds/quant, market makers, exchanges, payments, financial data, fintech), from any source. Filter by category, or pick "Any finance firm".
   - **Direct from career sites:** 73 of these firms' own career sites (JPMorgan, Bank of America, Citi, BlackRock, Franklin Templeton, Jane Street, Visa, Stripe…) are pulled every hour, US jobs from the last 30 days. The source shows as "Company site". The firm list is in `config/finance_firms.yaml`.
1b. **🇮🇳 India** and **🌍 Other countries** tabs: the same table and filters (Data Science & ML, finance firms, level, posted time…) for jobs outside the US, with buttons by city (Bengaluru, Hyderabad, Pune, Mumbai, Delhi NCR, Chennai…) or by country. Sources include:
   - India offices of the finance firms above (JPMorgan, Citi, Deutsche Bank, Barclays, BlackRock, Mastercard, Visa, American Express, LSEG, S&P…)
   - Indian tech & fintech (Paytm, Meesho, CRED, Groww, Sarvam AI, InMobi, HighRadius, Sigmoid…) and big tech India teams (Amazon, NVIDIA, Salesforce, Adobe, Intel, Target), listed in `config/more_companies.yaml`
   - LinkedIn India searches through Apify, when you click the button

   The country is worked out from each job's location; a job listed in several countries appears on each matching tab.
1c. **Applied checkbox + 📊 Analytics**: tick the box on the left of any job to mark it applied (the date and time are saved). Use the stage dropdown for interviewing / offer / rejected. The Analytics tab shows:
   - totals, the last 7 days vs the previous 7, daily average, streak, interview rate, and % of applications to H‑1B sponsors
   - applications per day, and breakdowns by sector, finance firm category, pipeline stage, country, level, top companies, how fast you apply after posting, weekday and source
   - your recent applications, with a table view under every chart
2. **Universities**: jobs pulled straight from the career systems of Harvard, Stanford, Yale, UPenn, UChicago, CMU, Cornell, Northeastern, UW, UT Austin, Maryland and Rochester. For MIT, Princeton, Columbia, Caltech, JHU, Duke and others, the page shows a link to their careers site plus any matching postings from your other sources. You can filter by school, role type (Tech & Software, Data/AI, Research, Finance & Business) and posting age. University employers are usually H-1B **cap-exempt**. Schools are listed in `config/universities.yaml`.
3. **Ask All LLMs**: send one prompt to ChatGPT, Claude, Gemini and OpenRouter and see the answers side by side. It includes templates for a cover letter, a recruiter message, interview prep and a fit score.
4. **Quick-copy bar**: slides up from the bottom when you scroll (📌 keeps it visible). One click copies your LinkedIn, GitHub or a saved answer such as "Work authorization". It also has a notes area. Everything saves automatically to `data/profile.json`.

## Start

Double-click **Job Portal** on your Desktop. It starts the portal in the background if it isn't already running, then opens <http://localhost:8787>. The first time, macOS may ask to let "Job Portal" access your Documents folder. Click **Allow**.

The portal keeps running after you close the browser tab, and it refreshes every source (GitHub lists and universities) **every hour** (`auto_refresh_minutes` in `config/sources.yaml`). An open page picks up new jobs automatically.

- **Start at login:** open System Settings → General → Login Items and add `Job Portal` from your Desktop.
- **Rebuild the Desktop app** (for example, after moving the folder):

```bash
./desktop/install.sh
```

- **Start without the Desktop app:**

```bash
./run.sh
```

- **Stop the portal:**

```bash
pkill -f "uvicorn app.main:app"
```

## Running it online (optional)

The portal only listens on this Mac. To use it from anywhere on your own domain, see **[DEPLOY.md](../DEPLOY.md)**. First turn on the built-in
password protection:

```bash
.venv/bin/python scripts/set_password.py --2fa
```

That adds a sign-in page (password stored only as a scrypt hash, optional authenticator-app codes, lockout after wrong attempts,
expiring sessions, cross-site request blocking). The portal refuses to start on a public address without a password.

## Keys (`.env`)

| Key | What it enables |
|---|---|
| `OPENAI_API_KEY` | ChatGPT answers in "Ask All LLMs" |
| `ANTHROPIC_API_KEY` | Claude answers in "Ask All LLMs" |
| `APIFY_TOKEN` | "Fetch LinkedIn (Apify)" button |
| `GEMINI_API_KEY`, `OPENROUTER_API_KEY` | Extra models in "Ask All" |

**API keys are not free, and ChatGPT Plus/Pro and Claude Pro do not include them.** Each key needs credit added on its billing page (platform.openai.com → Billing, console.anthropic.com → Plans & Billing). They're only used by **Ask All LLMs**; without a key, that tab gives you **Copy prompt** and **Open ChatGPT/Claude** buttons instead, which work with your subscriptions.

After editing `.env`, stop the portal (the `pkill` command above) and double-click **Job Portal** again so it picks up the new keys.

## Job sources

- Add GitHub lists from **Settings**, or edit `config/sources.yaml`. The portal handles SimplifyJobs-style `listings.json` files and README tables (Markdown or HTML).
- GitHub lists refresh every 60 minutes while the portal runs (`auto_refresh_minutes`).
- Apify only runs when you click its button, because each run uses Apify credits. The searches are listed in `config/sources.yaml`.
- To pull jobs without the UI running:

```bash
.venv/bin/python scripts/fetch_jobs.py
```

  Add `--apify` to that command to include the LinkedIn searches.
- The top‑company, finance, H‑1B sponsor and cap‑exempt lists are in `config/companies.yaml`. Add companies there.

### Posted time and source
- **Posted**: a short age (`12m`, `3h`, `0d`, `2d`), the same in words ("12 min ago", "Today"), and the date. The SimplifyJobs lists, Harvard and LinkedIn give an exact time. SpeedyApply, Workday universities and Stanford only give the day, so those show "Today", "Yesterday" or "N days ago" rather than a made-up time.
- **Source**: the type (GitHub / Apify · LinkedIn / University site / Added by you), the list name, when the portal first found the job, and "+ N more lists" if the same job appears on several lists. The date always comes from the most precise list.

### How the tags are decided
- **H‑1B**: the posting's own words take priority ("does not offer sponsorship", "US citizenship required", "clearance", "will sponsor", or the 🛂/🇺🇸 icons on GitHub lists). Otherwise the portal shows the employer's real **USCIS H‑1B approvals for FY2023** (initial + continuing, from the [H‑1B Employer Data Hub](https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub), stored in `config/h1b_fy2023.json`). Finance firms use their exact legal entities; other companies are matched by name, which is approximate. With no record, it's **Unknown**. Past sponsorship doesn't guarantee a specific role sponsors, so always confirm with the employer.
- **Cap‑exempt** is a guess from the employer's name (university, medical center, national lab…). Confirm it with the employer.
- **Level/category** come from the job title, the list it came from, and the company (for example, any role at a bank also appears under Finance & Banks).

## Layout
```
app/main.py          API + pipeline endpoints
app/fetchers/        github.py, apify.py
app/classify.py      category / level / H-1B / cap-exempt tagging
app/llm.py           ChatGPT, Claude, Gemini, OpenRouter
app/fetchers/careers.py     career-site readers: Workday, Oracle, SmartRecruiters, Greenhouse, Lever, Ashby, Phenom
app/finance.py       finance firm matching · app/h1b.py  USCIS H-1B approval lookup · app/geo.py  country detection
config/*.yaml        sources, company lists, universities
desktop/             Desktop launcher (AppleScript) + icon
data/                jobs.db, profile.json (quick-copy bar), server.log
```
