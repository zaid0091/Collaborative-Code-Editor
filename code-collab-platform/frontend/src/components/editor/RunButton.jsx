import { useCallback, useEffect, useRef, useState } from "react";

import { executeCode, getExecutionJob } from "../../services/api.js";

const POLL_INTERVAL_MS = 1000;
const MAX_ACTIVE_JOBS = 2;

export default function RunButton({ fileId, getCode, language, onResult, onActiveChange }) {
  const [submitting, setSubmitting] = useState(false);
  const [retryAfter, setRetryAfter] = useState(0);
  const [activeJobs, setActiveJobs] = useState(0);
  const pollTimerRef = useRef(null);
  const retryTimerRef = useRef(null);

  useEffect(() => {
    onActiveChange?.(activeJobs);
  }, [activeJobs, onActiveChange]);

  useEffect(
    () => () => {
      clearInterval(pollTimerRef.current);
      clearInterval(retryTimerRef.current);
    },
    [],
  );

  const pollJob = useCallback(
    (jobId) => {
      pollTimerRef.current = setInterval(async () => {
        try {
          const job = await getExecutionJob(jobId);
          onResult?.(job);

          if (job.status === "queued" || job.status === "running") {
            return;
          }

          clearInterval(pollTimerRef.current);
          pollTimerRef.current = null;
          setActiveJobs((count) => Math.max(0, count - 1));
          setSubmitting(false);
        } catch {
          clearInterval(pollTimerRef.current);
          pollTimerRef.current = null;
          setActiveJobs((count) => Math.max(0, count - 1));
          setSubmitting(false);
        }
      }, POLL_INTERVAL_MS);
    },
    [onResult],
  );

  async function handleRun() {
    const code = getCode?.() ?? "";
    if (!code.trim() || submitting || activeJobs >= MAX_ACTIVE_JOBS || retryAfter > 0) {
      return;
    }

    setSubmitting(true);
    setActiveJobs((count) => count + 1);

    try {
      const response = await executeCode({
        code,
        language,
        source: "ui_run",
        file_id: fileId,
      });

      onResult?.({ status: "queued", job_id: response.job_id, queue_position: 1 });
      pollJob(response.job_id);
    } catch (error) {
      setActiveJobs((count) => Math.max(0, count - 1));
      setSubmitting(false);

      const retrySec = error.response?.data?.retry_after_sec;
      if (retrySec) {
        setRetryAfter(retrySec);
        retryTimerRef.current = setInterval(() => {
          setRetryAfter((seconds) => {
            if (seconds <= 1) {
              clearInterval(retryTimerRef.current);
              retryTimerRef.current = null;
              return 0;
            }
            return seconds - 1;
          });
        }, 1000);
      }

      onResult?.({
        status: "failed",
        stderr: error.response?.data?.error || "Failed to start execution",
        exit_code: -1,
      });
    }
  }

  const disabled =
    submitting || activeJobs >= MAX_ACTIVE_JOBS || retryAfter > 0 || !getCode?.()?.trim();

  return (
    <button type="button" className="run-button" onClick={handleRun} disabled={disabled}>
      {retryAfter > 0
        ? `Retry in ${retryAfter}s`
        : submitting
          ? "Running..."
          : activeJobs >= MAX_ACTIVE_JOBS
            ? "Max jobs running"
            : "Run"}
    </button>
  );
}
