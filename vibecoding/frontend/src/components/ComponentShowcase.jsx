import React, { useState } from 'react'
import {
  Button,
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  Input,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '@/components/ui'
import { cn } from '@/lib/utils'

/**
 * ComponentShowcase.jsx
 * 
 * This is a quick reference showing all available shadcn/ui + Radix UI components
 * and how to use them in your application.
 */

export function ComponentShowcase() {
  const [selectedValue, setSelectedValue] = useState('option1')
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div className="space-y-8 p-8">
      <h1 className="text-3xl font-bold">Component Showcase</h1>

      {/* Button Examples */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Buttons</h2>
        <div className="flex flex-wrap gap-2">
          <Button>Default</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="destructive">Destructive</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="link">Link</Button>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button size="sm">Small</Button>
          <Button size="default">Default</Button>
          <Button size="lg">Large</Button>
          <Button size="icon">🔍</Button>
        </div>
      </section>

      {/* Input Examples */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Input</h2>
        <div className="flex flex-col gap-2 max-w-xs">
          <Input type="text" placeholder="Enter text..." />
          <Input type="email" placeholder="Email address" />
          <Input type="password" placeholder="Password" />
        </div>
      </section>

      {/* Select Examples */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Select</h2>
        <Select value={selectedValue} onValueChange={setSelectedValue}>
          <SelectTrigger className="w-[180px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="option1">Option 1</SelectItem>
            <SelectItem value="option2">Option 2</SelectItem>
            <SelectItem value="option3">Option 3</SelectItem>
          </SelectContent>
        </Select>
      </section>

      {/* Dialog Examples */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Dialog</h2>
        <Dialog open={isOpen} onOpenChange={setIsOpen}>
          <DialogTrigger asChild>
            <Button>Open Dialog</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Dialog Title</DialogTitle>
              <DialogDescription>
                This is a dialog description. You can put any content here.
              </DialogDescription>
            </DialogHeader>
            <div className="py-4">
              <p className="text-sm text-gray-500">Dialog content goes here</p>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsOpen(false)}>
                Cancel
              </Button>
              <Button onClick={() => setIsOpen(false)}>
                Confirm
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </section>

      {/* DropdownMenu Examples */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Dropdown Menu</h2>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline">Open Menu</Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-56">
            <DropdownMenuItem>New File</DropdownMenuItem>
            <DropdownMenuItem>Open File...</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem>Save</DropdownMenuItem>
            <DropdownMenuItem>Save As...</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="text-red-600">Exit</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </section>

      {/* Utility: cn() function */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Using cn() Utility</h2>
        <div className="bg-blue-100 p-4 rounded">
          <p className={cn(
            'text-sm',
            'font-semibold',
            selectedValue === 'option1' && 'text-blue-600',
            selectedValue !== 'option1' && 'text-gray-600'
          )}>
            This text changes color based on selection. Current: {selectedValue}
          </p>
        </div>
      </section>

      {/* Dark Mode Example */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Dark Mode Support</h2>
        <div className="bg-gray-100 dark:bg-gray-900 p-4 rounded">
          <p className="text-gray-900 dark:text-gray-100">
            All components automatically support dark mode!
            Try toggling your system's dark mode.
          </p>
        </div>
      </section>
    </div>
  )
}

export default ComponentShowcase
