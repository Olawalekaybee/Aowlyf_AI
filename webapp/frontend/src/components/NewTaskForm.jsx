import { useState } from 'react'
import { api } from '../api.js'
import Modal from './Modal.jsx'

export default function NewTaskForm({ token, projectId, staffOptions, onClose, onCreated }) {
  const [form, setForm] = useState({
    title: '',
    assignee_id: staffOptions[0]?.id || '',
    start_date: '',
    end_date: '',
    description: '',
  })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSaving(true)
    try {
      const task = await api.createTask(projectId, form, token)
      onCreated(task)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="New task" onClose={onClose}>
      <form onSubmit={handleSubmit} className="modal-form">
        <label>
          Title
          <input value={form.title} onChange={(e) => set('title', e.target.value)} required autoFocus />
        </label>
        <label>
          Assignee
          <select value={form.assignee_id} onChange={(e) => set('assignee_id', e.target.value)}>
            <option value="">Unassigned</option>
            {staffOptions.map((s) => (
              <option key={s.id} value={s.id}>
                {s.full_name}
              </option>
            ))}
          </select>
        </label>
        <div className="modal-form-row">
          <label>
            Start date
            <input
              type="date"
              value={form.start_date}
              onChange={(e) => set('start_date', e.target.value)}
              required
            />
          </label>
          <label>
            End date
            <input type="date" value={form.end_date} onChange={(e) => set('end_date', e.target.value)} required />
          </label>
        </div>
        <label>
          Description
          <textarea value={form.description} onChange={(e) => set('description', e.target.value)} rows={2} />
        </label>
        {error && <div className="login-error">{error}</div>}
        <button type="submit" disabled={saving}>
          {saving ? 'Creating…' : 'Create task'}
        </button>
      </form>
    </Modal>
  )
}
