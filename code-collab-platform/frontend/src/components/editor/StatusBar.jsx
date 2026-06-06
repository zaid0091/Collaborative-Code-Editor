const STATUS_CONFIG = {
  active: { label: "Live", className: "status-dot status-dot--active" },
  syncing: { label: "Syncing…", className: "status-dot status-dot--syncing" },
  connecting: { label: "Syncing…", className: "status-dot status-dot--syncing" },
  reconnecting: { label: "Reconnecting…", className: "status-dot status-dot--reconnecting" },
  offline: { label: "Offline", className: "status-dot status-dot--offline" },
};

export default function StatusBar({ status }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.offline;

  return (
    <div className="connection-status" aria-live="polite">
      <span className={config.className} aria-hidden="true" />
      <span>{config.label}</span>
    </div>
  );
}
