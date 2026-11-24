import { cn } from '@/lib/utils'
import { getAvatarGradient, getInitials } from '@/lib/profile'

const SIZES = {
  sm: 'h-8 w-8 rounded-lg text-xs',
  md: 'h-11 w-11 rounded-xl text-sm',
  lg: 'h-14 w-14 rounded-2xl text-base',
  xl: 'h-24 w-24 rounded-2xl text-3xl',
} as const

interface AvatarProps {
  name: string
  size?: keyof typeof SIZES
  className?: string
}

export function Avatar({ name, size = 'md', className }: AvatarProps) {
  return (
    <div
      aria-hidden
      className={cn(
        'flex shrink-0 items-center justify-center bg-gradient-to-br font-semibold tracking-wide text-white shadow-sm',
        getAvatarGradient(name),
        SIZES[size],
        className,
      )}
    >
      {getInitials(name)}
    </div>
  )
}
