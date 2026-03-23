import * as React from "react";

// Simple Button component – no external dependencies
const Button = React.forwardRef(({ className = '', variant = 'default', size = 'default', children, ...props }, ref) => {
  const base = 'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50';

  const variants = {
    default: 'bg-blue-600 text-white hover:bg-blue-700',
    destructive: 'bg-red-600 text-white hover:bg-red-700',
    outline: 'border border-gray-300 bg-transparent hover:bg-gray-100 text-gray-700',
    secondary: 'bg-gray-200 text-gray-800 hover:bg-gray-300',
    ghost: 'hover:bg-gray-100 text-gray-700',
    link: 'text-blue-600 underline-offset-4 hover:underline',
  };

  const sizes = {
    default: 'h-10 px-4 py-2',
    sm: 'h-8 px-3 text-xs',
    lg: 'h-11 px-8',
    icon: 'h-9 w-9',
  };

  // Only apply variant styles if className doesn't contain background or text color overrides
  const hasCustomBg = className.includes('bg-') || className.includes('!bg-');
  const hasCustomText = className.includes('text-') || className.includes('!text-');
  const hasCustomHover = className.includes('hover:');
  
  const variantClass = (hasCustomBg || hasCustomText || hasCustomHover) ? '' : (variants[variant] || variants.default);
  const cls = [base, variantClass, sizes[size] || sizes.default, className].join(' ');

  return (
    <button ref={ref} className={cls} {...props}>
      {children}
    </button>
  );
});

Button.displayName = 'Button';

export { Button };
