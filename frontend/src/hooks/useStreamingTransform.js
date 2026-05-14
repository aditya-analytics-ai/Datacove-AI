/**
 * useStreamingTransform — React hook for SSE-based large-file transforms.
 *
 * Automatically routes:
 *   < STREAM_THRESHOLD rows  → existing axios /clean endpoint (fast path)
 *   >= STREAM_THRESHOLD rows → SSE /clean/stream endpoint (chunked)
 *
 * Returns { runTransform, runAutoClean, progress, streaming, abort }
 */
import { useState, useCallback, useRef } from "react";
import { applyTransformation, autoClean } from "../services/api";

const STREAM_THRESHOLD = 100_000;   // must match backend settings.STREAM_THRESHOLD

export function useStreamingTransform(sessionId, totalRows) {
  const [progress,  setProgress]  = useState(null);
  const [streaming, setStreaming] = useState(false);
  const abortRef                  = useRef(null);

  const runTransform = useCallback(async (action, params, onComplete) => {
    if (totalRows < STREAM_THRESHOLD) {
      const result = await applyTransformation(sessionId, action, params);
      onComplete?.(result);
      return;
    }
    setStreaming(true);
    setProgress({ pct: 0, rowsDone: 0, totalRows, message: "Starting…" });
    try {
      const result = await _streamSSE(
        "/api/clean/stream",
        { session_id: sessionId, action, params },
        (evt) => setProgress({
          pct:      evt.pct,
          rowsDone: evt.rows_done,
          totalRows: evt.total_rows,
          message:  evt.message ?? `Processing ${evt.rows_done?.toLocaleString()} rows…`,
        }),
        abortRef,
      );
      onComplete?.(result);
    } finally {
      setStreaming(false);
      setProgress(null);
    }
  }, [sessionId, totalRows]);

  const runAutoClean = useCallback(async (onComplete) => {
    if (totalRows < STREAM_THRESHOLD) {
      const result = await autoClean(sessionId);
      onComplete?.(result);
      return;
    }
    setStreaming(true);
    setProgress({ pct: 0, rowsDone: 0, totalRows, message: "Starting auto-clean…" });
    try {
      const result = await _streamSSE(
        "/api/auto-clean/stream",
        { session_id: sessionId },
        (evt) => setProgress({
          pct:      evt.pct,
          rowsDone: evt.rows_done,
          totalRows: evt.total_rows,
          message:  evt.message ?? `Cleaning ${evt.rows_done?.toLocaleString()} rows…`,
        }),
        abortRef,
      );
      onComplete?.(result);
    } finally {
      setStreaming(false);
      setProgress(null);
    }
  }, [sessionId, totalRows]);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    setStreaming(false);
    setProgress(null);
  }, []);

  return { runTransform, runAutoClean, progress, streaming, abort };
}

async function _streamSSE(url, body, onProgress, abortRef) {
  const controller = new AbortController();
  abortRef.current = controller;

  // Mirror the Authorization header that axios carries so auth-enabled
  // deployments don't silently get 401s on streaming requests.
  const headers = { "Content-Type": "application/json" };
  const token = localStorage.getItem("dc_token");
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(url, {
    method:  "POST",
    headers,
    body:    JSON.stringify(body),
    signal:  controller.signal,
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err.detail ?? "Stream request failed");
  }

  const reader  = response.body.getReader();
  const decoder = new TextDecoder();
  let   buffer  = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data: ")) continue;
      let event;
      try { event = JSON.parse(line.slice(6)); } catch { continue; }
      if (event.type === "error")    throw new Error(event.detail ?? "Transform failed");
      if (event.type === "progress") onProgress(event);
      if (event.type === "done")     return event;
    }
  }
  throw new Error("SSE stream ended without a done event");
}
