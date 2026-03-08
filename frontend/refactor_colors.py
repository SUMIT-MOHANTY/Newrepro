import os
import re

# Comprehensive mapping of Tailwind colors to App Design System variables
# This will try to match colors with optional prefixes (text-, bg-, border-, from-, via-, to-, ring-, divide-)
# and optional opacities (e.g. /10, /20)
color_map = {
    # Main backgrounds and surfaces
    r'(?:gray|slate|zinc)-50': 'app-bg-page',
    r'(?:gray|slate|zinc)-100': 'app-bg-muted',
    r'(?:gray|slate|zinc)-200': 'app-bg-hover',
    r'(?:gray|slate|zinc)-300': 'app-bg-hover', # Collapsing 300 into hover for better dark mode consistency
    r'white': 'app-bg-card',
    
    # Text colors
    r'(?:gray|slate|zinc)-9[05]0': 'app-text-main',
    r'(?:gray|slate|zinc)-[8]00': 'app-text-main',
    r'(?:gray|slate|zinc)-[67]00': 'app-text-label',
    r'(?:gray|slate|zinc)-500': 'app-text-muted',
    r'(?:gray|slate|zinc)-400': 'app-text-light',
    r'(?:gray|slate|zinc)-300': 'app-border', # Text 300 is usually used as a border-like text
    
    # Primary / Active / Indigo / Blue
    r'(?:blue|indigo)-600': 'app-primary',
    r'(?:blue|indigo)-700': 'app-primary-hover',
    r'(?:blue|indigo)-500': 'app-primary', # indigo-500 usually maps to primary
    r'(?:blue|indigo)-50': 'app-primary-light',
    r'(?:blue|indigo)-100': 'app-primary-light',
    r'(?:blue|indigo)-200': 'app-primary-ring',
    r'(?:blue|indigo)-800': 'app-primary-dark',
    r'(?:blue|indigo)-900': 'app-primary-dark',
    
    # Statuses
    r'(?:red|rose)-[567]00': 'app-status-error',
    r'(?:red|rose)-[5]0': 'app-status-errorBg',
    r'(?:red|rose)-[1]00': 'app-status-errorBg',
    r'(?:green|emerald)-[567]00': 'app-status-success',
    r'(?:green|emerald)-[5]0': 'app-status-successBg',
    r'(?:green|emerald)-[1]00': 'app-status-successBg',
    r'(?:amber|yellow)-[567]00': 'app-status-warning',
    r'(?:amber|yellow)-[5]0': 'app-status-warningBg',
    r'(?:amber|yellow)-[1]00': 'app-status-warningBg',
}

prefixes = ['text-', 'bg-', 'border-', 'from-', 'via-', 'to-', 'ring-', 'divide-', 'shadow-']

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace common patterns
    for tailwind_color, app_var in color_map.items():
        for prefix in prefixes:
            # Match prefix + color + optional opacity (e.g. bg-white/90)
            # Use regex to match \bprefix tailwind_color (?P<opacity>/\d+)? \b
            pattern = r'\b' + prefix + tailwind_color + r'(?P<opacity>/\d+)?\b'
            
            def replace_func(match):
                opacity = match.group('opacity') if match.group('opacity') else ""
                return prefix + app_var + opacity
            
            content = re.sub(pattern, replace_func, content)

    # Special case for some hardcoded styles in Sidebar and others
    content = content.replace('bg-blue-900/40', 'bg-app-primary-dark/40')
    content = content.replace('bg-indigo-900/40', 'bg-app-primary-dark/40')
    content = content.replace('border-blue-800', 'border-app-border')
    content = content.replace('border-indigo-800', 'border-app-border')
    content = content.replace('text-blue-100', 'text-app-text-light')
    content = content.replace('text-indigo-100', 'text-app-text-light')

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

for root, dirs, files in os.walk('src'):
    for file in files:
        if file.endswith('.jsx') or file.endswith('.js'):
            process_file(os.path.join(root, file))

print("Done comprehensive color refactoring!")

