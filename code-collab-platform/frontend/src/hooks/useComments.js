import { useCallback, useEffect, useMemo, useState } from "react";

import {
  addCommentReaction,
  createComment as createCommentRequest,
  deleteComment as deleteCommentRequest,
  getComment,
  getComments,
  updateComment as updateCommentRequest,
} from "../services/api.js";
import { useCommentsStore } from "../store/comments.store.js";
import { useAuthStore } from "../store/auth.store.js";

const EMPTY_COMMENTS = [];

function buildCommentsByLine(comments) {
  const map = new Map();
  for (const comment of comments) {
    if (comment.parent_id) {
      continue;
    }
    for (let line = comment.line_start; line <= comment.line_end; line += 1) {
      if (!map.has(line)) {
        map.set(line, []);
      }
      map.get(line).push(comment);
    }
  }
  return map;
}

export function useComments(fileId, branchName = "main", provider) {
  const currentUser = useAuthStore((state) => state.user);
  const comments = useCommentsStore((state) => state.commentsByFile[fileId] || EMPTY_COMMENTS);
  const setComments = useCommentsStore((state) => state.setComments);
  const mergeCommentDetail = useCommentsStore((state) => state.mergeCommentDetail);
  const removeComment = useCommentsStore((state) => state.removeComment);
  const removeReply = useCommentsStore((state) => state.removeReply);

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchComments = useCallback(async () => {
    if (!fileId) {
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const data = await getComments(fileId, branchName);
      setComments(fileId, Array.isArray(data) ? data : data.results || []);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load comments.");
    } finally {
      setIsLoading(false);
    }
  }, [branchName, fileId, setComments]);

  useEffect(() => {
    fetchComments();
  }, [fetchComments]);

  const handleRealtimeEvent = useCallback(
    async (event) => {
      if (!fileId || event.file_id !== fileId) {
        return;
      }

      if (event.event === "deleted") {
        try {
          const detail = await getComment(event.comment_id);
          mergeCommentDetail(fileId, detail);
        } catch {
          await fetchComments();
        }
        return;
      }

      try {
        const detail = await getComment(event.comment_id);
        mergeCommentDetail(fileId, detail);
      } catch (err) {
        if (err.response?.status === 404) {
          await fetchComments();
        }
      }
    },
    [fetchComments, fileId, mergeCommentDetail],
  );

  useEffect(() => {
    if (!provider) {
      return undefined;
    }

    provider.on("comment_event", handleRealtimeEvent);
    return () => provider.off("comment_event", handleRealtimeEvent);
  }, [provider, handleRealtimeEvent]);

  const commentsByLine = useMemo(() => buildCommentsByLine(comments), [comments]);

  const createComment = useCallback(
    async ({ content, line_start, line_end, col_start, col_end, parent_id }) => {
      const optimisticId = `temp-${Date.now()}`;
      const optimisticComment = {
        id: optimisticId,
        file_id: fileId,
        author: currentUser,
        content,
        line_start,
        line_end,
        col_start: col_start ?? null,
        col_end: col_end ?? null,
        parent_id: parent_id ?? null,
        is_resolved: false,
        branch_name: branchName,
        replies: [],
        reply_count: 0,
        reactions: [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      if (parent_id) {
        mergeCommentDetail(fileId, { ...optimisticComment, parent_id });
      } else {
        useCommentsStore.getState().upsertComment(fileId, optimisticComment);
      }

      try {
        const created = await createCommentRequest({
          file_id: fileId,
          branch_name: branchName,
          content,
          line_start,
          line_end,
          col_start,
          col_end,
          parent_id,
        });
        if (parent_id) {
          removeReply(fileId, parent_id, optimisticId);
        } else {
          removeComment(fileId, optimisticId);
        }
        mergeCommentDetail(fileId, created);
        return created;
      } catch (err) {
        if (parent_id) {
          removeReply(fileId, parent_id, optimisticId);
        } else {
          removeComment(fileId, optimisticId);
        }
        throw err;
      } finally {
        await fetchComments();
      }
    },
    [
      branchName,
      currentUser,
      fetchComments,
      fileId,
      mergeCommentDetail,
      removeComment,
      removeReply,
    ],
  );

  const updateComment = useCallback(
    async (commentId, payload) => {
      const updated = await updateCommentRequest(commentId, payload);
      mergeCommentDetail(fileId, updated);
      await fetchComments();
      return updated;
    },
    [fetchComments, fileId, mergeCommentDetail],
  );

  const resolveComment = useCallback(
    async (commentId, isResolved) => {
      return updateComment(commentId, { is_resolved: isResolved });
    },
    [updateComment],
  );

  const deleteComment = useCallback(
    async (commentId) => {
      await deleteCommentRequest(commentId);
      removeComment(fileId, commentId);
      await fetchComments();
    },
    [fetchComments, fileId, removeComment],
  );

  const addReaction = useCallback(
    async (commentId, emoji) => {
      await addCommentReaction(commentId, emoji);
      await fetchComments();
    },
    [fetchComments],
  );

  return {
    comments,
    commentsByLine,
    isLoading,
    error,
    refetch: fetchComments,
    createComment,
    updateComment,
    resolveComment,
    deleteComment,
    addReaction,
  };
}
