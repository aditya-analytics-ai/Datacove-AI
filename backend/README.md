# Datacove 🔷

> **Clean messy data in seconds — AI-native data quality platform.**

Datacove lets you upload a CSV or Excel file, instantly profile it, score its quality, and apply smart transformations — with AI suggestions, natural language commands, undo/redo, pipelines, and dataset comparison.

---

## ✨ Features

| Feature | Description |
|---|---|
| **Dataset Profiling** | Column types, missing %, unique counts, value distributions |
| **Health Score** | 0–100 quality grade with penalty breakdown |
| **Issue Detection** | Duplicates, missing values, whitespace, invalid emails/phones, mixed types |
| **Auto-Clean** | One-click safe cleaning suite |
| **Anomaly Detection** | IQR-based statistical outlier detection |
| **AI Suggestions** | LLM-powered recommendations (rule-based fallback if no API key) |
| **Natural Language Commands** | Type `remove duplicate emails` → AI generates the transform |
| **Transformation History** | Full undo stack with history panel |
| **Pipelines** | Save & rerun cleaning workflows |
| **Dataset Comparison** | Diff two datasets — new rows, removed rows, changed cells, column changes |
| **Export** | Download cleaned data as CSV or Excel |

---

## 🏗 Project Structure

```
datacove/
├── backend/
│   ├── main.py                    # FastAPI app + CORS
│   ├── config.py                  # Environment-driven config
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── .env.example
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── upload_routes.py       # POST /api/upload
│   │   ├── analysis_routes.py     # POST /api/profile, /analyze, /nl-command
│   │   │                          # GET  /api/summary
│   │   │                          # POST /api/compare
│   │   ├── cleaning_routes.py     # POST /api/clean, /auto-clean, /undo, /reset
│   │   ├── export_routes.py       # GET  /api/export
│   │   └── pipeline_routes.py     # GET/POST /api/pipelines, POST /api/pipelines/run
│   ├── services/
│   │   ├── __init__.py
│   │   ├── dataset_loader.py
│   │   ├── profiling_engine.py
│   │   ├── issue_detector.py
│   │   ├── cleaning_engine.py
│   │   ├── health_score.py
│   │   ├── anomaly_detector.py
│   │   ├── ai_suggestions.py
│   │   └── pipeline_engine.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── dataset_session.py
│   │   └── pipeline_model.py
│   └── utils/
│       ├── __init__.py
│       ├── file_utils.py
│       └── validation_utils.py
│
└── frontend/                      # React + Vite + AG Grid
    ├── index.html
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── main.jsx
        ├── App.js                 # Router + global CSS variables
        ├── services/
        │   └── api.js             # Axios service layer
        ├── pages/
        │   ├── UploadPage.jsx     # Drag-and-drop upload
        │   └── Dashboard.jsx      # Main workspace
        └── components/
            ├── SpreadsheetGrid.jsx    # AG Grid integration
            ├── CleaningToolbar.jsx    # Actions + NL input + export
            ├── AIInsightsPanel.jsx    # Suggestions / issues / anomalies
            ├── HealthScoreCard.jsx    # Animated score gauge
            ├── DatasetSummary.jsx     # Stats strip
            └── PipelineManager.jsx   # Pipeline list + create + run
```

---

## 🚀 Quick Start

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — add OPENAI_API_KEY if you want AI features

uvicorn main:app --reload --port 8000
```

Swagger docs: **http://localhost:8000/docs**

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App: **http://localhost:5173**

> Vite proxies `/api/*` → `http://localhost:8000` automatically.

### Docker (both together)

```bash
docker-compose up --build
```

---

## 🔌 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/upload` | Upload CSV/Excel → `session_id` + preview |
| `POST` | `/api/profile` | Full column-level profile |
| `POST` | `/api/analyze` | Issues + health + anomalies + AI suggestions |
| `GET`  | `/api/summary?session_id=` | Lightweight summary (safe to poll) |
| `POST` | `/api/compare` | Diff two sessions — new/removed rows, cell changes |
| `POST` | `/api/nl-command` | Natural language → structured action |
| `POST` | `/api/clean` | Apply a single transformation |
| `POST` | `/api/auto-clean` | Full safe cleaning suite |
| `POST` | `/api/undo` | Undo last transformation |
| `POST` | `/api/reset` | Reset to original upload |
| `GET`  | `/api/export?session_id=&fmt=csv` | Download cleaned dataset |
| `GET`  | `/api/pipelines` | List saved pipelines |
| `POST` | `/api/pipelines` | Create pipeline |
| `POST` | `/api/pipelines/run` | Run pipeline on session |

---

## ⚙️ Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | _(empty)_ | Enables AI suggestions + NL commands |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model used for AI features |
| `MAX_UPLOAD_BYTES` | `52428800` | 50 MB upload limit |
| `MAX_ROWS` | `100000` | Row limit per dataset |
| `UPLOAD_DIR` | `/tmp/datacove_uploads` | Temp storage path |

---

## 🧹 Available Cleaning Actions

| Action | Description |
|---|---|
| `remove_duplicates` | Drop exact duplicate rows |
| `trim_whitespace` | Strip + collapse whitespace in string columns |
| `standardise_capitalisation` | title / upper / lower case |
| `normalise_categories` | Merge category variants by canonical form |
| `fill_missing` | mean / median / mode / value / drop strategy |
| `coerce_numeric` | Force numeric, NaN on failures |
| `standardise_dates` | Parse mixed formats → ISO 8601 |
| `flag_invalid_emails` | Add `{col}_invalid` boolean column |
| `rename_column` | Rename a column |
| `drop_column` | Remove a column |
| `drop_rows_where` | Filter rows by value match |

---

## 📄 License

MIT
