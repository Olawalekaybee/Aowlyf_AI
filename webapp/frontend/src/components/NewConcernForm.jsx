import { useState } from 'react'
import { api } from '../api.js'
import Modal from './Modal.jsx'

const CATEGORIES = [
  { value: 'project', label: 'Project issue' },
  { value: 'work', label: 'Work concern' },
  { value: 'procurement', label: 'Procurement related' },
  { value: 'general_update', label: 'General update' },
  { value: 'internal_review', label: 'Internal review' },
]

export default function NewConcernForm({ token, projects, onClose, onCreated }) {
  const [category, setCategory] = useState('work')
  const [message, setMessage] = useState('')
  const [projectId, setProjectId] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSaving(true)
    try {
      const concern = await api.createConcern(
        { category, message, project_id: projectId || null },
        token,
      )
      onCreated(concern)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="Raise a concern" onClose={onClose}>
      <form onSubmit={handleSubmit} className="modal-form">
        <label>
          Category
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Related project (optional)
          <select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            <option value="">None</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Message
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={4}
            required
            autoFocus
          />
        </label>
        <p className="modal-note">This goes directly to the admin queue for review.</p>
        {error && <div className="login-error">{error}</div>}
        <button type="submit" disabled={saving}>
          {saving ? 'Sending...' : 'Send concern'}
        </button>
      </form>
    </Modal>
  )
}
