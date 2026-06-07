import { useEffect, useMemo, useRef } from "react";

function buildGutterDecorations(comments, monaco) {
  const lineMap = new Map();

  for (const comment of comments) {
    if (comment.parent_id) {
      continue;
    }
    for (let line = comment.line_start; line <= comment.line_end; line += 1) {
      if (!lineMap.has(line)) {
        lineMap.set(line, []);
      }
      lineMap.get(line).push(comment);
    }
  }

  return Array.from(lineMap.entries()).map(([lineNumber, lineComments]) => {
    const allResolved = lineComments.every((comment) => comment.is_resolved);
    const classNames = [
      allResolved ? "comment-gutter-resolved" : "comment-gutter-icon",
      lineComments.length > 1 ? `comment-gutter-count-${lineComments.length}` : "",
    ]
      .filter(Boolean)
      .join(" ");

    return {
      range: new monaco.Range(lineNumber, 1, lineNumber, 1),
      options: {
        isWholeLine: true,
        glyphMarginClassName: classNames,
        glyphMarginHoverMessage: {
          value:
            lineComments.length === 1
              ? "View comment thread"
              : `${lineComments.length} comments on this line`,
        },
        stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
      },
    };
  });
}

export default function CommentGutter({ editor, monaco, comments, onLineClick }) {
  const decorationIdsRef = useRef([]);
  const onLineClickRef = useRef(onLineClick);

  onLineClickRef.current = onLineClick;

  const decorations = useMemo(() => {
    if (!editor || !monaco) {
      return [];
    }
    return buildGutterDecorations(comments, monaco);
  }, [comments, editor, monaco]);

  useEffect(() => {
    if (!editor) {
      return undefined;
    }

    decorationIdsRef.current = editor.deltaDecorations(decorationIdsRef.current, decorations);

    return () => {
      decorationIdsRef.current = editor.deltaDecorations(decorationIdsRef.current, []);
    };
  }, [editor, decorations]);

  useEffect(() => {
    if (!editor || !monaco) {
      return undefined;
    }

    const disposable = editor.onMouseDown((event) => {
      if (event.target.type !== monaco.editor.MouseTargetType.GUTTER_GLYPH_MARGIN) {
        return;
      }
      const lineNumber = event.target.position?.lineNumber;
      if (lineNumber) {
        onLineClickRef.current(lineNumber);
      }
    });

    return () => disposable.dispose();
  }, [editor, monaco]);

  return null;
}
