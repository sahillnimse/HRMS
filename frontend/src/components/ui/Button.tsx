import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-semibold transition-all duration-200 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-100 disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default:
          'bg-gradient-to-b from-brand-500 to-brand-600 text-white shadow-sm hover:from-brand-600 hover:to-brand-700 hover:shadow-glow',
        destructive:
          'bg-gradient-to-b from-coral-500 to-coral-600 text-white shadow-sm hover:from-coral-600 hover:to-coral-700',
        outline:
          'border border-slate-200/90 bg-white text-slate-700 shadow-sm hover:border-brand-200 hover:bg-brand-50/40 hover:text-brand-800',
        secondary: 'bg-stone-100 text-slate-800 hover:bg-stone-200/80',
        ghost: 'text-slate-600 hover:bg-brand-50/60 hover:text-brand-800',
        link: 'text-brand-600 underline-offset-4 hover:underline',
        soft: 'bg-brand-50 text-brand-700 hover:bg-brand-100/90',
      },
      size: {
        default: 'h-10 px-4',
        sm: 'h-9 px-3',
        lg: 'h-11 px-6 text-[15px]',
        icon: 'h-9 w-9',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
  loading?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, loading = false, disabled, children, ...props }, ref) => {
    if (asChild) {
      return (
        <Slot className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props}>
          {children}
        </Slot>
      )
    }
    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        disabled={disabled || loading}
        {...props}
      >
        {loading && <Loader2 size={16} className="animate-spin" />}
        {children}
      </button>
    )
  },
)
Button.displayName = 'Button'

export { buttonVariants, Button }
