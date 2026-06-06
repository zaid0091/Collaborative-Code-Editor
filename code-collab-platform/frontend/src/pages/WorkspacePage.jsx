import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import CodeEditor from "../components/editor/CodeEditor.jsx";
import PresenceBar from "../components/editor/PresenceBar.jsx";
import StatusBar from "../components/editor/StatusBar.jsx";
import FileTree from "../components/workspace/FileTree.jsx";
import { useAuth } from "../hooks/useAuth.js";
import { useCollaboration } from "../hooks/useCollaboration.js";
import { assignUserColor } from "../realtime/yjsProvider.js";
import { getFileMeta, getProjects, getWorkspaces } from "../services/api.js";
import api from "../lib/axios.js";

export default function WorkspacePage() {
  const { workspaceId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [workspace, setWorkspace] = useState(null);
  const [projects, setProjects] = useState([]);
  const [memberCount, setMemberCount] = useState(0);
  const [selectedFileId, setSelectedFileId] = useState(null);
  const [selectedFilePath, setSelectedFilePath] = useState("");
  const [fileMeta, setFileMeta] = useState(null);
  const [metaError, setMetaError] = useState(null);
  const [metaLoading, setMetaLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const { ydoc, provider, status } = useCollaboration(selectedFileId);

  const loadWorkspaceData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [workspacesResponse, projectsResponse, membersResponse] = await Promise.all([
        getWorkspaces(),
        getProjects(workspaceId),
        api.get(`/workspaces/${workspaceId}/members/`),
      ]);

      const currentWorkspace = workspacesResponse.data.find(
        (item) => item.id === workspaceId,
      );
      setWorkspace(currentWorkspace || null);
      setProjects(projectsResponse.data);
      setMemberCount(membersResponse.data.length);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load workspace.");
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    loadWorkspaceData();
  }, [loadWorkspaceData]);

  useEffect(() => {
    if (!selectedFileId) {
      setFileMeta(null);
      setMetaError(null);
      return undefined;
    }

    let cancelled = false;
    setMetaLoading(true);
    setMetaError(null);

    getFileMeta(selectedFileId)
      .then((response) => {
        if (!cancelled) {
          setFileMeta(response.data);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setMetaError(err.response?.data?.detail || "Failed to load file metadata.");
          setFileMeta(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setMetaLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedFileId]);

  const handleFileSelect = (fileId, filePath) => {
    setSelectedFileId(fileId);
    setSelectedFilePath(filePath);
  };

  const localUser = user
    ? {
        id: user.id,
        display_name: user.display_name,
        color: assignUserColor(user.id),
      }
    : null;

  if (isLoading) {
    return (
      <main className="workspace-page">
        <p className="muted">Loading workspace…</p>
      </main>
    );
  }

  if (error) {
    return (
      <main className="workspace-page">
        <p className="auth-error">{String(error)}</p>
        <button type="button" onClick={() => navigate("/dashboard")}>
          Back to dashboard
        </button>
      </main>
    );
  }

  return (
    <div className="workspace-page">
      <header className="workspace-header">
        <div>
          <button type="button" className="link-button" onClick={() => navigate("/dashboard")}>
            ← Dashboard
          </button>
          <h1>{workspace?.name || "Workspace"}</h1>
          <p className="muted">
            {memberCount} member{memberCount === 1 ? "" : "s"}
          </p>
        </div>
      </header>

      <div className="workspace-layout">
        <aside className="workspace-sidebar">
          <h2>Projects</h2>
          {projects.length === 0 ? (
            <p className="muted">No projects in this workspace.</p>
          ) : (
            projects.map((project) => (
              <section key={project.id} className="project-section">
                <h3>{project.name}</h3>
                <FileTree
                  projectId={project.id}
                  selectedFileId={selectedFileId}
                  onFileSelect={handleFileSelect}
                />
              </section>
            ))
          )}
        </aside>

        <main className="workspace-main workspace-main--editor">
          {selectedFileId ? (
            <div className="editor-panel">
              <div className="editor-toolbar">
                <div className="editor-toolbar-left">
                  <strong className="editor-file-path">{selectedFilePath}</strong>
                  {fileMeta ? (
                    <span className="editor-file-meta muted">
                      {fileMeta.language} · {fileMeta.tier}
                    </span>
                  ) : null}
                </div>
                <div className="editor-toolbar-right">
                  <PresenceBar provider={provider} />
                  <StatusBar status={status} />
                </div>
              </div>

              {metaLoading ? <p className="muted editor-loading">Loading file…</p> : null}
              {metaError ? <p className="auth-error editor-loading">{metaError}</p> : null}

              {!metaLoading && !metaError && fileMeta ? (
                <CodeEditor
                  fileId={selectedFileId}
                  fileMeta={fileMeta}
                  provider={provider}
                  ydoc={ydoc}
                  localUser={localUser}
                />
              ) : null}
            </div>
          ) : (
            <div className="workspace-placeholder">
              <h2>Select a file to edit</h2>
              <p className="muted">Choose a file from the sidebar to begin collaborating.</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
