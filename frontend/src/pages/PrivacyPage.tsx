import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Clock, RefreshCw, Shield, Trash2 } from 'lucide-react'
import { api, getErrorMessage } from '@/lib/api'
import { useAddToast } from '@/components/ui/Toast'
import { PageHeader } from '@/components/layout/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Badge } from '@/components/ui/Badge'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import type { PrivacySettings, RetentionPurgeResponse } from '@/types'

export default function PrivacyPage() {
  const addToast = useAddToast()
  const [settings, setSettings] = useState<PrivacySettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [daysInput, setDaysInput] = useState('365')
  const [preview, setPreview] = useState<RetentionPurgeResponse | null>(null)
  const [running, setRunning] = useState(false)
  const [confirmPurge, setConfirmPurge] = useState(false)
  const [cleaningOrphans, setCleaningOrphans] = useState(false)

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

  useEffect(() => {
    void loadSettings()
  }, [loadSettings])

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

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Compliance & Governance"
        title="Privacy & Data Retention"
        description="Configure candidate data retention, preview or run retention purges, and clean up orphaned pending resume files. Full deletion removes resume files and raw resume text while retaining PII-free audit entries."
        actions={
          <Button variant="outline" size="sm" onClick={() => void loadSettings()} loading={loading}>
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

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Shield size={17} className="text-brand-600" />
              <CardTitle>Run Candidate Retention Purge</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-xs leading-5 text-slate-600">
              Removes candidate records whose consent date (or creation date) is older than the
              specified number of days, permanently deletes their stored resume files and raw resume
              text, and logs a PII-free audit entry for each purged ID.
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

            <div className="flex flex-wrap items-center gap-2.5">
              <Button variant="outline" size="sm" loading={running} onClick={() => void runDryRun()}>
                <Clock size={14} />
                Dry Run Preview
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={running || (parseInt(daysInput, 10) || 0) <= 0}
                onClick={() => setConfirmPurge(true)}
                className="border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700"
              >
                <Trash2 size={14} />
                Purge Expired Now
              </Button>
            </div>

            {preview && (
              <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5 text-xs">
                <div className="flex items-center gap-2 font-semibold text-slate-900">
                  {preview.dry_run ? (
                    <AlertTriangle size={14} className="text-amber-600" />
                  ) : (
                    <CheckCircle2 size={14} className="text-emerald-600" />
                  )}
                  {preview.dry_run ? 'Dry Run Preview' : 'Purge Complete'} ({preview.retention_days}{' '}
                  days)
                </div>
                <p className="mt-1 text-slate-600">
                  Matched: <span className="font-semibold">{preview.matched_count}</span> · Purged:{' '}
                  <span className="font-semibold">{preview.purged_count}</span>
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Trash2 size={17} className="text-amber-600" />
              <CardTitle>Orphan Pending Resume Cleanup</CardTitle>
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
              Clean Up Orphan Files Now
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
    </div>
  )
}
