import { useEffect, useState } from 'react'
import { api, wsUrl } from '../api.js'
import GanttChart from '../components/GanttChart.jsx'
import NewProjectForm from '../components/NewProjectForm.jsx'
import NewTaskForm from '../components/NewTaskForm.jsx'
import AddMemberForm from '../components/AddMemberForm.jsx'

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
  const [labs, setLabs] = useState([])
  const [labsById, setLabsById] = useState({})
  const [staffOptions, setStaffOptions] = useState([])
  const [selected, setSelected] = useState(null)
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [showNewProject, setShowNewProject] = useState(false)
  const [showNewTask, setShowNewTask] = useState(false)
  const [showAddMember, setShowAddMember] = useState(false)

  const isAdmin = staff.role === 'admin'
  const canManageTeam = isAdmin || staff.can_grant_team_membership

  async function loadCore() {
    setLoading(true)
    try {
      const [projectList, labList, staffList] = await Promise.all([
        api.projects(token),
        api.labs(token),
        api.staff(token),
      ])
      setProjects(projectList)
      setLabs(labList)
      setLabsById(Object.fromEntries(labList.map((l) => [l.id, l.name])))
      setStaffOptions(staffList)
      if (projectList.length && !selected) setSelected(projectList[0].id)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadCore()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  function loadTasks() {
    if (!selected) return
    api.projectTasks(selected, token).then(setTasks).catch((err) => setError(err.message))
  }

  useEffect(loadTasks, [selected, token])

  useEffect(() => {
    const ws = new WebSocket(wsUrl())
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.project_id !== selected) return
      if (msg.type === 'task_updated') {
        setTasks((prev) =>
          prev.map((t) =>
            t.id === msg.task_id ? { ...t, progress_pct: msg.progress_pct, status: msg.status } : t,
          ),
        )
      } else if (msg.type === 'task_created') {
        loadTasks()
      }
    }
    return () => ws.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected])

  function logout() {
    localStorage.removeItem('aowlyf_token')
    localStorage.removeItem('aowlyf_staff')
    onLogout()
  }

  async function activateProject(projectId) {
    try {
      await api.updateProjectStatus(projectId, 'active', token)
      loadCore()
    } catch (err) {
      setError(err.message)
    }
  }

  const selectedProject = projects.find((p) => p.id === selected)
  const labStaffOptions = staffOptions.filter(
    (s) => !selectedProject || s.lab_id === selectedProject.lab_id,
  )

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
          <div className="console-sidebar-head">
            <h2>Projects</h2>
            <button className="btn-small" onClick={() => setShowNewProject(true)}>
              + New
            </button>
          </div>
          {loading && <p className="console-muted">Loading…</p>}
          {!loading && !projects.length && (
            <p className="console-muted">No projects yet — create the first one.</p>
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
                {isAdmin && p.status === 'proposed' && (
                  <button className="btn-activate" onClick={() => activateProject(p.id)}>
                    Activate
                  </button>
                )}
              </li>
            ))}
          </ul>
        </aside>

        <main className="console-main">
          {error && <div className="console-error">{error}</div>}
          {selected ? (
            <>
              <div className="main-toolbar">
                <h2>{selectedProject?.name}</h2>
                <div className="main-toolbar-actions">
                  {canManageTeam && (
                    <button className="btn-small" onClick={() => setShowAddMember(true)}>
                      + Add member
                    </button>
                  )}
                  <button className="btn-small" onClick={() => setShowNewTask(true)}>
                    + New task
                  </button>
                </div>
              </div>
              <GanttChart tasks={tasks} />
            </>
          ) : (
            <div className="gantt-empty">
              <p>Select or create a project to see its timeline.</p>
            </div>
          )}
        </main>
      </div>

      {showNewProject && (
        <NewProjectForm
          token={token}
          labs={labs}
          isAdmin={isAdmin}
          onClose={() => setShowNewProject(false)}
          onCreated={(project) => {
            setShowNewProject(false)
            setProjects((prev) => [...prev, project])
            setSelected(project.id)
          }}
        />
      )}

      {showNewTask && selected && (
        <NewTaskForm
          token={token}
          projectId={selected}
          staffOptions={labStaffOptions}
          onClose={() => setShowNewTask(false)}
          onCreated={() => {
            setShowNewTask(false)
            loadTasks()
          }}
        />
      )}

      {showAddMember && selected && (
        <AddMemberForm
          token={token}
          projectId={selected}
          staffOptions={labStaffOptions}
          onClose={() => setShowAddMember(false)}
          onAdded={() => setShowAddMember(false)}
        />
      )}
    </div>
  )
}
