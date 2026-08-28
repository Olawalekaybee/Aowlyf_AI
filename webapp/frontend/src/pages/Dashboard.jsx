import { useEffect, useState } from 'react'
import { api, wsUrl } from '../api.js'
import GanttChart from '../components/GanttChart.jsx'

const LAB_CODES = {
  Electronics: 'ELEC',
  'Embedded System and Control Lab': 'EMBD',
  '3D Lab': '3D',
  'Sustainable Lab': 'SUS',
  'Product Design Lab': 'PDL',
  'Autonomous Robotics Lab': 'ARL',
  'Software Lab': 'SW',
  'BioTech Lab': 'BIO',
  'Simulation Lab': 'SIM',
  Fabrication: 'FAB',
  Ecolab: 'ECO',
  Procurement: 'PROC',
}

function labCode(name) {
  if (!name) return '—'
  if (LAB_CODES[name]) return LAB_CODES[name]
  return name.split(' ').map((w) => w[0]).join('').slice(0, 4).toUpperCase()
}

export default function Dashboard({ token, staff, onLogout }) {
  const [projects, setProjects] = useState([])
  const [labsById, setLabsById] = useState({})
  const [selected, setSelected] = useState(null)
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    async function load() {
      try {
        const [projectList, labs] = await Promise.all([api.projects(token), api.labs(token)])
        setProjects(projectList)
        setLabsById(Object.fromEntries(labs.map((l) => [l.id, l.name])))
        if (projectList.length) setSelected(projectList[0].id)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [token])

  useEffect(() => {
    if (!selected) return
    api.projectTasks(selected, token).then(setTasks).catch((err) => setError(err.message))
  }, [selected, token])

  useEffect(() => {
    const ws = new WebSocket(wsUrl())
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === 'task_updated' && msg.project_id === selected) {
        setTasks((prev) =>
          prev.map((t) =>
            t.id === msg.task_id
              ? { ...t, progress_pct: msg.progress_pct, status: msg.status }
              : t,
          ),
        )
      }
    }
    return () => ws.close()
  }, [selected])

  function logout() {
    localStorage.removeItem('aowlyf_token')
    localStorage.removeItem('aowlyf_staff')
    onLogout()
  }

  return (
    <div className="console">
      <header className="console-header">
        <div className="console-brand">
          <span className="login-mark-dot" />
          AOWLYF_AI
        </div>
        <div className="console-user">
          <span>{staff.full_name}</span>
          <span className="console-role">{staff.role}</span>
          <button className="console-logout" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>

      <div className="console-body">
        <aside className="console-sidebar">
          <h2>Projects</h2>
          {loading && <p className="console-muted">Loading…</p>}
          {!loading && !projects.length && (
            <p className="console-muted">
              No projects visible yet. Projects are created via Claude or the MCP tools directly.
            </p>
          )}
          <ul className="project-list">
            {projects.map((p) => (
              <li key={p.id}>
                <button
                  className={p.id === selected ? 'project-item active' : 'project-item'}
                  onClick={() => setSelected(p.id)}
                >
                  <span className="project-eyebrow">{labCode(labsById[p.lab_id])}</span>
                  <span className="project-name">{p.name}</span>
                  <span className={`project-status project-status-${p.status}`}>{p.status}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <main className="console-main">
          {error && <div className="console-error">{error}</div>}
          {selected ? (
            <GanttChart tasks={tasks} />
          ) : (
            <div className="gantt-empty">
              <p>Select a project to see its timeline.</p>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
