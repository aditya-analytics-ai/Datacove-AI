# Frontend Architecture & Contents

**Framework:** React 18.3.1  
**Build Tool:** Vite 5.2.11  
**Routing:** React Router 6.23.1  
**UI Grid:** ag-grid-react 35.1.0  
**Charts:** Recharts 2.12.0  
**Node Version:** Latest (per package.json)  

---

## Directory Structure

```
frontend/
├── package.json                 # NPM dependencies & scripts
├── vite.config.js              # Vite build configuration
├── index.html                  # HTML entry point
│
├── src/
│   ├── main.jsx               # React app initialization
│   ├── App.jsx                # Root component with routing
│   │
│   ├── pages/                 # [5 Full-page components]
│   │   ├── UploadPage.jsx     # Dataset upload & initial processing
│   │   ├── Dashboard.jsx      # Main analysis dashboard
│   │   ├── DatasetsPage.jsx   # Dataset management & history
│   │   ├── BillingPage.jsx    # Subscription & payment
│   │   └── AdminPage.jsx      # Admin controls (user mgmt)
│   │
│   ├── components/            # [30+ Reusable components]
│   │   ├── AuthModal.jsx      # Login/register modal
│   │   ├── ErrorBoundary.jsx  # Error catching wrapper
│   │   │
│   │   ├── SpreadsheetGrid.jsx        # Data grid (ag-grid v35)
│   │   ├── StreamProgressBar.jsx      # Upload progress tracking
│   │   │
│   │   ├── CleaningToolbar.jsx        # Cleaning operations UI
│   │   ├── AutoCleanReport.jsx        # Auto-clean results
│   │   ├── BatchCleanPanel.jsx        # Batch operations
│   │   ├── ValidationPanel.jsx        # Rule validation UI
│   │   ├── SchemaApplyPanel.jsx       # Schema application
│   │   │
│   │   ├── ProfilingCharts.jsx        # Statistical charts
│   │   ├── ColumnQuality.jsx          # Column quality metrics
│   │   ├── CorrelationPanel.jsx       # Correlation heatmap
│   │   ├── VisualizationDashboard.jsx # Recharts-based viz
│   │   ├── DataIntelligencePanel.jsx  # Stats & insights
│   │   ├── HealthScoreCard.jsx        # Quality score display
│   │   │
│   │   ├── AIAgentPanel.jsx           # Automated cleaning UI
│   │   ├── AIInsightsPanel.jsx        # AI recommendations
│   │   ├── AICommandCenter.jsx        # AI command interface
│   │   ├── AIChatBox.jsx              # Natural language chat
│   │   ├── AIMLPanel.jsx              # ML training UI
│   │   │
│   │   ├── FuzzyDedupPanel.jsx        # Fuzzy dedup control
│   │   ├── PIIDetectorPanel.jsx       # PII detection & masking
│   │   ├── PatternLibraryPanel.jsx    # Pattern matching
│   │   ├── PowerToolsPanel.jsx        # Advanced features
│   │   ├── SQLPanel.jsx               # SQL query editor
│   │   │
│   │   ├── ConnectorsPanel.jsx        # Data connectors (S3, GSheets)
│   │   ├── OnboardingPanel.jsx        # Sample datasets
│   │   ├── SampleDatasetsPanel.jsx    # Sample data browser
│   │   │
│   │   ├── ExplanationToast.jsx       # Toast notifications
│   │   ├── JobPoller.jsx              # Background job monitor
│   │   ├── HistoryPanel.jsx           # Session history
│   │   ├── LineagePanel.jsx           # Data lineage visualization
│   │   ├── PipelineManager.jsx        # Workflow builder
│   │   ├── SharePanel.jsx             # Dataset sharing UI
│   │   └── ReportPanel.jsx            # Report generation
│   │
│   ├── services/              # [2 Service modules]
│   │   ├── api.js             # Axios HTTP client + all endpoints
│   │   └── vite.config.js     # Build configuration
│   │
│   └── hooks/                 # [1 Custom hook]
│       └── useStreamingTransform.js  # Streaming upload hook
│
└── node_modules/              # [Installed dependencies]
```

---

## Core Components

### 📌 Entry Points

**`main.jsx`**
- React DOM initialization
- Mounts App to #root

**`App.jsx`**
- Global CSS (theme tokens, colors, fonts)
- AuthModal rendered (now inside BrowserRouter)
- BrowserRouter with 5 routes:
  - `/` → UploadPage
  - `/dashboard` → Dashboard
  - `/datasets` → DatasetsPage
  - `/billing` → BillingPage
  - `/admin` → AdminPage (admin only)
- Authentication state management (needsAuth, authReady)

### 🔐 Authentication: `AuthModal.jsx`
- Login form
- Register form  
- Error handling
- Token storage (localStorage)
- Calls `authMe()` to verify current session
- Sets bearer token on `setAuthToken()`

### 📊 Dashboard: `Dashboard.jsx`
- Primary analysis interface
- Tabbed UI for different analysis views
- Sidebar with feature toggles
- Main grid + charts area
- Real-time updates via WebSocket (optional)

### 📈 Data Grid: `SpreadsheetGrid.jsx` [FIXED v7]
- ag-grid v35 integration
- Community edition (free)
- **Now uses clientSide row model** (removed InfiniteRowModelModule)
- Features:
  - Inline cell editing
  - Right-click context menu
  - Column reordering & pinning
  - Header sparklines
  - Quality color coding
  - Selection & multi-select

### 📉 Visualization: `VisualizationDashboard.jsx`
- Recharts integration
- Multiple chart types:
  - Line charts (trends)
  - Bar charts (distributions)
  - Scatter plots (correlations)
  - Heatmaps (anomalies)
- Responsive sizing
- Tooltip & legend support

### 🤖 AI Components
- **AIChatBox.jsx** — Natural language interface
- **AIAgentPanel.jsx** — Automated cleaning trigger
- **AICommandCenter.jsx** — Advanced AI commands
- **AIInsightsPanel.jsx** — Recommendations display
- **AIMLPanel.jsx** — ML model training UI

### 🛠️ Cleaning & Operations
- **CleaningToolbar.jsx** — UI for cleaning operations
- **BatchCleanPanel.jsx** — Bulk operation application
- **FuzzyDedupPanel.jsx** — Deduplication settings
- **ValidationPanel.jsx** — Rule-based validation
- **SchemaApplyPanel.jsx** — Schema enforcement

### 📡 Data Connection: `ConnectorsPanel.jsx`
- S3 bucket browser
- Google Sheets picker
- SQL database connector
- File upload from external sources

### 📋 Sharing & Collaboration: `SharePanel.jsx`
- Share link generation
- Permission management
- Fork dataset
- Revoke access

### 📅 Workflow & Scheduling
- **PipelineManager.jsx** — DAG builder
- **HistoryPanel.jsx** — Session history browser
- **LineagePanel.jsx** — Data lineage viewer

---

## Services Layer

### `api.js` — HTTP Client

**Axios Instance Configuration:**
- Base URL: `http://localhost:5173/api` (dev) or `/api` (prod)
- Timeout: 120 seconds
- Response type: JSON or blob (for downloads)

**Authentication Functions:**
```javascript
✓ authMe()              — Get current user
✓ authRegister()        — Create account
✓ authLogin()           — Login with credentials
✓ authRefresh()         — Refresh JWT token
✓ authLogout()          — Logout & clear token
✓ setAuthToken()        — Set bearer token
```

**Upload & Analysis:**
```javascript
✓ uploadDataset(file)   — Multipart upload
✓ fetchSummary()        — Quick summary (polling-safe)
✓ analyzeDataset()      — Full analysis
✓ fetchProfile()        — Column statistics
✓ compareDatasets()     — A vs B comparison
```

**Cleaning Operations:**
```javascript
✓ cleanDataset()        — Apply cleaning
✓ autoClean()          — Automated cleaning
✓ applyFormulaColumn() — Create computed column
✓ deduplicateDataset() — Fuzzy dedup
```

**Advanced Features:**
```javascript
✓ detectPII()          — PII detection
✓ maskPII()            — PII masking
✓ runAIAgent()         — Automated agent
✓ aiNLClean()          — NL command execution
✓ trainModel()         — ML training
✓ generateReport()     — PDF generation
✓ downloadExport()     — File download
```

**Error Handling:**
- Global error interceptor
- Blob response parsing for download errors
- 429 (rate limit) detection
- 401 (auth) redirect to login
- Network error fallback

**Token Normalization:**
```javascript
// Backward compatibility
if (data.access_token && !data.token) {
    data.token = data.access_token;
}
```
Kept in login/refresh, removed duplicate from register.

---

## State Management

### Local State (React hooks)
- Component-level `useState` for UI state
- `useContext` for auth context (via App.jsx)

### Persistent State
- `localStorage`:
  - `dc_token` — JWT access token
  - `dc_refresh` — Refresh token
  - Theme preferences (optional)
  - Last session ID

### Backend State
- MySQL for user data
- Redis for session caching
- Session files in backend/datasets/

---

## Dependencies

**Core:**
- react@18.3.1, react-dom@18.3.1
- react-router-dom@6.23.1

**UI Components:**
- ag-grid-react@35.1.0, ag-grid-community@35.1.0
- lucide-react@0.383.0 (icons)
- framer-motion@12.38.0 (animations)

**Data & Charts:**
- recharts@2.12.0 (chart library)
- axios@1.6.8 (HTTP client)

**Development:**
- vite@5.2.11 (build tool)
- @vitejs/plugin-react@4.3.0 (React plugin)
- eslint@8.57.0 (linting)

---

## Component Patterns

### Typical Component Structure
```jsx
export default function MyComponent({ sessionId, onComplete }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  async function handleAction() {
    try {
      setLoading(true);
      const result = await apiFunction(sessionId);
      setData(result);
      onComplete?.(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="panel">
      {loading && <Loader2 className="spin" />}
      {error && <div className="error">{error}</div>}
      {data && <Results data={data} />}
      <button onClick={handleAction}>Execute</button>
    </div>
  );
}
```

### Styling Approach
- **Global theme CSS** in App.jsx (CSS variables)
- **Inline styles** for dynamic styling
- **Utility classes** for common patterns
- **ag-theme-quartz-dark** for data grid

**Theme Variables:**
```css
--bg: #06080c                    /* Background */
--surface-1/2/3: #0d1017 etc     /* Surface layers */
--text-0/1/2/3: #f8fafc etc      /* Text colors */
--accent: #6366f1                /* Primary color */
--accent-light: #818cf8
--accent-hover: #4f46e5
--green: #22c55e                 /* Status colors */
--amber: #f59e0b
--red: #ef4444
--radius-sm/md/lg/xl: 6px etc    /* Border radius */
--shadow-sm/md/lg: 0 4px 12px... /* Shadows */
```

---

## Build & Deployment

### Development
```bash
cd frontend
npm install
npm run dev          # Starts Vite dev server on :5173
```

### Production Build
```bash
npm run build        # Outputs to dist/
npm run preview      # Preview built version
```

### Vite Configuration (`vite.config.js`)
- React plugin enabled
- HMR (Hot Module Replacement) for dev
- Optimized build output
- Proper source maps

### Build Output
- `dist/index.html` — HTML entry
- `dist/assets/index-*.js` — Bundled JS
- `dist/assets/index-*.css` — Bundled CSS
- All assets hashed for cache busting

---

## Environment Variables

**`.env` (Development):**
```
VITE_API_URL=http://localhost:8000/api
```

**Build Time Variables:**
- Accessible via `import.meta.env.VITE_*`
- Substituted at build time (not runtime)

---

## Error Handling

### AuthModal Errors
- Network errors show "Backend unavailable"
- 401/403 prompts re-login
- General errors show detail message

### Component Errors
- ErrorBoundary wraps all pages
- Caught errors show fallback UI
- Allows recovery without full page reload

### API Errors
- 4xx errors logged to console
- User-friendly messages in toast
- Rate limit (429) shows "Retry after X seconds"

---

## Performance Optimizations

✅ **Code Splitting** — Lazy-loaded route components  
✅ **Memoization** — useMemo for expensive computations  
✅ **Image Optimization** — Lucide icons (SVG)  
✅ **Bundle Size** — Tree-shaking, minification  
✅ **Streaming** — Chunked uploads (50-100KB/chunk)  
✅ **Caching** — localStorage for tokens & preferences  

---

## Security

✅ **HTTPS-ready** (configure in production)  
✅ **JWT storage** in localStorage  
✅ **CORS headers** validated by backend  
✅ **No secrets in code** (env vars only)  
✅ **XSS protection** (React auto-escapes)  
✅ **CSRF** (backend validates origin)  

---

## Responsive Design

- **Mobile-first** approach
- **Flexible grid layouts** (CSS Grid/Flexbox)
- **Adaptive components** (hide/show based on screen size)
- **Touch-friendly** buttons & interactions
- **Tested on:** Desktop, Tablet, Mobile

---

## Accessibility (a11y)

- ✅ Semantic HTML (`<button>`, `<form>`, etc.)
- ✅ ARIA labels for interactive elements
- ✅ Keyboard navigation support
- ✅ Color contrast ratios (WCAG AA)
- ✅ Focus indicators visible

---

## Browser Support

- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)
- Mobile browsers (iOS Safari, Chrome Mobile)

---

## Development Status

**Phase 2 Completed:**
- ✅ Data upload & profiling
- ✅ Interactive data grid
- ✅ Cleaning operations
- ✅ Analysis visualizations
- ✅ AI agent integration
- ✅ Sharing & export

**Phase 3 Features:**
- ✅ Connectors (S3, GSheets, DB)
- ✅ Onboarding (sample datasets)
- ✅ Sharing & collaboration
- ✅ Billing page
- ✅ Admin controls
- ✅ SQL query panel

**Bugs Fixed (Latest Session):**
- ✅ Removed InfiniteRowModelModule (ag-grid v35)
- ✅ Moved AuthModal inside BrowserRouter
- ✅ Removed duplicate token normalization

---

## Quick Start

```bash
# Install dependencies
npm install

# Start dev server
npm run dev
# → Vite server running on http://localhost:5173

# Build for production
npm run build

# Lint code
npm run lint

# API Docs
# http://localhost:8000/docs (Swagger)
# http://localhost:8000/redoc (ReDoc)
```

**Status:** ✅ **Production Ready** — All tests pass, builds succeed, no errors.
