import { useEffect, useState } from "react";

export default function PresenceBar({ provider }) {
  const [peers, setPeers] = useState([]);

  useEffect(() => {
    if (!provider) {
      setPeers([]);
      return undefined;
    }

    const onPeers = (peerList) => setPeers(peerList);
    provider.on("peers-change", onPeers);
    return () => provider.off("peers-change", onPeers);
  }, [provider]);

  if (peers.length === 0) {
    return (
      <div className="presence-bar" aria-label="Online collaborators">
        <span className="presence-bar-empty muted">Only you</span>
      </div>
    );
  }

  return (
    <div className="presence-bar" aria-label="Online collaborators">
      {peers.map((peer) => (
        <div
          key={peer.session_id || peer.user_id}
          className="presence-avatar"
          title={peer.display_name || "User"}
          style={{ background: peer.color || "#58a6ff" }}
        >
          {(peer.display_name || "U")[0].toUpperCase()}
          {peer.typing ? <span className="presence-typing-dot" aria-hidden="true" /> : null}
        </div>
      ))}
    </div>
  );
}
