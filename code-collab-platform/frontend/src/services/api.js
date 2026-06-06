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
