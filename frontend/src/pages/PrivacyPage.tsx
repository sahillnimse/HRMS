import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileWarning,
  Plus,
  RefreshCw,
  Shield,
  Sparkles,
  Trash2,
  UserPlus,
  Users,
} from 'lucide-react'
import { api, getErrorMessage } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useAddToast } from '@/components/ui/Toast'
import { PageHeader } from '@/components/layout/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Select } from '@/components/ui/Select'
import { Badge } from '@/components/ui/Badge'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import type { ErasureRequest, PrivacySettings, RetentionPurgeResponse, User, UserRole } from '@/types'

interface SectionRemapResponse {
  dry_run: boolean
  scanned: number
  would_update: number
  updated: number
  skipped_hand_edited: number
}

export default function PrivacyPage() {
  const { isAdmin } = useAuth()
  const addToast = useAddToast()
  const [settings, setSettings] = useState<PrivacySettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Retention & cleanup
  const [daysInput, setDaysInput] = useState('365')
  const [preview, setPreview] = useState<RetentionPurgeResponse | null>(null)
  const [running, setRunning] = useState(false)
  const [confirmPurge, setConfirmPurge] = useState(false)
  const [cleaningOrphans, setCleaningOrphans] = useState(false)

  // Legacy CV Section Re-mapping
  const [remapPreview, setRemapPreview] = useState<SectionRemapResponse | null>(null)
  const [remapping, setRemapping] = useState(false)
  const [confirmRemap, setConfirmRemap] = useState(false)

  // Team User Management
  const [users, setUsers] = useState<User[]>([])
  const [usersLoading, setUsersLoading] = useState(false)
  const [showAddUser, setShowAddUser] = useState(false)
  const [newName, setNewName] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newRole, setNewRole] = useState<UserRole>('recruiter')
  const [creatingUser, setCreatingUser] = useState(false)

  // India DPDP Act — Erasure & Consent Requests
  const [erasureRequests, setErasureRequests] = useState<ErasureRequest[]>([])
  const [erasureLoading, setErasureLoading] = useState(false)
  const [showNewErasure, setShowNewErasure] = useState(false)
  const [erasureCandidateId, setErasureCandidateId] = useState('')
  const [erasureType, setErasureType] = useState<'erasure' | 'consent_withdrawal' | 'data_export'>('erasure')
  const [erasureReason, setErasureReason] = useState('')
  const [creatingErasure, setCreatingErasure] = useState(false)
  const [executeTarget, setExecuteTarget] = useState<ErasureRequest | null>(null)
  const [executingErasure, setExecutingErasure] = useState(false)

  const loadSettings = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<PrivacySettings>('/privacy/settings')
      setSettings(res.data)
      setDaysInput(String(res.data.retention_days))
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load privacy settings'))
    } finally {
      setLoading(false)
    }
  }, [])

  const loadUsers = useCallback(async () => {
    setUsersLoading(true)
    try {
      const res = await api.get<User[]>('/auth/users')
      setUsers(res.data)
    } catch {
      // Non-blocking
    } finally {
      setUsersLoading(false)
    }
  }, [])

  const loadErasureRequests = useCallback(async () => {
    setErasureLoading(true)
    try {
      const res = await api.get<ErasureRequest[]>('/privacy/erasure-requests')
      setErasureRequests(res.data || [])
    } catch {
      // Non-blocking
    } finally {
      setErasureLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadSettings()
    void loadUsers()
    void loadErasureRequests()
  }, [loadSettings, loadUsers, loadErasureRequests])

  const handleCreateErasure = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!erasureCandidateId.trim()) {
      addToast('Enter the candidate UUID to log an erasure request.', 'error')
      return
    }
    setCreatingErasure(true)
    try {
      await api.post<ErasureRequest>('/privacy/erasure-requests', {
        candidate_id: erasureCandidateId.trim(),
        request_type: erasureType,
        reason: erasureReason.trim(),
      })
      addToast('DPDP erasure / consent request logged', 'success')
      setErasureCandidateId('')
      setErasureReason('')
      setShowNewErasure(false)
      void loadErasureRequests()
    } catch (err) {
      addToast(getErrorMessage(err, 'Failed to log DPDP request'), 'error')
    } finally {
      setCreatingErasure(false)
    }
  }

  const handleExecuteErasure = async () => {
    if (!executeTarget) return
    setExecutingErasure(true)
    try {
      await api.post<ErasureRequest>(`/privacy/erasure-requests/${executeTarget.id}/execute`)
      addToast('Candidate PII & resume deleted; PII-free DPDP compliance proof retained.', 'success')
      setExecuteTarget(null)
      void loadErasureRequests()
      void loadSettings()
    } catch (err) {
      addToast(getErrorMessage(err, 'Failed to execute erasure request'), 'error')
    } finally {
      setExecutingErasure(false)
    }
  }

  const runDryRun = async () => {
    const days = Math.max(0, parseInt(daysInput, 10) || 0)
    setRunning(true)
    try {
      const res = await api.post<RetentionPurgeResponse>('/privacy/purge-expired', null, {
        params: { retention_days: days, dry_run: true },
      })
      setPreview(res.data)
      addToast(
        `Dry run complete: ${res.data.matched_count} candidate${res.data.matched_count === 1 ? '' : 's'} eligible for purge`,
        'info',
      )
    } catch (err) {
      addToast(getErrorMessage(err, 'Dry run failed'), 'error')
    } finally {
      setRunning(false)
    }
  }

  const runPurge = async () => {
    const days = Math.max(0, parseInt(daysInput, 10) || 0)
    setRunning(true)
    try {
      const res = await api.post<RetentionPurgeResponse>('/privacy/purge-expired', null, {
        params: { retention_days: days, dry_run: false },
      })
      setPreview(res.data)
      setConfirmPurge(false)
      addToast(
        `Purged ${res.data.purged_count} expired candidate${res.data.purged_count === 1 ? '' : 's'} and their stored resume files`,
        'success',
      )
      void loadSettings()
    } catch (err) {
      addToast(getErrorMessage(err, 'Retention purge failed'), 'error')
    } finally {
      setRunning(false)
    }
  }

  const runOrphanCleanup = async () => {
    setCleaningOrphans(true)
    try {
      const res = await api.post<{ deleted: number; max_age_hours: number }>(
        '/resumes/cleanup',
        null,
        { params: { max_age_hours: settings?.orphan_max_age_hours ?? 24 } },
      )
      addToast(`Cleaned up ${res.data.deleted} orphan pending resume file(s)`, 'success')
    } catch (err) {
      addToast(getErrorMessage(err, 'Orphan cleanup failed'), 'error')
    } finally {
      setCleaningOrphans(false)
    }
  }

  const runSectionRemap = async (dryRun: boolean) => {
    setRemapping(true)
    try {
      const res = await api.post<SectionRemapResponse>('/candidates/admin/remap-sections', null, {
        params: { dry_run: dryRun, limit: 200 },
      })
      setRemapPreview(res.data)
      if (!dryRun) setConfirmRemap(false)
      addToast(
        dryRun
          ? `Remap preview: ${res.data.would_update} of ${res.data.scanned} profile(s) can be enriched`
          : `Re-mapped ${res.data.updated} legacy profile(s) (${res.data.skipped_hand_edited} hand-edited skipped)`,
        dryRun ? 'info' : 'success',
      )
    } catch (err) {
      addToast(getErrorMessage(err, 'Legacy section re-mapping failed'), 'error')
    } finally {
      setRemapping(false)
    }
  }

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newName.trim() || !newEmail.trim() || newPassword.length < 8) {
      addToast('Enter name, valid email, and a password (min 8 chars).', 'error')
      return
    }
    setCreatingUser(true)
    try {
      await api.post<User>('/auth/users', {
        full_name: newName.trim(),
        email: newEmail.trim(),
        password: newPassword,
        role: newRole,
        is_active: true,
      })
      addToast(`Created ${newRole} account for ${newName.trim()}`, 'success')
      setNewName('')
      setNewEmail('')
      setNewPassword('')
      setNewRole('recruiter')
      setShowAddUser(false)
      void loadUsers()
    } catch (err) {
      addToast(getErrorMessage(err, 'Failed to create user'), 'error')
    } finally {
      setCreatingUser(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Admin & Governance"
        title="Privacy, Retention & Admin Tools"
        description="Manage workspace team accounts, re-map legacy CV sections (education dates, employment types, projects), configure data retention, and clean up orphaned pending resume files."
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void loadSettings()
              void loadUsers()
              void loadErasureRequests()
            }}
            loading={loading}
          >
            <RefreshCw size={14} />
            Refresh
          </Button>
        }
      />

      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-800">
          {error}
        </div>
      )}

      {settings && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-2xl border bg-white p-5 shadow-card">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Configured Retention
            </p>
            <p className="mt-2 text-2xl font-bold text-slate-900">
              {settings.retention_days > 0 ? `${settings.retention_days} days` : 'Disabled'}
            </p>
            <Badge variant="brand" className="mt-2">
              RETENTION_DAYS env var
            </Badge>
          </div>

          <div className="rounded-2xl border bg-white p-5 shadow-card">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Past Retention Window
            </p>
            <p className="mt-2 text-2xl font-bold text-slate-900">
              {settings.expired_candidates_count}
            </p>
            <Badge
              variant={settings.expired_candidates_count > 0 ? 'warning' : 'success'}
              className="mt-2"
            >
              {settings.expired_candidates_count > 0 ? 'Eligible for purge' : 'All within policy'}
            </Badge>
          </div>

          <div className="rounded-2xl border bg-white p-5 shadow-card">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Orphan Pending TTL
            </p>
            <p className="mt-2 text-2xl font-bold text-slate-900">
              {settings.orphan_max_age_hours} hrs
            </p>
            <Badge variant="secondary" className="mt-2">
              Scheduled auto-cleanup
            </Badge>
          </div>

          <div className="rounded-2xl border bg-white p-5 shadow-card">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              OCR & Semantic Flags
            </p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <Badge variant={settings.ocr_fallback_enabled ? 'success' : 'secondary'}>
                OCR: {settings.ocr_fallback_enabled ? 'ON' : 'OFF'}
              </Badge>
              <Badge variant={settings.semantic_search_enabled ? 'success' : 'secondary'}>
                Semantic: {settings.semantic_search_enabled ? 'ON' : 'OFF'}
              </Badge>
            </div>
          </div>
        </div>
      )}

      {/* Workspace Team Users */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Users size={17} className="text-brand-600" />
              <CardTitle>Workspace Team ({users.length})</CardTitle>
            </div>
            <Button size="sm" variant="soft" onClick={() => setShowAddUser((v) => !v)}>
              <UserPlus size={14} />
              {showAddUser ? 'Close Form' : 'Add Team Member'}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {showAddUser && (
            <form
              onSubmit={handleCreateUser}
              className="grid grid-cols-1 gap-3 rounded-xl border border-brand-200/80 bg-brand-50/40 p-4 sm:grid-cols-2 lg:grid-cols-5 sm:items-end animate-fade-in"
            >
              <div className="space-y-1">
                <Label htmlFor="new-user-name" className="text-xs">Full Name *</Label>
                <Input
                  id="new-user-name"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="Priya Mehta"
                  required
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="new-user-email" className="text-xs">Email *</Label>
                <Input
                  id="new-user-email"
                  type="email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  placeholder="priya@company.com"
                  required
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="new-user-pass" className="text-xs">Temporary Password *</Label>
                <Input
                  id="new-user-pass"
                  type="password"
                  minLength={8}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Min 8 chars"
                  required
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="new-user-role" className="text-xs">Role</Label>
                <Select
                  id="new-user-role"
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value as UserRole)}
                >
                  <option value="recruiter">Recruiter</option>
                  <option value="viewer">Viewer (read-only)</option>
                  <option value="admin">Admin</option>
                </Select>
              </div>
              <Button type="submit" size="sm" loading={creatingUser}>
                Create User
              </Button>
            </form>
          )}

          {usersLoading && users.length === 0 ? (
            <div className="skeleton h-24 rounded-xl" />
          ) : (
            <div className="overflow-x-auto rounded-xl border border-stone-200/80">
              <table className="min-w-full divide-y divide-stone-100 text-xs">
                <thead className="bg-stone-50/80 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-4 py-2.5">Name</th>
                    <th className="px-4 py-2.5">Email</th>
                    <th className="px-4 py-2.5">Role</th>
                    <th className="px-4 py-2.5">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100 bg-white">
                  {users.map((u) => (
                    <tr key={u.id}>
                      <td className="px-4 py-2.5 font-semibold text-slate-900">{u.full_name}</td>
                      <td className="px-4 py-2.5 text-slate-600">{u.email}</td>
                      <td className="px-4 py-2.5">
                        <Badge
                          variant={
                            u.role === 'admin'
                              ? 'brand'
                              : u.role === 'recruiter'
                                ? 'secondary'
                                : 'outline'
                          }
                          className="capitalize"
                        >
                          {u.role}
                        </Badge>
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge variant={u.is_active ? 'success' : 'warning'}>
                          {u.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* India DPDP Act — Erasure & Consent Requests */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <FileWarning size={17} className="text-coral-600" />
              <CardTitle>India DPDP Act — Erasure &amp; Consent Requests ({erasureRequests.length})</CardTitle>
            </div>
            <Button size="sm" variant="outline" onClick={() => setShowNewErasure((v) => !v)}>
              <Plus size={14} />
              {showNewErasure ? 'Close Form' : 'Log Request'}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs leading-5 text-slate-600">
            Track candidate data erasure or consent-withdrawal requests. Executing a request
            permanently deletes the candidate profile, parsed text, and stored CV file while
            keeping a PII-free SHA-256 compliance proof (<code className="font-mono">candidate_ref_hash</code>).
          </p>

          {showNewErasure && (
            <form
              onSubmit={handleCreateErasure}
              className="grid grid-cols-1 gap-3 rounded-xl border border-coral-200/80 bg-coral-50/30 p-4 sm:grid-cols-2 lg:grid-cols-4 sm:items-end animate-fade-in"
            >
              <div className="space-y-1">
                <Label htmlFor="dpdp-cand-id" className="text-xs">Candidate ID (UUID) *</Label>
                <Input
                  id="dpdp-cand-id"
                  value={erasureCandidateId}
                  onChange={(e) => setErasureCandidateId(e.target.value)}
                  placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                  required
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="dpdp-type" className="text-xs">Request Type</Label>
                <Select
                  id="dpdp-type"
                  value={erasureType}
                  onChange={(e) =>
                    setErasureType(e.target.value as 'erasure' | 'consent_withdrawal' | 'data_export')
                  }
                >
                  <option value="erasure">Data Erasure (Right to be Forgotten)</option>
                  <option value="consent_withdrawal">Consent Withdrawal</option>
                  <option value="data_export">Data Access / Export</option>
                </Select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="dpdp-reason" className="text-xs">Reason / Ticket Ref</Label>
                <Input
                  id="dpdp-reason"
                  value={erasureReason}
                  onChange={(e) => setErasureReason(e.target.value)}
                  placeholder="Candidate requested via email"
                />
              </div>
              <Button type="submit" size="sm" loading={creatingErasure}>
                Log Request
              </Button>
            </form>
          )}

          {erasureLoading && erasureRequests.length === 0 ? (
            <div className="skeleton h-20 rounded-xl" />
          ) : erasureRequests.length === 0 ? (
            <p className="rounded-xl border border-dashed border-stone-200 py-5 text-center text-xs text-slate-500">
              No DPDP erasure or consent-withdrawal requests logged yet.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-stone-200/80">
              <table className="min-w-full divide-y divide-stone-100 text-xs">
                <thead className="bg-stone-50/80 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-4 py-2.5">Ref Hash (PII-free)</th>
                    <th className="px-4 py-2.5">Type</th>
                    <th className="px-4 py-2.5">Status</th>
                    <th className="px-4 py-2.5">Reason</th>
                    <th className="px-4 py-2.5">Created</th>
                    <th className="px-4 py-2.5 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100 bg-white">
                  {erasureRequests.map((req) => (
                    <tr key={req.id}>
                      <td className="px-4 py-2.5 font-mono text-[11px] text-slate-700">
                        {req.candidate_ref_hash.slice(0, 12)}…
                      </td>
                      <td className="px-4 py-2.5 capitalize text-slate-700">
                        {req.request_type.replace(/_/g, ' ')}
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge
                          variant={
                            req.status === 'completed'
                              ? 'success'
                              : req.status === 'pending'
                                ? 'warning'
                                : 'secondary'
                          }
                          className="capitalize"
                        >
                          {req.status}
                        </Badge>
                      </td>
                      <td className="max-w-xs truncate px-4 py-2.5 text-slate-600">
                        {req.reason || '—'}
                      </td>
                      <td className="px-4 py-2.5 text-slate-500">
                        {new Date(req.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        {req.status === 'pending' && isAdmin ? (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setExecuteTarget(req)}
                            className="h-7 border-red-200 px-2.5 text-[11px] text-red-600 hover:bg-red-50 hover:text-red-700"
                          >
                            <Trash2 size={12} />
                            Execute Erasure
                          </Button>
                        ) : (
                          <span className="text-[11px] text-slate-400">
                            {req.processed_at
                              ? `Done ${new Date(req.processed_at).toLocaleDateString()}`
                              : '—'}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Retention Purge */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Shield size={17} className="text-brand-600" />
              <CardTitle>Candidate Retention Purge</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-xs leading-5 text-slate-600">
              Removes candidate records whose consent/creation date exceeds the retention window,
              permanently deleting stored files and raw resume text while keeping PII-free audit logs.
            </p>

            <div className="max-w-xs space-y-1.5">
              <Label htmlFor="retention-days">Retention Window (days)</Label>
              <Input
                id="retention-days"
                type="number"
                min={0}
                value={daysInput}
                onChange={(e) => setDaysInput(e.target.value)}
              />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Button variant="outline" size="sm" loading={running} onClick={() => void runDryRun()}>
                <Clock size={14} />
                Dry Run
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={running || (parseInt(daysInput, 10) || 0) <= 0}
                onClick={() => setConfirmPurge(true)}
                className="border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700"
              >
                <Trash2 size={14} />
                Purge Now
              </Button>
            </div>

            {preview && (
              <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3 text-xs">
                <div className="flex items-center gap-2 font-semibold text-slate-900">
                  {preview.dry_run ? (
                    <AlertTriangle size={14} className="text-amber-600" />
                  ) : (
                    <CheckCircle2 size={14} className="text-emerald-600" />
                  )}
                  {preview.dry_run ? 'Dry Run Preview' : 'Purge Complete'} ({preview.retention_days}d)
                </div>
                <p className="mt-1 text-slate-600">
                  Matched: <span className="font-semibold">{preview.matched_count}</span> · Purged:{' '}
                  <span className="font-semibold">{preview.purged_count}</span>
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Legacy Section Re-mapping */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Sparkles size={17} className="text-sky-600" />
              <CardTitle>Re-map Legacy CV Sections</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-xs leading-5 text-slate-600">
              Deterministically backfills <code className="font-mono">employment_type</code>,
              education start/end years, and <code className="font-mono">projects</code> on older
              candidates from their saved resume files. Automatically skips hand-edited sections.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                loading={remapping}
                onClick={() => void runSectionRemap(true)}
              >
                <Clock size={14} />
                Dry Run Preview
              </Button>
              <Button
                size="sm"
                variant="soft"
                disabled={remapping}
                onClick={() => setConfirmRemap(true)}
              >
                <Sparkles size={14} />
                Apply Re-map
              </Button>
            </div>
            {remapPreview && (
              <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3 text-xs">
                <p className="font-semibold text-slate-900">
                  {remapPreview.dry_run ? 'Dry Run Preview' : 'Re-map Applied'}
                </p>
                <p className="mt-1 text-slate-600">
                  Scanned: <b>{remapPreview.scanned}</b> · Eligible: <b>{remapPreview.would_update}</b> ·
                  Updated: <b>{remapPreview.updated}</b> · Skipped (hand-edited):{' '}
                  <b>{remapPreview.skipped_hand_edited}</b>
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Orphan Cleanup */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Trash2 size={17} className="text-amber-600" />
              <CardTitle>Orphan Resume Cleanup</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-xs leading-5 text-slate-600">
              Immediately purge uploaded resume files that were never saved to a candidate profile
              and exceed the configured pending TTL ({settings?.orphan_max_age_hours ?? 24} hours).
            </p>
            <Button
              variant="outline"
              size="sm"
              loading={cleaningOrphans}
              onClick={() => void runOrphanCleanup()}
            >
              <Trash2 size={14} />
              Clean Up Orphan Files
            </Button>
          </CardContent>
        </Card>
      </div>

      <ConfirmDialog
        open={confirmPurge}
        title={`Purge candidates older than ${daysInput} days?`}
        description="This permanently deletes all expired candidate profiles, raw resume text, and stored resume files. PII-free audit records will be retained."
        confirmLabel="Confirm Purge"
        loading={running}
        onConfirm={runPurge}
        onCancel={() => setConfirmPurge(false)}
      />

      <ConfirmDialog
        open={Boolean(executeTarget)}
        title="Execute DPDP Erasure Request?"
        description={`This permanently deletes the candidate profile, parsed text, and stored resume file for ref ${executeTarget?.candidate_ref_hash.slice(0, 12) ?? ''}… while retaining a PII-free compliance proof. This cannot be undone.`}
        confirmLabel="Execute Erasure"
        loading={executingErasure}
        onConfirm={() => void handleExecuteErasure()}
        onCancel={() => setExecuteTarget(null)}
      />

      <ConfirmDialog
        open={confirmRemap}
        title="Apply section re-mapping to legacy candidates?"
        description="Updates education dates, work employment_type, and empty projects from stored resume files. Any section previously edited by hand via Edit Details will be skipped."
        confirmLabel="Apply Re-map"
        loading={remapping}
        onConfirm={() => void runSectionRemap(false)}
        onCancel={() => setConfirmRemap(false)}
      />
    </div>
  )
}
