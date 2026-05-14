/**
 * JobPoller — polls a background job and renders its progress.
 *
 * Props:
 *   jobId      {string}   — job_id returned from /upload/async or /ai-agent/run/async
 *   onDone     {fn}       — called with job.result when status === "done"
 *   onFail     {fn}       — called with job.error when status === "failed"
 *   label      {string}   — description shown under the progress bar
 *   intervalMs {number}   — polling interval in ms (default 1500)
 */
import React, { useEffect, useRef, useState } from "react";
import { Loader2, CheckCircle2, AlertCircle, X } from "lucide-react";
import { getJob } from "../services/api";

export default function JobPoller({
  jobId,
  onDone,
  onFail,
  label = "Processing…",
  intervalMs = 1500,
}) {
  const [job, setJob]       = useState(null);
  const [dismissed, setDismissed] = useState(false);
  const timerRef = useRef(null);

  useEffect(() => {
    if (!jobId || dismissed) return;

    const poll = async () => {
      try {
        const data = await getJob(jobId);
        setJob(data);
        if (data.status === "done") {
          clearInterval(timerRef.current);
          onDone?.(data.result);
        } else if (data.status === "failed") {
          clearInterval(timerRef.current);
          onFail?.(data.error);
        }
      } catch {
        // Network hiccup — keep polling
      }
    };

    poll();
    timerRef.current = setInterval(poll, intervalMs);
    return () => clearInterval(timerRef.current);
  }, [jobId, dismissed, intervalMs, onDone, onFail]);

  if (!jobId || dismissed) return null;

  const status   = job?.status ?? "pending";
  const progress = job?.progress ?? 0;
  const message  = job?.message ?? "Queued…";
  const isDone   = status === "done";
  const isFailed = status === "failed";

  const barColor = isFailed ? "#ef4444" : isDone ? "#22c55e" : "#6366f1";
  const css = `
    .jp-wrap { position: fixed; bottom: 24px; right: 24px; z-index: 9999;
      width: 320px; background: var(--surface-2); border: 1px solid var(--border);
      border-radius: var(--radius-lg); padding: 14px 16px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.35); }
    .jp-header { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
    .jp-icon { flex-shrink: 0; }
    .jp-label { flex: 1; font-size: 12px; font-weight: 600; color: var(--text-0); }
    .jp-close { border: none; background: none; color: var(--text-3);
      cursor: pointer; padding: 2px; border-radius: 3px; display: flex; }
    .jp-close:hover { color: var(--text-1); }
    .jp-track { height: 4px; background: var(--surface-3); border-radius: 99px; overflow: hidden; }
    .jp-fill  { height: 100%; border-radius: 99px; transition: width 0.4s ease; }
    .jp-msg   { font-size: 11px; color: var(--text-2); margin-top: 6px; }
    @keyframes spin { to { transform: rotate(360deg); } }
  `;

  return (
    <>
      <style>{css}</style>
      <div className="jp-wrap">
        <div className="jp-header">
          <span className="jp-icon">
            {isFailed
              ? <AlertCircle size={14} color="#ef4444" />
              : isDone
              ? <CheckCircle2 size={14} color="#22c55e" />
              : <Loader2 size={14} color="#6366f1" style={{ animation: "spin .7s linear infinite" }} />}
          </span>
          <span className="jp-label">{label}</span>
          {(isDone || isFailed) && (
            <button className="jp-close" onClick={() => setDismissed(true)}>
              <X size={12} />
            </button>
          )}
        </div>
        <div className="jp-track">
          <div className="jp-fill" style={{ width: `${progress}%`, background: barColor }} />
        </div>
        <div className="jp-msg">{message}</div>
      </div>
    </>
  );
}
