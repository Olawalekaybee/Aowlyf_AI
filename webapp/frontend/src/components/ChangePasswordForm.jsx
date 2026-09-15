import { useState } from 'react'
import { api } from '../api.js'
import Modal from './Modal.jsx'

export default function ChangePasswordForm({ token, onClose }) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    if (newPassword !== confirmPassword) {
      setError('New password and confirmation do not match')
      return
    }
    setSaving(true)
    try {
      await api.changePassword(currentPassword, newPassword, token)
      setSuccess(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="Change password" onClose={onClose}>
      {success ? (
        <p className="modal-note">
          Your password has been updated. Use it the next time you log in.
        </p>
      ) : (
        <form onSubmit={handleSubmit} className="modal-form">
          <label>
            Current password
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              autoFocus
            />
          </label>
          <label>
            New password
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              minLength={8}
              required
            />
          </label>
          <label>
            Confirm new password
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              minLength={8}
              required
            />
          </label>
          {error && <div className="login-error">{error}</div>}
          <button type="submit" disabled={saving}>
            {saving ? 'Saving...' : 'Update password'}
          </button>
        </form>
      )}
    </Modal>
  )
}
