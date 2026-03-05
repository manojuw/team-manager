const MANAGEMENT_API = "/api/management";
const AI_API = "/api/ai";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

async function fetchWithAuth(url: string, options: RequestInit = {}) {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(url, { ...options, headers });

  if (res.status === 401) {
    if (typeof window !== "undefined") {
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      window.location.href = "/login";
    }
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || `Request failed (${res.status})`);
  }

  return res.json();
}

export const auth = {
  signup: (data: { email: string; password: string; name: string; tenantName: string }) =>
    fetchWithAuth(`${MANAGEMENT_API}/auth/signup`, { method: "POST", body: JSON.stringify(data) }),
  login: (data: { email: string; password: string }) =>
    fetchWithAuth(`${MANAGEMENT_API}/auth/login`, { method: "POST", body: JSON.stringify(data) }),
  me: () => fetchWithAuth(`${MANAGEMENT_API}/auth/me`),
};

export const projects = {
  list: () => fetchWithAuth(`${MANAGEMENT_API}/projects`),
  create: (data: { name: string; description?: string }) =>
    fetchWithAuth(`${MANAGEMENT_API}/projects`, { method: "POST", body: JSON.stringify(data) }),
  get: (id: string) => fetchWithAuth(`${MANAGEMENT_API}/projects/${id}`),
  update: (id: string, data: { name: string; description?: string }) =>
    fetchWithAuth(`${MANAGEMENT_API}/projects/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (id: string) =>
    fetchWithAuth(`${MANAGEMENT_API}/projects/${id}`, { method: "DELETE" }),
};

export const connectors = {
  list: (projectId: string) => fetchWithAuth(`${MANAGEMENT_API}/connectors/project/${projectId}`),
  get: (id: string) => fetchWithAuth(`${MANAGEMENT_API}/connectors/${id}`),
  create: (data: { projectId: string; name: string; connectorType: string; config?: Record<string, unknown> }) =>
    fetchWithAuth(`${MANAGEMENT_API}/connectors`, { method: "POST", body: JSON.stringify(data) }),
  update: (id: string, data: { name?: string; config?: Record<string, unknown> }) =>
    fetchWithAuth(`${MANAGEMENT_API}/connectors/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (id: string) =>
    fetchWithAuth(`${MANAGEMENT_API}/connectors/${id}`, { method: "DELETE" }),
};

export const dataSources = {
  listByConnector: (connectorId: string) => fetchWithAuth(`${MANAGEMENT_API}/datasources/connector/${connectorId}`),
  listByProject: (projectId: string) => fetchWithAuth(`${MANAGEMENT_API}/datasources/project/${projectId}`),
  get: (id: string) => fetchWithAuth(`${MANAGEMENT_API}/datasources/${id}`),
  create: (data: { connectorId: string; name: string; sourceType: string; config?: Record<string, unknown>; syncIntervalMinutes?: number; syncEnabled?: boolean }) =>
    fetchWithAuth(`${MANAGEMENT_API}/datasources`, { method: "POST", body: JSON.stringify(data) }),
  update: (id: string, data: { name?: string; config?: Record<string, unknown>; syncIntervalMinutes?: number; syncEnabled?: boolean }) =>
    fetchWithAuth(`${MANAGEMENT_API}/datasources/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (id: string) =>
    fetchWithAuth(`${MANAGEMENT_API}/datasources/${id}`, { method: "DELETE" }),
};

export const sync = {
  history: (projectId: string) => fetchWithAuth(`${MANAGEMENT_API}/sync/history/${projectId}`),
  historyByConnector: (connectorId: string) => fetchWithAuth(`${MANAGEMENT_API}/sync/history/connector/${connectorId}`),
  status: (projectId: string) => fetchWithAuth(`${MANAGEMENT_API}/sync/status/${projectId}`),
};

export const teams = {
  listTeams: (connectorId: string) =>
    fetchWithAuth(`${AI_API}/teams/list-teams`, { method: "POST", body: JSON.stringify({ connector_id: connectorId }) }),
  listChannels: (connectorId: string, teamId: string) =>
    fetchWithAuth(`${AI_API}/teams/list-channels`, { method: "POST", body: JSON.stringify({ connector_id: connectorId, team_id: teamId }) }),
  listUsers: (connectorId: string) =>
    fetchWithAuth(`${AI_API}/teams/list-users`, { method: "POST", body: JSON.stringify({ connector_id: connectorId }) }),
  listGroupChats: (connectorId: string, userIds: string[]) =>
    fetchWithAuth(`${AI_API}/teams/list-group-chats`, { method: "POST", body: JSON.stringify({ connector_id: connectorId, user_ids: userIds }) }),
  syncChannel: (data: { project_id: string; connector_id: string; data_source_id?: string; team_id: string; team_name: string; channel_id: string; channel_name: string }) =>
    fetchWithAuth(`${AI_API}/sync/channel`, { method: "POST", body: JSON.stringify(data) }),
  syncGroupChat: (data: { project_id: string; connector_id: string; data_source_id?: string; chat_id: string; chat_name: string }) =>
    fetchWithAuth(`${AI_API}/sync/group-chat`, { method: "POST", body: JSON.stringify(data) }),
};

export const devops = {
  listProjects: (connectorId: string) =>
    fetchWithAuth(`${AI_API}/devops/list-projects`, { method: "POST", body: JSON.stringify({ connector_id: connectorId }) }),
  listIterations: (connectorId: string, projectName: string) =>
    fetchWithAuth(`${AI_API}/devops/list-iterations`, { method: "POST", body: JSON.stringify({ connector_id: connectorId, project_name: projectName }) }),
  syncProject: (data: { project_id: string; connector_id: string; data_source_id?: string; devops_project_id: string; devops_project_name: string }) =>
    fetchWithAuth(`${AI_API}/sync/devops-project`, { method: "POST", body: JSON.stringify(data) }),
  getWorkItemDetail: (semanticDataId: string, workItemId: string) =>
    fetchWithAuth(`${AI_API}/devops/work-item-detail?semantic_data_id=${encodeURIComponent(semanticDataId)}&work_item_id=${encodeURIComponent(workItemId)}`),
};

export const devopsStats = {
  get: (projectId: string) => fetchWithAuth(`${AI_API}/devops/stats/${projectId}`),
};

export const threads = {
  list: (projectId: string, filters: Record<string, string> = {}) => {
    const params = new URLSearchParams({ project_id: projectId, limit: "200", ...filters });
    return fetchWithAuth(`${AI_API}/threads?${params.toString()}`);
  },
  getWorkItems: (threadId: string) =>
    fetchWithAuth(`${AI_API}/threads/${threadId}/work-items`),
  getTranscript: (threadId: string) =>
    fetchWithAuth(`${AI_API}/threads/${threadId}/transcript`),
  updateStatus: (threadId: string, body: { review_status?: string; viewed?: boolean }) =>
    fetchWithAuth(`${AI_API}/threads/${threadId}/status`, { method: "PATCH", body: JSON.stringify(body) }),
  getDataSources: (projectId: string) =>
    fetchWithAuth(`${AI_API}/threads/data-sources?project_id=${projectId}`),
};

export const ai = {
  search: (data: { project_id: string; query: string; n_results?: number; filter_team?: string; filter_channel?: string }) =>
    fetchWithAuth(`${AI_API}/search`, { method: "POST", body: JSON.stringify(data) }),
  ask: (data: { project_id: string; question: string; chat_history?: Array<{ role: string; content: string }>; filter_team?: string; filter_channel?: string }) =>
    fetchWithAuth(`${AI_API}/ask`, { method: "POST", body: JSON.stringify(data) }),
  summarize: (projectId: string) =>
    fetchWithAuth(`${AI_API}/summarize`, { method: "POST", body: JSON.stringify({ project_id: projectId }) }),
  stats: (projectId: string) => fetchWithAuth(`${AI_API}/stats/${projectId}`),
  clearData: (projectId: string) =>
    fetchWithAuth(`${AI_API}/project-data/${projectId}`, { method: "DELETE" }),
};
