const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function request(path, { method = 'GET', body, token } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })

  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail || `Request failed (${res.status})`)
  }
  return res.json()
}

export const api = {
  login: (email, password) => request('/auth/login', { method: 'POST', body: { email, password } }),
  me: (token) => request('/auth/me', { token }),
  labs: (token) => request('/labs', { token }),
  staff: (token) => request('/staff', { token }),
  projects: (token) => request('/projects', { token }),
  createProject: (body, token) => request('/projects', { method: 'POST', body, token }),
  updateProjectStatus: (projectId, status, token) =>
    request(`/projects/${projectId}`, { method: 'PATCH', body: { status }, token }),
  projectTasks: (projectId, token) => request(`/projects/${projectId}/tasks`, { token }),
  createTask: (projectId, body, token) =>
    request(`/projects/${projectId}/tasks`, { method: 'POST', body, token }),
  updateTask: (taskId, body, token) => request(`/tasks/${taskId}`, { method: 'PATCH', body, token }),
  projectMembers: (projectId, token) => request(`/projects/${projectId}/members`, { token }),
  addMember: (projectId, body, token) =>
    request(`/projects/${projectId}/members`, { method: 'POST', body, token }),
}

export function wsUrl() {
  const base = API_URL.replace(/^http/, 'ws')
  return `${base}/ws`
}
