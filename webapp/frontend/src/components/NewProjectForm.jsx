import { useState } from 'react'
import { api } from '../api.js'
import Modal from './Modal.jsx'

export default function NewProjectForm({ token, labs, isAdmin, onClose, onCreated }) {
  const [form, setForm] = useState({
    name: '',
    lab_id: labs[0]?.id || '',
    category: 'Prototype',
    description: '',
    start_date: '',
    end_date: '',
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
      const project = await api.createProject(form, token)
      onCreated(project)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="New project" onClose={onClose}>
      <form onSubmit={handleSubmit} className="modal-form">
        <label>
          Name
          <input value={form.name} onChange={(e) => set('name', e.target.value)} required autoFocus />
        </label>
        <label>
          Lab
          <select value={form.lab_id} onChange={(e) => set('lab_id', e.target.value)} required>
            {labs.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Category
          <select value={form.category} onChange={(e) => set('category', e.target.value)}>
            <option>R&D</option>
            <option>Prototype</option>
            <option>Technical Program</option>
            <option>Departmental</option>
          </select>
        </label>
        <label>
          Description
          <textarea value={form.description} onChange={(e) => set('description', e.target.value)} rows={2} />
        </label>
        <div className="modal-form-row">
          <label>
            Start date
            <input type="date" value={form.start_date} onChange={(e) => set('start_date', e.target.value)} />
          </label>
          <label>
            End date
            <input type="date" value={form.end_date} onChange={(e) => set('end_date', e.target.value)} />
          </label>
        </div>
        {!isAdmin && (
          <p className="modal-note">
            You're not an admin, so this project starts as "proposed" until an admin activates it.
          </p>
        )}
        {error && <div className="login-error">{error}</div>}
        <button type="submit" disabled={saving}>
          {saving ? 'Creating…' : 'Create project'}
        </button>
      </form>
    </Modal>
  )
}
