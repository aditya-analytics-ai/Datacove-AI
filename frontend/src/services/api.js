/**
 * api.js — Axios service layer for the Datacove AI API v2.
 * All functions return the `data` payload from the Axios response.
 *
 * Fixed in v2:
 *  - downloadExport / downloadVersion / downloadReport now use
 *    axios with responseType:"blob" + URL.createObjectURL() instead
 *    of building a bare <a href> and clicking it.
 *
 *    The old anchor-tag approach had two problems:
 *      1. It never sent the Authorization header, breaking auth-enabled
 *         deployments silently (the server returned 401, the browser
 *         showed nothing, no file appeared).
 *      2. For binary responses (xlsx) the browser occasionally treated
 *         the response as a navigation rather than a download, especially
 *         in Safari or when CORS preflight was involved.
 *
 *    The blob approach routes everything through the same axios instance,
 *    so all request headers (auth, custom) are sent correctly, and the
 *    file is always downloaded regardless of MIME type.
 */
import axios from "axios";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "/api",
  timeout: 120_000,
});

// ── Global error interceptor ───────────────────────────────────────────────
function extractErrorMessage(data) {
  if (typeof data?.detail === "string") return data.detail;
  if (typeof data?.detail?.msg === "string") return data.detail.msg;
  if (Array.isArray(data?.detail)) {
    return data.detail.map(e => e.msg || JSON.stringify(e)).join(", ");
  }
  return null;
}

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const status  = error.response?.status;
    // Blob responses wrap errors as Blobs — parse them back to text
    const rawDetail = error.response?.data instanceof Blob
      ? "(download failed — see network tab)"
      : error.response?.data?.detail;
    const detail = extractErrorMessage(error.response?.data) ?? rawDetail;

    if (status === 429) {
      const retryAfter = error.response?.headers?.["retry-after"] ?? "60";
      console.warn(`AI rate limit hit. Retry after ${retryAfter}s`);
    } else if (status >= 500) {
      console.error("Server error:", detail ?? error.message);
    } else if (status === 404) {
      console.warn("Session not found — may need re-upload.");
    } else {
      console.error("API Error:", detail ?? error.message);
    }

    return Promise.reject(error);
  }
);

// ── Upload ─────────────────────────────────────────────────────────────────

export async function uploadDataset(file, onProgress) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await client.post("/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (evt) => {
      if (onProgress && evt.total)
        onProgress(Math.round((evt.loaded * 100) / evt.total));
    },
  });
  return data;
}

// ── Analysis ───────────────────────────────────────────────────────────────

/** Full analysis: profile + issues + health + anomalies + suggestions */
export async function analyzeDataset(sessionId) {
  const { data } = await client.post("/analyze", { session_id: sessionId });
  return data;
}

/** Lightweight summary — safe to poll */
export async function fetchSummary(sessionId) {
  const res = await client.get("/summary", {
    params: { session_id: sessionId },
    validateStatus: s => s === 200 || s === 202,  // 202 = not ready yet, retry silently
  });
  if (res.status === 202) throw Object.assign(new Error("not_ready"), { code: "NOT_READY" });
  return res.data;
}

/** Full column-level profile */
export async function fetchProfile(sessionId) {
  const { data } = await client.post("/profile", { session_id: sessionId });
  return data;
}

/** Compare two sessions */
export async function compareDatasets(sessionIdA, sessionIdB) {
  const { data } = await client.post("/compare", {
    session_id_a: sessionIdA,
    session_id_b: sessionIdB,
  });
  return data;
}

/** Parse a NL command into a structured action */
export async function sendNLCommand(sessionId, command) {
  const { data } = await client.post("/nl-command", { session_id: sessionId, command });
  return data;
}

// ── Cleaning ───────────────────────────────────────────────────────────────

export async function applyTransformation(sessionId, action, params = {}) {
  const { data } = await client.post("/clean", { session_id: sessionId, action, params });
  return data;
}

export async function autoClean(sessionId) {
  const { data } = await client.post("/auto-clean", { session_id: sessionId });
  return data;
}

export async function undoTransformation(sessionId) {
  const { data } = await client.post("/undo", { session_id: sessionId });
  return data;
}

export async function resetDataset(sessionId) {
  const { data } = await client.post("/reset", { session_id: sessionId });
  return data;
}

/** Inline cell edit — single cell or propagate to all matching values */
export async function editCell(sessionId, rowIndex, column, value, propagate = false) {
  const { data } = await client.post("/edit-cell", {
    session_id: sessionId, row_index: rowIndex,
    column, value, propagate,
  });
  return data;
}

// ── Export ─────────────────────────────────────────────────────────────────

/**
 * Internal helper — fetch a binary/text file via axios and trigger a
 * browser download using a temporary Blob URL.
 *
 * Using axios (instead of a bare <a href>) means:
 *  - Authorization and all other request headers are sent automatically.
 *  - Works for both text (CSV/JSON) and binary (XLSX) responses.
 *  - Errors surface as rejected promises with proper status codes.
 */
const MIME_TYPES = {
  csv:  "text/csv",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  json: "application/json",
};

async function _blobDownload(path, params, fallbackFilename) {
  const response = await client.get(path, {
    params,
    responseType: "blob",
    timeout: 180_000,   // give large files extra time
  });

  // When the server returns an error with responseType:"blob", axios wraps the
  // error body as a Blob instead of rejecting — detect and surface it properly.
  if (response.status >= 400) {
    const text = await response.data.text();
    let detail = text;
    try { detail = JSON.parse(text)?.detail ?? text; } catch { /* leave as text */ }
    throw new Error(detail || `Export failed (HTTP ${response.status})`);
  }

  // Try to extract the server-provided filename from Content-Disposition
  const disposition = response.headers?.["content-disposition"] ?? "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] ?? fallbackFilename;

  const fmt = filename.split(".").pop()?.toLowerCase() ?? "csv";
  const blob = new Blob([response.data], {
    type: MIME_TYPES[fmt] ?? "application/octet-stream",
  });

  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  // Keep the element and URL alive long enough for the browser to process
  // the click — removing them synchronously cancels the download in Chrome.
  setTimeout(() => {
    document.body.removeChild(a);
    URL.revokeObjectURL(blobUrl);
  }, 10_000);
}

/** Download the cleaned dataset as CSV, XLSX, or JSON. */
export async function downloadExport(sessionId, fmt = "csv") {
  await _blobDownload(
    "/export",
    { session_id: sessionId, fmt },
    `cleaned.${fmt}`,
  );
}

/** List all saved version snapshots. */
export async function listExportVersions(sessionId) {
  const { data } = await client.get("/export/versions", { params: { session_id: sessionId } });
  return data;
}

/** Download a specific versioned snapshot. */
export async function downloadVersion(sessionId, version, fmt = "csv") {
  await _blobDownload(
    `/export/version/${version}`,
    { session_id: sessionId, fmt },
    `dataset_v${version}.${fmt}`,
  );
}

// ── Pipelines ─────────────────────────────────────────────────────────────

export async function listPipelines() {
  const { data } = await client.get("/pipelines");
  return data;
}

export async function createPipeline(name, steps) {
  const { data } = await client.post("/pipelines", { name, steps });
  return data;
}

export async function runPipeline(sessionId, pipelineId) {
  const { data } = await client.post("/pipelines/run", {
    session_id: sessionId,
    pipeline_id: pipelineId,
  });
  return data;
}

// ── AI Agent ──────────────────────────────────────────────────────────────

/** Run the full AI cleaning agent pipeline */
export async function runAIAgent(sessionId) {
  const { data } = await client.post("/ai-agent/run", { session_id: sessionId });
  return data;
}

/** Execute an NL cleaning command via AI agent */
export async function aiNLClean(sessionId, command, history = []) {
  const { data } = await client.post("/ai-agent/nl-clean", { session_id: sessionId, command, history });
  return data;
}

/** List dataset version snapshots */
export async function listVersions(sessionId) {
  const { data } = await client.get("/ai-agent/versions", { params: { session_id: sessionId } });
  return data;
}

// ── AI Data Scientist ─────────────────────────────────────────────────────

/** Train an auto-ML model on the current dataset */
export async function trainModel(sessionId, targetColumn = null) {
  const { data } = await client.post("/ai-ml/train", {
    session_id: sessionId,
    target_column: targetColumn,
  });
  return data;
}

/** Get candidate target columns ranked by likelihood */
export async function suggestTargets(sessionId) {
  const { data } = await client.get("/ai-ml/targets", { params: { session_id: sessionId } });
  return data;
}

// ── Auth ───────────────────────────────────────────────────────────────────
export async function authRegister(username, password, fullName, email) {
  const { data } = await client.post("/auth/register", { username, password, full_name: fullName, email });
  return data;
}
export async function authLogin(username, password) {
  const { data } = await client.post("/auth/login", { username, password });
  // Normalise: backend now returns access_token + refresh_token.
  // Keep backward-compat alias `token` pointing at access_token.
  if (data.access_token && !data.token) data.token = data.access_token;
  return data;
}
export async function authRefresh(refreshToken) {
  const { data } = await client.post("/auth/refresh", { refresh_token: refreshToken });
  if (data.access_token && !data.token) data.token = data.access_token;
  return data;
}
export async function authLogout() {
  const { data } = await client.post("/auth/logout");
  return data;
}
export async function authMe() {
  const { data } = await client.get("/auth/me");
  return data;
}
export function setAuthToken(token) {
  if (token) client.defaults.headers.common["Authorization"] = `Bearer ${token}`;
  else delete client.defaults.headers.common["Authorization"];
}
export async function authForgotPassword(username) {
  const { data } = await client.post("/auth/forgot-password", { username });
  return data;
}
export async function authResetPassword(token, newPassword) {
  const { data } = await client.post("/auth/reset-password", { token, new_password: newPassword });
  return data;
}

// ── SQL ────────────────────────────────────────────────────────────────────
export async function runSQL(sessionId, query) {
  const { data } = await client.post("/sql/query", { session_id: sessionId, query });
  return data;
}
export async function applySQL(sessionId, query) {
  const { data } = await client.post("/sql/apply", { session_id: sessionId, query });
  return data;
}

// ── Fuzzy dedup ────────────────────────────────────────────────────────────
export async function findFuzzyDuplicates(sessionId, threshold = 85, columns = null) {
  const { data } = await client.post("/fuzzy/find",
    { session_id: sessionId, threshold, columns });
  return data;
}
export async function removeFuzzyDuplicates(sessionId, threshold = 85, columns = null) {
  const { data } = await client.post("/fuzzy/remove",
    { session_id: sessionId, threshold, columns });
  return data;
}

// ── Validation ─────────────────────────────────────────────────────────────
export async function runValidation(sessionId, rules) {
  const { data } = await client.post("/validate", { session_id: sessionId, rules });
  return data;
}
export async function saveRuleset(sessionId, name, rules) {
  const { data } = await client.post("/validate/save", { session_id: sessionId, name, rules });
  return data;
}
export async function listRulesets(sessionId) {
  const { data } = await client.get("/validate/rules", { params: { session_id: sessionId } });
  return data;
}

// ── Report ─────────────────────────────────────────────────────────────────
export async function downloadReport(sessionId) {
  await _blobDownload(
    "/report",
    { session_id: sessionId },
    "quality_report.html",
  );
}


// ── Fix All ────────────────────────────────────────────────────────────────
/** Apply all fix suggestions in sequence */
export async function fixAllIssues(sessionId, suggestions) {
  const { data } = await client.post("/fix-all", { session_id: sessionId, suggestions });
  return data;
}

// ── Paste CSV upload ────────────────────────────────────────────────────────
export async function uploadPastedCSV(csvText, filename = "pasted_data.csv") {
  const { data } = await client.post("/upload/paste", { csv_text: csvText, filename });
  return data;
}

// ── Schema suggestions ─────────────────────────────────────────────────────
/** Apply batch schema cast suggestions */
export async function applySchemasuggestions(sessionId, suggestions) {
  const { data } = await client.post("/clean", {
    session_id: sessionId,
    action: "apply_schema_suggestions",
    params: { suggestions },
  });
  return data;
}

// ── Power Features ────────────────────────────────────────────────────────────

/** Auto-generate chart data for the current session */
export async function fetchVisualizations(sessionId) {
  const { data } = await client.post("/visualize", { session_id: sessionId });
  return data;
}

/** Detect PII columns */
export async function detectPII(sessionId) {
  const { data } = await client.post("/pii/detect", { session_id: sessionId });
  return data;
}

/** Mask PII columns — columns: [{column, pii_type, strategy}] */
export async function maskPII(sessionId, columns) {
  const { data } = await client.post("/pii/mask", { session_id: sessionId, columns });
  return data;
}

/** Preview a formula expression without saving (dry-run on first 5 rows) */
export async function previewFormula(sessionId, expression, previewRows = 5) {
  const { data } = await client.post("/formula/preview", {
    session_id: sessionId, expression, preview_rows: previewRows,
  });
  return data;
}

/** Add a computed formula column */
export async function addFormulaColumn(sessionId, newColumn, expression) {
  const { data } = await client.post("/formula", {
    session_id: sessionId,
    new_column:  newColumn,
    expression,
  });
  return data;
}

/** Compute pairwise correlations (Pearson / Spearman / Cramér's V) */
export async function detectCorrelations(sessionId, method = "auto", threshold = 0.3) {
  const { data } = await client.post("/correlations", { session_id: sessionId, method, threshold });
  return data;
}

/** Check referential integrity — detect orphaned FK values and duplicate PKs */
export async function checkReferentialIntegrity(sessionId) {
  const { data } = await client.post("/referential-integrity", { session_id: sessionId });
  return data;
}

/** Detect semantically similar columns and suggest merges */
export async function findSimilarColumns(sessionId) {
  const { data } = await client.post("/column-similarity", { session_id: sessionId });
  return data;
}

/** Time-series anomaly detection via STL decomposition */
export async function detectTimeseriesAnomalies(sessionId, dateCol = null, valueCols = null, period = null) {
  const { data } = await client.post("/anomalies/timeseries", {
    session_id: sessionId, date_col: dateCol, value_cols: valueCols, period,
  });
  return data;
}

/** List all named patterns from the pattern library */
export async function listPatterns() {
  const { data } = await client.get("/patterns");
  return data;
}

/** Validate a column against a named pattern */
export async function validatePattern(sessionId, column, patternName) {
  const { data } = await client.post("/patterns/validate", {
    session_id: sessionId, column, pattern_name: patternName,
  });
  return data;
}

/** Test a single value against a named pattern */
export async function testPattern(value, patternName) {
  const { data } = await client.post("/patterns/test", { value, pattern_name: patternName });
  return data;
}


// ── Vocabulary Mapper / Rollback / Lineage / Batch (v3) ─────────────────────

export async function vocabList() {
  const { data } = await client.get("/vocab/list");
  return data;
}

/**
 * Preview how an array of sample values would be mapped through a vocabulary.
 * @param {string[]} values  — sample values to map
 * @param {string}   vocab   — e.g. "country_name", "currency", "gender"
 */
export async function vocabPreview(values, vocab) {
  const { data } = await client.post("/vocab/preview", { values, vocab });
  return data;
}

/**
 * Apply a vocabulary mapping to a column in the session dataset.
 * @param {string} sessionId
 * @param {string} column     — column to transform
 * @param {string} vocab      — vocabulary key
 * @param {string} unmapped   — "keep" | "blank" | "error"
 */
export async function vocabApply(sessionId, column, vocab, unmapped = "keep") {
  const { data } = await client.post("/vocab/apply", {
    session_id: sessionId,
    column,
    vocab,
    unmapped,
  });
  return data;
}


// ── Rollback ──────────────────────────────────────────────────────────────────

/**
 * Roll back the dataset to the state after a specific version step.
 *
 * @param {string} sessionId
 * @param {number} versionIndex  — 0-based index into session.versions
 *                                 (step 1 = index 0, step 2 = index 1, …)
 */
export async function rollbackToVersion(sessionId, versionIndex) {
  const { data } = await client.post("/rollback", {
    session_id: sessionId,
    version_index: versionIndex,
  });
  return data;
}


// ── Column Lineage ─────────────────────────────────────────────────────────────

/**
 * Fetch the column-level lineage DAG for the current session.
 * Returns: { lineage: { "<col>": [{action, params, step, ts, event}] } }
 */
export async function getLineage(sessionId) {
  const { data } = await client.get("/lineage", {
    params: { session_id: sessionId },
  });
  return data;
}


// ── Batch / Multi-file Cleaning ────────────────────────────────────────────────

/**
 * Upload multiple CSV / XLSX files for batch processing.
 * @param {File[]} files  — array of File objects
 * @returns {{ batch_id: string, files: Array }} manifest
 */
export async function batchUpload(files) {
  const form = new FormData();
  files.forEach(f => form.append("files", f));
  const { data } = await client.post("/batch/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

/**
 * Apply a transformation pipeline to all files in a batch.
 * @param {string}  batchId   — from batchUpload()
 * @param {Array}   pipeline  — [{action, params}, ...]
 * @param {string}  [sessionId] — optional: copy schema from existing session
 */
export async function batchRun(batchId, pipeline, sessionId = null) {
  const { data } = await client.post("/batch/run", {
    batch_id: batchId,
    pipeline,
    ...(sessionId ? { session_id: sessionId } : {}),
  });
  return data;
}

/**
 * Download all cleaned batch files as a ZIP archive.
 * Triggers a browser download automatically.
 * @param {string} batchId
 */
export async function batchDownload(batchId) {
  await _blobDownload(
    "/batch/download",
    { batch_id: batchId },
    `batch_${batchId.slice(0, 8)}_cleaned.zip`
  );
}


// ── Sessions (My Datasets) ─────────────────────────────────────────────────

export async function fetchMySessions() {
  const { data } = await client.get("/sessions");
  return data;
}

export async function deleteSession(sessionId) {
  const { data } = await client.delete(`/sessions/${sessionId}`);
  return data;
}

export async function fetchRows(sessionId, startRow, endRow) {
  const { data } = await client.get(`/sessions/${sessionId}/rows`, {
    params: { startRow, endRow }
  });
  return data;
}

// ── NL command (two-step: parse then confirm) ──────────────────────────────

export async function parseNLCommand(sessionId, command, history = []) {
  const { data } = await client.post("/ai-agent/nl-clean", {
    session_id: sessionId,
    command,
    history,
    confirmed: false,
  });
  return data;
}

export async function confirmNLCommand(sessionId, command, history = []) {
  const { data } = await client.post("/ai-agent/nl-clean", {
    session_id: sessionId,
    command,
    history,
    confirmed: true,
  });
  return data;
}

// ── Onboarding ─────────────────────────────────────────────────────────────
export async function fetchSamples() {
  const { data } = await client.get("/samples");
  return data;
}
export async function loadSample(sampleId) {
  const { data } = await client.post("/samples/load", { sample_id: sampleId });
  return data;
}

// ── Sharing ────────────────────────────────────────────────────────────────
export async function createShare(sessionId, opts = {}) {
  const { data } = await client.post("/share", { session_id: sessionId, ...opts });
  return data;
}
export async function resolveShare(token) {
  const { data } = await client.get(`/share/${token}`);
  return data;
}
export async function forkShared(token) {
  const { data } = await client.post(`/share/${token}/fork`);
  return data;
}
export async function listShares(sessionId) {
  const { data } = await client.get(`/sessions/${sessionId}/shares`);
  return data;
}
export async function revokeShare(token) {
  const { data } = await client.delete(`/share/${token}`);
  return data;
}

// ── Billing ────────────────────────────────────────────────────────────────
export async function fetchBillingMe() {
  const { data } = await client.get("/billing/me");
  return data;
}
export async function fetchPlans() {
  const { data } = await client.get("/billing/plans");
  return data;
}
export async function createCheckout(planId, successUrl, cancelUrl) {
  const { data } = await client.post("/billing/upgrade", {
    plan_id: planId, success_url: successUrl, cancel_url: cancelUrl,
  });
  return data;
}

// ── Connectors ─────────────────────────────────────────────────────────────
export async function connectURL(url, filename) {
  const { data } = await client.post("/connectors/url", { url, filename });
  return data;
}
export async function connectDatabase(connectionString, query, filename) {
  const { data } = await client.post("/connectors/database", {
    connection_string: connectionString, query, filename,
  });
  return data;
}
export async function connectGSheets(spreadsheetId, sheetName, serviceAccountJson) {
  const { data } = await client.post("/connectors/gsheets", {
    spreadsheet_id:       spreadsheetId,
    sheet_name:           sheetName || undefined,
    service_account_json: serviceAccountJson || undefined,
  });
  return data;
}
export async function connectS3(bucket, key, awsAccessKeyId, awsSecretAccessKey, region) {
  const { data } = await client.post("/connectors/s3", {
    bucket,
    key,
    aws_access_key_id:     awsAccessKeyId || undefined,
    aws_secret_access_key: awsSecretAccessKey || undefined,
    region:                region || "us-east-1",
  });
  return data;
}
export async function fetchAvailableConnectors() {
  const { data } = await client.get("/connectors/available");
  return data;
}

// ── Export destinations ────────────────────────────────────────────────────
export async function exportToAirtable(sessionId, baseId, tableName, apiKey) {
  const { data } = await client.post("/export/airtable", {
    session_id: sessionId, base_id: baseId, table_name: tableName, api_key: apiKey,
  });
  return data;
}
export async function exportToSlack(sessionId, webhookUrl) {
  const { data } = await client.post("/export/slack", {
    session_id: sessionId, webhook_url: webhookUrl,
  });
  return data;
}

// ── Background jobs ────────────────────────────────────────────────────────
export async function getJob(jobId) {
  const { data } = await client.get(`/jobs/${jobId}`);
  return data;
}
export async function uploadAsync(file, onProgress) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await client.post("/upload/async", form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: e => onProgress?.(Math.round((e.loaded / e.total) * 100)),
  });
  return data;
}
export async function runAgentAsync(sessionId) {
  const { data } = await client.post("/ai-agent/run/async", { session_id: sessionId });
  return data;
}

// ── Admin ──────────────────────────────────────────────────────────────────
export async function fetchAdminStats() {
  const { data } = await client.get("/admin/stats");
  return data;
}
export async function fetchAdminUsers(page = 1, pageSize = 20) {
  const { data } = await client.get("/admin/users", { params: { page, page_size: pageSize } });
  return data;
}
export async function setUserRole(userId, role) {
  const { data } = await client.post(`/admin/users/${userId}/role`, { role });
  return data;
}
export async function setUserActive(userId, active) {
  const endpoint = active ? "activate" : "deactivate";
  const { data } = await client.post(`/admin/users/${userId}/${endpoint}`);
  return data;
}
export async function fetchAuditLog(page = 1, pageSize = 100) {
  const { data } = await client.get("/admin/audit-log", { params: { page, page_size: pageSize } });
  return data;
}

// ── AI Orchestrator ────────────────────────────────────────────────────────
export async function orchestrateAI(sessionId, userGoal = null) {
  const { data } = await client.post("/ai/orchestrate", {
    session_id: sessionId,
    user_goal:  userGoal,
  });
  return data;
}
export async function executeAction(sessionId, actionId) {
  const { data } = await client.post("/ai/execute-action", {
    session_id: sessionId,
    action_id:  actionId,
  });
  return data;
}
