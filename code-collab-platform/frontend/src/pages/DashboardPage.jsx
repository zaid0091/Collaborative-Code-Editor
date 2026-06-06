import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { createWorkspace, getWorkspaces } from "../services/api.js";

export default function DashboardPage() {
  const navigate = useNavigate();
  const [workspaces, setWorkspaces] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [newName, setNewName] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  const loadWorkspaces = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getWorkspaces();
      setWorkspaces(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load workspaces.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadWorkspaces();
  }, [loadWorkspaces]);

  const handleCreate = async (event) => {
    event.preventDefault();
    if (!newName.trim()) {
      return;
    }

    setIsCreating(true);
    setError(null);
    try {
      const response = await createWorkspace(newName.trim());
      setNewName("");
      navigate(`/workspace/${response.data.id}`);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to create workspace.");
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <main className="dashboard-page">
      <header className="dashboard-header">
        <div>
          <h1>Workspaces</h1>
          <p className="muted">Select a workspace or create a new one.</p>
        </div>
        <form className="create-workspace-form" onSubmit={handleCreate}>
          <input
            type="text"
            placeholder="Workspace name"
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            maxLength={200}
          />
          <button type="submit" disabled={isCreating || !newName.trim()}>
            {isCreating ? "Creating…" : "Create workspace"}
          </button>
        </form>
      </header>

      {error && <p className="auth-error">{String(error)}</p>}

      {isLoading ? (
        <p className="muted">Loading workspaces…</p>
      ) : workspaces.length === 0 ? (
        <p className="muted">No workspaces yet. Create one to get started.</p>
      ) : (
        <div className="workspace-grid">
          {workspaces.map((workspace) => (
            <button
              key={workspace.id}
              type="button"
              className="workspace-card"
              onClick={() => navigate(`/workspace/${workspace.id}`)}
            >
              <h2>{workspace.name}</h2>
              <p className="muted">{workspace.slug}</p>
            </button>
          ))}
        </div>
      )}
    </main>
  );
}
