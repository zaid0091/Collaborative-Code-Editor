import { useMemo, useState } from "react";

import CommentThread from "./CommentThread.jsx";
import { canEditComments } from "./commentUtils.js";
import { useCommentsStore } from "../../store/comments.store.js";

export default function CommentPanel({
  comments,
  isLoading,
  error,
  currentUser,
  userRole,
  activeLine,
  onLineSelect,
  onCreateAtSelection,
  onReply,
  onResolve,
  onDelete,
  onReact,
  onEdit,
}) {
  const setActiveThread = useCommentsStore((state) => state.setActiveThread);
  const [activeTab, setActiveTab] = useState("open");
  const [authorFilter, setAuthorFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [lineFilter, setLineFilter] = useState("");

  const openCount = comments.filter((comment) => !comment.is_resolved).length;

  const authors = useMemo(() => {
    const names = new Set();
    for (const comment of comments) {
      if (comment.author?.display_name) {
        names.add(comment.author.display_name);
      }
      for (const reply of comment.replies || []) {
        if (reply.author?.display_name) {
          names.add(reply.author.display_name);
        }
      }
    }
    return Array.from(names).sort();
  }, [comments]);

  const filteredComments = useMemo(() => {
    const resolvedFilter = activeTab === "resolved";
    return comments
      .filter((comment) => comment.is_resolved === resolvedFilter)
      .filter((comment) => {
        if (authorFilter !== "all" && comment.author?.display_name !== authorFilter) {
          return false;
        }
        if (lineFilter) {
          const line = Number(lineFilter);
          if (!Number.isNaN(line) && (line < comment.line_start || line > comment.line_end)) {
            return false;
          }
        }
        if (!searchQuery.trim()) {
          return true;
        }
        const query = searchQuery.toLowerCase();
        const haystack = [comment.content, ...(comment.replies || []).map((reply) => reply.content)]
          .join(" ")
          .toLowerCase();
        return haystack.includes(query);
      })
      .sort((left, right) => left.line_start - right.line_start);
  }, [activeTab, authorFilter, comments, lineFilter, searchQuery]);

  function handleLineJump(lineNumber) {
    onLineSelect?.(lineNumber);
    const match = comments.find(
      (comment) => lineNumber >= comment.line_start && lineNumber <= comment.line_end,
    );
    if (match) {
      setActiveThread(match.id);
    }
  }

  return (
    <aside className="comment-panel">
      <header className="comment-panel__header">
        <div>
          <h3>Comments</h3>
          <span className="comment-panel__badge">{openCount} open</span>
        </div>
        <button
          type="button"
          className="comment-btn"
          disabled={!canEditComments(userRole)}
          onClick={onCreateAtSelection}
        >
          New Comment
        </button>
      </header>

      <div className="comment-panel__tabs">
        <button
          type="button"
          className={`comment-panel__tab${activeTab === "open" ? " comment-panel__tab--active" : ""}`}
          onClick={() => setActiveTab("open")}
        >
          Open
        </button>
        <button
          type="button"
          className={`comment-panel__tab${activeTab === "resolved" ? " comment-panel__tab--active" : ""}`}
          onClick={() => setActiveTab("resolved")}
        >
          Resolved
        </button>
      </div>

      <div className="comment-panel__filters">
        <input
          type="search"
          placeholder="Search comments…"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
        />
        <div className="comment-panel__filter-row">
          <label>
            Line
            <input
              type="number"
              min="1"
              placeholder={activeLine ? String(activeLine) : "Any"}
              value={lineFilter}
              onChange={(event) => setLineFilter(event.target.value)}
            />
          </label>
          <label>
            Author
            <select value={authorFilter} onChange={(event) => setAuthorFilter(event.target.value)}>
              <option value="all">All authors</option>
              {authors.map((author) => (
                <option key={author} value={author}>
                  {author}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <div className="comment-panel__body">
        {isLoading ? <p className="muted">Loading comments…</p> : null}
        {error ? <p className="auth-error">{error}</p> : null}
        {!isLoading && !error && filteredComments.length === 0 ? (
          <p className="muted comment-panel__empty">
            No comments yet. Select lines in the editor to add one.
          </p>
        ) : null}
        {filteredComments.map((comment) => (
          <div
            key={comment.id}
            className={`comment-panel__entry${
              activeLine >= comment.line_start && activeLine <= comment.line_end
                ? " comment-panel__entry--active"
                : ""
            }`}
          >
            <button
              type="button"
              className="comment-panel__jump"
              onClick={() => handleLineJump(comment.line_start)}
            >
              Jump to line {comment.line_start}
            </button>
            <CommentThread
              comment={comment}
              replies={comment.replies || []}
              currentUser={currentUser}
              userRole={userRole}
              onReply={onReply}
              onResolve={onResolve}
              onDelete={onDelete}
              onReact={onReact}
              onEdit={onEdit}
            />
          </div>
        ))}
      </div>
    </aside>
  );
}
