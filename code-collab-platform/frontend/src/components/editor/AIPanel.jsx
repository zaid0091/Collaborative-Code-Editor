import { useCallback, useEffect, useRef, useState } from "react";

import {
  aiComplete,
  aiDetectBugs,
  aiDetectBugsResult,
  aiExplain,
  getAIUsage,
} from "../../services/api.js";

const TABS = [
  { id: "autocomplete", label: "Autocomplete" },
  { id: "explain", label: "Explain" },
  { id: "bugs", label: "Bug Detection" },
];

const SEVERITY_CLASS = {
  error: "ai-issue--error",
  warning: "ai-issue--warning",
  info: "ai-issue--info",
};

function extractContext(model, position, monaco, lineRadius = 20) {
  const startLine = Math.max(1, position.lineNumber - lineRadius);
  const endLine = Math.min(model.getLineCount(), position.lineNumber + lineRadius);
  return model.getValueInRange(
    new monaco.Range(startLine, 1, endLine, model.getLineMaxColumn(endLine)),
  );
}

export default function AIPanel({ editorRef, monacoRef, fileId, language = "python" }) {
  const [activeTab, setActiveTab] = useState("autocomplete");
  const [autocompleteEnabled, setAutocompleteEnabled] = useState(false);
  const [explanation, setExplanation] = useState("");
  const [explainLoading, setExplainLoading] = useState(false);
  const [explainError, setExplainError] = useState("");
  const [bugsLoading, setBugsLoading] = useState(false);
  const [bugsError, setBugsError] = useState("");
  const [issues, setIssues] = useState([]);
  const [usage, setUsage] = useState({ used: 0, budget: 50000, remaining: 50000 });

  const providerDisposableRef = useRef(null);
  const decorationIdsRef = useRef([]);
  const pollTimerRef = useRef(null);

  const refreshUsage = useCallback(async () => {
    try {
      const data = await getAIUsage();
      setUsage(data);
    } catch {
      // Keep last known usage if the request fails.
    }
  }, []);

  useEffect(() => {
    refreshUsage();
    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
      }
    };
  }, [refreshUsage]);

  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco) {
      return undefined;
    }

    providerDisposableRef.current?.dispose();
    providerDisposableRef.current = null;

    if (!autocompleteEnabled) {
      editor.updateOptions({ inlineSuggest: { enabled: false } });
      return undefined;
    }

    editor.updateOptions({ inlineSuggest: { enabled: true } });

    let debounceTimer = null;

    const provider = monaco.languages.registerInlineCompletionsProvider(language, {
      provideInlineCompletions: (model, position, _context, token) =>
        new Promise((resolve) => {
          clearTimeout(debounceTimer);
          debounceTimer = setTimeout(async () => {
            if (token.isCancellationRequested) {
              resolve({ items: [] });
              return;
            }

            try {
              const codeContext = extractContext(model, position, monaco);
              const data = await aiComplete({
                file_id: fileId,
                code_context: codeContext,
                cursor_line: position.lineNumber,
                cursor_column: position.column,
                language,
              });

              const suggestion = (data.suggestion || "").trim();
              if (!suggestion || token.isCancellationRequested) {
                resolve({ items: [] });
                return;
              }

              resolve({
                items: [
                  {
                    insertText: suggestion,
                    range: new monaco.Range(
                      position.lineNumber,
                      position.column,
                      position.lineNumber,
                      position.column,
                    ),
                  },
                ],
              });
              refreshUsage();
            } catch {
              resolve({ items: [] });
            }
          }, 800);
        }),
      freeInlineCompletions: () => {},
    });

    providerDisposableRef.current = provider;

    return () => {
      clearTimeout(debounceTimer);
      provider.dispose();
    };
  }, [autocompleteEnabled, editorRef, monacoRef, fileId, language, refreshUsage]);

  const applyBugDecorations = useCallback(
    (nextIssues) => {
      const editor = editorRef.current;
      const monaco = monacoRef.current;
      if (!editor || !monaco) {
        return;
      }

      const decorations = nextIssues
        .filter((issue) => issue.line && issue.line > 0)
        .map((issue) => ({
          range: new monaco.Range(issue.line, 1, issue.line, 1),
          options: {
            isWholeLine: true,
            className: `ai-bug-line ai-bug-line--${issue.severity || "info"}`,
            glyphMarginClassName: `ai-bug-glyph ai-bug-glyph--${issue.severity || "info"}`,
            hoverMessage: {
              value: `${issue.message}${issue.suggestion ? `\n\n${issue.suggestion}` : ""}`,
            },
          },
        }));

      decorationIdsRef.current = editor.deltaDecorations(decorationIdsRef.current, decorations);
    },
    [editorRef, monacoRef],
  );

  async function handleExplain() {
    const editor = editorRef.current;
    if (!editor) {
      return;
    }

    const selection = editor.getModel()?.getValueInRange(editor.getSelection());
    if (!selection?.trim()) {
      setExplainError("Select code in the editor first.");
      return;
    }

    setExplainLoading(true);
    setExplainError("");
    setExplanation("");

    try {
      const data = await aiExplain({ selected_code: selection, language });
      setExplanation(data.explanation || "");
      refreshUsage();
    } catch (error) {
      setExplainError(error.response?.data?.error || "Failed to explain selection.");
    } finally {
      setExplainLoading(false);
    }
  }

  async function handleDetectBugs() {
    const editor = editorRef.current;
    if (!editor) {
      return;
    }

    const code = editor.getModel()?.getValue() ?? "";
    setBugsLoading(true);
    setBugsError("");
    setIssues([]);

    try {
      const { job_id: jobId } = await aiDetectBugs({ code, language, file_id: fileId });
      refreshUsage();

      pollTimerRef.current = setInterval(async () => {
        try {
          const result = await aiDetectBugsResult(jobId);
          if (result.status === "pending") {
            return;
          }

          clearInterval(pollTimerRef.current);
          pollTimerRef.current = null;
          setBugsLoading(false);

          if (result.error) {
            setBugsError(result.error);
            return;
          }

          const nextIssues = result.issues || [];
          setIssues(nextIssues);
          applyBugDecorations(nextIssues);
        } catch (error) {
          clearInterval(pollTimerRef.current);
          pollTimerRef.current = null;
          setBugsLoading(false);
          setBugsError(error.response?.data?.error || "Bug detection failed.");
        }
      }, 2000);
    } catch (error) {
      setBugsLoading(false);
      setBugsError(error.response?.data?.error || "Failed to start bug detection.");
    }
  }

  const usagePercent = usage.budget ? Math.min(100, (usage.used / usage.budget) * 100) : 0;

  return (
    <aside className="ai-panel">
      <div className="ai-panel__tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`ai-panel__tab${activeTab === tab.id ? " ai-panel__tab--active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="ai-panel__body">
        {activeTab === "autocomplete" ? (
          <div className="ai-panel__section">
            <label className="ai-panel__toggle">
              <input
                type="checkbox"
                checked={autocompleteEnabled}
                onChange={(event) => setAutocompleteEnabled(event.target.checked)}
              />
              Enable ghost text completions
            </label>
            <p className="muted ai-panel__hint">
              Suggestions appear after 800ms idle. Press Tab to accept.
            </p>
          </div>
        ) : null}

        {activeTab === "explain" ? (
          <div className="ai-panel__section">
            <button
              type="button"
              className="ai-panel__action"
              onClick={handleExplain}
              disabled={explainLoading}
            >
              {explainLoading ? "Explaining…" : "Explain Selection"}
            </button>
            {explainError ? <p className="auth-error">{explainError}</p> : null}
            {explanation ? (
              <div className="ai-panel__explanation">
                <pre>{explanation}</pre>
              </div>
            ) : null}
          </div>
        ) : null}

        {activeTab === "bugs" ? (
          <div className="ai-panel__section">
            <button
              type="button"
              className="ai-panel__action"
              onClick={handleDetectBugs}
              disabled={bugsLoading}
            >
              {bugsLoading ? "Detecting…" : "Detect Bugs"}
            </button>
            {bugsError ? <p className="auth-error">{bugsError}</p> : null}
            {issues.length > 0 ? (
              <ul className="ai-issue-list">
                {issues.map((issue, index) => (
                  <li
                    key={`${issue.line}-${issue.message}-${index}`}
                    className={`ai-issue ${SEVERITY_CLASS[issue.severity] || SEVERITY_CLASS.info}`}
                  >
                    <div className="ai-issue__header">
                      <span className="ai-issue__line">
                        {issue.line ? `Line ${issue.line}` : "General"}
                      </span>
                      <span className="ai-issue__severity">{issue.severity || "info"}</span>
                    </div>
                    <p className="ai-issue__message">{issue.message}</p>
                    {issue.suggestion ? (
                      <p className="ai-issue__suggestion muted">{issue.suggestion}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </div>

      <footer className="ai-panel__footer">
        <div className="ai-panel__usage-label">
          Today: {usage.used}/{usage.budget} tokens
        </div>
        <div className="ai-panel__usage-bar">
          <div className="ai-panel__usage-fill" style={{ width: `${usagePercent}%` }} />
        </div>
      </footer>
    </aside>
  );
}
