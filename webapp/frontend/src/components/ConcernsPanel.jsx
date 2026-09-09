import { useEffect, useState } from 'react'
import { api } from '../api.js'

const CATEGORY_LABEL = {
  project: 'Project issue',
  work: 'Work concern',
  procurement: 'Procurement related',
  general_update: 'General update',
  internal_review: 'Internal review',
}

function ResolveForm({ concern, token, onResolved }) {
  const [response, setResponse] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.resolveConcern(concern.id, response, token)
      onResolved()
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="inline-resolve-form">
      <textarea
        value={response}
        onChange={(e) => setResponse(e.target.value)}
        placeholder="Write a response and resolve this concern"
        rows={2}
        required
      />
      <button type="submit" disabled={saving} className="btn-small">
        {saving ? 'Saving...' : 'Resolve'}
      </button>
    </form>
  )
}

export default function ConcernsPanel({ token, isAdmin }) {
  const [concerns, setConcerns] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')

  function load() {
    setLoading(true)
    const fetcher = isAdmin ? api.concerns(filter || null, token) : api.myConcerns(token)
    fetcher.then(setConcerns).finally(() => setLoading(false))
  }

  useEffect(load, [token, isAdmin, filter])

  return (
    <div className="queue-panel">
      <div className="queue-header">
        <h2>{isAdmin ? 'Concern queue' : 'Concerns you raised'}</h2>
        {isAdmin && (
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All</option>
            <option value="open">Open</option>
            <option value="in_review">In review</option>
            <option value="resolved">Resolved</option>
          </select>
        )}
      </div>
      {loading && <p className="console-muted">Loading...</p>}
      {!loading && !concerns.length && <p className="console-muted">Nothing here yet.</p>}
      <ul className="queue-list">
        {concerns.map((c) => (
          <li key={c.id} className="queue-item">
            <div className="queue-item-head">
              <span className="queue-badge">{CATEGORY_LABEL[c.category] || c.category}</span>
              {isAdmin && <span className="queue-from">{c.raised_by_name}</span>}
              {c.project_name && <span className="queue-project">{c.project_name}</span>}
              <span className={`queue-status queue-status-${c.status}`}>{c.status}</span>
            </div>
            <p className="queue-message">{c.message}</p>
            {c.admin_response && (
              <p className="queue-response">
                <strong>Admin response:</strong> {c.admin_response}
              </p>
            )}
            {isAdmin && c.status !== 'resolved' && (
              <ResolveForm concern={c} token={token} onResolved={load} />
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
