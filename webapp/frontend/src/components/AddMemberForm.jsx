import { useState } from 'react'
import { api } from '../api.js'
import Modal from './Modal.jsx'

export default function AddMemberForm({ token, projectId, staffOptions, onClose, onAdded }) {
  const [staffId, setStaffId] = useState(staffOptions[0]?.id || '')
  const [roleOnTeam, setRoleOnTeam] = useState('contributor')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSaving(true)
    try {
      const member = await api.addMember(projectId, { staff_id: staffId, role_on_team: roleOnTeam }, token)
      onAdded(member)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="Add team member" onClose={onClose}>
      <form onSubmit={handleSubmit} className="modal-form">
        <label>
          Staff member
          <select value={staffId} onChange={(e) => setStaffId(e.target.value)} required autoFocus>
            {staffOptions.map((s) => (
              <option key={s.id} value={s.id}>
                {s.full_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Role on this project
          <select value={roleOnTeam} onChange={(e) => setRoleOnTeam(e.target.value)}>
            <option value="lead">Lead</option>
            <option value="contributor">Contributor</option>
            <option value="reviewer">Reviewer</option>
          </select>
        </label>
        {error && <div className="login-error">{error}</div>}
        <button type="submit" disabled={saving}>
          {saving ? 'Adding…' : 'Add to team'}
        </button>
      </form>
    </Modal>
  )
}
