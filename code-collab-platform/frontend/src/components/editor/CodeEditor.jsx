import { useEffect, useRef } from "react";
import Editor from "@monaco-editor/react";

import { useThrottledAwareness } from "../../hooks/useThrottledAwareness.js";
import { useYjsUndo } from "../../hooks/useYjsUndo.js";
import CursorLayer from "./CursorLayer.jsx";

export default function CodeEditor({ fileId, fileMeta, provider, ydoc, localUser }) {
  const editorRef = useRef(null);
  const bindingRef = useRef(null);

  const yText = ydoc?.getText("content");
  const localOrigin = provider?.LOCAL_ORIGIN;
  const { undo, redo, clearOnSync } = useYjsUndo(yText, localOrigin);
  const { updateCursor, updateSelection, updateTyping } = useThrottledAwareness(
    ydoc?.awareness,
    localUser,
  );

  const monacoOptions = {
    fontSize: 14,
    minimap: { enabled: fileMeta?.tier === "standard" },
    largeFileOptimizations: fileMeta?.tier !== "standard",
    wordBasedSuggestions: fileMeta?.tier === "standard" ? "currentDocument" : "off",
    renderValidationDecorations: "editable",
    scrollBeyondLastLine: false,
    automaticLayout: true,
  };

  function handleEditorDidMount(editor, monaco) {
    editorRef.current = editor;

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
    <div className="editor-shell">
      <Editor
        key={fileId}
        language={fileMeta?.language || "plaintext"}
        theme="vs-dark"
        options={monacoOptions}
        onMount={handleEditorDidMount}
      />
      <CursorLayer provider={provider} editorRef={editorRef} />
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
