import { create } from "zustand";

const EMPTY_COMMENTS = [];

export const useCommentsStore = create((set, get) => ({
  commentsByFile: {},
  activeThread: null,

  setComments: (fileId, comments) =>
    set((state) => ({
      commentsByFile: {
        ...state.commentsByFile,
        [fileId]: comments,
      },
    })),

  upsertComment: (fileId, comment) =>
    set((state) => {
      const existing = state.commentsByFile[fileId] || [];
      const index = existing.findIndex((item) => item.id === comment.id);
      const nextComments =
        index >= 0
          ? existing.map((item, itemIndex) => (itemIndex === index ? comment : item))
          : [...existing, comment];
      return {
        commentsByFile: {
          ...state.commentsByFile,
          [fileId]: nextComments,
        },
      };
    }),

  mergeCommentDetail: (fileId, detail) =>
    set((state) => {
      const existing = state.commentsByFile[fileId] || [];
      const nextComments = mergeCommentIntoList(existing, detail);
      return {
        commentsByFile: {
          ...state.commentsByFile,
          [fileId]: nextComments,
        },
      };
    }),

  removeComment: (fileId, commentId) =>
    set((state) => ({
      commentsByFile: {
        ...state.commentsByFile,
        [fileId]: (state.commentsByFile[fileId] || []).filter((item) => item.id !== commentId),
      },
    })),

  removeReply: (fileId, parentId, replyId) =>
    set((state) => ({
      commentsByFile: {
        ...state.commentsByFile,
        [fileId]: (state.commentsByFile[fileId] || []).map((comment) => {
          if (comment.id !== parentId) {
            return comment;
          }
          const replies = (comment.replies || []).filter((reply) => reply.id !== replyId);
          return {
            ...comment,
            replies,
            reply_count: replies.length,
          };
        }),
      },
    })),

  setActiveThread: (commentId) => set({ activeThread: commentId }),

  getCommentsForFile: (fileId) => get().commentsByFile[fileId] || EMPTY_COMMENTS,
}));

export function getCommentsForLine(fileId, lineNumber) {
  const comments = useCommentsStore.getState().commentsByFile[fileId] || EMPTY_COMMENTS;
  return comments.filter(
    (comment) =>
      !comment.parent_id && lineNumber >= comment.line_start && lineNumber <= comment.line_end,
  );
}

function mergeCommentIntoList(list, detail) {
  if (!detail.parent_id) {
    const index = list.findIndex((item) => item.id === detail.id);
    if (index >= 0) {
      return list.map((item, itemIndex) => (itemIndex === index ? detail : item));
    }
    return [...list, detail];
  }

  return list.map((comment) => {
    if (comment.id !== detail.parent_id) {
      return comment;
    }
    const replies = comment.replies || [];
    const replyIndex = replies.findIndex((reply) => reply.id === detail.id);
    const nextReplies =
      replyIndex >= 0
        ? replies.map((reply, index) => (index === replyIndex ? detail : reply))
        : [...replies, detail];
    return {
      ...comment,
      replies: nextReplies,
      reply_count: nextReplies.length,
    };
  });
}
