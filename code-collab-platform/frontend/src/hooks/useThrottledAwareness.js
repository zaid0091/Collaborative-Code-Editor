import { useEffect, useRef } from "react";

const CURSOR_THROTTLE_MS = parseInt(import.meta.env.VITE_AWARENESS_THROTTLE_MS || "80", 10);
const SELECTION_DEBOUNCE_MS = 100;
const TYPING_CLEAR_MS = 3000;

export function useThrottledAwareness(awareness, localUser) {
  const lastCursorRef = useRef(null);
  const selectionDebounceRef = useRef(null);
  const typingClearRef = useRef(null);
  const throttleTimerRef = useRef(null);
  const pendingStateRef = useRef({});

  function flushAwareness() {
    if (!awareness || Object.keys(pendingStateRef.current).length === 0) {
      return;
    }

    awareness.setLocalState({
      ...awareness.getLocalState(),
      ...pendingStateRef.current,
      user: localUser,
    });
    pendingStateRef.current = {};
  }

  function scheduleFlush() {
    if (throttleTimerRef.current) {
      return;
    }

    throttleTimerRef.current = setTimeout(() => {
      flushAwareness();
      throttleTimerRef.current = null;
    }, CURSOR_THROTTLE_MS);
  }

  function updateCursor(position) {
    const key = `${position.lineNumber}:${position.column}`;
    if (key === lastCursorRef.current) {
      return;
    }
    lastCursorRef.current = key;
    pendingStateRef.current.cursor = position;
    scheduleFlush();
  }

  function updateSelection(selection) {
    clearTimeout(selectionDebounceRef.current);
    selectionDebounceRef.current = setTimeout(() => {
      pendingStateRef.current.selection = selection;
      scheduleFlush();
    }, SELECTION_DEBOUNCE_MS);
  }

  function updateTyping() {
    pendingStateRef.current.typing = true;
    scheduleFlush();

    clearTimeout(typingClearRef.current);
    typingClearRef.current = setTimeout(() => {
      pendingStateRef.current.typing = false;
      scheduleFlush();
    }, TYPING_CLEAR_MS);
  }

  useEffect(
    () => () => {
      clearTimeout(throttleTimerRef.current);
      clearTimeout(selectionDebounceRef.current);
      clearTimeout(typingClearRef.current);
    },
    [],
  );

  return { updateCursor, updateSelection, updateTyping };
}
