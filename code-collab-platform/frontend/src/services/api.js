import api from "../lib/axios.js";

export function getWorkspaces() {
  return api.get("/workspaces/");
}

export function createWorkspace(name) {
  return api.post("/workspaces/", { name });
}

export function getProjects(workspaceId) {
  return api.get(`/workspaces/${workspaceId}/projects/`);
}

export function getFileTree(projectId) {
  return api.get("/files/", { params: { project_id: projectId } });
}

export function getFile(fileId) {
  return api.get(`/files/${fileId}/`);
}

export function getFileMeta(fileId) {
  return api.get(`/files/${fileId}/meta/`);
}

export function createFile(projectId, path, content = "") {
  return api.post("/files/", { project: projectId, path, content });
}

export function updateFileContent(fileId, content) {
  return api.patch(`/files/${fileId}/`, { content });
}

export function updateFilePath(fileId, path) {
  return api.patch(`/files/${fileId}/`, { path });
}

export function deleteFile(fileId) {
  return api.delete(`/files/${fileId}/`);
}

export async function getVersions(fileId, branch = "main") {
  const response = await api.get(`/files/${fileId}/versions/`, { params: { branch } });
  return response.data;
}

export async function getVersion(fileId, versionId) {
  const response = await api.get(`/files/${fileId}/versions/${versionId}/`);
  return response.data;
}

export async function createVersion(fileId, label = "") {
  const response = await api.post(`/files/${fileId}/versions/`, { label });
  return response.data;
}

export async function getBranches(fileId) {
  const response = await api.get(`/files/${fileId}/branches/`);
  return response.data;
}

export async function getDiff(fileId, fromId, toId, algorithm = "myers") {
  const response = await api.get(`/files/${fileId}/diff/`, {
    params: { from: fromId, to: toId, algorithm },
  });
  return response.data;
}

export async function getMergePreview(fileId, sourceVersionId, targetVersionId = null) {
  const response = await api.post(`/files/${fileId}/merge/preview/`, {
    source_version_id: sourceVersionId,
    target_version_id: targetVersionId,
  });
  return response.data;
}

export async function resolveMerge(fileId, mergeJobId, resolutions) {
  const response = await api.post(`/files/${fileId}/merge/resolve/`, {
    merge_job_id: mergeJobId,
    resolutions,
  });
  return response.data;
}

export async function restoreVersion(fileId, versionId, strategy = "manual") {
  const response = await api.post(`/files/${fileId}/restore/${versionId}/`, { strategy });
  return response.data;
}

export async function executeCode(payload) {
  const response = await api.post("/execute/", payload);
  return response.data;
}

export async function getExecutionJob(jobId) {
  const response = await api.get(`/execute/${jobId}/`);
  return response.data;
}

export async function aiComplete(payload) {
  const response = await api.post("/ai/complete/", payload);
  return response.data;
}

export async function aiExplain(payload) {
  const response = await api.post("/ai/explain/", payload);
  return response.data;
}

export async function aiDetectBugs(payload) {
  const response = await api.post("/ai/detect-bugs/", payload);
  return response.data;
}

export async function aiDetectBugsResult(jobId) {
  const response = await api.get(`/ai/detect-bugs/${jobId}/`);
  return response.data;
}

export async function getAIUsage() {
  const response = await api.get("/ai/usage/");
  return response.data;
}

export async function getComments(fileId, branchName = "main", params = {}) {
  const response = await api.get("/comments/", {
    params: { file_id: fileId, branch_name: branchName, ...params },
  });
  return response.data;
}

export async function getComment(commentId) {
  const response = await api.get(`/comments/${commentId}/`);
  return response.data;
}

export async function createComment(payload) {
  const response = await api.post("/comments/", payload);
  return response.data;
}

export async function updateComment(commentId, payload) {
  const response = await api.patch(`/comments/${commentId}/`, payload);
  return response.data;
}

export async function deleteComment(commentId) {
  await api.delete(`/comments/${commentId}/`);
}

export async function addCommentReaction(commentId, emoji) {
  const response = await api.post(`/comments/${commentId}/reactions/`, { emoji });
  return response.status === 201 ? response.data : null;
}
