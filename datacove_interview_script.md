# 🎤 Datacove AI — Interview Script

> **How to use this:** Read through it tonight so it feels natural. Don't memorize word-for-word — internalize the *flow* and the *key phrases* marked in **bold**. Adapt to the interviewer's energy.

---

## 1. 🚀 Elevator Pitch (30 seconds)

> *Use this when they say "Tell me about a project you've worked on."*

"I built **Datacove AI** — an end-to-end, AI-native data quality platform. The idea is simple: every data team spends a huge chunk of time just cleaning and validating data before they can do anything useful with it. Datacove automates that entire process. You upload a CSV or connect a data source, and the platform **automatically profiles your dataset, detects quality issues, generates AI-powered fix suggestions, and lets you apply them in one click** — all without writing a single line of code. It's built with a FastAPI backend, a React frontend, and integrates with Claude/Anthropic for the AI features."

---

## 2. 🏗️ Architecture Overview (1–2 minutes)

> *Use when asked "Walk me through the architecture" or "How is it built?"*

"The project has two main layers:

**Backend — FastAPI (Python):**
- It's organized around **20+ route files** and **60+ service modules**, each handling a focused responsibility.
- Core services include: a `profiling_engine` for column-level statistics, a `cleaning_engine` for 35+ automated transformations, an `issue_detector` and `anomaly_detector` for flagging data quality problems, and an `ai_suggestions` service that wraps the Anthropic API to generate context-aware fix recommendations.
- Authentication is JWT-based with PBKDF2-SHA256 password hashing, and sessions are **user-scoped** — so users can only access their own datasets.
- Data is persisted in SQLite so sessions survive server restarts.

**Frontend — React + Vite:**
- 25+ panel components including an `AIInsightsPanel` that shows suggestions, detected issues (with severity tagging), anomalies with sparkline mini-charts, and schema inference results — all collapsible and interactive.
- The NL command flow is **two-step: parse first, confirm second** — so the AI never blindly mutates your data.

**Infrastructure:**
- Fully Dockerized with `docker-compose` for local dev.
- Supports external connectors: Google Sheets, AWS S3, SQL databases, and raw URLs.
- Export destinations include Airtable, Notion, Slack, and Google Sheets."

---

## 3. 🔍 Key Features Deep Dive

> *Pick 2–3 of these based on what the interviewer seems interested in.*

### Feature A — AI-Powered Data Profiling & Issue Detection
"When you upload a dataset, the profiling engine runs **column-level analysis automatically** — it detects semantic types like email, phone, date, currency, and country using heuristics. It computes missing value rates, unique value counts, numeric stats (min, max, mean, std, percentiles), and even generates **8-bar sparkline histograms** for outlier visualization. The issue detector then flags problems like duplicate rows, mixed data types, invalid emails, encoding garbage, date format inconsistencies, and unexpected negatives in positive columns — all severity-ranked as high, medium, or low."

### Feature B — Smart Auto-Clean Engine
"The cleaning engine is the heart of the product. It has **35+ cleaning operations** — things like stripping whitespace, standardizing date formats, removing duplicate rows, fixing encoding issues, casting column types, and replacing outliers with median values. What makes it 'smart' is the `SmartAutoClean` service, which combines rule-based domain knowledge with learned patterns to auto-select the right operations for a given dataset without needing user input."

### Feature C — AI Suggestions & NL Commands
"The AI layer sits on top of the profiling and issue detection results. It sends structured context to the Anthropic API and gets back prioritized, actionable suggestions — things like 'This column looks like a date but is stored as text — cast it to datetime.' The user sees these suggestions in the panel with an Apply button. There's also a **natural language command interface** where you can type something like 'remove all rows where revenue is negative' — but crucially, it **parses and previews the change first, then requires confirmation before applying** — so there's a human in the loop."

### Feature D — Pipelines, Scheduling & Sharing
"For teams, there's a **visual pipeline builder** where you can chain cleaning steps into a repeatable workflow. These pipelines can be scheduled with cron expressions or triggered via webhooks. There's also a **sharing system** where you can generate share links with view or fork permissions, set expiry dates, and revoke access — it's designed for collaborative data work."

### Feature E — Security & Multi-tenancy
"Security was a Phase 1 priority. Every route is protected by an auth dependency. Passwords are hashed with PBKDF2-SHA256 and salted per user. CORS is locked to configured origins — not wildcard. Sessions are **stamped with an owner_id**, and any cross-user access returns a 403. The platform also has a PII detector to flag sensitive columns like SSNs and credit card numbers."

---

## 4. 💡 Technical Decisions & Trade-offs

> *Use when asked "Why did you choose X?" or "What was your hardest technical challenge?"*

**Q: Why FastAPI over Django or Flask?**
> "FastAPI gave me async support out of the box, automatic OpenAPI docs at `/docs`, and Pydantic validation — which is critical when you're dealing with unpredictable user-uploaded data. Django would have been overkill for an API-first backend."

**Q: Why SQLite for persistence?**
> "It was a deliberate trade-off for simplicity in the early stages. SQLite is zero-config, survives restarts, and is perfectly adequate for single-server deployments. The architecture is designed so swapping to PostgreSQL would be a config change, not a rewrite."

**Q: What was the hardest challenge?**
> "The hardest part was the **SmartAutoClean engine**. Data quality issues are incredibly domain-specific — a column called 'price' has different cleaning rules than one called 'phone_number'. I had to build a layered system: first detect semantic type, then apply domain-specific rules, then fall back to generic cleaning. Getting that heuristic stack right without false positives took several iterations and a lot of testing against real-world datasets."

**Q: How did you handle the NL command parsing safely?**
> "The two-step parse-then-confirm flow. The backend parses the natural language into a structured operation object — essentially a diff of what would change — and returns that to the frontend for the user to review before anything is committed. This prevents the AI from making irreversible changes to production data."

---

## 5. 📊 Impact & Metrics

> *Use when asked "What was the outcome?" or "Did it work?"*

"The platform has **35+ unit tests** covering the cleaning engine, health scoring, and auth. The cleaning engine handles 35+ distinct data quality operations. The profiling engine runs column-level analysis in milliseconds on typical CSVs. In terms of scope — it's a full-stack product with a 20-route API, 60+ backend services, 25+ frontend components, Docker support, external integrations, billing tiers, and a sharing system. It's production-ready, not a toy."

---

## 6. 🧠 Closing Statement

> *Use at the end, or if asked "Is there anything else you'd like to share?"*

"What I'm most proud of with Datacove is that it solves a genuinely painful problem — data quality is estimated to cost businesses trillions of dollars annually, and yet most teams still handle it manually or with brittle scripts. Building an AI-native tool that automates this end-to-end, with a clean UX and a robust backend, was both technically challenging and commercially meaningful. It's the kind of project that sharpened my skills in API design, AI integration, data engineering, and product thinking all at once."

---

## 7. ❓ Likely Follow-up Questions

| Question | Quick Answer |
|---|---|
| "How does it scale?" | Batch processor + streaming engine for large files; designed for horizontal scaling |
| "What LLM do you use?" | Anthropic Claude (via `ANTHROPIC_API_KEY`), but the AI layer is abstracted so it's swappable |
| "What's the tech stack exactly?" | FastAPI + Python 3.12 / React + Vite / SQLite / Docker / Anthropic |
| "How do you handle large files?" | `batch_processor.py` + `streaming_engine.py` for chunked processing |
| "What about data privacy?" | PII detector flags sensitive columns; all data is user-scoped; JWT-gated |
| "Would you add X feature?" | Always say yes and explain how — shows product thinking |
| "What would you do differently?" | "I'd add a proper PostgreSQL layer earlier, and invest in E2E tests sooner." |

---

## 8. 📝 Quick-Reference Cheat Sheet

```
Product:    Datacove AI — AI-native data quality platform
Backend:    FastAPI, Python 3.12, SQLite, JWT auth, 20 routes, 60 services
Frontend:   React + Vite, 25 components
AI:         Anthropic Claude — suggestions, NL commands, schema inference
Cleaning:   35+ operations via SmartAutoClean engine
Key flows:  Upload → Profile → Detect Issues → AI Suggest → Confirm → Apply
Integrates: Google Sheets, AWS S3, SQL DBs, Airtable, Notion, Slack
Security:   JWT, PBKDF2-SHA256, CORS, user-scoped sessions, PII detection
Tests:      35+ pytest unit tests
```

---

> **💪 Good luck tomorrow! You know this product inside out — trust yourself.**
