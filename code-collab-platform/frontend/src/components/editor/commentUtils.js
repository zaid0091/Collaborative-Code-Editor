export const ALLOWED_EMOJIS = ["👍", "👎", "❤️", "🎉", "😕", "🚀", "👀", "✅"];

export function formatRelativeTime(value) {
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) {
    return "";
  }

  const diffMs = Date.now() - timestamp;
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  const days = Math.floor(hours / 24);
  if (days < 30) {
    return `${days}d ago`;
  }
  return new Date(value).toLocaleDateString();
}

export function renderMarkdownLite(text) {
  const escaped = String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  return escaped
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br />");
}

export function formatLineRange(lineStart, lineEnd) {
  if (lineStart === lineEnd) {
    return `Line ${lineStart}`;
  }
  return `Lines ${lineStart}–${lineEnd}`;
}

export function canEditComments(role) {
  return role === "owner" || role === "editor";
}

export function canResolveComments(role) {
  return role === "owner" || role === "editor";
}

export function canDeleteComment(role, comment, currentUserId) {
  if (comment.author?.id === currentUserId) {
    return true;
  }
  return role === "owner";
}
