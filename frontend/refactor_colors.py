import os
import re

mapping = {
    # Text
    r'text-(gray|slate)-900': 'text-app-text-main',
    r'text-(gray|slate)-[67]00': 'text-app-text-label',
    r'text-(gray|slate)-500': 'text-app-text-muted',
    r'text-(gray|slate)-400': 'text-app-text-light',
    r'text-(gray|slate)-300': 'text-app-border',
    r'text-(blue|indigo)-600': 'text-app-primary',
    r'text-(blue|indigo)-700': 'text-app-primary-hover',
    r'text-blue-50': 'text-app-primary-light',
    r'text-blue-200': 'text-app-primary-ring',
    r'text-blue-800': 'text-app-primary-dark',
    r'text-(red|rose)-[56]00': 'text-app-status-error',
    r'text-(green|emerald)-[56]00': 'text-app-status-success',
    r'text-(amber|yellow)-[56]00': 'text-app-status-warning',

    # Backgrounds
    r'bg-(gray|slate)-50': 'bg-app-bg-page',
    r'bg-(gray|slate)-100': 'bg-app-bg-muted',
    r'bg-(gray|slate)-200': 'bg-app-bg-hover',
    r'bg-(gray|slate)-800': 'bg-app-text-label',
    r'bg-(gray|slate)-900': 'bg-app-text-main',
    r'bg-white': 'bg-app-bg-card',
    r'bg-(blue|indigo)-600': 'bg-app-primary',
    r'bg-(blue|indigo)-700': 'bg-app-primary-hover',
    r'bg-(blue|indigo)-50': 'bg-app-primary-light',
    r'bg-blue-100': 'bg-app-primary-light',
    r'bg-(red|rose)-50': 'bg-app-status-errorBg',
    r'bg-(green|emerald)-50': 'bg-app-status-successBg',
    r'bg-(amber|yellow)-50': 'bg-app-status-warningBg',
    
    # Borders
    r'border-(gray|slate)-100': 'border-app-border-light',
    r'border-(gray|slate)-200': 'border-app-border',
    r'border-(gray|slate)-300': 'border-app-border',
    r'border-(gray|slate)-400': 'border-app-border-active',
    r'border-(blue|indigo)-500': 'border-app-primary',
    r'border-(blue|indigo)-600': 'border-app-primary',
    r'border-blue-200': 'border-app-primary-ring',
    r'border-blue-100': 'border-app-primary-light',

    # Rings
    r'ring-(blue|indigo)-500': 'ring-app-primary',
    r'ring-(blue|indigo)-200': 'ring-app-primary-ring',
}

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
        
    for pattern, replacement in mapping.items():
        # Match word boundaries to prevent partial matches like text-gray-50000
        content = re.sub(r'\b' + pattern + r'\b', replacement, content)
        
    with open(filepath, 'w') as f:
        f.write(content)

for root, dirs, files in os.walk('src'):
    for file in files:
        if file.endswith('.jsx') or file.endswith('.js'):
            process_file(os.path.join(root, file))

print("Done refactoring colors!")
