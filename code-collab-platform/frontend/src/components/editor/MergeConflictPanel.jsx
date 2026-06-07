import { useState } from "react";

import { resolveMerge } from "../../services/api.js";

export default function MergeConflictPanel({ fileId, mergeJobId, conflicts, onResolved }) {
  const [resolutions, setResolutions] = useState({});
  const [submitting, setSubmitting] = useState(false);

  function setChoice(hunkId, choice, customText = null) {
    setResolutions((previous) => ({
      ...previous,
      [hunkId]: { hunk_id: hunkId, choice, custom_text: customText },
    }));
  }

  const allResolved = conflicts.every((conflict) => resolutions[conflict.hunk_id]);

  async function handleApply() {
    setSubmitting(true);
    try {
      await resolveMerge(fileId, mergeJobId, Object.values(resolutions));
      onResolved?.();
    } finally {
      setSubmitting(false);
    }
  }

  if (!conflicts?.length) {
    return null;
  }

  return (
    <div className="merge-conflict-panel">
      <h3>Merge Conflicts ({conflicts.length})</h3>
      {conflicts.map((conflict) => (
        <div key={conflict.hunk_id} className="conflict-hunk">
          <div className="conflict-hunk__meta">
            Lines {conflict.line_range.start}–{conflict.line_range.end}
          </div>
          <div className="conflict-hunk__panes">
            <div className="pane pane--base">
              <h4>Base</h4>
              <pre>{conflict.base}</pre>
            </div>
            <div className="pane pane--ours">
              <h4>Current</h4>
              <pre>{conflict.ours}</pre>
              <button type="button" onClick={() => setChoice(conflict.hunk_id, "ours")}>
                Keep Current
              </button>
            </div>
            <div className="pane pane--theirs">
              <h4>Incoming</h4>
              <pre>{conflict.theirs}</pre>
              <button type="button" onClick={() => setChoice(conflict.hunk_id, "theirs")}>
                Keep Incoming
              </button>
            </div>
          </div>
          {resolutions[conflict.hunk_id] ? (
            <div className="resolution-badge">Resolved: {resolutions[conflict.hunk_id].choice}</div>
          ) : null}
        </div>
      ))}
      <button type="button" onClick={handleApply} disabled={!allResolved || submitting}>
        {submitting ? "Applying..." : "Apply Resolutions"}
      </button>
    </div>
  );
}
