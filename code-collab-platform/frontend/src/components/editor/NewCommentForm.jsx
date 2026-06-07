import { useEffect, useRef, useState } from "react";

export default function NewCommentForm({ editor, selection, parentId = null, onSubmit, onCancel }) {
  const textareaRef = useRef(null);
  const formRef = useRef(null);
  const [content, setContent] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });

  useEffect(() => {
    if (!editor || !selection) {
      return;
    }

    const anchorPosition = {
      lineNumber: selection.startLineNumber,
      column: selection.startColumn,
    };
    const coords = editor.getScrolledVisiblePosition(anchorPosition);
    const domNode = editor.getDomNode();
    if (!coords || !domNode) {
      return;
    }

    const editorRect = domNode.getBoundingClientRect();
    setPosition({
      top: editorRect.top + coords.top + 24,
      left: editorRect.left + coords.left + 32,
    });
  }, [editor, selection]);

  useEffect(() => {
    textareaRef.current?.focus();
  }, [selection]);

  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
      }
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        event.preventDefault();
        formRef.current?.requestSubmit();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onCancel]);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!content.trim() || isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    try {
      await onSubmit({
        content: content.trim(),
        line_start: selection.startLineNumber,
        line_end: selection.endLineNumber,
        col_start: selection.startColumn,
        col_end: selection.endColumn,
        parent_id: parentId,
      });
      setContent("");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (!selection) {
    return null;
  }

  return (
    <div className="comment-popover" style={{ top: position.top, left: position.left }}>
      <form ref={formRef} className="comment-popover__form" onSubmit={handleSubmit}>
        <label htmlFor="new-comment-content">Add comment</label>
        <textarea
          id="new-comment-content"
          ref={textareaRef}
          value={content}
          rows={4}
          maxLength={10000}
          placeholder="Leave a comment…"
          onChange={(event) => setContent(event.target.value)}
        />
        <div className="comment-popover__actions">
          <button type="button" className="comment-btn comment-btn--ghost" onClick={onCancel}>
            Cancel
          </button>
          <button type="submit" className="comment-btn" disabled={!content.trim() || isSubmitting}>
            Comment
          </button>
        </div>
        <p className="muted comment-popover__hint">Ctrl/Cmd+Enter to submit · Esc to cancel</p>
      </form>
    </div>
  );
}

export function SelectionCommentTrigger({ editor, selection, onOpen }) {
  const [position, setPosition] = useState(null);

  useEffect(() => {
    if (!editor || !selection || selection.isEmpty()) {
      setPosition(null);
      return;
    }

    const anchorPosition = {
      lineNumber: selection.endLineNumber,
      column: selection.endColumn,
    };
    const coords = editor.getScrolledVisiblePosition(anchorPosition);
    const domNode = editor.getDomNode();
    if (!coords || !domNode) {
      setPosition(null);
      return;
    }

    const editorRect = domNode.getBoundingClientRect();
    setPosition({
      top: editorRect.top + coords.top - 8,
      left: editorRect.left + coords.left + 12,
    });
  }, [editor, selection]);

  if (!position) {
    return null;
  }

  return (
    <button
      type="button"
      className="comment-selection-trigger"
      style={{ top: position.top, left: position.left }}
      title="Add comment"
      onClick={onOpen}
    >
      💬
    </button>
  );
}
