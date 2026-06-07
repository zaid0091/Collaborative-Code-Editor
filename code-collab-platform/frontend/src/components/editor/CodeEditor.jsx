import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Editor from "@monaco-editor/react";

import { useComments } from "../../hooks/useComments.js";
import { useThrottledAwareness } from "../../hooks/useThrottledAwareness.js";
import { useYjsUndo } from "../../hooks/useYjsUndo.js";
import { useAuthStore } from "../../store/auth.store.js";
import { useCommentsStore } from "../../store/comments.store.js";
import AIPanel from "./AIPanel.jsx";
import CommentGutter from "./CommentGutter.jsx";
import CommentPanel from "./CommentPanel.jsx";
import NewCommentForm, { SelectionCommentTrigger } from "./NewCommentForm.jsx";
import CursorLayer from "./CursorLayer.jsx";
import OutputPanel from "./OutputPanel.jsx";
import RunButton from "./RunButton.jsx";

export default function CodeEditor({
  fileId,
  fileMeta,
  provider,
  ydoc,
  localUser,
  userRole = "viewer",
}) {
  const currentUser = useAuthStore((state) => state.user);
  const editorRef = useRef(null);
  const monacoRef = useRef(null);
  const bindingRef = useRef(null);
  const selectionListenerRef = useRef(null);
  const [editorInstance, setEditorInstance] = useState(null);
  const [monacoInstance, setMonacoInstance] = useState(null);
  const [executionResult, setExecutionResult] = useState(null);
  const [activeJobs, setActiveJobs] = useState(0);
  const [commentSelection, setCommentSelection] = useState(null);
  const [showCommentForm, setShowCommentForm] = useState(false);
  const [showCommentPanel, setShowCommentPanel] = useState(false);
  const [activeCommentLine, setActiveCommentLine] = useState(null);
  const setActiveThread = useCommentsStore((state) => state.setActiveThread);

  const {
    comments,
    isLoading: commentsLoading,
    error: commentsError,
    createComment,
    updateComment,
    resolveComment,
    deleteComment,
    addReaction,
  } = useComments(fileId, "main", provider);

  const openCommentCount = useMemo(
    () => comments.filter((comment) => !comment.is_resolved).length,
    [comments],
  );

  const yText = ydoc?.getText("content");
  const localOrigin = provider?.LOCAL_ORIGIN;
  const { undo, redo, clearOnSync } = useYjsUndo(yText, localOrigin);
  const { updateCursor, updateSelection, updateTyping } = useThrottledAwareness(
    ydoc?.awareness,
    localUser,
  );

  const monacoOptions = {
    fontSize: 14,
    glyphMargin: true,
    minimap: { enabled: fileMeta?.tier === "standard" },
    largeFileOptimizations: fileMeta?.tier !== "standard",
    wordBasedSuggestions: fileMeta?.tier === "standard" ? "currentDocument" : "off",
    renderValidationDecorations: "editable",
    scrollBeyondLastLine: false,
    automaticLayout: true,
  };

  const handleLineClick = useCallback(
    (lineNumber) => {
      setActiveCommentLine(lineNumber);
      setShowCommentPanel(true);
      editorInstance?.revealLineInCenter(lineNumber);
      const match = comments.find(
        (comment) => lineNumber >= comment.line_start && lineNumber <= comment.line_end,
      );
      if (match) {
        setActiveThread(match.id);
      }
    },
    [comments, editorInstance, setActiveThread],
  );

  const clearCommentSelection = useCallback(() => {
    setShowCommentForm(false);
    setCommentSelection(null);
    if (editorInstance) {
      const position = editorInstance.getPosition();
      if (position) {
        editorInstance.setSelection({
          startLineNumber: position.lineNumber,
          startColumn: position.column,
          endLineNumber: position.lineNumber,
          endColumn: position.column,
        });
      }
    }
  }, [editorInstance]);

  const handleCreateComment = useCallback(
    async (payload) => {
      await createComment(payload);
      setShowCommentForm(false);
      setCommentSelection(null);
      setShowCommentPanel(true);
    },
    [createComment],
  );

  function handleEditorDidMount(editor, monaco) {
    editorRef.current = editor;
    monacoRef.current = monaco;
    setMonacoInstance(monaco);
    setEditorInstance(editor);

    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyZ, () => undo());
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyY, () => redo());
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyZ, () =>
      redo(),
    );

    if (yText && localOrigin) {
      bindingRef.current?.destroy();
      bindingRef.current = bindYjsToMonaco(editor, yText, localOrigin);
    }

    editor.onDidChangeCursorPosition((event) => updateCursor(event.position));
    editor.onDidChangeCursorSelection((event) => updateSelection(event.selection));
    editor.onDidChangeModelContent(() => updateTyping());

    selectionListenerRef.current?.dispose();
    selectionListenerRef.current = editor.onDidChangeCursorSelection((event) => {
      const selection = event.selection;
      if (selection.isEmpty()) {
        setCommentSelection(null);
        setShowCommentForm(false);
        return;
      }
      setCommentSelection({
        startLineNumber: selection.startLineNumber,
        startColumn: selection.startColumn,
        endLineNumber: selection.endLineNumber,
        endColumn: selection.endColumn,
        isEmpty: () => false,
      });
    });
  }

  useEffect(() => {
    if (!provider) {
      return undefined;
    }

    provider.on("synced", clearOnSync);
    return () => provider.off("synced", clearOnSync);
  }, [provider, clearOnSync]);

  useEffect(
    () => () => {
      selectionListenerRef.current?.dispose();
      bindingRef.current?.destroy();
      bindingRef.current = null;
    },
    [],
  );

  if (!ydoc || !provider || !yText) {
    return (
      <div className="editor-shell">
        <p className="muted">Connecting editor…</p>
      </div>
    );
  }

  return (
    <div className="editor-workspace">
      <div className="editor-toolbar-actions">
        <RunButton
          fileId={fileId}
          language={fileMeta?.language || "python"}
          getCode={() => editorRef.current?.getModel()?.getValue() ?? yText.toString()}
          onResult={setExecutionResult}
          onActiveChange={setActiveJobs}
        />
        <button
          type="button"
          className={`comments-toolbar-btn${showCommentPanel ? " comments-toolbar-btn--active" : ""}`}
          onClick={() => setShowCommentPanel((value) => !value)}
        >
          Comments ({openCommentCount})
        </button>
        {activeJobs > 0 ? (
          <span className="muted editor-active-jobs">{activeJobs} active job(s)</span>
        ) : null}
      </div>
      <div className={`editor-body${showCommentPanel ? " editor-body--with-comments" : ""}`}>
        <div className="editor-shell">
          <Editor
            key={fileId}
            language={fileMeta?.language || "plaintext"}
            theme="vs-dark"
            options={monacoOptions}
            onMount={handleEditorDidMount}
          />
          <CursorLayer provider={provider} editorRef={editorRef} />
          <CommentGutter
            editor={editorInstance}
            monaco={monacoInstance}
            comments={comments}
            onLineClick={handleLineClick}
          />
          <SelectionCommentTrigger
            editor={editorInstance}
            selection={commentSelection}
            onOpen={() => setShowCommentForm(true)}
          />
          {showCommentForm && commentSelection ? (
            <NewCommentForm
              editor={editorInstance}
              selection={commentSelection}
              onSubmit={handleCreateComment}
              onCancel={clearCommentSelection}
            />
          ) : null}
        </div>
        {showCommentPanel ? (
          <CommentPanel
            comments={comments}
            isLoading={commentsLoading}
            error={commentsError}
            currentUser={currentUser}
            userRole={userRole}
            activeLine={activeCommentLine}
            onLineSelect={(lineNumber) => {
              setActiveCommentLine(lineNumber);
              editorInstance?.revealLineInCenter(lineNumber);
            }}
            onCreateAtSelection={() => {
              if (commentSelection && !commentSelection.isEmpty()) {
                setShowCommentForm(true);
                return;
              }
              const position = editorInstance?.getPosition();
              if (position) {
                setCommentSelection({
                  startLineNumber: position.lineNumber,
                  startColumn: 1,
                  endLineNumber: position.lineNumber,
                  endColumn: 1,
                  isEmpty: () => false,
                });
                setShowCommentForm(true);
              }
            }}
            onReply={(comment, content) =>
              createComment({
                content,
                line_start: comment.line_start,
                line_end: comment.line_end,
                col_start: comment.col_start,
                col_end: comment.col_end,
                parent_id: comment.id,
              })
            }
            onResolve={resolveComment}
            onDelete={deleteComment}
            onReact={addReaction}
            onEdit={(commentId, content) => updateComment(commentId, { content })}
          />
        ) : null}
        <AIPanel
          editorRef={editorRef}
          monacoRef={monacoRef}
          fileId={fileId}
          language={fileMeta?.language || "python"}
        />
      </div>
      <OutputPanel result={executionResult} />
    </div>
  );
}

function bindYjsToMonaco(editor, yText, LOCAL_ORIGIN) {
  let isApplyingRemote = false;
  let isApplyingLocal = false;
  const model = editor.getModel();

  if (model && model.getValue() !== yText.toString()) {
    isApplyingRemote = true;
    model.setValue(yText.toString());
    isApplyingRemote = false;
  }

  const remoteObserver = (event) => {
    if (event.transaction.origin === LOCAL_ORIGIN || isApplyingLocal) {
      return;
    }

    const currentModel = editor.getModel();
    if (!currentModel) {
      return;
    }

    isApplyingRemote = true;
    const position = editor.getPosition();
    const yjsContent = yText.toString();
    if (currentModel.getValue() !== yjsContent) {
      currentModel.setValue(yjsContent);
      if (position) {
        editor.setPosition(position);
      }
    }
    isApplyingRemote = false;
  };

  yText.observe(remoteObserver);

  const localContentListener = editor.onDidChangeModelContent((event) => {
    if (isApplyingRemote) {
      return;
    }

    const currentModel = editor.getModel();
    if (!currentModel) {
      return;
    }

    isApplyingLocal = true;
    yText.doc.transact(() => {
      event.changes
        .sort((left, right) => right.rangeOffset - left.rangeOffset)
        .forEach((change) => {
          yText.delete(change.rangeOffset, change.rangeLength);
          if (change.text) {
            yText.insert(change.rangeOffset, change.text);
          }
        });
    }, LOCAL_ORIGIN);
    isApplyingLocal = false;
  });

  return {
    destroy() {
      yText.unobserve(remoteObserver);
      localContentListener.dispose();
    },
  };
}
