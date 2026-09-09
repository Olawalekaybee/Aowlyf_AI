import { useEffect, useState } from 'react'
import { api } from '../api.js'

const STATUS_OPTIONS = ['requested', 'approved', 'ordered', 'received', 'rejected']

export default function ProcurementPanel({ token, isAdmin }) {
  const [requests, setRequests] = useState([])
  const [loading, setLoading] = useState(true)

  function load() {
    setLoading(true)
    const fetcher = isAdmin ? api.procurementRequests(token) : api.myProcurementRequests(token)
    fetcher.then(setRequests).finally(() => setLoading(false))
  }

  useEffect(load, [token, isAdmin])

  async function changeStatus(requestId, status) {
    await api.updateProcurementStatus(requestId, status, token)
    load()
  }

  return (
    <div className="queue-panel">
      <div className="queue-header">
        <h2>{isAdmin ? 'Procurement queue' : 'Your procurement requests'}</h2>
      </div>
      {loading && <p className="console-muted">Loading...</p>}
      {!loading && !requests.length && <p className="console-muted">Nothing here yet.</p>}
      <ul className="queue-list">
        {requests.map((r) => (
          <li key={r.id} className="queue-item">
            <div className="queue-item-head">
              <span className="queue-badge">
                {r.item} × {r.quantity}
              </span>
              {isAdmin && <span className="queue-from">{r.requested_by_name}</span>}
              {r.project_name && <span className="queue-project">{r.project_name}</span>}
              {isAdmin ? (
                <select
                  className="queue-status-select"
                  value={r.status}
                  onChange={(e) => changeStatus(r.id, e.target.value)}
                >
                  {STATUS_OPTIONS.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              ) : (
                <span className={`queue-status queue-status-${r.status}`}>{r.status}</span>
              )}
            </div>
            {r.justification && <p className="queue-message">{r.justification}</p>}
          </li>
        ))}
      </ul>
    </div>
  )
}
