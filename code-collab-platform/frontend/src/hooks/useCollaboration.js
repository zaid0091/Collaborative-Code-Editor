import { useEffect, useRef, useState } from "react";
import * as Y from "yjs";

import { CollabProvider } from "../realtime/yjsProvider.js";
import { useAuthStore } from "../store/auth.store.js";

function createLocalAwareness(onChange) {
  let state = {};

  return {
    getLocalState() {
      return state;
    },
    setLocalState(nextState) {
      state = nextState;
      onChange?.(state);
    },
  };
}

export function useCollaboration(fileId) {
  const accessToken = useAuthStore((state) => state.accessToken);
  const ydocRef = useRef(null);
  const providerRef = useRef(null);
  const [status, setStatus] = useState("connecting");
  const [peers, setPeers] = useState([]);
  const [provider, setProvider] = useState(null);
  const [ydoc, setYdoc] = useState(null);

  useEffect(() => {
    if (!fileId || !accessToken) {
      setProvider(null);
      setYdoc(null);
      setStatus("offline");
      setPeers([]);
      return undefined;
    }

    const nextDoc = new Y.Doc();
    ydocRef.current = nextDoc;
    setYdoc(nextDoc);

    const nextProvider = new CollabProvider(
      fileId,
      () => useAuthStore.getState().accessToken,
      nextDoc,
    );
    const awareness = createLocalAwareness((state) => {
      nextProvider.sendAwarenessState(state);
    });
    nextDoc.awareness = awareness;
    nextProvider.attachAwareness(awareness);

    providerRef.current = nextProvider;
    setProvider(nextProvider);

    const onStatusChange = (nextStatus) => setStatus(nextStatus);
    const onPeersChange = (peerList) => setPeers(peerList);

    nextProvider.on("status-change", onStatusChange);
    nextProvider.on("peers-change", onPeersChange);
    nextProvider.connect();

    return () => {
      nextProvider.destroy();
      nextDoc.destroy();
      providerRef.current = null;
      ydocRef.current = null;
      setProvider(null);
      setYdoc(null);
      setPeers([]);
      setStatus("offline");
    };
  }, [fileId, accessToken]);

  return {
    ydoc,
    provider,
    status,
    peers,
  };
}
