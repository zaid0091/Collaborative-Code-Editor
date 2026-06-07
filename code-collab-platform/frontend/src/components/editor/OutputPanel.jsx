export default function OutputPanel({ result }) {
  if (!result) {
    return (
      <div className="output-panel output-panel--empty">
        <p className="muted">Run output will appear here.</p>
      </div>
    );
  }

  const isPending = result.status === "queued" || result.status === "running";
  const exitCode = result.exit_code;
  const exitLabel = exitCode === 0 ? "Success" : exitCode == null ? "Pending" : `Exit ${exitCode}`;

  return (
    <div className="output-panel">
      <div className="output-panel__header">
        <h3>Output</h3>
        <div className="output-panel__meta">
          {isPending ? <span className="output-panel__spinner" aria-hidden="true" /> : null}
          {result.status === "queued" && result.queue_position ? (
            <span className="muted">Queued — position {result.queue_position}</span>
          ) : null}
          {result.status === "running" ? <span className="muted">Running…</span> : null}
          {!isPending ? (
            <>
              <span className={`exit-badge exit-badge--${exitCode === 0 ? "ok" : "error"}`}>
                {exitLabel}
              </span>
              {result.duration_ms != null ? (
                <span className="muted">{result.duration_ms} ms</span>
              ) : null}
            </>
          ) : null}
        </div>
      </div>

      {result.stdout ? (
        <section className="output-block">
          <h4>stdout</h4>
          <pre>{result.stdout}</pre>
        </section>
      ) : null}

      {result.stderr ? (
        <section className="output-block output-block--stderr">
          <h4>stderr</h4>
          <pre>{result.stderr}</pre>
        </section>
      ) : null}
    </div>
  );
}
