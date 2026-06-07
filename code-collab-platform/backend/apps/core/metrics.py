"""Custom Prometheus metrics (Section 11)."""

from prometheus_client import Counter, Gauge, Histogram

ws_active_connections = Gauge(
    "ws_active_connections_total",
    "Currently active WebSocket connections",
    ["file_id"],
)
ws_messages_total = Counter(
    "ws_messages_total",
    "Total WebSocket messages processed",
    ["message_type", "direction"],
)
ws_abuse_disconnects_total = Counter(
    "ws_abuse_disconnects_total",
    "WebSocket connections force-closed due to abuse",
    ["reason"],
)
ws_ban_active = Gauge(
    "ws_ban_active_total",
    "Users currently banned from WebSocket",
)

crdt_buffer_depth = Gauge(
    "crdt_buffer_depth_ops",
    "Ops in Redis hot buffer awaiting flush",
    ["file_id"],
)
crdt_compaction_duration_seconds = Histogram(
    "crdt_compaction_duration_seconds",
    "Time taken for snapshot compaction",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)
crdt_ops_compacted_total = Counter(
    "crdt_ops_compacted_total",
    "Total OperationLog rows compacted into snapshots",
)

execution_queue_depth = Gauge(
    "execution_queue_depth",
    "Jobs waiting in Celery execution queues",
    ["queue"],
)
execution_duration_seconds = Histogram(
    "execution_duration_seconds",
    "Code execution wall-clock duration",
    ["language", "status"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)
execution_fairness_rejections_total = Counter(
    "execution_fairness_rejections_total",
    "Jobs rejected by fairness scheduler",
    ["reason"],
)
execution_active_per_user = Gauge(
    "execution_active_jobs",
    "Currently running execution jobs per user (sampled)",
)
