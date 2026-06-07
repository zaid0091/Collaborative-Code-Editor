import { useEffect, useState } from "react";

import { createVersion, getVersions } from "../../services/api.js";

export default function VersionTimeline({ fileId, onVersionSelect }) {
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!fileId) {
      setVersions([]);
      return undefined;
    }

    let cancelled = false;
    setLoading(true);

    getVersions(fileId)
      .then((data) => {
        if (!cancelled) {
          setVersions(data);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [fileId]);

  async function handleSaveCheckpoint() {
    setCreating(true);
    try {
      const label = prompt("Checkpoint label (optional):") || "";
      await createVersion(fileId, label);
      const data = await getVersions(fileId);
      setVersions(data);
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="version-timeline">
      <div className="version-timeline__header">
        <h3>Version History</h3>
        <button type="button" onClick={handleSaveCheckpoint} disabled={creating || !fileId}>
          {creating ? "Saving..." : "Save Checkpoint"}
        </button>
      </div>
      {loading ? (
        <p className="muted">Loading...</p>
      ) : (
        <ul className="version-timeline__list">
          {versions.map((version) => (
            <li key={version.id}>
              <button
                type="button"
                className="version-timeline__item"
                onClick={() => onVersionSelect?.(version)}
              >
                <span className="version-label">{version.label || "Checkpoint"}</span>
                <span className="version-meta">
                  {version.created_by?.display_name} ·{" "}
                  {new Date(version.created_at).toLocaleString()}
                </span>
                <span className="version-source">{version.source}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
