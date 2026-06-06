import { useEffect, useRef, useState } from "react";

const CURSOR_FPS = parseInt(import.meta.env.VITE_CURSOR_RENDER_FPS || "12", 10);
const CURSOR_INTERVAL_MS = 1000 / CURSOR_FPS;

export default function CursorLayer({ provider, editorRef }) {
  const [peers, setPeers] = useState([]);
  const pendingPeersRef = useRef([]);
  const rafRef = useRef(null);
  const lastRenderRef = useRef(0);
  const decorationIdsRef = useRef([]);

  useEffect(() => {
    if (!provider) {
      return undefined;
    }

    function onCursorChange() {
      pendingPeersRef.current = Array.from(provider.peers.values());

      const now = performance.now();
      if (now - lastRenderRef.current < CURSOR_INTERVAL_MS) {
        if (!rafRef.current) {
          rafRef.current = requestAnimationFrame(() => {
            setPeers([...pendingPeersRef.current]);
            lastRenderRef.current = performance.now();
            rafRef.current = null;
          });
        }
        return;
      }

      setPeers([...pendingPeersRef.current]);
      lastRenderRef.current = now;
    }

    provider.on("cursor-change", onCursorChange);
    provider.on("peers-change", onCursorChange);

    return () => {
      provider.off("cursor-change", onCursorChange);
      provider.off("peers-change", onCursorChange);
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
  }, [provider]);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) {
      return;
    }

    const decorations = peers
      .filter((peer) => peer.cursor)
      .map((peer) => ({
        range: {
          startLineNumber: peer.cursor.lineNumber,
          startColumn: peer.cursor.column,
          endLineNumber: peer.cursor.lineNumber,
          endColumn: peer.cursor.column + 1,
        },
        options: {
          className: "remote-cursor-marker",
          beforeContentClassName: "remote-cursor-label",
          hoverMessage: { value: peer.display_name || "User" },
          stickiness: 1,
        },
      }));

    decorationIdsRef.current = editor.deltaDecorations(decorationIdsRef.current, decorations);
  }, [peers, editorRef]);

  return null;
}
