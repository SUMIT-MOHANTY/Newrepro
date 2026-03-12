"""
Runtime detector for auto-detecting web frameworks and runtimes
"""
import re

class RuntimeDetector:
    """Detects runtime/framework from code and provides configuration"""
    
    def __init__(self):
        self.runtimes = {
            'python-flask': {
                'image': 'vibecoding-python-executor:latest',
                'port': 5000,
                'filename': 'app.py',
                'patterns': [
                    r'from flask import',
                    r'import flask',
                    r'Flask\(',
                ]
            },
            'python-django': {
                'image': 'vibecoding-python-executor:latest',
                'port': 8000,
                'filename': 'app.py',
                'patterns': [
                    r'from django',
                    r'import django',
                    r'django\.setup\(',
                ]
            },
            'python-fastapi': {
                'image': 'vibecoding-python-executor:latest',
                'port': 8000,
                'filename': 'main.py',
                'patterns': [
                    r'from fastapi import',
                    r'import fastapi',
                    r'FastAPI\(',
                ]
            },
            'python-streamlit': {
                'image': 'vibecoding-python-executor:latest',
                'port': 8501,
                'filename': 'app.py',
                'patterns': [
                    r'import streamlit',
                    r'streamlit\.',
                ]
            },
            'static-html': {
                'image': 'vibecoding-code-executor:latest',
                'port': 80,
                'filename': 'index.html',
                'patterns': []
            }
        }
    
    def detect(self, code: str) -> tuple:
        """
        Detect runtime from code
        Returns: (runtime_name, runtime_config)
        """
        code_lower = code.lower()
        
        # Check each runtime pattern
        for runtime_name, config in self.runtimes.items():
            if runtime_name == 'static-html':
                continue  # Skip static HTML for now
            
            for pattern in config['patterns']:
                if re.search(pattern, code, re.IGNORECASE):
                    return runtime_name, config
        
        # Check if it's HTML
        if '<html' in code_lower or '<!doctype html' in code_lower:
            return 'static-html', self.runtimes['static-html']
        
        # Default to Python Flask
        return 'python-flask', self.runtimes['python-flask']
    
    def get_filename(self, runtime_name: str) -> str:
        """Get the default filename for a runtime"""
        return self.runtimes.get(runtime_name, {}).get('filename', 'app.py')

# Global instance
runtime_detector = RuntimeDetector()
