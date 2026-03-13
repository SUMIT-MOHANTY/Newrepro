"""
Runtime detector for auto-detecting web frameworks and runtimes
Supports: Python, JavaScript/Node.js, Java, C/C++, React, Next.js, HTML, and more
"""
import re

class RuntimeDetector:
    """Detects runtime/framework from code and provides configuration"""
    
    def __init__(self):
        self.runtimes = {
            # ===== PYTHON FRAMEWORKS =====
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
            'python-basic': {
                'image': 'vibecoding-python-executor:latest',
                'port': 8000,
                'filename': 'app.py',
                'patterns': [
                    r'import ',
                    r'def ',
                    r'print\(',
                ]
            },
            
            # ===== JAVASCRIPT/NODE.JS =====
            'nodejs-express': {
                'image': 'vibecoding-nodejs-executor:latest',
                'port': 3000,
                'filename': 'server.js',
                'patterns': [
                    r'require\([\'"]express[\'"]\)',
                    r'import.*express',
                    r'app\.listen\(',
                ]
            },
            'nodejs-nextjs': {
                'image': 'vibecoding-nodejs-executor:latest',
                'port': 3000,
                'filename': 'pages/index.js',
                'patterns': [
                    r'from [\'"]next',
                    r'import.*next',
                    r'getServerSideProps',
                    r'getStaticProps',
                ]
            },
            'react': {
                'image': 'vibecoding-nodejs-executor:latest',
                'port': 3000,
                'filename': 'App.jsx',
                'patterns': [
                    r'import.*React',
                    r'from [\'"]react[\'"]',
                    r'useState',
                    r'useEffect',
                    r'ReactDOM',
                ]
            },
            'nodejs-basic': {
                'image': 'vibecoding-nodejs-executor:latest',
                'port': 3000,
                'filename': 'index.js',
                'patterns': [
                    r'require\(',
                    r'module\.exports',
                    r'console\.log',
                ]
            },
            
            # ===== JAVA =====
            'java-spring': {
                'image': 'vibecoding-java-executor:latest',
                'port': 8080,
                'filename': 'Application.java',
                'patterns': [
                    r'@SpringBootApplication',
                    r'import org\.springframework',
                    r'@RestController',
                    r'@Controller',
                ]
            },
            'java-basic': {
                'image': 'vibecoding-java-executor:latest',
                'port': 8080,
                'filename': 'Main.java',
                'patterns': [
                    r'public class',
                    r'public static void main',
                    r'System\.out\.println',
                ]
            },
            
            # ===== C/C++ =====
            'cpp': {
                'image': 'vibecoding-cpp-executor:latest',
                'port': 8080,
                'filename': 'main.cpp',
                'patterns': [
                    r'#include <iostream>',
                    r'std::cout',
                    r'int main\(',
                ]
            },
            'c': {
                'image': 'vibecoding-c-executor:latest',
                'port': 8080,
                'filename': 'main.c',
                'patterns': [
                    r'#include <stdio\.h>',
                    r'printf\(',
                    r'int main\(',
                ]
            },
            
            # ===== GO =====
            'golang': {
                'image': 'vibecoding-go-executor:latest',
                'port': 8080,
                'filename': 'main.go',
                'patterns': [
                    r'package main',
                    r'import "fmt"',
                    r'func main\(',
                ]
            },
            
            # ===== RUST =====
            'rust': {
                'image': 'vibecoding-rust-executor:latest',
                'port': 8080,
                'filename': 'main.rs',
                'patterns': [
                    r'fn main\(',
                    r'println!',
                    r'use std::',
                ]
            },
            
            # ===== PHP =====
            'php': {
                'image': 'vibecoding-php-executor:latest',
                'port': 8000,
                'filename': 'index.php',
                'patterns': [
                    r'<\?php',
                    r'\$_GET',
                    r'\$_POST',
                    r'echo ',
                ]
            },
            
            # ===== RUBY =====
            'ruby-rails': {
                'image': 'vibecoding-ruby-executor:latest',
                'port': 3000,
                'filename': 'app.rb',
                'patterns': [
                    r'require [\'"]rails[\'"]',
                    r'Rails\.application',
                ]
            },
            'ruby-sinatra': {
                'image': 'vibecoding-ruby-executor:latest',
                'port': 4567,
                'filename': 'app.rb',
                'patterns': [
                    r'require [\'"]sinatra[\'"]',
                    r'get [\'"]/',
                ]
            },
            
            # ===== STATIC FILES =====
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
        
        # Priority order: Check specific frameworks first, then generic languages
        priority_order = [
            # Python frameworks (most specific first)
            'python-streamlit', 'python-fastapi', 'python-django', 'python-flask',
            # JavaScript frameworks
            'nodejs-nextjs', 'react', 'nodejs-express',
            # Java frameworks
            'java-spring',
            # Ruby frameworks
            'ruby-rails', 'ruby-sinatra',
            # Generic languages
            'golang', 'rust', 'php', 'cpp', 'c', 'java-basic', 'nodejs-basic', 'python-basic',
        ]
        
        # Check priority runtimes first
        for runtime_name in priority_order:
            if runtime_name not in self.runtimes:
                continue
            config = self.runtimes[runtime_name]
            for pattern in config['patterns']:
                if re.search(pattern, code, re.IGNORECASE):
                    return runtime_name, config
        
        # Check if it's HTML/CSS/JS static content
        if '<html' in code_lower or '<!doctype html' in code_lower:
            return 'static-html', self.runtimes['static-html']
        
        # Default to Python Flask (most common for quick prototypes)
        return 'python-flask', self.runtimes['python-flask']
    
    def get_filename(self, runtime_name: str) -> str:
        """Get the default filename for a runtime"""
        return self.runtimes.get(runtime_name, {}).get('filename', 'app.py')

# Global instance
runtime_detector = RuntimeDetector()
