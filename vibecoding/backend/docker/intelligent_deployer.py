#!/usr/bin/env python3
"""
Intelligent Deployer - Universal AI-powered build and deployment system
Works with ANY tech stack by analyzing errors and asking AI to fix them
"""

import re
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

class IntelligentDeployer:
    """
    Universal deployer that:
    1. Attempts to build/deploy the application
    2. If errors occur, extracts error details
    3. Asks AI to analyze and fix the errors
    4. Retries deployment with fixes
    5. Repeats until success or max retries
    """
    
    def __init__(self, workspace_dir: Path, ai_caller, max_retries: int = 5):
        self.workspace_dir = Path(workspace_dir)
        self.ai_caller = ai_caller
        self.max_retries = max_retries
        self.error_history = []
        
    def extract_error_context(self, error_output: str, exit_code: int) -> Dict[str, Any]:
        """
        Extract meaningful error information from build/runtime output
        Works for any language/framework
        """
        context = {
            'exit_code': exit_code,
            'raw_output': error_output,
            'error_type': 'unknown',
            'missing_dependencies': [],
            'syntax_errors': [],
            'import_errors': [],
            'file_errors': [],
            'suggestions': []
        }
        
        lines = error_output.split('\n')
        
        # Detect error patterns (language-agnostic)
        for line in lines:
            line_lower = line.lower()
            
            # Missing dependencies/modules
            if any(keyword in line_lower for keyword in [
                'cannot find module', 'module not found', 'no module named',
                'failed to resolve import', 'cannot resolve', 'unresolved',
                'package not found', 'dependency', 'not installed'
            ]):
                context['error_type'] = 'missing_dependency'
                # Extract package name
                match = re.search(r"['\"]([^'\"]+)['\"]", line)
                if match:
                    context['missing_dependencies'].append(match.group(1))
            
            # Syntax errors
            elif any(keyword in line_lower for keyword in [
                'syntaxerror', 'syntax error', 'unexpected token',
                'parse error', 'invalid syntax'
            ]):
                context['error_type'] = 'syntax_error'
                context['syntax_errors'].append(line.strip())
            
            # Import/require errors
            elif any(keyword in line_lower for keyword in [
                'import error', 'importerror', 'cannot import'
            ]):
                context['error_type'] = 'import_error'
                context['import_errors'].append(line.strip())
            
            # File not found errors
            elif any(keyword in line_lower for keyword in [
                'no such file', 'file not found', 'enoent', 'cannot find'
            ]):
                context['error_type'] = 'file_error'
                context['file_errors'].append(line.strip())
            
            # Port/network errors
            elif any(keyword in line_lower for keyword in [
                'eaddrinuse', 'address already in use', 'port', 'bind'
            ]):
                context['error_type'] = 'port_conflict'
            
            # Permission errors
            elif any(keyword in line_lower for keyword in [
                'eacces', 'permission denied', 'access denied'
            ]):
                context['error_type'] = 'permission_error'
        
        return context
    
    def create_fix_prompt(self, error_context: Dict[str, Any], attempt: int) -> str:
        """
        Create an AI prompt to analyze and fix the error
        Framework-agnostic - AI figures out the tech stack
        """
        prompt = f"""# Build/Deployment Error - Fix Required (Attempt {attempt}/{self.max_retries})

## Error Information
- **Exit Code**: {error_context['exit_code']}
- **Error Type**: {error_context['error_type']}

## Error Output
```
{error_context['raw_output'][-2000:]}  # Last 2000 chars
```

## Your Task
Analyze the error above and provide SPECIFIC fixes to resolve it.

### Instructions:
1. **Identify the root cause** of the error
2. **Determine what needs to be fixed**:
   - Missing dependencies? → Provide exact package names and versions
   - Syntax errors? → Provide corrected code
   - Missing files? → Provide file content
   - Configuration issues? → Provide correct config
3. **Provide fixes in this EXACT format**:

```json
{{
  "analysis": "Brief explanation of what went wrong",
  "fix_type": "dependency|code|config|file",
  "fixes": [
    {{
      "action": "install_package|modify_file|create_file|delete_file",
      "target": "package-name or file-path",
      "content": "package version or file content or code changes",
      "reason": "why this fix is needed"
    }}
  ],
  "confidence": "high|medium|low"
}}
```

### Examples:

**Missing Dependency:**
```json
{{
  "analysis": "Build failed because 'recharts' package is imported but not installed",
  "fix_type": "dependency",
  "fixes": [
    {{
      "action": "install_package",
      "target": "recharts",
      "content": "^2.10.0",
      "reason": "Used in LineChart.jsx for data visualization"
    }}
  ],
  "confidence": "high"
}}
```

**Code Error:**
```json
{{
  "analysis": "Syntax error in App.jsx - missing closing brace",
  "fix_type": "code",
  "fixes": [
    {{
      "action": "modify_file",
      "target": "src/App.jsx",
      "content": "<<<SEARCH\\nfunction App() {{\\n  return (\\n>>>\\n<<<REPLACE\\nfunction App() {{\\n  return (\\n  );\\n}}\\n>>>",
      "reason": "Add missing closing brace and parenthesis"
    }}
  ],
  "confidence": "high"
}}
```

**Missing File:**
```json
{{
  "analysis": "Build expects index.html but it doesn't exist",
  "fix_type": "file",
  "fixes": [
    {{
      "action": "create_file",
      "target": "index.html",
      "content": "<!DOCTYPE html>\\n<html>\\n<head>...</head>\\n<body>...</body>\\n</html>",
      "reason": "Entry point for the application"
    }}
  ],
  "confidence": "high"
}}
```

## IMPORTANT:
- Be SPECIFIC - provide exact package names, versions, file paths
- If multiple issues, provide ALL fixes in the fixes array
- Use SEARCH/REPLACE format for code modifications
- Return ONLY valid JSON, no extra text
"""
        return prompt
    
    def apply_fixes(self, fixes_json: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Apply the fixes suggested by AI
        Returns: (success, message)
        """
        if not fixes_json or 'fixes' not in fixes_json:
            return False, "No fixes provided by AI"
        
        fixes = fixes_json['fixes']
        applied = []
        errors = []
        
        for fix in fixes:
            action = fix.get('action')
            target = fix.get('target')
            content = fix.get('content')
            reason = fix.get('reason', '')
            
            try:
                if action == 'install_package':
                    # Install npm/pip/etc package
                    success, msg = self._install_package(target, content)
                    if success:
                        applied.append(f"✅ Installed {target}@{content}")
                    else:
                        errors.append(f"❌ Failed to install {target}: {msg}")
                
                elif action == 'modify_file':
                    # Modify existing file using SEARCH/REPLACE
                    success, msg = self._modify_file(target, content)
                    if success:
                        applied.append(f"✅ Modified {target}")
                    else:
                        errors.append(f"❌ Failed to modify {target}: {msg}")
                
                elif action == 'create_file':
                    # Create new file
                    success, msg = self._create_file(target, content)
                    if success:
                        applied.append(f"✅ Created {target}")
                    else:
                        errors.append(f"❌ Failed to create {target}: {msg}")
                
                elif action == 'delete_file':
                    # Delete file
                    success, msg = self._delete_file(target)
                    if success:
                        applied.append(f"✅ Deleted {target}")
                    else:
                        errors.append(f"❌ Failed to delete {target}: {msg}")
                
                else:
                    errors.append(f"❌ Unknown action: {action}")
            
            except Exception as e:
                errors.append(f"❌ Error applying fix: {e}")
        
        if errors:
            return False, '\n'.join(errors)
        
        return True, '\n'.join(applied)
    
    def _install_package(self, package: str, version: str) -> Tuple[bool, str]:
        """Install a package (auto-detects package manager)"""
        # Detect package manager
        if (self.workspace_dir / 'package.json').exists():
            # Node.js project
            cmd = ['npm', 'install', f'{package}@{version}']
        elif (self.workspace_dir / 'requirements.txt').exists():
            # Python project
            cmd = ['pip', 'install', f'{package}=={version}']
        elif (self.workspace_dir / 'Gemfile').exists():
            # Ruby project
            cmd = ['bundle', 'add', package, '--version', version]
        elif (self.workspace_dir / 'go.mod').exists():
            # Go project
            cmd = ['go', 'get', f'{package}@{version}']
        else:
            return False, "Could not detect package manager"
        
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.workspace_dir),
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                return True, f"Installed {package}@{version}"
            else:
                return False, result.stderr
        
        except Exception as e:
            return False, str(e)
    
    def _modify_file(self, file_path: str, content: str) -> Tuple[bool, str]:
        """Modify file using SEARCH/REPLACE pattern"""
        target = self.workspace_dir / file_path
        
        if not target.exists():
            return False, f"File not found: {file_path}"
        
        try:
            # Parse SEARCH/REPLACE blocks
            search_match = re.search(r'<<<SEARCH\n(.*?)\n>>>', content, re.DOTALL)
            replace_match = re.search(r'<<<REPLACE\n(.*?)\n>>>', content, re.DOTALL)
            
            if not search_match or not replace_match:
                # Direct content replacement
                target.write_text(content, encoding='utf-8')
                return True, f"Replaced content in {file_path}"
            
            search_text = search_match.group(1)
            replace_text = replace_match.group(1)
            
            file_content = target.read_text(encoding='utf-8')
            
            if search_text not in file_content:
                return False, f"Search pattern not found in {file_path}"
            
            new_content = file_content.replace(search_text, replace_text)
            target.write_text(new_content, encoding='utf-8')
            
            return True, f"Modified {file_path}"
        
        except Exception as e:
            return False, str(e)
    
    def _create_file(self, file_path: str, content: str) -> Tuple[bool, str]:
        """Create a new file"""
        target = self.workspace_dir / file_path
        
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
            return True, f"Created {file_path}"
        
        except Exception as e:
            return False, str(e)
    
    def _delete_file(self, file_path: str) -> Tuple[bool, str]:
        """Delete a file"""
        target = self.workspace_dir / file_path
        
        try:
            if target.exists():
                target.unlink()
                return True, f"Deleted {file_path}"
            else:
                return True, f"File already deleted: {file_path}"
        
        except Exception as e:
            return False, str(e)
    
    def deploy_with_ai_fixes(self, build_command: str, report_func=None) -> Tuple[bool, str]:
        """
        Main deployment loop with AI-powered error fixing
        
        Args:
            build_command: Command to build/deploy (e.g., "npm run build")
            report_func: Optional function to report progress to user
        
        Returns:
            (success, message)
        """
        def report(msg):
            if report_func:
                report_func(msg)
            print(msg)
        
        for attempt in range(1, self.max_retries + 1):
            report(f"🚀 Deployment attempt {attempt}/{self.max_retries}...")
            
            # Try to build/deploy
            try:
                result = subprocess.run(
                    build_command.split(),
                    cwd=str(self.workspace_dir),
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                if result.returncode == 0:
                    report(f"✅ Deployment successful on attempt {attempt}!")
                    return True, "Deployment successful"
                
                # Build failed - extract error context
                error_output = result.stderr + result.stdout
                error_context = self.extract_error_context(error_output, result.returncode)
                
                report(f"❌ Build failed: {error_context['error_type']}")
                
                # Ask AI to fix the error
                report(f"🤖 Asking AI to analyze and fix the error...")
                
                fix_prompt = self.create_fix_prompt(error_context, attempt)
                
                messages = [
                    {"role": "system", "content": "You are an expert developer who fixes build and deployment errors. Always respond with valid JSON."},
                    {"role": "user", "content": fix_prompt}
                ]
                
                ai_response = self.ai_caller(messages, temperature=0.1, show_thinking=False)
                
                # Parse AI response
                try:
                    # Extract JSON from response (handle markdown code blocks)
                    json_match = re.search(r'```json\n(.*?)\n```', ai_response, re.DOTALL)
                    if json_match:
                        fixes_json = json.loads(json_match.group(1))
                    else:
                        fixes_json = json.loads(ai_response)
                    
                    report(f"💡 AI Analysis: {fixes_json.get('analysis', 'No analysis')}")
                    report(f"🔧 Applying {len(fixes_json.get('fixes', []))} fix(es)...")
                    
                    # Apply fixes
                    success, message = self.apply_fixes(fixes_json)
                    
                    if success:
                        report(f"✅ Fixes applied:\n{message}")
                    else:
                        report(f"⚠️ Some fixes failed:\n{message}")
                    
                    # Store error history
                    self.error_history.append({
                        'attempt': attempt,
                        'error': error_context,
                        'fixes': fixes_json,
                        'applied': success
                    })
                
                except json.JSONDecodeError as e:
                    report(f"⚠️ AI response was not valid JSON: {e}")
                    report(f"AI Response: {ai_response[:500]}")
                    continue
            
            except subprocess.TimeoutExpired:
                report(f"⏱️ Build timed out after 5 minutes")
                return False, "Build timeout"
            
            except Exception as e:
                report(f"❌ Unexpected error: {e}")
                return False, str(e)
        
        # Max retries reached
        report(f"❌ Deployment failed after {self.max_retries} attempts")
        return False, f"Failed after {self.max_retries} attempts"


# Integration function for ai-agent.py
def deploy_with_intelligent_fixer(workspace_dir: Path, ai_caller, report_func) -> bool:
    """
    Wrapper function to integrate with existing ai-agent.py
    
    Usage in ai-agent.py:
        from intelligent_deployer import deploy_with_intelligent_fixer
        success = deploy_with_intelligent_fixer(WORKSPACE_DIR, call_ai, report)
    """
    deployer = IntelligentDeployer(workspace_dir, ai_caller, max_retries=5)
    
    # Auto-detect build command
    package_json = workspace_dir / 'package.json'
    if package_json.exists():
        build_cmd = 'npm run build'
    else:
        # Try other common build commands
        build_cmd = 'make build'
    
    success, message = deployer.deploy_with_ai_fixes(build_cmd, report_func)
    return success
