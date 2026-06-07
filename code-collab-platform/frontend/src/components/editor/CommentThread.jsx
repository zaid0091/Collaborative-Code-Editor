import { useMemo, useState } from "react";

import {
  ALLOWED_EMOJIS,
  canDeleteComment,
  canResolveComments,
  formatLineRange,
  formatRelativeTime,
  renderMarkdownLite,
} from "./commentUtils.js";

function ReplyInput({ onSubmit, onCancel }) {
  const [value, setValue] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!value.trim() || isSubmitting) {
      return;
    }
    setIsSubmitting(true);
    try {
      await onSubmit(value.trim());
      setValue("");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="comment-reply-form" onSubmit={handleSubmit}>
      <textarea
        value={value}
        maxLength={10000}
        rows={3}
        placeholder="Write a reply…"
        onChange={(event) => setValue(event.target.value)}
      />
      <div className="comment-reply-form__actions">
        <button type="button" className="comment-btn comment-btn--ghost" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="comment-btn" disabled={!value.trim() || isSubmitting}>
          Reply
        </button>
      </div>
    </form>
  );
}

function CommentBody({
  comment,
  currentUser,
  userRole,
  depth,
  onReply,
  onResolve,
  onDelete,
  onReact,
  onEdit,
}) {
  const [showReply, setShowReply] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(comment.content);
  const [showConfirmDelete, setShowConfirmDelete] = useState(false);
  const [collapsed, setCollapsed] = useState(comment.is_resolved);

  const isAuthor = comment.author?.id === currentUser?.id;
  const canResolve = canResolveComments(userRole);
  const canDelete = canDeleteComment(userRole, comment, currentUser?.id);
  const reactionMap = useMemo(() => {
    const map = new Map();
    for (const reaction of comment.reactions || []) {
      map.set(reaction.emoji, reaction.count || 0);
    }
    return map;
  }, [comment.reactions]);

  async function handleEditSave() {
    if (!editValue.trim()) {
      return;
    }
    await onEdit(comment.id, editValue.trim());
    setIsEditing(false);
  }

  if (comment.is_resolved && collapsed && depth === 0) {
    return (
      <div className="comment-thread comment-thread--resolved comment-thread--collapsed">
        <button
          type="button"
          className="comment-btn comment-btn--ghost"
          onClick={() => setCollapsed(false)}
        >
          Show resolved thread
        </button>
      </div>
    );
  }

  return (
    <article
      className={`comment-thread${comment.is_resolved ? " comment-thread--resolved" : ""}${depth > 0 ? " comment-thread--reply" : ""}`}
    >
      <header className="comment-thread__header">
        <div className="comment-thread__author">
          <span className="comment-thread__avatar" aria-hidden="true">
            {(comment.author?.display_name || "?").slice(0, 1).toUpperCase()}
          </span>
          <div>
            <strong>{comment.author?.display_name || "Deleted user"}</strong>
            <span className="muted comment-thread__time">
              {formatRelativeTime(comment.created_at)}
            </span>
          </div>
        </div>
        {depth === 0 ? (
          <span className="comment-thread__line-badge">
            {formatLineRange(comment.line_start, comment.line_end)}
          </span>
        ) : null}
      </header>

      {isEditing ? (
        <div className="comment-edit-form">
          <textarea
            value={editValue}
            maxLength={10000}
            rows={4}
            onChange={(event) => setEditValue(event.target.value)}
          />
          <div className="comment-reply-form__actions">
            <button
              type="button"
              className="comment-btn comment-btn--ghost"
              onClick={() => setIsEditing(false)}
            >
              Cancel
            </button>
            <button type="button" className="comment-btn" onClick={handleEditSave}>
              Save
            </button>
          </div>
        </div>
      ) : (
        <div
          className="comment-thread__content"
          dangerouslySetInnerHTML={{ __html: renderMarkdownLite(comment.content) }}
        />
      )}

      <div className="comment-reactions">
        {ALLOWED_EMOJIS.map((emoji) => {
          const count = reactionMap.get(emoji) || 0;
          if (count === 0) {
            return (
              <button
                key={emoji}
                type="button"
                className="comment-reaction-btn comment-reaction-btn--empty"
                onClick={() => onReact(comment.id, emoji)}
              >
                {emoji}
              </button>
            );
          }
          return (
            <button
              key={emoji}
              type="button"
              className="comment-reaction-btn"
              onClick={() => onReact(comment.id, emoji)}
            >
              {emoji} {count}
            </button>
          );
        })}
      </div>

      <div className="comment-thread__actions">
        {depth === 0 ? (
          <button
            type="button"
            className="comment-btn comment-btn--ghost"
            onClick={() => setShowReply((value) => !value)}
          >
            Reply
          </button>
        ) : null}
        {isAuthor ? (
          <button
            type="button"
            className="comment-btn comment-btn--ghost"
            onClick={() => setIsEditing(true)}
          >
            Edit
          </button>
        ) : null}
        {canResolve ? (
          <button
            type="button"
            className="comment-btn comment-btn--ghost"
            onClick={() => onResolve(comment.id, !comment.is_resolved)}
          >
            {comment.is_resolved ? "Unresolve" : "Resolve"}
          </button>
        ) : null}
        {canDelete ? (
          <button
            type="button"
            className="comment-btn comment-btn--danger"
            onClick={() => setShowConfirmDelete(true)}
          >
            Delete
          </button>
        ) : null}
        {comment.is_resolved && depth === 0 ? (
          <button
            type="button"
            className="comment-btn comment-btn--ghost"
            onClick={() => setCollapsed(true)}
          >
            Hide resolved
          </button>
        ) : null}
      </div>

      {showConfirmDelete ? (
        <div className="comment-delete-confirm">
          <p>Delete this comment?</p>
          <div className="comment-reply-form__actions">
            <button
              type="button"
              className="comment-btn comment-btn--ghost"
              onClick={() => setShowConfirmDelete(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="comment-btn comment-btn--danger"
              onClick={async () => {
                await onDelete(comment.id);
                setShowConfirmDelete(false);
              }}
            >
              Delete
            </button>
          </div>
        </div>
      ) : null}

      {showReply && depth === 0 ? (
        <ReplyInput
          onCancel={() => setShowReply(false)}
          onSubmit={async (content) => {
            await onReply(comment, content);
            setShowReply(false);
          }}
        />
      ) : null}

      {depth === 0 && (comment.replies || []).length > 0 ? (
        <div className="comment-thread__replies">
          {(comment.replies || []).map((reply) => (
            <CommentBody
              key={reply.id}
              comment={reply}
              currentUser={currentUser}
              userRole={userRole}
              depth={1}
              onReply={onReply}
              onResolve={onResolve}
              onDelete={onDelete}
              onReact={onReact}
              onEdit={onEdit}
            />
          ))}
        </div>
      ) : null}
    </article>
  );
}

export default function CommentThread(props) {
  return <CommentBody {...props} depth={0} />;
}
