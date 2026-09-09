import { useState } from 'react'
import { api } from '../api.js'
import Modal from './Modal.jsx'

export default function NewProcurementForm({ token, projects, onClose, onCreated }) {
  const [item, setItem] = useState('')
  const [quantity, setQuantity] = useState(1)
  const [justification, setJustification] = useState('')
  const [projectId, setProjectId] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSaving(true)
    try {
      const request = await api.createProcurement(
        { item, quantity: Number(quantity), justification, project_id: projectId || null },
        token,
      )
      onCreated(request)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="Procurement request" onClose={onClose}>
      <form onSubmit={handleSubmit} className="modal-form">
        <label>
          Item
          <input value={item} onChange={(e) => setItem(e.target.value)} required autoFocus />
        </label>
        <label>
          Quantity
          <input
            type="number"
            min={1}
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            required
          />
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
          Justification
          <textarea
            value={justification}
            onChange={(e) => setJustification(e.target.value)}
            rows={3}
          />
        </label>
        {error && <div className="login-error">{error}</div>}
        <button type="submit" disabled={saving}>
          {saving ? 'Sending...' : 'Submit request'}
        </button>
      </form>
    </Modal>
  )
}
