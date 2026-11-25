import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import { CSS } from '@dnd-kit/utilities'
import { ArrowUpRight, Clock, GripVertical, Trash2 } from 'lucide-react'
import type { ApplicationItem, ApplicationStage } from '@/types'
import { Avatar } from '@/components/ui/Avatar'
import { Button } from '@/components/ui/Button'
import { Textarea } from '@/components/ui/Textarea'
import { cn, formatRelativeDate, formatYears } from '@/lib/utils'

export const PIPELINE_STAGES: {
  id: ApplicationStage
  label: string
  accent: string
  badge: string
  ring: string
}[] = [
  {
    id: 'applied',
    label: 'Applied',
    accent: 'bg-slate-500',
    badge: 'bg-slate-100 text-slate-700',
    ring: 'ring-slate-300',
  },
  {
    id: 'screened',
    label: 'Screened',
    accent: 'bg-sky-500',
    badge: 'bg-sky-50 text-sky-700',
    ring: 'ring-sky-300',
  },
  {
    id: 'interview',
    label: 'Interview',
    accent: 'bg-brand-600',
    badge: 'bg-brand-50 text-brand-700',
    ring: 'ring-brand-300',
  },
  {
    id: 'offer',
    label: 'Offer',
    accent: 'bg-amber-500',
    badge: 'bg-amber-50 text-amber-800',
    ring: 'ring-amber-300',
  },
  {
    id: 'hired',
    label: 'Hired',
    accent: 'bg-emerald-600',
    badge: 'bg-emerald-50 text-emerald-700',
    ring: 'ring-emerald-300',
  },
  {
    id: 'rejected',
    label: 'Rejected',
    accent: 'bg-rose-500',
    badge: 'bg-rose-50 text-rose-700',
    ring: 'ring-rose-300',
  },
]

interface KanbanBoardProps {
  applications: ApplicationItem[]
  canWrite: boolean
  onMoveStage: (
    applicationId: string,
    toStage: ApplicationStage,
    rejectionReason?: string,
  ) => Promise<void>
  onRemoveApplication: (applicationId: string) => Promise<void>
}

function CardBody({
  app,
  canWrite,
  onSelectStage,
  onRemove,
  dragHandleProps,
}: {
  app: ApplicationItem
  canWrite: boolean
  onSelectStage?: (stage: ApplicationStage) => void
  onRemove?: () => void
  dragHandleProps?: Record<string, unknown>
}) {
  const cand = app.candidate
  const name = cand?.full_name || 'Candidate'

  return (
    <div className="rounded-xl border border-slate-200/90 bg-white p-3.5 shadow-sm transition hover:border-brand-200 hover:shadow-md">
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          {canWrite && (
            <button
              type="button"
              {...dragHandleProps}
              className="cursor-grab touch-none rounded p-0.5 text-slate-300 hover:bg-slate-100 hover:text-slate-600 active:cursor-grabbing"
              aria-label="Drag card"
            >
              <GripVertical size={14} />
            </button>
          )}
          <Avatar name={name} size="sm" />
          <div className="min-w-0">
            <Link
              to={`/candidates/${app.candidate_id}`}
              className="block truncate text-sm font-semibold text-slate-900 hover:text-brand-600"
            >
              {name}
            </Link>
            <p className="truncate text-[11px] text-slate-500">
              {cand?.primary_domain || 'General'} · {formatYears(cand?.years_experience)}
            </p>
          </div>
        </div>

        <Link
          to={`/candidates/${app.candidate_id}`}
          className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-brand-600"
          title="Open candidate profile"
        >
          <ArrowUpRight size={14} />
        </Link>
      </div>

      {cand && cand.technical_skills.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1">
          {cand.technical_skills.slice(0, 3).map((sk, i) => (
            <span
              key={i}
              className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600"
            >
              {sk}
            </span>
          ))}
          {cand.technical_skills.length > 3 && (
            <span className="rounded bg-brand-50 px-1.5 py-0.5 text-[10px] font-semibold text-brand-700">
              +{cand.technical_skills.length - 3}
            </span>
          )}
        </div>
      )}

      {app.stage === 'rejected' && app.rejection_reason && (
        <p className="mt-2 rounded-lg bg-rose-50 px-2 py-1 text-[11px] text-rose-700">
          Reason: {app.rejection_reason}
        </p>
      )}

      <div className="mt-3 flex items-center justify-between gap-2 border-t border-slate-100 pt-2">
        <span className="inline-flex items-center gap-1 text-[10px] text-slate-400">
          <Clock size={11} />
          {formatRelativeDate(app.stage_changed_at)}
        </span>

        {canWrite && onSelectStage && (
          <div className="flex items-center gap-1">
            <select
              value={app.stage}
              onChange={(e) => onSelectStage(e.target.value as ApplicationStage)}
              aria-label={`Change stage for ${name}`}
              className="h-6 rounded border border-slate-200 bg-slate-50 px-1.5 text-[11px] font-medium text-slate-700 outline-none focus:border-brand-400"
            >
              {PIPELINE_STAGES.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
            {onRemove && (
              <button
                type="button"
                onClick={onRemove}
                title="Remove from job"
                className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600"
              >
                <Trash2 size={12} />
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function DraggableApplicationCard({
  app,
  canWrite,
  onSelectStage,
  onRemove,
}: {
  app: ApplicationItem
  canWrite: boolean
  onSelectStage: (stage: ApplicationStage) => void
  onRemove: () => void
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: app.id,
    disabled: !canWrite,
  })

  const style = {
    transform: CSS.Translate.toString(transform),
  }

  return (
    <div ref={setNodeRef} style={style} className={cn(isDragging && 'opacity-30')}>
      <CardBody
        app={app}
        canWrite={canWrite}
        onSelectStage={onSelectStage}
        onRemove={onRemove}
        dragHandleProps={{ ...attributes, ...listeners }}
      />
    </div>
  )
}

function StageColumn({
  stage,
  items,
  canWrite,
  onRequestStageChange,
  onRemove,
}: {
  stage: (typeof PIPELINE_STAGES)[number]
  items: ApplicationItem[]
  canWrite: boolean
  onRequestStageChange: (app: ApplicationItem, toStage: ApplicationStage) => void
  onRemove: (applicationId: string) => void
}) {
  const { isOver, setNodeRef } = useDroppable({ id: stage.id })

  return (
    <div
      ref={setNodeRef}
      className={cn(
        'flex min-h-[420px] w-[280px] shrink-0 flex-col rounded-2xl border border-slate-200/80 bg-slate-50/80 p-3 transition',
        isOver && `bg-white ring-2 ${stage.ring}`,
      )}
    >
      <div className="mb-3 flex items-center justify-between px-1">
        <div className="flex items-center gap-2">
          <span className={cn('h-2.5 w-2.5 rounded-full', stage.accent)} />
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-700">
            {stage.label}
          </h3>
        </div>
        <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-semibold', stage.badge)}>
          {items.length}
        </span>
      </div>

      <div className="flex-1 space-y-2.5">
        {items.length === 0 ? (
          <div className="flex h-24 items-center justify-center rounded-xl border border-dashed border-slate-200 text-xs text-slate-400">
            {canWrite ? 'Drop candidate here' : 'Empty'}
          </div>
        ) : (
          items.map((app) => (
            <DraggableApplicationCard
              key={app.id}
              app={app}
              canWrite={canWrite}
              onSelectStage={(nextStage) => onRequestStageChange(app, nextStage)}
              onRemove={() => onRemove(app.id)}
            />
          ))
        )}
      </div>
    </div>
  )
}

export function KanbanBoard({
  applications,
  canWrite,
  onMoveStage,
  onRemoveApplication,
}: KanbanBoardProps) {
  const [activeId, setActiveId] = useState<string | null>(null)
  const [pendingReject, setPendingReject] = useState<{
    app: ApplicationItem
    reason: string
  } | null>(null)

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 6 },
    }),
  )

  const activeApp = applications.find((a) => a.id === activeId) ?? null

  const triggerMove = (app: ApplicationItem, toStage: ApplicationStage) => {
    if (app.stage === toStage) return
    if (toStage === 'rejected') {
      setPendingReject({ app, reason: app.rejection_reason || '' })
      return
    }
    void onMoveStage(app.id, toStage)
  }

  const handleDragStart = (event: DragStartEvent) => {
    setActiveId(String(event.active.id))
  }

  const handleDragEnd = (event: DragEndEvent) => {
    setActiveId(null)
    const { active, over } = event
    if (!over) return
    const app = applications.find((a) => a.id === String(active.id))
    const toStage = String(over.id) as ApplicationStage
    if (!app || app.stage === toStage) return
    triggerMove(app, toStage)
  }

  const confirmReject = async () => {
    if (!pendingReject) return
    const { app, reason } = pendingReject
    setPendingReject(null)
    await onMoveStage(app.id, 'rejected', reason.trim() || undefined)
  }

  return (
    <>
      <DndContext sensors={sensors} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
        <div className="flex gap-4 overflow-x-auto pb-4">
          {PIPELINE_STAGES.map((stage) => (
            <StageColumn
              key={stage.id}
              stage={stage}
              items={applications.filter((a) => a.stage === stage.id)}
              canWrite={canWrite}
              onRequestStageChange={triggerMove}
              onRemove={(id) => void onRemoveApplication(id)}
            />
          ))}
        </div>

        <DragOverlay>
          {activeApp ? (
            <div className="w-[260px] rotate-1 opacity-95">
              <CardBody app={activeApp} canWrite={false} />
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>

      {pendingReject && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-slate-900/30 backdrop-blur-sm"
            onClick={() => setPendingReject(null)}
          />
          <div className="relative w-full max-w-md rounded-2xl border bg-white p-6 shadow-2xl animate-fade-in">
            <h3 className="text-base font-semibold text-slate-900">
              Reject {pendingReject.app.candidate?.full_name || 'Candidate'}?
            </h3>
            <p className="mt-1 text-xs text-slate-500">
              Optionally record a rejection reason for the hiring audit trail.
            </p>
            <Textarea
              rows={3}
              className="mt-4"
              value={pendingReject.reason}
              onChange={(e) =>
                setPendingReject((prev) => (prev ? { ...prev, reason: e.target.value } : null))
              }
              placeholder="e.g. Skills mismatch on backend systems, compensation outside band…"
            />
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setPendingReject(null)}>
                Cancel
              </Button>
              <Button variant="destructive" onClick={confirmReject}>
                Move to Rejected
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
