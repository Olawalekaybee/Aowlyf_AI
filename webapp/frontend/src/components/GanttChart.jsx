import { useMemo } from 'react'

const STATUS_LABEL = {
  not_started: 'Not started',
  in_progress: 'In progress',
  blocked: 'Blocked',
  done: 'Done',
}

function toTime(d) {
  return new Date(`${d}T00:00:00`).getTime()
}

export default function GanttChart({ tasks }) {
  const { minDate, maxDate } = useMemo(() => {
    if (!tasks.length) return { minDate: null, maxDate: null }
    return {
      minDate: Math.min(...tasks.map((t) => toTime(t.start_date))),
      maxDate: Math.max(...tasks.map((t) => toTime(t.end_date))),
    }
  }, [tasks])

  if (!tasks.length) {
    return (
      <div className="gantt-empty">
        <p>No tasks on this project yet.</p>
        <p className="gantt-empty-sub">
          Tasks appear here as soon as they're created — via Claude, or the MCP tools directly.
        </p>
      </div>
    )
  }

  const span = maxDate - minDate || 1
  const todayPct = ((Date.now() - minDate) / span) * 100

  return (
    <div className="gantt">
      <div className="gantt-ruler">
        <span>{new Date(minDate).toLocaleDateString()}</span>
        <span>{new Date(maxDate).toLocaleDateString()}</span>
      </div>
      <div className="gantt-rows">
        {todayPct >= 0 && todayPct <= 100 && (
          <div className="gantt-today" style={{ left: `${todayPct}%` }} />
        )}
        {tasks.map((task) => {
          const start = toTime(task.start_date)
          const end = toTime(task.end_date)
          const left = ((start - minDate) / span) * 100
          const width = Math.max(((end - start) / span) * 100, 1.5)
          return (
            <div className="gantt-row" key={task.id}>
              <div className="gantt-label">
                <span className="gantt-label-title">{task.title}</span>
                <span className="gantt-label-assignee">{task.assignee_name || 'Unassigned'}</span>
              </div>
              <div className="gantt-track">
                <div
                  className={`gantt-bar gantt-bar-${task.status}`}
                  style={{ left: `${left}%`, width: `${width}%` }}
                  title={`${STATUS_LABEL[task.status]} — ${task.progress_pct}%`}
                >
                  <div className="gantt-bar-fill" style={{ width: `${task.progress_pct}%` }} />
                  {task.status === 'in_progress' && <span className="gantt-pulse" />}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
