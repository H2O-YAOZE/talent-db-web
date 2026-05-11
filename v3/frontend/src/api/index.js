const BASE = ''  // proxied by vite

function headers() {
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
  }
}

async function request(method, url, data) {
  const opts = { method, headers: headers() }
  if (data) opts.body = JSON.stringify(data)
  const resp = await fetch(BASE + url, opts)
  if (resp.status === 401) {
    localStorage.clear()
    window.location.href = '/login'
    return
  }
  if (resp.status === 404) return { error: 'Not found' }
  return resp.json()
}

export const api = {
  login: (data) => request('POST', '/api/auth/login', data),
  register: (data) => request('POST', '/api/auth/register', data),
  me: () => request('GET', '/api/auth/me'),

  // Candidates
  listCandidates: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return request('GET', `/api/candidates?${q}`)
  },
  getCandidate: (id) => request('GET', `/api/candidates/${id}`),
  deleteCandidate: (id) => request('DELETE', `/api/candidates/${id}`),
  getCompanies: () => request('GET', '/api/companies'),
  getDegrees: () => request('GET', '/api/degrees'),
  getUploaders: () => request('GET', '/api/uploaders'),

  // Papers
  listPapers: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return request('GET', `/api/papers?${q}`)
  },
  getTeams: () => request('GET', '/api/papers/teams'),
  getSchools: () => request('GET', '/api/papers/schools'),

  // Upload & Tasks
  upload: (formData) => fetch(BASE + '/api/upload', { method: 'POST', headers: { 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` }, body: formData }),
  processPending: () => request('POST', '/api/tasks/process'),
  listTasks: () => request('GET', '/api/tasks'),
  deleteTask: (id) => request('DELETE', `/api/tasks/${id}`),
  downloadUrl: (id) => BASE + `/api/download/${id}?token=${localStorage.getItem('token') || ''}`,
}
