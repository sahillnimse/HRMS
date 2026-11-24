import * as React from 'react'
import { AlertTriangle, CheckCircle, Info, X } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface Toast {
  id: string
  message: string
  type: 'success' | 'error' | 'info'
}

const TOAST_LIMIT = 4
const TOAST_REMOVE_DELAY = 4500

interface ToastContextValue {
  addToast: (message: string, type?: Toast['type']) => void
}

const ToastContext = React.createContext<ToastContextValue | null>(null)

const TOAST_STYLES: Record<Toast['type'], { icon: typeof Info; iconClass: string; bar: string }> = {
  success: { icon: CheckCircle, iconClass: 'bg-emerald-50 text-emerald-600', bar: 'bg-emerald-500' },
  error: { icon: AlertTriangle, iconClass: 'bg-red-50 text-red-600', bar: 'bg-red-500' },
  info: { icon: Info, iconClass: 'bg-brand-50 text-brand-600', bar: 'bg-brand-500' },
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([])

  const removeToast = React.useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const addToast = React.useCallback(
    (message: string, type: Toast['type'] = 'info') => {
      const id = crypto.randomUUID()
      setToasts((prev) => [{ id, message, type }, ...prev].slice(0, TOAST_LIMIT))
      window.setTimeout(() => removeToast(id), TOAST_REMOVE_DELAY)
    },
    [removeToast],
  )

  const value = React.useMemo(() => ({ addToast }), [addToast])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed right-4 top-4 z-[60] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2">
        {toasts.map((toast) => {
          const style = TOAST_STYLES[toast.type]
          const Icon = style.icon
          return (
            <div
              key={toast.id}
              role="status"
              className="pointer-events-auto relative flex items-start gap-3 overflow-hidden rounded-xl border bg-white p-4 pl-5 text-sm shadow-lg animate-fade-in"
            >
              <span className={cn('absolute inset-y-0 left-0 w-1', style.bar)} />
              <span className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-lg', style.iconClass)}>
                <Icon size={16} />
              </span>
              <p className="flex-1 pt-1.5 font-medium leading-5 text-slate-800">{toast.message}</p>
              <button
                type="button"
                onClick={() => removeToast(toast.id)}
                className="rounded-md p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
                aria-label="Dismiss notification"
              >
                <X size={14} />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useAddToast() {
  const context = React.useContext(ToastContext)
  if (!context) {
    throw new Error('useAddToast must be used within a ToastProvider')
  }
  return context.addToast
}
