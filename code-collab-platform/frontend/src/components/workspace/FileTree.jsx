import { useCallback, useEffect, useMemo, useState } from "react";

import { createFile, deleteFile, getFileTree, updateFilePath } from "../../services/api.js";

const LANGUAGE_ICONS = {
  python: "PY",
  javascript: "JS",
  typescript: "TS",
  html: "HTML",
  css: "CSS",
  json: "JSON",
  markdown: "MD",
};

function buildTree(files) {
  const root = { name: "", children: {}, files: [] };

  for (const file of files) {
    const segments = file.path.split("/").filter(Boolean);
    let node = root;

    for (const segment of segments.slice(0, -1)) {
      if (!node.children[segment]) {
        node.children[segment] = { name: segment, children: {}, files: [] };
      }
      node = node.children[segment];
    }

    const fileName = segments[segments.length - 1] || file.path;
    node.files.push({ ...file, fileName });
  }

  return root;
}

function TreeNode({ node, depth, selectedFileId, onFileSelect, onRename, onDelete }) {
  const childFolders = Object.values(node.children).sort((a, b) => a.name.localeCompare(b.name));
  const files = [...node.files].sort((a, b) => a.fileName.localeCompare(b.fileName));

  return (
    <div className="tree-node" style={{ paddingLeft: `${depth * 12}px` }}>
      {childFolders.map((child) => (
        <div key={child.name} className="tree-folder">
          <div className="tree-folder-label">{child.name}/</div>
          <TreeNode
            node={child}
            depth={depth + 1}
            selectedFileId={selectedFileId}
            onFileSelect={onFileSelect}
            onRename={onRename}
            onDelete={onDelete}
          />
        </div>
      ))}

      {files.map((file) => (
        <div
          key={file.id}
          className={`tree-file${selectedFileId === file.id ? " is-selected" : ""}`}
        >
          <button
            type="button"
            className="tree-file-button"
            onClick={() => onFileSelect(file.id, file.path)}
          >
            <span className="language-icon" title={file.language}>
              {LANGUAGE_ICONS[file.language] || "FILE"}
            </span>
            <span>{file.fileName}</span>
          </button>
          <div className="tree-file-actions">
            <button type="button" onClick={() => onRename(file)}>
              Rename
            </button>
            <button type="button" onClick={() => onDelete(file.id)}>
              Delete
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function FileTree({ projectId, selectedFileId, onFileSelect }) {
  const [files, setFiles] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [newPath, setNewPath] = useState("");

  const loadFiles = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getFileTree(projectId);
      setFiles(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load files.");
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  const tree = useMemo(() => buildTree(files), [files]);

  const handleCreate = async (event) => {
    event.preventDefault();
    if (!newPath.trim()) {
      return;
    }

    try {
      await createFile(projectId, newPath.trim());
      setNewPath("");
      await loadFiles();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to create file.");
    }
  };

  const handleRename = async (file) => {
    const nextPath = window.prompt("Rename file path", file.path);
    if (!nextPath || nextPath === file.path) {
      return;
    }

    try {
      await updateFilePath(file.id, nextPath);
      await loadFiles();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to rename file.");
    }
  };

  const handleDelete = async (fileId) => {
    if (!window.confirm("Delete this file?")) {
      return;
    }

    try {
      await deleteFile(fileId);
      await loadFiles();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to delete file.");
    }
  };

  if (isLoading) {
    return <p className="muted">Loading files…</p>;
  }

  return (
    <nav className="file-tree" aria-label="Project files">
      <form className="file-tree-create" onSubmit={handleCreate}>
        <input
          type="text"
          placeholder="path/to/file.py"
          value={newPath}
          onChange={(event) => setNewPath(event.target.value)}
        />
        <button type="submit">New file</button>
      </form>

      {error && <p className="auth-error">{String(error)}</p>}

      {files.length === 0 ? (
        <p className="muted">No files yet.</p>
      ) : (
        <TreeNode
          node={tree}
          depth={0}
          selectedFileId={selectedFileId}
          onFileSelect={onFileSelect}
          onRename={handleRename}
          onDelete={handleDelete}
        />
      )}
    </nav>
  );
}
