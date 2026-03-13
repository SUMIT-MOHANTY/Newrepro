"""
Runtime detector for auto-detecting web frameworks and runtimes
Supports: Python, JavaScript/Node.js, Java, C/C++, React, Next.js, HTML, and more
"""
import re

class RuntimeDetector:
    """Detects runtime/framework from code and provides configuration"""
    
    def __init__(self):
        # Single intelligent agent runtime for ALL projects
        # Use consistent port 5000 for all Python apps, 3000 for Node.js
        self.agent_runtime = {
            'image': 'vibecoding-agent-runtime:latest',
            'port': 5000,  # Default port
        }
        
        # Detection patterns (for logging/metadata only)
        self.patterns = {
            'python-django': [r'from django', r'import django', r'manage\.py'],
            'python-flask': [r'from flask import', r'import flask', r'Flask\('],
            'python-fastapi': [r'from fastapi import', r'FastAPI\('],
            'python-streamlit': [r'import streamlit', r'streamlit\.'],
            'nodejs-express': [r'require\([\'"]express[\'"]\)', r'import.*express'],
            'nodejs-nextjs': [r'from [\'"]next', r'getServerSideProps'],
            'react': [r'import.*React', r'from [\'"]react[\'"]', r'useState'],
            'static-html': [r'<html', r'<!doctype html'],
        }
        
        # All Python frameworks use port 5000, all Node.js use port 3000
        self.runtimes = {
            'python-django': {'image': 'vibecoding-agent-runtime:latest', 'port': 5000},
            'python-flask': {'image': 'vibecoding-agent-runtime:latest', 'port': 5000},
            'python-fastapi': {'image': 'vibecoding-agent-runtime:latest', 'port': 5000},
            'python-streamlit': {'image': 'vibecoding-agent-runtime:latest', 'port': 8501},
            'python-basic': {'image': 'vibecoding-agent-runtime:latest', 'port': 5000},
            'nodejs-express': {'image': 'vibecoding-agent-runtime:latest', 'port': 3000},
            'nodejs-nextjs': {'image': 'vibecoding-agent-runtime:latest', 'port': 3000},
            'react': {'image': 'vibecoding-agent-runtime:latest', 'port': 3000},
            'nodejs-basic': {'image': 'vibecoding-agent-runtime:latest', 'port': 3000},
            'static-html': {'image': 'vibecoding-agent-runtime:latest', 'port': 5000},
        }
    
    def detect(self, code: str) -> tuple:
        """
        Detect runtime from code (for metadata only - agent handles actual execution)
        Returns: (runtime_name, runtime_config)
        """
        code_lower = code.lower()
        
        # Priority order
        priority_order = [
            'python-django', 'python-flask', 'python-fastapi', 'python-streamlit',
            'nodejs-nextjs', 'react', 'nodejs-express',
            'static-html', 'python-basic', 'nodejs-basic'
        ]
        
        # Check patterns
        for runtime_name in priority_order:
            if runtime_name not in self.patterns:
                continue
            for pattern in self.patterns[runtime_name]:
                if re.search(pattern, code, re.IGNORECASE):
                    return runtime_name, self.runtimes[runtime_name]
        
        # Default to agent runtime
        return 'python-basic', self.agent_runtime
    
    def get_filename(self, runtime_name: str) -> str:
        """Get the default filename for a runtime"""
        return self.runtimes.get(runtime_name, {}).get('filename', 'app.py')

# Global instance
runtime_detector = RuntimeDetector()
