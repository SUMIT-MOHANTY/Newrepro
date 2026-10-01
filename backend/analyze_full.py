import os
import ast
import json

def get_endpoints(file_path):
    endpoints = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    for decorator in node.decorator_list:
                        if isinstance(decorator, ast.Call) and getattr(decorator.func, 'attr', None) in ['get', 'post', 'put', 'delete', 'patch']:
                            method = decorator.func.attr
                            path = ''
                            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                                path = decorator.args[0].value
                            endpoints.append({'file': file_path, 'method': method.upper(), 'path': path, 'func': node.name})
    except Exception as e:
        pass
    return endpoints

backend_dir = r'd:\BRD Analyzer\BRD_Analyzer\backend'
all_endpoints = []
for root, _, files in os.walk(backend_dir):
    if 'venv' in root or 'node_modules' in root or '__pycache__' in root:
        continue
    for file in files:
        if file.endswith('.py'):
            all_endpoints.extend(get_endpoints(os.path.join(root, file)))

with open(r'C:\Users\AbhishekPattnayak\.gemini\antigravity\brain\c7082374-268e-4d68-b711-2305b0f3c6ad\endpoints_report_full.json', 'w') as f:
    json.dump(all_endpoints, f, indent=2)
