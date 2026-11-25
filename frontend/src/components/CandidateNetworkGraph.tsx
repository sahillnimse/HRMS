import { useMemo, useRef, useState } from 'react'
import {
  Award,
  Briefcase,
  Code2,
  Download,
  GraduationCap,
  Maximize2,
  Minimize2,
  Network,
  RotateCcw,
  Sparkles,
  Wrench,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import type { CandidateProfileData } from '@/types'
import { cn, formatDate, formatYears } from '@/lib/utils'
import { getInitials, getSeniority } from '@/lib/profile'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'

type NodeKind = 'candidate' | 'domain' | 'experience' | 'skill' | 'tool' | 'education' | 'credential'

interface GraphNode {
  id: string
  label: string
  sublabel?: string
  kind: NodeKind
  x: number
  y: number
  radius: number
  details: {
    title: string
    subtitle?: string
    meta?: string[]
    bullets?: string[]
    tags?: string[]
  }
}

interface GraphEdge {
  id: string
  from: string
  to: string
  kind: 'primary' | 'inferred'
  label?: string
}

const KIND_STYLE: Record<
  NodeKind,
  { label: string; fill: string; stroke: string; text: string; badgeBg: string; dot: string }
> = {
  candidate: {
    label: 'Candidate',
    fill: '#0d8274',
    stroke: '#0b685e',
    text: '#ffffff',
    badgeBg: 'bg-brand-50 text-brand-700 border-brand-200',
    dot: '#0d8274',
  },
  domain: {
    label: 'Domain',
    fill: '#edfaf7',
    stroke: '#0f9d8a',
    text: '#0b685e',
    badgeBg: 'bg-brand-50 text-brand-700 border-brand-200',
    dot: '#0f9d8a',
  },
  experience: {
    label: 'Experience',
    fill: '#f0f9ff',
    stroke: '#0284c7',
    text: '#0c4a6e',
    badgeBg: 'bg-sky-50 text-sky-700 border-sky-200',
    dot: '#0284c7',
  },
  skill: {
    label: 'Tech Skills',
    fill: '#fff4f2',
    stroke: '#f25c43',
    text: '#bc331d',
    badgeBg: 'bg-coral-50 text-coral-700 border-coral-200',
    dot: '#f25c43',
  },
  tool: {
    label: 'Tools',
    fill: '#ecfdf5',
    stroke: '#059669',
    text: '#064e3b',
    badgeBg: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    dot: '#059669',
  },
  education: {
    label: 'Education',
    fill: '#fffbeb',
    stroke: '#d97706',
    text: '#78350f',
    badgeBg: 'bg-amber-50 text-amber-800 border-amber-200',
    dot: '#d97706',
  },
  credential: {
    label: 'Credentials',
    fill: '#fff1f2',
    stroke: '#e11d48',
    text: '#881337',
    badgeBg: 'bg-rose-50 text-rose-700 border-rose-200',
    dot: '#e11d48',
  },
}

const FILTER_KINDS: NodeKind[] = ['experience', 'skill', 'tool', 'education', 'credential']

const VIEW_W = 1040
const VIEW_H = 640
const CX = VIEW_W / 2
const CY = VIEW_H / 2

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function mentionsTerm(haystack: string, term: string): boolean {
  const clean = term.trim()
  if (clean.length < 2) return false
  const escaped = escapeRegExp(clean)
  const boundary = /^[a-z0-9]/i.test(clean) && /[a-z0-9]$/i.test(clean)
  const regex = boundary ? new RegExp(`\\b${escaped}\\b`, 'i') : new RegExp(escaped, 'i')
  return regex.test(haystack)
}

function clipText(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

/** Build deterministic radial sectors so nodes never pile up, plus inferred role↔skill links. */
function buildCandidateGraph(profile: CandidateProfileData): {
  nodes: GraphNode[]
  edges: GraphEdge[]
  inferredCount: number
} {
  const nodes: GraphNode[] = []
  const edges: GraphEdge[] = []

  const centerId = 'candidate'
  nodes.push({
    id: centerId,
    label: profile.full_name || 'Candidate',
    sublabel: `${formatYears(profile.years_experience)} · ${getSeniority(profile.years_experience)}`,
    kind: 'candidate',
    x: CX,
    y: CY,
    radius: 46,
    details: {
      title: profile.full_name || 'Candidate Profile',
      subtitle: `${profile.primary_domain || 'General'} · ${formatYears(profile.years_experience)}`,
      meta: [
        profile.city ? `Location: ${profile.city}` : '',
        profile.email ? `Email: ${profile.email}` : '',
        `Seniority: ${getSeniority(profile.years_experience)}`,
      ].filter(Boolean),
      bullets: profile.profile_summary ? [profile.profile_summary] : [],
    },
  })

  // Primary Domain anchor directly above candidate
  if (profile.primary_domain?.trim()) {
    const domainId = 'domain'
    nodes.push({
      id: domainId,
      label: clipText(profile.primary_domain, 22),
      sublabel: 'Primary Domain',
      kind: 'domain',
      x: CX,
      y: CY - 135,
      radius: 30,
      details: {
        title: profile.primary_domain,
        subtitle: 'Primary Domain & Specialization',
        meta: [
          `${formatYears(profile.years_experience)} total experience`,
          `${profile.work_experience.length} career role${profile.work_experience.length === 1 ? '' : 's'}`,
          `${profile.technical_skills.length} technical skill${profile.technical_skills.length === 1 ? '' : 's'}`,
        ],
      },
    })
    edges.push({ id: `e-${centerId}-${domainId}`, from: centerId, to: domainId, kind: 'primary' })
  }

  // Place groups into non-overlapping angular arcs around the candidate
  const placeArc = <T,>(
    items: T[],
    startDeg: number,
    endDeg: number,
    baseRx: number,
    baseRy: number,
    makeNode: (item: T, idx: number, x: number, y: number) => GraphNode,
  ) => {
    const count = items.length
    if (count === 0) return
    items.forEach((item, idx) => {
      const t = count === 1 ? 0.5 : idx / (count - 1)
      const deg = startDeg + (endDeg - startDeg) * t
      const rad = (deg * Math.PI) / 180
      // Stagger alternate radii when a cluster has many nodes so labels breathe cleanly
      const stagger = count > 4 ? (idx % 2 === 0 ? 1.08 : 0.84) : 1
      const x = Math.round(CX + Math.cos(rad) * baseRx * stagger)
      const y = Math.round(CY + Math.sin(rad) * baseRy * stagger)
      const node = makeNode(item, idx, x, y)
      nodes.push(node)
      edges.push({ id: `e-${centerId}-${node.id}`, from: centerId, to: node.id, kind: 'primary' })
    })
  }

  // 1. Experience — Left sector (142° to 228°)
  const expItems = (profile.work_experience || []).slice(0, 6)
  const expTextById = new Map<string, string>()
  placeArc(expItems, 142, 228, 315, 225, (exp, idx, x, y) => {
    const id = `exp-${idx}`
    expTextById.set(id, [exp.company, exp.job_title, ...(exp.bullets || [])].join(' '))
    const dateRange = [formatDate(exp.start_date), formatDate(exp.end_date)].filter((d) => d !== '-').join(' – ')
    return {
      id,
      label: clipText(exp.company || exp.job_title || `Role ${idx + 1}`, 18),
      sublabel: clipText(exp.job_title || '', 20),
      kind: 'experience',
      x,
      y,
      radius: 28,
      details: {
        title: exp.job_title || exp.company || 'Experience',
        subtitle: exp.company,
        meta: dateRange ? [dateRange] : [],
        bullets: exp.bullets || [],
      },
    }
  })

  // 2. Technical Skills — Upper-right sector (-55° to 24°)
  const techItems = (profile.technical_skills || []).slice(0, 10)
  placeArc(techItems, -55, 24, 340, 235, (skill, idx, x, y) => ({
    id: `skill-${idx}`,
    label: clipText(skill, 15),
    kind: 'skill',
    x,
    y,
    radius: 21,
    details: {
      title: skill,
      subtitle: 'Technical Skill',
      meta: [],
    },
  }))

  // 3. Tools & Platforms — Lower-right sector (38° to 88°)
  const toolItems = (profile.tools || []).slice(0, 8)
  placeArc(toolItems, 38, 88, 325, 235, (tool, idx, x, y) => ({
    id: `tool-${idx}`,
    label: clipText(tool, 15),
    kind: 'tool',
    x,
    y,
    radius: 20,
    details: {
      title: tool,
      subtitle: 'Tool / Platform',
      meta: [],
    },
  }))

  // 4. Education — Bottom sector (102° to 132°)
  const eduItems = (profile.education || []).slice(0, 4)
  placeArc(eduItems, 102, 132, 285, 245, (edu, idx, x, y) => ({
    id: `edu-${idx}`,
    label: clipText(edu.institution || edu.degree || `Education ${idx + 1}`, 18),
    sublabel: edu.graduation_year ? String(edu.graduation_year) : undefined,
    kind: 'education',
    x,
    y,
    radius: 25,
    details: {
      title: edu.degree || 'Education',
      subtitle: edu.institution,
      meta: edu.graduation_year ? [`Class of ${edu.graduation_year}`] : [],
    },
  }))

  // 5. Certifications & Languages — Upper-left sector (-128° to -102°)
  const credentials = [
    ...(profile.certifications || []).slice(0, 4).map((c) => ({ label: c, type: 'Certification' })),
    ...(profile.languages || []).slice(0, 3).map((l) => ({ label: l, type: 'Language' })),
  ].slice(0, 5)

  placeArc(credentials, -138, -104, 310, 235, (cred, idx, x, y) => ({
    id: `cred-${idx}`,
    label: clipText(cred.label, 16),
    sublabel: cred.type,
    kind: 'credential',
    x,
    y,
    radius: 20,
    details: {
      title: cred.label,
      subtitle: cred.type,
    },
  }))

  // Cross-edges: connect Work Experience roles to Technical Skills & Tools mentioned in their bullets/titles
  let inferredCount = 0
  const capabilityNodes = nodes.filter((n) => n.kind === 'skill' || n.kind === 'tool')
  const nodeById = new Map(nodes.map((n) => [n.id, n]))

  for (const [expId, haystack] of expTextById.entries()) {
    const expNode = nodeById.get(expId)
    if (!expNode) continue
    const matchedSkills: string[] = []
    for (const cap of capabilityNodes) {
      if (mentionsTerm(haystack, cap.details.title)) {
        edges.push({
          id: `inf-${expId}-${cap.id}`,
          from: expId,
          to: cap.id,
          kind: 'inferred',
          label: 'Used in role',
        })
        matchedSkills.push(cap.details.title)
        cap.details.tags = [...(cap.details.tags || []), expNode.details.subtitle || expNode.details.title]
        inferredCount++
      }
    }
    if (matchedSkills.length > 0) {
      expNode.details.tags = matchedSkills
    }
  }

  return { nodes, edges, inferredCount }
}

interface CandidateNetworkGraphProps {
  profile: CandidateProfileData
  title?: string
  subtitle?: string
  height?: number
  className?: string
}

export function CandidateNetworkGraph({
  profile,
  title = 'Candidate Knowledge Network',
  subtitle = 'Interactive map linking career roles, technical skills, tools, education & credentials',
  height = 520,
  className,
}: CandidateNetworkGraphProps) {
  const baseGraph = useMemo(() => buildCandidateGraph(profile), [profile])
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({})
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [activeFilter, setActiveFilter] = useState<NodeKind | 'all'>('all')
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [expanded, setExpanded] = useState(false)

  const svgRef = useRef<SVGSVGElement>(null)
  const dragRef = useRef<{
    type: 'node' | 'canvas'
    nodeId?: string
    startX: number
    startY: number
    origX: number
    origY: number
    moved: boolean
  } | null>(null)

  const getPos = (node: GraphNode) => positions[node.id] ?? { x: node.x, y: node.y }

  const visibleNodes = useMemo(() => {
    if (activeFilter === 'all') return baseGraph.nodes
    return baseGraph.nodes.filter(
      (n) => n.kind === 'candidate' || n.kind === 'domain' || n.kind === activeFilter,
    )
  }, [baseGraph.nodes, activeFilter])

  const visibleNodeIds = useMemo(() => new Set(visibleNodes.map((n) => n.id)), [visibleNodes])

  const visibleEdges = useMemo(
    () => baseGraph.edges.filter((e) => visibleNodeIds.has(e.from) && visibleNodeIds.has(e.to)),
    [baseGraph.edges, visibleNodeIds],
  )

  const focusId = hoveredId ?? selectedId
  const connectedIds = useMemo(() => {
    if (!focusId) return null
    const set = new Set<string>([focusId])
    for (const e of visibleEdges) {
      if (e.from === focusId) set.add(e.to)
      if (e.to === focusId) set.add(e.from)
    }
    return set
  }, [focusId, visibleEdges])

  const selectedNode = useMemo(
    () => baseGraph.nodes.find((n) => n.id === selectedId) ?? null,
    [baseGraph.nodes, selectedId],
  )

  const toSvgCoords = (clientX: number, clientY: number) => {
    const svg = svgRef.current
    if (!svg) return { x: 0, y: 0 }
    const rect = svg.getBoundingClientRect()
    const scaleX = VIEW_W / rect.width
    const scaleY = VIEW_H / rect.height
    return {
      x: (clientX - rect.left) * scaleX,
      y: (clientY - rect.top) * scaleY,
    }
  }

  const handleNodePointerDown = (e: React.PointerEvent, node: GraphNode) => {
    e.stopPropagation()
    ;(e.currentTarget as Element).setPointerCapture(e.pointerId)
    const pt = toSvgCoords(e.clientX, e.clientY)
    const pos = getPos(node)
    dragRef.current = {
      type: 'node',
      nodeId: node.id,
      startX: pt.x,
      startY: pt.y,
      origX: pos.x,
      origY: pos.y,
      moved: false,
    }
  }

  const handleCanvasPointerDown = (e: React.PointerEvent) => {
    const pt = toSvgCoords(e.clientX, e.clientY)
    dragRef.current = {
      type: 'canvas',
      startX: pt.x,
      startY: pt.y,
      origX: pan.x,
      origY: pan.y,
      moved: false,
    }
  }

  const handlePointerMove = (e: React.PointerEvent) => {
    const drag = dragRef.current
    if (!drag) return
    const pt = toSvgCoords(e.clientX, e.clientY)
    const dx = (pt.x - drag.startX) / zoom
    const dy = (pt.y - drag.startY) / zoom
    if (Math.abs(dx) > 2 || Math.abs(dy) > 2) drag.moved = true

    if (drag.type === 'node' && drag.nodeId) {
      setPositions((prev) => ({
        ...prev,
        [drag.nodeId!]: { x: drag.origX + dx, y: drag.origY + dy },
      }))
    } else if (drag.type === 'canvas') {
      setPan({ x: drag.origX + (pt.x - drag.startX), y: drag.origY + (pt.y - drag.startY) })
    }
  }

  const handlePointerUp = () => {
    const drag = dragRef.current
    if (drag && !drag.moved) {
      if (drag.type === 'node' && drag.nodeId) {
        setSelectedId((prev) => (prev === drag.nodeId ? null : drag.nodeId!))
      } else if (drag.type === 'canvas') {
        setSelectedId(null)
      }
    }
    dragRef.current = null
  }

  const resetView = () => {
    setZoom(1)
    setPan({ x: 0, y: 0 })
    setPositions({})
    setActiveFilter('all')
    setSelectedId(null)
  }

  const exportSvg = () => {
    const svg = svgRef.current
    if (!svg) return
    const serializer = new XMLSerializer()
    const source = serializer.serializeToString(svg)
    const blob = new Blob([source], { type: 'image/svg+xml;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${(profile.full_name || 'candidate').toLowerCase().replace(/\s+/g, '-')}-network.svg`
    a.click()
    URL.revokeObjectURL(url)
  }

  const countsByKind = useMemo(() => {
    const map: Partial<Record<NodeKind, number>> = {}
    for (const n of baseGraph.nodes) map[n.kind] = (map[n.kind] ?? 0) + 1
    return map
  }, [baseGraph.nodes])

  const renderCurve = (from: { x: number; y: number }, to: { x: number; y: number }, inferred: boolean) => {
    const mx = (from.x + to.x) / 2
    const my = (from.y + to.y) / 2
    const dx = to.x - from.x
    const dy = to.y - from.y
    const bend = inferred ? 0.16 : 0.08
    const cx = mx - dy * bend
    const cy = my + dx * bend
    return `M ${from.x} ${from.y} Q ${cx} ${cy} ${to.x} ${to.y}`
  }

  const nodeById = useMemo(() => new Map(visibleNodes.map((n) => [n.id, n])), [visibleNodes])

  const containerClass = expanded
    ? 'fixed inset-4 z-50 flex flex-col overflow-hidden rounded-2xl border bg-white shadow-2xl'
    : cn('overflow-hidden rounded-2xl border bg-white shadow-card', className)

  const SelectedIcon =
    selectedNode?.kind === 'experience'
      ? Briefcase
      : selectedNode?.kind === 'skill'
        ? Code2
        : selectedNode?.kind === 'tool'
          ? Wrench
          : selectedNode?.kind === 'education'
            ? GraduationCap
            : selectedNode?.kind === 'credential'
              ? Award
              : Sparkles

  return (
    <>
      {expanded && (
        <div
          className="fixed inset-0 z-40 bg-slate-900/30 backdrop-blur-sm"
          onClick={() => setExpanded(false)}
        />
      )}
      <div className={containerClass}>
        {/* Header Bar */}
        <div className="flex flex-col gap-3 border-b border-slate-100 bg-gradient-to-r from-white via-slate-50/60 to-brand-50/40 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 ring-1 ring-brand-100">
              <Network size={20} />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-base font-semibold text-slate-900">{title}</h3>
                <Badge variant="brand">{baseGraph.nodes.length} nodes</Badge>
                <Badge variant="secondary">{baseGraph.edges.length} links</Badge>
                {baseGraph.inferredCount > 0 && (
                  <Badge variant="success">{baseGraph.inferredCount} skill-role matches</Badge>
                )}
              </div>
              <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={() => setZoom((z) => Math.min(1.8, +(z + 0.15).toFixed(2)))}
              title="Zoom in"
              aria-label="Zoom in"
            >
              <ZoomIn size={15} />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={() => setZoom((z) => Math.max(0.65, +(z - 0.15).toFixed(2)))}
              title="Zoom out"
              aria-label="Zoom out"
            >
              <ZoomOut size={15} />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={resetView}
              title="Reset layout"
              aria-label="Reset layout"
            >
              <RotateCcw size={15} />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={exportSvg}
              title="Download graph SVG"
              aria-label="Download graph SVG"
            >
              <Download size={15} />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={() => setExpanded((e) => !e)}
              title={expanded ? 'Exit fullscreen' : 'Fullscreen'}
              aria-label={expanded ? 'Exit fullscreen' : 'Fullscreen'}
            >
              {expanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
            </Button>
          </div>
        </div>

        {/* Filter & Legend Strip */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-white px-5 py-2.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => setActiveFilter('all')}
              className={cn(
                'rounded-full border px-3 py-1 text-xs font-medium transition',
                activeFilter === 'all'
                  ? 'border-brand-600 bg-brand-600 text-white shadow-sm'
                  : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50',
              )}
            >
              All ({baseGraph.nodes.length})
            </button>
            {FILTER_KINDS.map((kind) => {
              const count = countsByKind[kind] ?? 0
              if (count === 0) return null
              const style = KIND_STYLE[kind]
              const active = activeFilter === kind
              return (
                <button
                  key={kind}
                  type="button"
                  onClick={() => setActiveFilter((prev) => (prev === kind ? 'all' : kind))}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition',
                    active
                      ? 'border-slate-900 bg-slate-900 text-white'
                      : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50',
                  )}
                >
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: active ? '#ffffff' : style.dot }}
                  />
                  {style.label}
                  <span className="opacity-70">{count}</span>
                </button>
              )
            })}
          </div>
          <span className="hidden text-[11px] text-slate-400 md:inline">
            Drag nodes to rearrange · Click any node to inspect · Dashed lines = skills used in role
          </span>
        </div>

        {/* Interactive SVG Canvas */}
        <div
          className={cn(
            'relative w-full select-none overflow-hidden bg-slate-50/70 bg-dots',
            expanded ? 'flex-1' : '',
          )}
          style={expanded ? undefined : { height }}
        >
          <svg
            ref={svgRef}
            viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
            className="h-full w-full cursor-grab active:cursor-grabbing"
            onPointerDown={handleCanvasPointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerLeave={handlePointerUp}
          >
            <defs>
              <linearGradient id="candGrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#6366f1" />
                <stop offset="100%" stopColor="#7c3aed" />
              </linearGradient>
              <filter id="nodeShadow" x="-25%" y="-25%" width="150%" height="150%">
                <feDropShadow dx="0" dy="3" stdDeviation="4" floodColor="#0f172a" floodOpacity="0.08" />
              </filter>
              <filter id="centerGlow" x="-40%" y="-40%" width="180%" height="180%">
                <feDropShadow dx="0" dy="6" stdDeviation="10" floodColor="#4f46e5" floodOpacity="0.28" />
              </filter>
            </defs>

            <g
              transform={`translate(${pan.x + CX * (1 - zoom)}, ${pan.y + CY * (1 - zoom)}) scale(${zoom})`}
            >
              {/* Subtle orbital guide rings */}
              <ellipse
                cx={CX}
                cy={CY}
                rx={165}
                ry={125}
                fill="none"
                stroke="#e2e8f0"
                strokeWidth={1}
                strokeDasharray="4 6"
              />
              <ellipse
                cx={CX}
                cy={CY}
                rx={325}
                ry={235}
                fill="none"
                stroke="#e2e8f0"
                strokeWidth={1}
                strokeDasharray="4 6"
              />

              {/* Edges */}
              {visibleEdges.map((edge) => {
                const a = nodeById.get(edge.from)
                const b = nodeById.get(edge.to)
                if (!a || !b) return null
                const pa = getPos(a)
                const pb = getPos(b)
                const isHighlighted =
                  focusId != null && (edge.from === focusId || edge.to === focusId)
                const dimmed = focusId != null && !isHighlighted
                const strokeColor =
                  edge.kind === 'inferred'
                    ? isHighlighted
                      ? '#0284c7'
                      : '#93c5fd'
                    : isHighlighted
                      ? KIND_STYLE[b.kind].stroke
                      : '#cbd5e1'

                return (
                  <path
                    key={edge.id}
                    d={renderCurve(pa, pb, edge.kind === 'inferred')}
                    fill="none"
                    stroke={strokeColor}
                    strokeWidth={isHighlighted ? 2.4 : edge.kind === 'inferred' ? 1.5 : 1.35}
                    strokeDasharray={edge.kind === 'inferred' ? '5 4' : undefined}
                    opacity={dimmed ? 0.16 : isHighlighted ? 0.95 : edge.kind === 'inferred' ? 0.7 : 0.72}
                    className={cn('transition-opacity duration-200', isHighlighted && edge.kind === 'inferred' && 'animate-dash')}
                  />
                )
              })}

              {/* Nodes */}
              {visibleNodes.map((node) => {
                const pos = getPos(node)
                const style = KIND_STYLE[node.kind]
                const isSelected = selectedId === node.id
                const isHovered = hoveredId === node.id
                const dimmed = connectedIds != null && !connectedIds.has(node.id)
                const isCenter = node.kind === 'candidate'

                return (
                  <g
                    key={node.id}
                    transform={`translate(${pos.x}, ${pos.y})`}
                    opacity={dimmed ? 0.25 : 1}
                    className="cursor-pointer transition-opacity duration-200"
                    onPointerDown={(e) => handleNodePointerDown(e, node)}
                    onPointerEnter={() => setHoveredId(node.id)}
                    onPointerLeave={() => setHoveredId((prev) => (prev === node.id ? null : prev))}
                  >
                    {isCenter && (
                      <circle
                        r={node.radius + 11}
                        fill="none"
                        stroke="#818cf8"
                        strokeWidth={2}
                        className="animate-pulse-soft"
                        style={{ transformOrigin: '0 0' }}
                      />
                    )}

                    {(isSelected || isHovered) && !isCenter && (
                      <circle
                        r={node.radius + 6}
                        fill={style.stroke}
                        opacity={0.14}
                      />
                    )}

                    <circle
                      r={node.radius}
                      fill={isCenter ? 'url(#candGrad)' : style.fill}
                      stroke={isSelected ? '#0f172a' : style.stroke}
                      strokeWidth={isCenter ? 3 : isSelected ? 2.5 : 1.75}
                      filter={isCenter ? 'url(#centerGlow)' : 'url(#nodeShadow)'}
                    />

                    {isCenter ? (
                      <>
                        <text
                          y={-2}
                          textAnchor="middle"
                          dominantBaseline="central"
                          fill="#ffffff"
                          fontSize={16}
                          fontWeight={700}
                          letterSpacing="0.04em"
                        >
                          {getInitials(node.label)}
                        </text>
                        <rect
                          x={-76}
                          y={node.radius + 8}
                          width={152}
                          height={24}
                          rx={12}
                          fill="#ffffff"
                          stroke="#e2e8f0"
                          strokeWidth={1}
                        />
                        <text
                          y={node.radius + 20}
                          textAnchor="middle"
                          dominantBaseline="central"
                          fill="#0f172a"
                          fontSize={11.5}
                          fontWeight={600}
                        >
                          {clipText(node.label, 20)}
                        </text>
                      </>
                    ) : (
                      <>
                        <text
                          textAnchor="middle"
                          dominantBaseline="central"
                          fill={style.text}
                          fontSize={node.radius >= 25 ? 10.5 : 9.5}
                          fontWeight={700}
                        >
                          {node.kind === 'domain'
                            ? 'DOM'
                            : node.kind === 'experience'
                              ? 'ROLE'
                              : node.kind === 'education'
                                ? 'EDU'
                                : node.kind === 'tool'
                                  ? 'TOOL'
                                  : node.kind === 'credential'
                                    ? 'CERT'
                                    : 'TECH'}
                        </text>
                        <g transform={`translate(0, ${node.radius + 13})`}>
                          <rect
                            x={-Math.min(78, Math.max(38, node.label.length * 3.6 + 12))}
                            y={-10}
                            width={Math.min(156, Math.max(76, node.label.length * 7.2 + 24))}
                            height={20}
                            rx={10}
                            fill="#ffffff"
                            fillOpacity={0.94}
                            stroke={isSelected || isHovered ? style.stroke : '#e2e8f0'}
                            strokeWidth={1}
                          />
                          <text
                            textAnchor="middle"
                            dominantBaseline="central"
                            fill="#1e293b"
                            fontSize={11}
                            fontWeight={600}
                          >
                            {node.label}
                          </text>
                        </g>
                      </>
                    )}
                  </g>
                )
              })}
            </g>
          </svg>

          {/* Floating Inspector Card */}
          {selectedNode && (
            <div className="absolute bottom-4 right-4 z-10 w-[min(320px,calc(100%-2rem))] rounded-2xl border border-slate-200 bg-white/95 p-4 shadow-xl backdrop-blur animate-fade-in">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-start gap-2.5">
                  <span
                    className={cn(
                      'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border',
                      KIND_STYLE[selectedNode.kind].badgeBg,
                    )}
                  >
                    <SelectedIcon size={15} />
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold leading-snug text-slate-900">
                      {selectedNode.details.title}
                    </p>
                    {selectedNode.details.subtitle && (
                      <p className="text-xs text-slate-500">{selectedNode.details.subtitle}</p>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedId(null)}
                  className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                  aria-label="Close details"
                >
                  <X size={14} />
                </button>
              </div>

              {selectedNode.details.meta && selectedNode.details.meta.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {selectedNode.details.meta.map((m, i) => (
                    <span
                      key={i}
                      className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600"
                    >
                      {m}
                    </span>
                  ))}
                </div>
              )}

              {selectedNode.details.bullets && selectedNode.details.bullets.length > 0 && (
                <ul className="mt-3 max-h-36 space-y-1.5 overflow-y-auto pr-1 text-xs leading-5 text-slate-600">
                  {selectedNode.details.bullets.map((b, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-brand-500" />
                      <span>{b}</span>
                    </li>
                  ))}
                </ul>
              )}

              {selectedNode.details.tags && selectedNode.details.tags.length > 0 && (
                <div className="mt-3 border-t border-slate-100 pt-2.5">
                  <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    {selectedNode.kind === 'experience' ? 'Skills matched in role' : 'Applied at'}
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {selectedNode.details.tags.map((tag, i) => (
                      <Badge key={i} variant="brand" className="text-[11px]">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  )
}
