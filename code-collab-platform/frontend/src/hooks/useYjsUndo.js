import { useCallback, useEffect, useRef, useState } from "react";
import * as Y from "yjs";

const CAPTURE_TIMEOUT = parseInt(import.meta.env.VITE_UNDO_CAPTURE_TIMEOUT_MS || "500", 10);

export function useYjsUndo(yText, LOCAL_ORIGIN) {
  const managerRef = useRef(null);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  useEffect(() => {
    if (!yText || !LOCAL_ORIGIN) {
      return undefined;
    }

    const manager = new Y.UndoManager(yText, {
      trackedOrigins: new Set([LOCAL_ORIGIN]),
      captureTimeout: CAPTURE_TIMEOUT,
    });
    managerRef.current = manager;

    function updateState() {
      setCanUndo(manager.canUndo());
      setCanRedo(manager.canRedo());
    }

    manager.on("stack-item-added", updateState);
    manager.on("stack-item-popped", updateState);
    updateState();

    return () => {
      manager.destroy();
      managerRef.current = null;
      setCanUndo(false);
      setCanRedo(false);
    };
  }, [yText, LOCAL_ORIGIN]);

  const undo = useCallback(() => {
    managerRef.current?.undo();
  }, []);

  const redo = useCallback(() => {
    managerRef.current?.redo();
  }, []);

  const clearOnSync = useCallback(() => {
    managerRef.current?.clear();
    setCanUndo(false);
    setCanRedo(false);
  }, []);

  return { undo, redo, canUndo, canRedo, clearOnSync };
}
