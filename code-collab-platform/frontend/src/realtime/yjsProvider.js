import * as Y from "yjs";

const LOCAL_ORIGIN = Symbol("local");

class EventEmitter {
  constructor() {
    this._listeners = new Map();
  }

  on(event, handler) {
    if (!this._listeners.has(event)) {
      this._listeners.set(event, new Set());
    }
    this._listeners.get(event).add(handler);
  }

  off(event, handler) {
    this._listeners.get(event)?.delete(handler);
  }

  emit(event, ...args) {
    this._listeners.get(event)?.forEach((handler) => handler(...args));
  }

  removeAllListeners() {
    this._listeners.clear();
  }
}

function bytesToBase64(bytes) {
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

function base64ToBytes(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function getWsBaseUrl() {
  const configured = import.meta.env.VITE_WS_URL;
  if (configured) {
    return configured.replace(/\/$/, "");
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws`;
}

export class CollabProvider extends EventEmitter {
  constructor(fileId, getAccessToken, ydoc) {
    super();
    this.fileId = fileId;
    this.getAccessToken = getAccessToken;
    this.ydoc = ydoc;
    this.ws = null;
    this.status = "connecting";
    this.lastKnownVersion = null;
    this.offlineQueue = [];
    this.peers = new Map();
    this._reconnectAttempts = 0;
    this._maxReconnectDelay = 30000;
    this._reconnectTimer = null;
    this._pageVisible = !document.hidden;
    this._heartbeatInterval = null;
    this._updateHandler = null;
    this._visibilityHandler = () => {
      this._pageVisible = !document.hidden;
      if (this._pageVisible && this.status === "offline") {
        this._scheduleReconnect();
      }
    };

    document.addEventListener("visibilitychange", this._visibilityHandler);

    this._updateHandler = (update, origin) => {
      if (origin !== LOCAL_ORIGIN) {
        return;
      }

      const encoded = bytesToBase64(update);
      if (this.status === "active") {
        this._send({ type: "update", update: encoded });
      } else {
        this.offlineQueue.push(encoded);
      }
    };
    this.ydoc.on("update", this._updateHandler);
  }

  attachAwareness(awareness) {
    this.awareness = awareness;
  }

  sendAwarenessState(state) {
    if (this.status !== "active" || !state) {
      return;
    }

    this._send({
      type: "awareness",
      data: bytesToBase64(new TextEncoder().encode(JSON.stringify(state))),
    });

    if (state.cursor) {
      this._send({
        type: "cursor",
        position: state.cursor,
        selection: state.selection || {},
      });
    }
  }

  connect() {
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onclose = null;
      this.ws.onerror = null;
      if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
        this.ws.close();
      }
    }

    const token = this.getAccessToken();
    if (!token) {
      this._setStatus("offline");
      this.emit("auth-failed");
      return;
    }

    const wsUrl = `${getWsBaseUrl()}/collab/${this.fileId}/?token=${encodeURIComponent(token)}`;
    this.ws = new WebSocket(wsUrl);
    this.ws.binaryType = "arraybuffer";
    this._setStatus("connecting");

    this.ws.onopen = () => {
      this._reconnectAttempts = 0;
      this._setStatus("syncing");

      const stateVector = Y.encodeStateVector(this.ydoc);
      this._send({
        type: "sync_request",
        file_id: this.fileId,
        last_known_version: this.lastKnownVersion,
        client_state_vector: bytesToBase64(stateVector),
      });

      this._startHeartbeat();
    };

    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      this._handleMessage(message);
    };

    this.ws.onclose = (event) => {
      this._stopHeartbeat();
      if (event.code === 4001) {
        this._setStatus("offline");
        this.emit("auth-failed");
        return;
      }
      if (event.code === 4000 || event.code === 4010) {
        this._scheduleReconnect(0);
        return;
      }
      if (event.code === 4003) {
        this._setStatus("offline");
        this.emit("auth-failed");
        return;
      }
      this._setStatus("reconnecting");
      this._scheduleReconnect();
    };

    this.ws.onerror = () => {
      // onclose handles recovery
    };
  }

  _handleMessage(message) {
    switch (message.type) {
      case "sync_response":
        this._applySyncResponse(message);
        break;
      case "sync_complete":
        this._onSyncComplete(message);
        break;
      case "update":
        this._applyRemoteUpdate(message.update);
        break;
      case "awareness":
        this.emit("awareness-change", message.data);
        break;
      case "cursor":
        this._updatePeerCursor(message);
        break;
      case "user_joined":
        this.peers.set(message.session_id, {
          user_id: message.user_id,
          display_name: message.display_name,
          session_id: message.session_id,
          color: assignUserColor(message.user_id),
        });
        this.emit("peers-change", Array.from(this.peers.values()));
        break;
      case "user_left":
        this.peers.delete(message.session_id);
        this.emit("peers-change", Array.from(this.peers.values()));
        break;
      case "ack":
        this.lastKnownVersion = message.version;
        break;
      case "pong":
        break;
      case "server_draining":
        this._setStatus("reconnecting");
        this._showToast(message.message || "Server updating — reconnecting automatically...");
        setTimeout(() => this._scheduleReconnect(0), 2000);
        break;
      case "server_version":
        this.lastKnownVersion = message.version;
        break;
      case "rate_limit_warning":
        this.emit("rate-limit-warning", message);
        break;
      case "error":
        this.emit("error", message);
        break;
      case "comment_event":
        this.emit("comment_event", message);
        break;
      default:
        break;
    }
  }

  _applySyncResponse(message) {
    if (message.snapshot) {
      Y.applyUpdate(this.ydoc, base64ToBytes(message.snapshot));
    }

    for (const updateB64 of message.delta_updates || []) {
      Y.applyUpdate(this.ydoc, base64ToBytes(updateB64));
    }

    if (message.server_version != null) {
      this.lastKnownVersion = message.server_version;
    }
  }

  _onSyncComplete(message) {
    this.lastKnownVersion = message.server_version;

    for (const updateB64 of this.offlineQueue) {
      this._send({ type: "update", update: updateB64 });
    }
    this.offlineQueue = [];

    this._setStatus("active");
    this.emit("synced");

    const localState = this.awareness?.getLocalState?.();
    if (localState && Object.keys(localState).length > 0) {
      this.sendAwarenessState(localState);
    }
  }

  _applyRemoteUpdate(updateB64) {
    Y.applyUpdate(this.ydoc, base64ToBytes(updateB64));
  }

  _scheduleReconnect(overrideDelay = null) {
    if (!this._pageVisible) {
      return;
    }

    clearTimeout(this._reconnectTimer);
    const delay =
      overrideDelay ??
      Math.min(1000 * 2 ** this._reconnectAttempts + Math.random() * 500, this._maxReconnectDelay);
    this._reconnectAttempts += 1;
    this._reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  _send(message) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  _startHeartbeat() {
    this._stopHeartbeat();
    this._heartbeatInterval = setInterval(() => {
      this._send({ type: "ping" });
    }, 25000);
  }

  _stopHeartbeat() {
    clearInterval(this._heartbeatInterval);
    this._heartbeatInterval = null;
  }

  _setStatus(status) {
    this.status = status;
    this.emit("status-change", status);
  }

  _showToast(message) {
    const toast = document.createElement("div");
    toast.textContent = message;
    toast.setAttribute("role", "status");
    Object.assign(toast.style, {
      position: "fixed",
      bottom: "24px",
      right: "24px",
      padding: "12px 16px",
      background: "#1e293b",
      color: "#f8fafc",
      borderRadius: "8px",
      boxShadow: "0 8px 24px rgba(15, 23, 42, 0.35)",
      zIndex: "9999",
      maxWidth: "320px",
      fontSize: "14px",
    });
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
  }

  _updatePeerCursor(message) {
    const peer = this.peers.get(message.session_id) || {};
    this.peers.set(message.session_id, {
      ...peer,
      user_id: message.user_id || peer.user_id,
      display_name: peer.display_name,
      session_id: message.session_id,
      color: peer.color || assignUserColor(message.user_id || message.session_id),
      cursor: message.position,
      selection: message.selection,
    });
    this.emit("cursor-change", { session_id: message.session_id, ...message });
  }

  destroy() {
    clearTimeout(this._reconnectTimer);
    this._stopHeartbeat();
    document.removeEventListener("visibilitychange", this._visibilityHandler);
    if (this._updateHandler) {
      this.ydoc.off("update", this._updateHandler);
      this._updateHandler = null;
    }
    this.ws?.close();
    this.ws = null;
    this.removeAllListeners();
  }

  get LOCAL_ORIGIN() {
    return LOCAL_ORIGIN;
  }
}

function assignUserColor(userId) {
  const colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD"];
  const index = (userId?.charCodeAt(0) || 0) % colors.length;
  return colors[index];
}

export { LOCAL_ORIGIN, assignUserColor };
