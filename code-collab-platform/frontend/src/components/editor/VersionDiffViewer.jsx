import { useEffect, useState } from "react";
import { DiffEditor } from "@monaco-editor/react";

export default function VersionDiffViewer({ fileId, fromVersion, toVersion, language }) {
  const [diffMode, setDiffMode] = useState("myers");
  const [fromText, setFromText] = useState("");
  const [toText, setToText] = useState("");

  useEffect(() => {
    if (!fromVersion || !toVersion) {
      setFromText("");
      setToText("");
      return;
    }

    setFromText(fromVersion.snapshot || "");
    setToText(toVersion.snapshot || "");
  }, [fromVersion, toVersion, fileId, diffMode]);

  if (!fromVersion || !toVersion) {
    return (
      <div className="diff-viewer">
        <p className="muted">Select two versions to compare.</p>
      </div>
    );
  }

  return (
    <div className="diff-viewer">
      <div className="diff-viewer__controls">
        <button
          type="button"
          onClick={() => setDiffMode("myers")}
          className={diffMode === "myers" ? "active" : ""}
        >
          Standard Diff
        </button>
        <button
          type="button"
          onClick={() => setDiffMode("patience")}
          className={diffMode === "patience" ? "active" : ""}
        >
          Semantic Diff (Patience)
        </button>
      </div>
      <DiffEditor
        original={fromText}
        modified={toText}
        language={language || fromVersion.language || "plaintext"}
        theme="vs-dark"
        options={{ readOnly: true, renderSideBySide: true }}
        height="70vh"
      />
    </div>
  );
}
