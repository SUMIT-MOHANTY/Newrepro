#!/usr/bin/env python3
"""
🤖 VibeCoding Autonomous Agent v4
===================================
Two-phase agent:
  Phase 1 — CODE GENERATION: Call AI to generate app files into /project/workspace
  Phase 2 — DEPLOYMENT:      Detect stack, install deps, build, start server, configure Nginx

Self-healing watchdog monitors Nginx error logs and re-runs Phase 2 on failures.
Mailbox at /tmp/vibe_prompt accepts new user instructions at any time.
All user-facing messages are written in plain, friendly language.
"""

import os
import sys
import json
import time
import re
import signal
import sqlite3
import uuid
import subprocess
import requests
import threading
import queue
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

# Import task-based development modules
from task_planner import TaskPlanner, Task
from task_executor import TaskExecutor
from task_executor import TaskExecutor

# ── Configuration ─────────────────────────────────────────────────────────────
PROJECT_DIR   = Path(os.environ.get('PROJECT_DIR', '/project'))
WORKSPACE_DIR = PROJECT_DIR / 'workspace'
DB_PATH       = '/tmp/vibecoding_users.db'
NGINX_CONF    = '/etc/nginx/sites-available/default'
PROJECT_ID    = os.environ.get('PROJECT_ID', 'default')

# AI Configuration with USE_BRN_LLAMA support (DSuite-style)
def _is_brn_llama_enabled():
    use_brn = os.environ.get('USE_BRN_LLAMA', 'false').lower().strip()
    return use_brn in ('true', '1', 'yes')

if _is_brn_llama_enabled():
    # BRN Llama configuration
    API_KEY     = os.environ.get('BRN_AGENT_ID', '')
    API_URL     = os.environ.get('BRN_LLAMA_URL', 'https://brn-llama.bourntec.com/api/process')
    AI_MODEL    = os.environ.get('BRN_MODEL', 'BournAI')
    AI_PROVIDER = 'bournai'
else:
    # OpenAI-compatible configuration (NVIDIA, OpenAI, etc.)
    API_KEY     = os.environ.get('AI_API_KEY', '')
    API_URL     = os.environ.get('AI_BASE_URL') or os.environ.get('AI_API_URL', 'https://integrate.api.nvidia.com/v1/chat/completions')
    AI_MODEL    = os.environ.get('AI_MODEL', 'openai/gpt-4.1')
    AI_PROVIDER = os.environ.get('AI_PROVIDER', 'openai').lower().strip()

NGINX_ERROR_LOG = '/var/log/nginx/error.log'
MAILBOX         = Path('/tmp/vibe_prompt')


# ── Logging ────────────────────────────────────────────────────────────────────
def log(msg: str):
    print(f'🛠️  [Agent] {msg}', flush=True)


def _get_db(timeout: int = 15):
    """Get a robust DB connection with WAL mode enabled."""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=timeout)
        conn.row_factory = sqlite3.Row
        # Always try to enable WAL - it improves performance and prevents some locks
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except:
            pass
        return conn
    except Exception as e:
        log(f"DB Connection failed: {e}")
        return None


def report(msg: str, code: str = None, suggestions: list = None, metadata: dict = None, summary: str = None, message_type: str = None):
    """
    Persist a user-facing message to the host SQLite DB with rich context.
    
    Args:
        msg: Main message content
        code: Code snippet or error output
        suggestions: List of actionable suggestions for the user
        metadata: Additional structured data (status, progress, etc.)
        summary: Short summary for UI display
        message_type: Type of message (status, question, error, success, thinking, action)
    """
    clean = str(msg).strip()
    print(f'\n💬 {clean}', flush=True)

    if not os.path.exists(DB_PATH):
        return
        
    conn = _get_db()
    if not conn:
        return
    
    # Build metadata
    meta = metadata or {}
    if message_type:
        meta['type'] = message_type
    
    # Auto-detect message type from emoji if not provided
    if not message_type:
        if clean.startswith('❓'):
            meta['type'] = 'question'
            meta['requires_response'] = True
        elif clean.startswith('✅'):
            meta['type'] = 'success'
        elif clean.startswith('⚠️') or clean.startswith('❌'):
            meta['type'] = 'error'
        elif clean.startswith('🔧') or clean.startswith('📦'):
            meta['type'] = 'action'
        elif clean.startswith('💡'):
            meta['type'] = 'thinking'
        elif clean.startswith('🎉'):
            meta['type'] = 'celebration'
        else:
            meta['type'] = 'status'
    
    # Generate suggestions if this is an error or question
    if meta.get('type') in ['error', 'question'] and not suggestions:
        suggestions = _generate_contextual_suggestions(clean, code)
    
    # Generate summary if not provided
    if not summary:
        summary = _generate_summary(clean)
    
    try:
        conn.execute(
            """INSERT INTO messages
               (id, project_id, container_id, role, content, code, version_id,
                timestamp, suggestions, tool_calls, image_paths, metadata, summary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (f'agent_{int(time.time())}_{uuid.uuid4().hex[:4]}',
             PROJECT_ID, 'vibecoding-ai-agent', 'assistant',
             clean, code, None,
             datetime.now().isoformat(),
             json.dumps(suggestions) if suggestions else None,
             None, None,
             json.dumps(meta) if meta else None,
             summary)
        )
        conn.commit()
    except Exception as e:
        print(f'DEBUG: DB write failed: {e}', flush=True)
    finally:
        try:
            conn.close()
        except:
            pass


def _generate_contextual_suggestions(message: str, code: str = None) -> list:
    """Generate actionable suggestions based on the message context."""
    suggestions = []
    
    msg_lower = message.lower()
    
    # Error-specific suggestions
    if 'syntax error' in msg_lower or 'syntaxerror' in msg_lower:
        suggestions.append({
            'text': 'Review the syntax error and send me the corrected code',
            'action': 'edit_code',
            'icon': '✏️'
        })
        suggestions.append({
            'text': 'Let me try to auto-fix the syntax error',
            'action': 'auto_fix',
            'icon': '🔧',
            'prompt': 'Fix the syntax error automatically'
        })
    
    elif 'command not found' in msg_lower or 'exit 127' in msg_lower:
        suggestions.append({
            'text': 'Install missing dependencies',
            'action': 'install_deps',
            'icon': '📦',
            'prompt': 'Install the missing dependencies'
        })
        suggestions.append({
            'text': 'Check the deployment script',
            'action': 'review_script',
            'icon': '🔍',
            'prompt': 'Review and fix the deployment script'
        })
    
    elif 'port' in msg_lower or '502' in msg_lower or 'connection' in msg_lower:
        suggestions.append({
            'text': 'Try a different port',
            'action': 'change_port',
            'icon': '🔌',
            'prompt': 'Use a different port for the application'
        })
        suggestions.append({
            'text': 'Check if the app is running',
            'action': 'check_status',
            'icon': '🔍',
            'prompt': 'Check the application status and logs'
        })
    
    elif 'test' in msg_lower and 'fail' in msg_lower:
        suggestions.append({
            'text': 'Fix the failing tests',
            'action': 'fix_tests',
            'icon': '🔧',
            'prompt': 'Fix the code to make the tests pass'
        })
        suggestions.append({
            'text': 'Show me the test results',
            'action': 'show_tests',
            'icon': '📊',
            'prompt': 'Show detailed test results'
        })
        suggestions.append({
            'text': 'Skip tests for now',
            'action': 'skip_tests',
            'icon': '⏭️',
            'prompt': 'Skip the tests and deploy anyway'
        })
    
    # Question-specific suggestions
    elif message.startswith('❓'):
        suggestions.append({
            'text': 'Provide more details',
            'action': 'clarify',
            'icon': '💬',
            'prompt': None  # User will type their own response
        })
        suggestions.append({
            'text': 'Just fix it based on your analysis',
            'action': 'auto_decide',
            'icon': '🤖',
            'prompt': 'Fix it based on your best judgment'
        })
    
    # General suggestions
    if not suggestions:
        suggestions.append({
            'text': 'Try again',
            'action': 'retry',
            'icon': '🔄',
            'prompt': 'Try the deployment again'
        })
        suggestions.append({
            'text': 'Show me the logs',
            'action': 'show_logs',
            'icon': '📋',
            'prompt': 'Show me the detailed logs'
        })
    
    return suggestions


def _generate_summary(message: str) -> str:
    """Generate a short summary for UI display."""
    # Remove emoji
    clean = re.sub(r'[^\w\s\-.,!?]', '', message)
    
    # Truncate to first sentence or 100 chars
    sentences = re.split(r'[.!?]\s+', clean)
    if sentences:
        summary = sentences[0]
        if len(summary) > 100:
            summary = summary[:97] + '...'
        return summary
    
    return clean[:100]


def _generate_task_breakdown(user_prompt: str, existing_files: dict = None) -> str:
    """
    Use AI to generate a clear task breakdown of what will be done.
    Returns a formatted string with bullet points of tasks.
    """
    try:
        is_edit = bool(existing_files)
        
        if is_edit:
            # For edits, analyze what needs to change
            file_context = "\n".join([f"- {path}" for path in list(existing_files.keys())[:10]])
            breakdown_prompt = f"""The user wants to modify their existing application.

USER REQUEST: {user_prompt}

EXISTING FILES:
{file_context}

Generate a concise task breakdown (3-5 bullet points) of what you'll do to fulfill this request.
Format as bullet points, each starting with an action verb.
Keep it user-friendly and non-technical.

Example format:
• Update the color scheme to use blue tones
• Modify the navigation bar layout
• Add smooth transitions to buttons

Your breakdown:"""
        else:
            # For new projects, outline the structure
            breakdown_prompt = f"""The user wants to build a new application.

USER REQUEST: {user_prompt}

Generate a concise task breakdown (3-5 bullet points) of what you'll build.
Format as bullet points, each starting with an action verb.
Keep it user-friendly and non-technical.

Example format:
• Create a responsive landing page with hero section
• Build an interactive calculator with history
• Add dark mode styling with glassmorphism effects

Your breakdown:"""
        
        response = call_ai([
            {'role': 'system', 'content': 'You are a helpful assistant that creates clear, concise task breakdowns.'},
            {'role': 'user', 'content': breakdown_prompt}
        ], temperature=0.3, show_thinking=False)
        
        # Clean up the response
        breakdown = response.strip()
        
        # Ensure it's formatted as bullet points
        if not any(breakdown.startswith(prefix) for prefix in ['•', '-', '*', '1.', '2.']):
            # Convert to bullet points if not already
            lines = [line.strip() for line in breakdown.split('\n') if line.strip()]
            breakdown = '\n'.join([f'• {line}' for line in lines])
        
        return breakdown
    except Exception as e:
        log(f'Failed to generate task breakdown: {e}')
        # Fallback to generic message
        if is_edit:
            return '• Analyzing your request\n• Updating the necessary files\n• Applying changes to your app'
        else:
            return '• Planning the application structure\n• Creating the necessary files\n• Building your app'


def _generate_change_summary(user_prompt: str, files_written: list, patches_applied: int, is_edit: bool) -> str:
    """
    Use AI to generate a user-friendly summary of what was actually changed.
    Returns a formatted string describing the changes made.
    """
    try:
        if is_edit:
            summary_prompt = f"""The user requested: "{user_prompt}"

I just made the following changes:
- Modified {patches_applied} file(s) with targeted updates
- Created/updated {len(files_written)} file(s): {', '.join(files_written[:5])}

Generate a concise summary (2-4 bullet points) of what was ACTUALLY changed, written in past tense.
Focus on the functional/visual changes the user will see, not technical details.
Keep it user-friendly and celebratory.

Example format:
• Updated the button colors to match your brand
• Added smooth hover animations throughout
• Improved mobile responsiveness

Your summary:"""
        else:
            summary_prompt = f"""The user requested: "{user_prompt}"

I just created a new application with {len(files_written)} file(s): {', '.join(files_written[:5])}

Generate a concise summary (2-4 bullet points) of what was built, written in past tense.
Focus on the features and capabilities, not technical details.
Keep it user-friendly and exciting.

Example format:
• Built a responsive landing page with hero section
• Created an interactive calculator with history tracking
• Added dark mode styling with glassmorphism effects

Your summary:"""
        
        response = call_ai([
            {'role': 'system', 'content': 'You are a helpful assistant that creates clear, concise summaries of completed work.'},
            {'role': 'user', 'content': summary_prompt}
        ], temperature=0.3, show_thinking=False)
        
        # Clean up the response
        summary = response.strip()
        
        # Ensure it's formatted as bullet points
        if not any(summary.startswith(prefix) for prefix in ['•', '-', '*', '1.', '2.']):
            # Convert to bullet points if not already
            lines = [line.strip() for line in summary.split('\n') if line.strip()]
            summary = '\n'.join([f'• {line}' for line in lines])
        
        return summary
    except Exception as e:
        log(f'Failed to generate change summary: {e}')
        # Fallback to generic message
        if is_edit:
            return f'• Applied {patches_applied} targeted update(s)\n• Modified {len(files_written)} file(s)\n• Your changes are ready'
        else:
            return f'• Created {len(files_written)} file(s)\n• Built your application structure\n• Ready for deployment'


# ── Nginx helpers ──────────────────────────────────────────────────────────────
def nginx_reload() -> bool:
    t = subprocess.run(['/usr/sbin/nginx', '-t'], capture_output=True, text=True)
    if t.returncode != 0:
        log(f'Nginx config error: {t.stderr}')
        return False
    r = subprocess.run(['/usr/sbin/nginx', '-s', 'reload'], capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run('pkill -9 nginx || true', shell=True, capture_output=True)
        time.sleep(0.5)
        s = subprocess.run(['/usr/sbin/nginx'], capture_output=True, text=True)
        if s.returncode != 0:
            log(f'Nginx failed to start: {s.stderr}')
            return False
    return True


def write_nginx_config(conf: str) -> bool:
    """
    Write and validate nginx configuration.
    Automatically fixes common issues before applying.
    """
    # ═══════════════════════════════════════════════════════════════════
    # AUTO-FIX: Ensure all location blocks have proxy_pass or root/alias
    # ═══════════════════════════════════════════════════════════════════
    conf = _auto_fix_nginx_config(conf)
    
    Path(NGINX_CONF).parent.mkdir(parents=True, exist_ok=True)
    Path(NGINX_CONF).write_text(conf)
    subprocess.run('rm -f /etc/nginx/sites-enabled/*', shell=True)
    subprocess.run('rm -f /etc/nginx/conf.d/*.conf', shell=True)
    subprocess.run(f'ln -sf {NGINX_CONF} /etc/nginx/sites-enabled/default', shell=True)
    return nginx_reload()


def _validate_nginx_config(conf: str, app_port: int = None) -> list:
    """
    Validate nginx configuration for common issues.
    Returns list of issues found (empty if config is valid).
    """
    issues = []
    
    # Issue 1: Location blocks with caching but no proxy_pass/root/alias
    location_pattern = re.compile(
        r'location\s+[^{]+\{[^}]*?(?:expires|add_header\s+Cache-Control)[^}]*?\}',
        re.DOTALL
    )
    
    for match in location_pattern.finditer(conf):
        location_block = match.group(0)
        has_backend = any(keyword in location_block for keyword in ['proxy_pass', 'root ', 'alias '])
        
        if not has_backend:
            # Extract location path
            loc_match = re.search(r'location\s+([^{]+)\{', location_block)
            loc_path = loc_match.group(1).strip() if loc_match else 'unknown'
            issues.append(f'Location "{loc_path}" has caching headers but no proxy_pass/root/alias')
    
    # Issue 2: proxy_pass without required headers
    proxy_locations = re.finditer(
        r'location\s+[^{]+\{[^}]*?proxy_pass[^}]*?\}',
        conf,
        re.DOTALL
    )
    
    for match in proxy_locations:
        location_block = match.group(0)
        
        # Check for essential proxy headers
        if 'proxy_set_header Host' not in location_block:
            loc_match = re.search(r'location\s+([^{]+)\{', location_block)
            loc_path = loc_match.group(1).strip() if loc_match else 'unknown'
            issues.append(f'Location "{loc_path}" missing proxy_set_header Host')
    
    # Issue 3: No gzip compression
    if 'gzip on' not in conf and 'gzip_static on' not in conf:
        issues.append('Gzip compression not enabled')
    
    # Issue 4: App port mismatch
    if app_port:
        proxy_passes = re.findall(r'proxy_pass\s+http://[^:]+:(\d+)', conf)
        if proxy_passes:
            for port_str in proxy_passes:
                port = int(port_str)
                if port != app_port:
                    issues.append(f'Nginx proxies to port {port} but app uses port {app_port}')
    
    return issues


def _auto_fix_nginx_config(conf: str) -> str:
    """
    Automatically fix common nginx configuration issues:
    1. Location blocks missing proxy_pass/root/alias
    2. Static asset caching without proxy_pass
    3. Missing proxy headers
    
    Returns fixed configuration.
    """
    original_conf = conf
    fixes_applied = []
    
    # ═══════════════════════════════════════════════════════════════════
    # FIX 1: Static asset location blocks missing proxy_pass
    # ═══════════════════════════════════════════════════════════════════
    # Pattern: location block with caching headers but no proxy_pass/root/alias
    location_pattern = re.compile(
        r'(location\s+[^{]+\{[^}]*?(?:expires|add_header\s+Cache-Control)[^}]*?)(\})',
        re.DOTALL
    )
    
    for match in location_pattern.finditer(conf):
        location_block = match.group(1)
        closing_brace = match.group(2)
        
        # Check if this location block has proxy_pass, root, or alias
        has_backend = any(keyword in location_block for keyword in ['proxy_pass', 'root ', 'alias '])
        
        if not has_backend:
            # Extract app port from main location / block
            main_proxy = re.search(r'location\s+/\s*\{[^}]*?proxy_pass\s+([^;]+);', conf)
            if main_proxy:
                proxy_url = main_proxy.group(1).strip()
                
                # Inject proxy_pass before closing brace
                fixed_block = location_block + f'\n        proxy_pass {proxy_url};\n    ' + closing_brace
                conf = conf.replace(match.group(0), fixed_block)
                fixes_applied.append('Added missing proxy_pass to static asset location block')
                log(f'🔧 Auto-fix: Added proxy_pass to static asset caching block')
    
    # ═══════════════════════════════════════════════════════════════════
    # FIX 2: Ensure proxy headers are present in all proxy_pass blocks
    # ═══════════════════════════════════════════════════════════════════
    required_headers = [
        'proxy_set_header Host $host;',
        'proxy_set_header X-Real-IP $remote_addr;',
        'proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;'
    ]
    
    # Find all location blocks with proxy_pass
    proxy_locations = re.finditer(
        r'(location\s+[^{]+\{[^}]*?proxy_pass[^}]*?)(\})',
        conf,
        re.DOTALL
    )
    
    for match in proxy_locations:
        location_block = match.group(1)
        closing_brace = match.group(2)
        
        # Check which headers are missing
        missing_headers = [h for h in required_headers if h not in location_block]
        
        if missing_headers:
            # Add missing headers before closing brace
            headers_to_add = '\n        ' + '\n        '.join(missing_headers)
            fixed_block = location_block + headers_to_add + '\n    ' + closing_brace
            conf = conf.replace(match.group(0), fixed_block)
            fixes_applied.append(f'Added {len(missing_headers)} missing proxy headers')
            log(f'🔧 Auto-fix: Added {len(missing_headers)} missing proxy headers')
    
    # ═══════════════════════════════════════════════════════════════════
    # FIX 3: Ensure gzip is enabled for common types
    # ═══════════════════════════════════════════════════════════════════
    if 'gzip on;' not in conf:
        # Find server block and add gzip config
        server_match = re.search(r'(server\s*\{)', conf)
        if server_match:
            gzip_config = '''
    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript application/json application/javascript application/xml+rss application/rss+xml font/truetype font/opentype application/vnd.ms-fontobject image/svg+xml;
'''
            conf = conf.replace(server_match.group(0), server_match.group(0) + gzip_config)
            fixes_applied.append('Added gzip compression configuration')
            log('🔧 Auto-fix: Added gzip compression')
    
    # Log all fixes
    if fixes_applied:
        log(f'🔧 Nginx auto-fix applied {len(fixes_applied)} fixes:')
        for fix in fixes_applied:
            log(f'   ✓ {fix}')
    
    return conf


def apply_baseline_gateway():
    """Serve a friendly loading page immediately so the iframe never shows a connection error."""
    write_nginx_config("""
server {
    listen 80 default_server;
    server_name _;
    location / {
        default_type text/html;
        return 200 '<html><body style="background:#0f172a;color:white;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;flex-direction:column;gap:16px"><h2 style="margin:0">Getting things ready...</h2><p style="margin:0;opacity:.7">Your app is being built. This usually takes about a minute.</p></body></html>';
    }
}
""")


def get_nginx_errors():
    """Get RECENT nginx errors (from last 10 seconds only) to avoid false positives from old errors."""
    try:
        if not Path(NGINX_ERROR_LOG).exists():
            return []
        
        # Only check errors from the last 10 seconds
        cutoff_time = time.time() - 10
        recent_errors = []
        
        lines = Path(NGINX_ERROR_LOG).read_text().strip().split('\n')
        for line in lines[-50:]:  # Check last 50 lines
            if not line or not ('connect() failed' in line or '502' in line or 'upstream' in line):
                continue
            
            # Parse nginx timestamp: 2026/04/13 10:54:26
            try:
                # Extract timestamp from nginx log format
                timestamp_match = re.search(r'(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})', line)
                if timestamp_match:
                    timestamp_str = timestamp_match.group(1)
                    log_time = datetime.strptime(timestamp_str, '%Y/%m/%d %H:%M:%S').timestamp()
                    
                    # Only include if error is recent (within last 10 seconds)
                    if log_time >= cutoff_time:
                        recent_errors.append(line)
            except:
                # If we can't parse timestamp, skip this line
                continue
        
        return recent_errors
    except:
        return []


# ── AI call ────────────────────────────────────────────────────────────────────
def call_ai(messages: list, temperature: float = 0.2, show_thinking: bool = True) -> str:
    """
    Call AI model and optionally extract/show thinking.
    
    Args:
        messages: List of message dicts with 'role' and 'content'
        temperature: Sampling temperature
        show_thinking: If True, extract and show AI's thinking to user
    
    Returns:
        AI response text
    """
    headers = {'Content-Type': 'application/json'}

    if AI_PROVIDER == 'bournai':
        parts = []
        for m in messages:
            role = m.get('role', 'user')
            content = m.get('content', '')
            tag = {'system': '[System]', 'user': '[User]', 'assistant': '[Assistant]'}.get(role, f'[{role}]')
            parts.append(f'{tag}\n{content}')
        payload = {
            'agent_id': API_KEY,
            'model': AI_MODEL or 'BournAI',
            'platform_id': os.environ.get('BRN_PLATFORM_ID', 'DSuite'),
            'stream': True,
            'prompt': '\n\n'.join(parts),
        }
        resp = requests.post(API_URL, headers=headers, json=payload, stream=True, timeout=180)
        resp.raise_for_status()
        content = ''
        for raw in resp.iter_lines():
            if not raw:
                continue
            line = raw.decode('utf-8')
            if line.startswith('data: '):
                line = line[6:]
            if line.strip() == '[DONE]':
                break
            try:
                chunk = json.loads(line)
                for part in chunk.get('content', []):
                    if isinstance(part, dict) and part.get('type') == 'text':
                        content += part.get('text', '')
                if chunk.get('stop_reason') == 'end_turn':
                    break
            except json.JSONDecodeError:
                pass
        
        # Extract and show thinking if enabled
        if show_thinking and content:
            _extract_and_show_thinking(content)
        
        return content
    else:
        headers['Authorization'] = f'Bearer {API_KEY}'
        payload = {
            'model': AI_MODEL,
            'messages': messages,
            'temperature': temperature,
        }
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=180)
        resp.raise_for_status()
        content = resp.json()['choices'][0]['message']['content']
        
        # Extract and show thinking if enabled
        if show_thinking and content:
            _extract_and_show_thinking(content)
        
        return content


def _extract_and_show_thinking(response_text: str):
    """
    Extract and show AI's thinking from response.
    Looks for:
    1. "thinking" field in JSON responses
    2. Text before first code/file marker
    3. Explanatory text at the start
    """
    # Try to extract from JSON first
    try:
        # Clean markdown code fences
        cleaned = re.sub(r'^```[a-z]*\n?', '', response_text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r'\n?```$', '', cleaned.strip(), flags=re.MULTILINE)
        
        # Try to find JSON
        m = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                thinking = data.get('thinking') or data.get('thought') or data.get('analysis')
                if thinking and isinstance(thinking, str) and 10 < len(thinking) < 500:
                    report(f'💡 {thinking}')
                    log(f'AI thinking: {thinking}')
                    return
            except:
                pass
    except:
        pass
    
    # Try to extract text before first marker (FILE:, PATCH:, code fence, etc.)
    markers = [
        r'(?://|#|<!--)\s*(?:FILE|PATCH):',  # File/patch markers
        r'^```',  # Code fences
        r'^\{',  # JSON start
    ]
    
    for marker_pattern in markers:
        match = re.search(marker_pattern, response_text, re.MULTILINE)
        if match:
            thinking = response_text[:match.start()].strip()
            # Clean up common prefixes
            thinking = re.sub(r'^(Sure|Okay|Alright|Got it)[,!.]?\s*', '', thinking, flags=re.IGNORECASE)
            thinking = re.sub(r'^(I will|I\'ll|Let me)\s+', '', thinking, flags=re.IGNORECASE)
            
            if thinking and 10 < len(thinking) < 500:
                report(f'💡 {thinking}')
                log(f'AI thinking: {thinking}')
                return
    
    # If response is short and looks like an explanation, show it
    if len(response_text) < 300 and not any(marker in response_text for marker in ['```', '//', '<<<', '>>>']):
        thinking = response_text.strip()
        if thinking and 10 < len(thinking) < 300:
            report(f'💡 {thinking}')
            log(f'AI thinking: {thinking}')


# ── Phase 1: Code Generation ───────────────────────────────────────────────────
def generate_code(user_prompt: str, existing_files: dict = None) -> bool:
    is_edit = bool(existing_files)

    if is_edit:
        # Generate task breakdown for edits
        task_summary = _generate_task_breakdown(user_prompt, existing_files)
        report(f'✏️ Got your request! Here\'s what I\'ll do:\n\n{task_summary}', 
               message_type='thinking',
               summary='Analyzing changes needed')
    else:
        # Generate task breakdown for new projects
        task_summary = _generate_task_breakdown(user_prompt, None)
        report(f'🧠 Planning your app:\n\n{task_summary}',
               message_type='thinking', 
               summary='Planning application structure')

    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    existing_context = ''
    if existing_files:
        lines = []
        for path, content in list(existing_files.items())[:20]:
            lines.append(f'// FILE: {path}\n{content[:3000]}')
        existing_context = '\n\n'.join(lines)

    system_prompt = """You are an elite full-stack engineer. Generate complete, production-ready application code.

DEPLOYMENT ENVIRONMENT (Docker Ubuntu 22.04):
- Pre-installed: Python3, pip3, Node.js 18, npm, Nginx, serve, git, curl
- Nginx listens on port 80 and reverse-proxies to your app's internal port
- Your app MUST use an internal port (3000, 5000, 8000, etc.) — NEVER port 80

CRITICAL PORT RULE:
- Nginx owns port 80. Your app binds to an internal port like 3000 or 5000.
- Use process.env.PORT || 3000 for Node/Express
- Use os.environ.get('PORT', '5000') for Python/Flask
- NEVER bind to port 80 in your app code

FILE OUTPUT FORMAT — use EXACTLY this, one marker per file:
// FILE: path/to/file.ext
[complete file content]

FOR EDITS — use EXACTLY this patch format (NOT git diff):
// PATCH: path/to/file.ext
<<<SEARCH
exact lines to replace (include 2-3 lines of context)
>>>
<<<REPLACE
new lines
>>>

RULES:
1. Write COMPLETE files — no truncation, no "// ... rest of code"
2. NEVER use git diff format (no @@, no +line, no -line) — use <<<SEARCH/<<<REPLACE only
3. NEVER hardcode localhost or 127.0.0.1 in frontend fetch/axios — use relative paths (/api/...)
4. Dark-mode first UI: rich dark backgrounds, glassmorphism cards, smooth transitions
5. For React/Vite: include index.html, src/main.jsx, src/App.jsx, package.json, vite.config.js
6. For static HTML: just index.html (+ style.css, script.js) — no build tools needed
7. Keep conversational text to 1-2 sentences max before file markers
8. NO setup instructions — the platform deploys automatically

FOR EDITS: Start your response with a brief explanation of what you're changing (1-2 sentences), then output the file markers."""

    if is_edit:
        user_content = f"""EXISTING PROJECT FILES:
{existing_context}

USER REQUEST: {user_prompt}

CRITICAL: You MUST use file markers to apply changes:
- For small changes: Use // PATCH: with <<<SEARCH/<<<REPLACE blocks
- For complete rewrites: Use // FILE: with full file content
- DO NOT respond conversationally - output ONLY file markers and code

Apply the requested changes now."""
    else:
        user_content = f'Build this: {user_prompt}'

    try:
        response_text = call_ai([
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_content},
        ], temperature=0.3, show_thinking=is_edit)  # Show thinking for edits
        
        # Log AI response for debugging
        log(f'AI response length: {len(response_text)} chars')
        log(f'AI response preview: {response_text[:500]}...')
        
    except Exception as e:
        report(f'⚠️ Something went wrong while generating the code. Please try again. (Details: {e})')
        return False

    # Parse FILE: markers
    file_marker_re = re.compile(
        r'(?://\s*FILE:\s*|#\s*FILE:\s*|<!--\s*FILE:\s*)([^\n>]+?)(?:\s*-->)?\s*\n',
        re.IGNORECASE
    )
    matches = list(file_marker_re.finditer(response_text))

    # Parse PATCH: markers
    patch_marker_re = re.compile(r'//\s*PATCH:\s*([^\n]+)', re.IGNORECASE)
    patch_matches = list(patch_marker_re.finditer(response_text))
    
    log(f'Found {len(matches)} FILE markers and {len(patch_matches)} PATCH markers')

    if not matches and not patch_matches:
        # No file markers found
        if is_edit:
            # For edits, we MUST have file markers - don't guess
            log('⚠️ AI response for edit has no FILE/PATCH markers')
            log(f'Response preview: {response_text[:500]}')
            report('⚠️ I need to try that again with the proper format. One moment...')
            
            # Retry with more explicit instructions
            retry_prompt = f"""CRITICAL: You must use file markers to make changes.

USER REQUEST: {user_prompt}

EXISTING FILES:
{existing_context[:2000]}

Output ONLY file markers - no explanations:
// PATCH: filename.ext
<<<SEARCH
exact lines to find
>>>
<<<REPLACE
new lines
>>>

Or for complete rewrites:
// FILE: filename.ext
[complete file content]

Apply the changes now using ONLY these markers."""
            
            try:
                response_text = call_ai([
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': retry_prompt},
                ], temperature=0.2, show_thinking=True)  # Show retry thinking
                
                log(f'Retry response length: {len(response_text)} chars')
                
                # Re-parse markers
                matches = list(file_marker_re.finditer(response_text))
                patch_matches = list(patch_marker_re.finditer(response_text))
                log(f'Retry found {len(matches)} FILE markers and {len(patch_matches)} PATCH markers')
                
                if not matches and not patch_matches:
                    report('⚠️ The AI didn\'t return any code changes. Please try rephrasing your request.')
                    return False
            except Exception as e:
                report(f'⚠️ Something went wrong. Please try again. (Details: {e})')
                return False
        else:
            # For new projects, try to detect the file type
            code = response_text.strip()
            if not code or len(code) < 30:
                report('⚠️ The AI didn\'t return any code. Please try rephrasing your request.')
                return False
            filename = _detect_filename(code)
            _write_file(WORKSPACE_DIR / filename, code)
            report(f'✅ Code is ready! Starting the build process...')
            return True

    files_written = []
    for i, match in enumerate(matches):
        filename = _clean_filename(match.group(1))
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(response_text)
        patch_in_range = [p for p in patch_matches if start <= p.start() < end]
        if patch_in_range:
            end = patch_in_range[0].start()
        content = response_text[start:end].strip()
        if content:
            log(f'Writing file: {filename} ({len(content)} chars)')
            _write_file(WORKSPACE_DIR / filename, content)
            files_written.append(filename)
        else:
            log(f'Skipping empty file: {filename}')

    patches_applied = _apply_patches(response_text, patch_matches)
    log(f'Applied {patches_applied} patches')

    total = len(files_written) + patches_applied
    if total == 0:
        log('⚠️ No files written and no patches applied!')
        report('⚠️ The code was generated but couldn\'t be saved. Please try again.')
        return False

    # Generate a summary of what was changed
    change_summary = _generate_change_summary(user_prompt, files_written, patches_applied, is_edit)

    if is_edit:
        report(f'✅ Changes applied:\n\n{change_summary}',
               message_type='success',
               summary=f'Updated {total} file(s)')
        # Store what changed for post-deployment testing
        changed_files = files_written + [_clean_filename(pm.group(1)) for pm in patch_matches]
        return {'success': True, 'changed_files': changed_files, 'user_prompt': user_prompt}
    else:
        report(f'✅ App created:\n\n{change_summary}',
               message_type='success',
               summary=f'Created {total} file(s)')
        return True


def _write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    log(f'  📄 {path.relative_to(PROJECT_DIR)}')


def _clean_filename(filename: str) -> str:
    filename = filename.strip().lstrip('/')
    for prefix in ('project/workspace/', 'workspace/'):
        if filename.startswith(prefix):
            filename = filename[len(prefix):]
    return filename


def _detect_filename(code: str) -> str:
    c = code.strip()
    if '<html' in c.lower() or '<!doctype' in c.lower():
        return 'index.html'
    if 'def ' in c or 'import flask' in c or 'from flask' in c or 'fastapi' in c:
        return 'app.py'
    if 'function ' in c or 'const ' in c or 'require(' in c:
        return 'index.js'
    return 'index.html'


def _apply_patches(text: str, patch_matches: list) -> int:
    """
    Apply SEARCH/REPLACE patch hunks to workspace files.
    Also handles git-diff format (@@...@@ / +line / -line) by converting it first.
    Falls back to rewriting the full file if no hunks match.
    """
    applied = 0
    hunk_re = re.compile(r'<<<SEARCH\n(.*?)\n>>>\n<<<REPLACE\n(.*?)\n>>>', re.DOTALL)

    for pm in patch_matches:
        filename = _clean_filename(pm.group(1))
        log(f'Processing PATCH for: {filename}')
        target = WORKSPACE_DIR / filename
        if not target.exists():
            log(f'  ⚠️ PATCH target not found: {filename}')
            continue

        file_content = target.read_text(encoding='utf-8')
        next_patch = next((p for p in patch_matches if p.start() > pm.start()), None)
        segment_end = next_patch.start() if next_patch else len(text)
        segment = text[pm.end():segment_end]
        
        log(f'  Patch segment length: {len(segment)} chars')

        # Detect and convert git-diff format to SEARCH/REPLACE
        if re.search(r'^@@.*@@', segment, re.MULTILINE):
            log(f'  Converting git-diff format to SEARCH/REPLACE')
            segment = _git_diff_to_search_replace(segment, file_content)

        hunks = list(hunk_re.finditer(segment))
        log(f'  Found {len(hunks)} hunks in patch')
        
        if not hunks:
            log(f'  ⚠️ No valid patch hunks found for {filename}')
            log(f'  Segment preview: {segment[:200]}')
            continue

        for idx, hunk in enumerate(hunks):
            search, replace = hunk.group(1), hunk.group(2)
            log(f'  Hunk {idx+1}: searching for {len(search)} chars, replacing with {len(replace)} chars')
            
            # Show first and last line of search for debugging
            search_lines = search.splitlines()
            if search_lines:
                log(f'  Search first line: "{search_lines[0][:80]}"')
                if len(search_lines) > 1:
                    log(f'  Search last line: "{search_lines[-1][:80]}"')
            
            if search in file_content:
                file_content = file_content.replace(search, replace, 1)
                applied += 1
                log(f'  ✅ Hunk {idx+1} applied successfully')
            else:
                log(f'  ⚠️ Hunk {idx+1} not found in {filename}')
                log(f'  Search text (first 100 chars): {search[:100]}...')
                
                # Try to find similar content (for debugging)
                search_stripped = search.strip()
                if search_stripped in file_content:
                    log(f'  ℹ️ Found similar content when ignoring leading/trailing whitespace')
                else:
                    # Check if individual lines exist
                    search_lines = [l.strip() for l in search.splitlines() if l.strip()]
                    found_lines = sum(1 for l in search_lines if l in file_content)
                    log(f'  ℹ️ Found {found_lines}/{len(search_lines)} individual lines in file')

        target.write_text(file_content, encoding='utf-8')
        log(f'  📄 Updated {filename}')

    return applied


def _git_diff_to_search_replace(diff_segment: str, original_content: str) -> str:
    """
    Convert a git unified diff segment into <<<SEARCH/<<<REPLACE format.
    Each @@ hunk becomes one SEARCH/REPLACE block.
    """
    result_blocks = []
    hunk_re = re.compile(r'@@[^@]*@@[^\n]*\n((?:[+\- ][^\n]*\n?)*)', re.MULTILINE)

    for hunk in hunk_re.finditer(diff_segment):
        hunk_lines = hunk.group(1).splitlines()
        search_lines = []
        replace_lines = []
        for line in hunk_lines:
            if line.startswith('-'):
                search_lines.append(line[1:])
            elif line.startswith('+'):
                replace_lines.append(line[1:])
            else:
                # Context line — appears in both
                ctx = line[1:] if line.startswith(' ') else line
                search_lines.append(ctx)
                replace_lines.append(ctx)

        if search_lines:
            result_blocks.append(
                f'<<<SEARCH\n{chr(10).join(search_lines)}\n>>>\n'
                f'<<<REPLACE\n{chr(10).join(replace_lines)}\n>>>'
            )

    return '\n'.join(result_blocks)


def read_workspace_files() -> dict:
    skip_dirs  = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build', '.next'}
    skip_files = {'metadata.json'}
    files = {}
    if not WORKSPACE_DIR.exists():
        return files
    for fp in sorted(WORKSPACE_DIR.rglob('*')):
        if any(p in skip_dirs for p in fp.parts):
            continue
        if fp.name in skip_files or not fp.is_file():
            continue
        try:
            files[str(fp.relative_to(WORKSPACE_DIR))] = fp.read_text(encoding='utf-8')[:8000]
        except Exception:
            pass
    return files


def sanitize_workspace():
    """
    Scan all text files in the workspace for git diff corruption
    (lines starting with @@, +, - that indicate a raw diff was written as file content).
    For corrupted files, ask the AI to regenerate them cleanly.
    """
    skip_dirs  = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build', '.next'}
    corrupted  = []

    if not WORKSPACE_DIR.exists():
        return

    for fp in sorted(WORKSPACE_DIR.rglob('*')):
        if any(p in skip_dirs for p in fp.parts):
            continue
        if not fp.is_file():
            continue
        # Only check text-based source files
        if fp.suffix not in ('.css', '.js', '.jsx', '.ts', '.tsx', '.html', '.py', '.json', '.md'):
            continue
        try:
            content = fp.read_text(encoding='utf-8')
            # Detect git diff markers: lines starting with @@ or a block of +/- lines
            lines = content.splitlines()
            diff_lines = sum(1 for l in lines if l.startswith('@@') or (len(l) > 1 and l[0] in ('+', '-') and not l.startswith('---') and not l.startswith('+++')))
            if diff_lines > 3 or any(l.startswith('@@') for l in lines):
                corrupted.append(fp)
                log(f'  🔴 Corrupted file detected: {fp.relative_to(PROJECT_DIR)}')
        except Exception:
            pass

    if not corrupted:
        return

    report(f'🔧 Found {len(corrupted)} file(s) with formatting issues — fixing them automatically...')

    for fp in corrupted:
        try:
            rel = str(fp.relative_to(WORKSPACE_DIR))
            content = fp.read_text(encoding='utf-8')

            # Ask AI to regenerate the clean version of this file
            fix_prompt = f"""The following file has been corrupted with git diff markers (lines starting with @@, +, -).
Please rewrite it as a clean, complete, valid file with no diff markers.

File: {rel}
Corrupted content:
{content[:4000]}

Return ONLY the clean file content with no explanation, no markers, no fences."""

            clean = call_ai([
                {'role': 'system', 'content': 'You are a code repair tool. Return only clean file content.'},
                {'role': 'user', 'content': fix_prompt},
            ], temperature=0.1, show_thinking=False)  # Don't show thinking for file repair

            # Strip any accidental code fences
            clean = re.sub(r'^```[a-z]*\n?', '', clean.strip(), flags=re.MULTILINE)
            clean = re.sub(r'\n?```$', '', clean.strip(), flags=re.MULTILINE)

            if clean and len(clean) > 10:
                fp.write_text(clean, encoding='utf-8')
                log(f'  ✅ Fixed: {rel}')
            else:
                log(f'  ⚠️ AI returned empty content for {rel} — skipping')

        except Exception as e:
            log(f'  ⚠️ Failed to fix {fp.name}: {e}')


# ── Phase 2: Deployment ────────────────────────────────────────────────────────
def deploy(error_context: dict = None, max_retries: int = 3, test_changes: bool = False, changed_files: list = None, user_prompt: str = None) -> bool:
    report('🔧 Figuring out the best way to run your app...')
    
    # Show loading page immediately so users see progress
    apply_baseline_gateway()

    # Scan and fix any corrupted workspace files before attempting deployment
    sanitize_workspace()

    tree      = _discover_workspace()
    manifests = _read_manifests()
    
    # Detect available ports
    available_ports = _detect_available_ports()

    system_prompt = """You are a senior DevOps engineer deploying applications in a Docker container.

ENVIRONMENT:
- Ubuntu 22.04 container with Node.js, Python, Nginx pre-installed
- Workspace: /project/workspace/ (all user files are here)
- Nginx: Listens on port 80, proxies to your app's internal port
- Available ports: {available_ports}

YOUR TASK:
Analyze the workspace structure and create a deployment strategy.

STEP 1: UNDERSTAND THE STRUCTURE
- workspace_discovery shows the complete file tree
- workspace_discovery.server_files_content contains the ACTUAL CODE of server files (server.js, app.py, etc.)
- manifest_list shows where package.json, requirements.txt, etc. are located
- entry_point_list shows main files like server.js, app.py, index.html

STEP 2: READ SERVER FILES TO UNDERSTAND DEPENDENCIES
The workspace_discovery.server_files_content gives you the actual code.
Look for these patterns:

In server.js or app.js:
```javascript
app.use(express.static(path.join(__dirname, 'dist')))
// → Server expects dist/ in same directory

app.use(express.static(path.join(__dirname, 'client', 'dist')))
// → Server expects dist/ at ./client/dist/

app.use(express.static(path.join(__dirname, '../frontend/build')))
// → Server expects build/ at ../frontend/build/
```

In Python (app.py, main.py):
```python
app.mount("/", StaticFiles(directory="dist"), name="static")
# → Server expects dist/ in same directory

app.mount("/", StaticFiles(directory="../client/dist"), name="static")
# → Server expects dist/ at ../client/dist/
```

STEP 3: DETERMINE BUILD ORDER
- If server references a dist/build folder, that component must be built FIRST
- Then copy/move dist to where server expects it OR start server from correct directory

STEP 4: GENERATE DEPLOYMENT SCRIPT

Pattern A: Single-page app (Vite/React) with no backend
```bash
cd /project/workspace
rm -rf dist build .next out node_modules/.vite
npm install
npm run build
npx serve -s dist -l 3000 &
```

Pattern B: Client/Server in separate folders (server expects ./client/dist)
```bash
# Build client first
cd /project/workspace/client
rm -rf dist build node_modules/.vite
npm install
npm run build

# Copy dist to where server expects it
mkdir -p /project/workspace/server/client
cp -r dist /project/workspace/server/client/

# Start server
cd /project/workspace/server
npm install
PORT=3000 node server.js >> /tmp/app.log 2>&1 &
```

Pattern C: Client/Server in separate folders (server expects ../client/dist)
```bash
# Build client first
cd /project/workspace/client
rm -rf dist build node_modules/.vite
npm install
npm run build

# Start server (it will find ../client/dist)
cd /project/workspace/server
npm install
PORT=3000 node server.js >> /tmp/app.log 2>&1 &
```

Pattern D: Frontend/Backend (separate apps)
```bash
# Build frontend
cd /project/workspace/frontend
rm -rf dist build node_modules/.vite
npm install
npm run build

# Start backend
cd /project/workspace/backend
pip3 install -r requirements.txt
gunicorn -w 4 -b 0.0.0.0:5000 app:app >> /tmp/app.log 2>&1 &

# Serve frontend
cd /project/workspace/frontend
npx serve -s dist -l 3000 >> /tmp/app.log 2>&1 &
```

Pattern E: Monorepo (server in root, serves built client)
```bash
# Build client
cd /project/workspace
npm install
npm run build:client  # or npm run build

# Start server
PORT=3000 node server.js >> /tmp/app.log 2>&1 &
```

STEP 5: CHOOSE THE RIGHT PATTERN
- Look at workspace_discovery structure
- Read server file to see what path it expects
- Match to the appropriate pattern above
- Adjust paths based on actual structure

IMPORTANT:
- ALWAYS clean build artifacts first: rm -rf dist build .next out node_modules/.vite
- Use "npm install" not "npm ci"
- App serves at root / (no base URL configuration)
- Use background processes (&) and redirect logs (>> /tmp/app.log 2>&1)
- Port 80 is for Nginx only - app uses internal port (3000, 5000, 8000, etc.)
- The workspace_discovery shows you the EXACT file structure
- Look at manifest_list to see where package.json, requirements.txt, etc. are located
- If you see ./frontend/package.json, the path is /project/workspace/frontend/
- If you see ./package.json, the path is /project/workspace/

COMMON PATTERNS:

Single-page app (Vite/React):
  cd /project/workspace
  rm -rf dist build .next out node_modules/.vite
  npm install
  npm run build
  npx serve -s dist -l 3000 &

Nested frontend:
  cd /project/workspace/frontend
  rm -rf dist build .next out node_modules/.vite
  npm install
  npm run build
  npx serve -s dist -l 3000 &

Client/Server structure (separate folders):
  # Build client
  cd /project/workspace/client
  rm -rf dist build .next out node_modules/.vite
  npm install
  npm run build
  # Copy dist to where server expects it OR update server path
  # Then start server
  cd /project/workspace/server
  npm install
  PORT=3000 node server.js &

Node.js server:
  cd /project/workspace
  npm install
  PORT=3000 node server.js &

Python Flask:
  cd /project/workspace
  pip3 install -r requirements.txt
  gunicorn -w 4 -b 0.0.0.0:5000 app:app &

IMPORTANT NOTES:
- ALWAYS clean build artifacts before rebuilding: rm -rf dist build .next out node_modules/.vite
- Use "npm install" not "npm ci" (package-lock.json may not exist)
- Serve BUILT output (dist/ or build/) not source files
- App serves at root / (no base URL configuration needed)
- Use background processes (&) and redirect logs (>> /tmp/app.log 2>&1)

NGINX CONFIGURATION:
Your nginx config MUST:
- Listen on port 80
- Proxy ALL requests (including assets) to your app port
- Include proxy headers (Host, X-Real-IP, X-Forwarded-For)
- Enable gzip compression
- Add security headers

Example nginx config:
server {{
    listen 80;
    
    # Gzip
    gzip on;
    gzip_types text/plain text/css application/json application/javascript;
    
    # Security
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    
    # Proxy everything to app
    location / {{
        proxy_pass http://127.0.0.1:APP_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        add_header Cache-Control "no-cache, no-store, must-revalidate" always;
        add_header Pragma "no-cache" always;
        expires 0;
    }}
    
    # Static assets (also proxied)
    # Use short cache during development to see updates immediately
    location ~* \.(js|css|png|jpg|svg|ico|woff|woff2)$ {{
        proxy_pass http://127.0.0.1:APP_PORT;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        add_header Cache-Control "no-cache, must-revalidate" always;
        expires 0;
    }}
}}

RESPONSE FORMAT:
{{
  "thought": "Explain your deployment strategy in 1-2 sentences for the user. Example: 'I see a Vite React app in the frontend folder. I'll build it and serve the dist folder on port 3000.'",
  "app_port": 3000,
  "deployment_script": "#!/bin/bash\\nset -e\\n...",
  "nginx_config": "server {{ ... }}"
}}

Remember: You're Claude, a highly capable AI. Trust your analysis of the workspace_discovery data and choose the right approach for the specific project structure you see.""".format(available_ports=', '.join(map(str, available_ports)))

    user_content = {
        'workspace_tree': tree,
        'manifest_files': manifests,
        'error_context': error_context,
    }

    error_history = []  # Track all errors across attempts for pattern detection
    attempted_strategies = []  # Track deployment strategies to avoid repetition

    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            report(f'🔄 Something didn\'t work as expected. Trying a different approach... (attempt {attempt}/{max_retries})')

            # Before retrying, check if we have a repeating pattern — fix code if so
            if len(error_history) >= 2:
                workspace_files = read_workspace_files()
                fixed = _targeted_code_fix(error_history, workspace_files)
                if fixed:
                    # Refresh workspace tree after code fix
                    tree = _discover_workspace()
                    manifests = _read_manifests()
            
            # ALWAYS refresh workspace discovery before retry
            log('Performing fresh workspace discovery for retry attempt')
            tree = _discover_workspace()
            manifests = _read_manifests()
            
            # On ENOENT errors, run diagnostic commands
            if error_context and 'enoent' in error_context.get('reason', '').lower():
                log('ENOENT detected - running diagnostic commands')
                try:
                    # Find all manifest files
                    find_result = subprocess.run(
                        ['find', '.', '-name', 'package.json', '-o', '-name', 'requirements.txt', '-o', '-name', 'index.html'],
                        cwd=str(WORKSPACE_DIR),
                        capture_output=True, text=True, timeout=5
                    )
                    if find_result.returncode == 0:
                        log(f'Diagnostic find results:\n{find_result.stdout}')
                        # Add to error context
                        if error_context:
                            error_context['diagnostic_find'] = find_result.stdout
                    
                    # List directory structure
                    ls_result = subprocess.run(
                        ['ls', '-R'],
                        cwd=str(WORKSPACE_DIR),
                        capture_output=True, text=True, timeout=5
                    )
                    if ls_result.returncode == 0:
                        log(f'Diagnostic ls -R results (first 500 chars):\n{ls_result.stdout[:500]}')
                        if error_context:
                            error_context['diagnostic_ls'] = ls_result.stdout[:1000]
                except Exception as e:
                    log(f'Diagnostic commands failed: {e}')

        # Always include full error history so the architect learns from past failures
        # Refined instruction based on history
        instruction = 'Generate the deployment strategy based on the complete workspace scan provided.'
        if error_history:
            last_err = error_history[-1].get('reason', '').lower()
            
            # Check for validation errors (most recent)
            if 'validation' in last_err or 'adjustments' in last_err:
                validation_errors = error_history[-1].get('validation_errors', [])
                script_excerpt = error_history[-1].get('script_excerpt', '')
                workspace_structure = error_history[-1].get('workspace_structure', {})
                
                instruction = (
                    "Your previous deployment script had some issues. Here's what needs to be fixed:\n\n"
                    + '\n'.join(f"  • {err}" for err in validation_errors) +
                    "\n\nYour script excerpt:\n"
                    f"{script_excerpt}\n\n"
                    "Workspace structure:\n"
                    f"Manifests: {workspace_structure.get('manifests', [])}\n"
                    f"Entry points: {workspace_structure.get('entry_points', [])}\n"
                    f"Hints: {workspace_structure.get('hints', [])}\n\n"
                    "Please analyze the workspace structure carefully and generate a corrected deployment strategy. "
                    "Use the exact paths shown in the manifests list."
                )
            elif 'enoent' in last_err or 'no such file' in last_err:
                instruction = (
                    "CRITICAL: Previous attempt failed with file not found error. "
                    "The complete workspace scan is provided below with ALL actual file locations. "
                    "You MUST use the EXACT paths from the workspace scan. "
                    "DO NOT assume or guess file locations. "
                    "If you see a manifest file in the scan, use its exact path."
                )
            elif 'port' in last_err or '502' in last_err:
                instruction = (
                    "Previous attempt failed with port/connection issues. "
                    "Generate a DIFFERENT strategy: use a different internal port, "
                    "verify the app binds to the internal port (not port 80), "
                    "and ensure the nginx config proxies correctly."
                )
            else:
                instruction = (
                    "Previous attempt failed. Generate a DIFFERENT strategy from previous attempts "
                    "based on the error logs and workspace scan below. "
                    "Do not repeat what failed."
                )
        
        user_content = {
            'workspace_discovery': tree,  # Now structured data
            'manifest_files': manifests,  # Now includes metadata
            'error_context': error_context,
            'error_history': error_history[-3:] if error_history else [],
            'attempted_strategies': attempted_strategies[-2:] if attempted_strategies else [],
            'instruction': instruction,
        }

        try:
            raw = call_ai([
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': json.dumps(user_content)},
            ], temperature=0.05, show_thinking=True)  # Always show deployment thinking

            raw = re.sub(r'^```[a-z]*\n?', '', raw.strip(), flags=re.MULTILINE)
            raw = re.sub(r'\n?```$', '', raw.strip(), flags=re.MULTILINE)
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if not m:
                raise ValueError('No JSON in architect response')
            strategy = json.loads(m.group(0))
            
        except Exception as e:
            log(f'Architect failed on attempt {attempt}: {e}')
            time.sleep(3)
            continue

        # Kill any running app processes on non-Nginx ports dynamically
        # Find all listening ports except 80 (Nginx) and kill them
        subprocess.run(
            'ss -tlnp | awk \'NR>1 && $4 !~ /:80$/ {match($4, /:([0-9]+)$/, a); if(a[1]) print a[1]}\' '
            '| sort -u | xargs -r -I{} fuser -k {}/tcp 2>/dev/null || true',
            shell=True, capture_output=True
        )
        time.sleep(1)

        script = strategy.get('deployment_script', '')
        app_port = strategy.get('app_port', None)
        log(f'App will use internal port: {app_port}')

        if script:
            # ═══════════════════════════════════════════════════════════════
            # CRITICAL: Validate deployment script before execution
            # ═══════════════════════════════════════════════════════════════
            # ═══════════════════════════════════════════════════════════════
            # Validation: Only check for critical errors that would break deployment
            # Trust Claude to use correct paths based on workspace_discovery
            # ═══════════════════════════════════════════════════════════════
            validation_errors = []
            
            # Check 1: Port 80 binding (critical - conflicts with Nginx)
            port80_patterns = [
                r'listen\s+80\b', r'PORT\s*=\s*["\']?80["\']?\b',
                r'port\s*[=:]\s*["\']?80["\']?\b',
                r'0\.0\.0\.0:80\b', r'localhost:80\b',
            ]
            if any(re.search(p, script, re.IGNORECASE) for p in port80_patterns):
                validation_errors.append('Script tries to bind to port 80 (reserved for Nginx)')
            
            # Check 2: npm ci usage (will fail without package-lock.json)
            if 'npm ci' in script:
                validation_errors.append('Script uses "npm ci" which requires package-lock.json - use "npm install" instead')
            
            # That's it! Trust Claude for everything else.
            # Claude can see workspace_discovery and will use correct paths.
            
            # If validation fails, provide constructive feedback
            if validation_errors:
                log(f'⚠️ Deployment script has issues that need fixing:')
                for err in validation_errors:
                    log(f'   ⚠️ {err}')
                
                # Build helpful feedback
                helpful_feedback = {
                    'reason': 'The deployment script needs adjustments: ' + '; '.join(validation_errors),
                    'validation_errors': validation_errors,
                    'script_excerpt': script[:500],
                    'workspace_structure': {
                        'manifests': tree.get('manifest_list', []),
                        'entry_points': tree.get('entry_point_list', []),
                        'hints': tree.get('deployment_hints', [])
                    },
                    'nginx_errors': [],
                }
                error_history.append(helpful_feedback)
                time.sleep(1)
                continue

            report('📦 Installing dependencies and building your app...')
            script_path = '/tmp/autodeploy.sh'
            # Wrap script to redirect app stdout/stderr to a log file for diagnostics
            script_with_logging = (
                script if script.startswith('#') else '#!/bin/bash\nset -e\n' + script
            )
            # Redirect background process output to a log file
            script_with_logging = script_with_logging.replace(
                ' &\n', ' >> /tmp/app_stdout.log 2>&1 &\n'
            )
            # Clear previous log
            Path('/tmp/app_stdout.log').write_text('')
            Path(script_path).write_text(script_with_logging)
            os.chmod(script_path, 0o755)
            build_output_lines = []
            try:
                proc = subprocess.Popen(
                    ['bash', script_path],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
                )
                for line in proc.stdout:
                    line = line.strip()
                    if line:
                        print(f'  📦 {line}', flush=True)
                        build_output_lines.append(line)
                proc.wait(timeout=300)
                log(f'Build script done (exit={proc.returncode})')

                if proc.returncode != 0:
                    build_output_str = '\n'.join(build_output_lines[-50:])
                    # Automatically harvest logs (both referenced and dynamic)
                    extra_logs = _get_combined_logs(build_output_str)
                    full_error = build_output_str
                    if extra_logs:
                        full_error += '\n\n--- AUTO-HARVESTED LOGS ---\n' + extra_logs
                    
                    log(f'Build failed with exit code {proc.returncode}')
                    log(f'Error output length: {len(full_error)} chars')
                    
                    # Exit code 127 = command not found (not a syntax error)
                    if proc.returncode == 127:
                        log('Exit code 127 detected - command not found error')
                        log(f'Error output: {full_error[:500]}')
                        # Don't try to fix as syntax error
                        diagnostics = _collect_runtime_diagnostics(app_port=app_port, workspace_discovery=tree)
                        error_context = {
                            'reason': f'Command not found (exit 127) - likely missing dependency or incorrect command',
                            'build_output': full_error,
                            'nginx_errors': [],
                            'diagnostics': diagnostics,
                            'workspace_discovery_summary': {
                                'manifests': [m.get('path') for m in tree.get('manifests', [])],
                                'tech_indicators': tree.get('tech_indicators', {}),
                            }
                        }
                        error_history.append(error_context)
                        time.sleep(2)
                        continue
                    
                    log(f'Checking for syntax errors...')
                    
                    # ═══════════════════════════════════════════════════════════════
                    # AUTO-FIX: Detect and fix syntax errors automatically
                    # ═══════════════════════════════════════════════════════════════
                    has_syntax_error = 'SyntaxError' in full_error or 'IndentationError' in full_error or 'TabError' in full_error
                    log(f'Syntax error detected: {has_syntax_error}')
                    
                    if has_syntax_error:
                        log('🔧 Syntax error detected - attempting automatic fix')
                        report('🔧 I found a syntax error in the code. Let me fix it...')
                        
                        fix_result = _auto_fix_syntax_error(full_error, tree)
                        log(f'Fix result: {fix_result}')
                        
                        if fix_result.get('fixed'):
                            report(f'✅ Fixed syntax error in {fix_result["file"]}. Rebuilding...')
                            log('Retrying deployment after syntax fix')
                            time.sleep(2)
                            continue  # Retry deployment with fixed code
                        else:
                            error_msg = fix_result.get('error', 'Unknown error')
                            log(f'⚠️ Auto-fix failed: {error_msg}')
                            report(f'⚠️ I found a syntax error but couldn\'t fix it automatically: {error_msg}')
                    else:
                        log('No syntax errors detected in build output')
                    
                    # Collect comprehensive diagnostics
                    diagnostics = _collect_runtime_diagnostics(app_port=app_port, workspace_discovery=tree)
                    
                    error_context = {
                        'reason': f'Build/install failed (exit {proc.returncode})',
                        'build_output': full_error,
                        'nginx_errors': [],
                        'diagnostics': diagnostics,
                        'workspace_discovery_summary': {
                            'manifests': [m.get('path') for m in tree.get('manifests', [])],
                            'tech_indicators': tree.get('tech_indicators', {}),
                        }
                    }
                    error_history.append(error_context)
                    time.sleep(2)
                    continue

            except Exception as e:
                log(f'Build script error: {e}')
                diagnostics = _collect_runtime_diagnostics(app_port=app_port, workspace_discovery=tree)
                error_context = {
                    'reason': str(e),
                    'nginx_errors': [],
                    'diagnostics': diagnostics
                }
                error_history.append(error_context)

        time.sleep(4)

        nginx_conf = strategy.get('nginx_config', '')
        if nginx_conf:
            report('🌐 Setting up the web server...')
            
            # ═══════════════════════════════════════════════════════════════
            # VALIDATE: Check nginx config for common issues before applying
            # ═══════════════════════════════════════════════════════════════
            nginx_issues = _validate_nginx_config(nginx_conf, app_port)
            if nginx_issues:
                log(f'⚠️ Nginx config has {len(nginx_issues)} potential issues:')
                for issue in nginx_issues:
                    log(f'   ⚠️ {issue}')
                log('🔧 Applying auto-fixes...')
            
            write_nginx_config(nginx_conf)

        time.sleep(2)

        healthy, msg = _health_check(app_port=app_port)
        if healthy:
            report('🎉 Your app is live! The preview should appear any moment now.',
                   suggestions=[
                       {'text': 'Make changes', 'action': 'edit', 'icon': '✏️', 'prompt': 'I want to make some changes'},
                       {'text': 'Add features', 'action': 'add_feature', 'icon': '✨', 'prompt': 'Add a new feature'},
                       {'text': 'Fix issues', 'action': 'fix', 'icon': '🔧', 'prompt': 'Fix any issues'}
                   ],
                   metadata={'status': 'success', 'app_port': app_port, 'deployment_time': time.time()},
                   summary='App deployed successfully')
            
            # If this was an edit with changes, automatically test them
            if test_changes and changed_files and user_prompt:
                test_result = _test_changes_automatically(changed_files, user_prompt, app_port)
                
                # If fix was applied, redeploy
                if test_result.get('fix_applied'):
                    log('Auto-fix applied, redeploying...')
                    time.sleep(2)
                    continue  # Retry deployment with the fix
            
            return True

        nginx_errors = get_nginx_errors()
        fail_reason = msg
        if nginx_errors:
            fail_reason += f' | {nginx_errors[-1]}'
        log(f'Health check failed on attempt {attempt}: {fail_reason}')

        error_context = {'reason': fail_reason, 'nginx_errors': nginx_errors}
        error_history.append(error_context)
        time.sleep(3)

    if error_history:
        last_failure = error_history[-1]
        reason = last_failure.get('reason', 'Unknown failure')
        
        # Get exact app output for the user
        diag = last_failure.get('diagnostics', {})
        app_log = diag.get('app_log', '')
        
        msg = f"⚠️ I couldn't get the app running. The exact error was: {reason}"
        if not app_log:
             # Try harvesting logs one last time if they are missing
             app_log = _get_combined_logs('')
        
        # Generate contextual suggestions based on error type
        suggestions = []
        metadata = {'status': 'failed', 'error_type': 'deployment'}
        
        if 'exit 127' in reason.lower() or 'command not found' in reason.lower():
            suggestions = [
                {'text': 'Install missing dependencies', 'action': 'install_deps', 'icon': '📦', 'prompt': 'Install the missing dependencies'},
                {'text': 'Check deployment script', 'action': 'review_script', 'icon': '🔍', 'prompt': 'Review and fix the deployment script'},
                {'text': 'Show me the full logs', 'action': 'show_logs', 'icon': '📋', 'prompt': 'Show me the detailed error logs'}
            ]
            metadata['error_category'] = 'missing_command'
        elif 'port' in reason.lower() or '502' in reason.lower():
            suggestions = [
                {'text': 'Try a different port', 'action': 'change_port', 'icon': '🔌', 'prompt': 'Use a different port for the application'},
                {'text': 'Check if app is running', 'action': 'check_status', 'icon': '🔍', 'prompt': 'Check the application status'},
                {'text': 'Restart the deployment', 'action': 'retry', 'icon': '🔄', 'prompt': 'Try deploying again'}
            ]
            metadata['error_category'] = 'port_issue'
        elif 'syntax' in reason.lower():
            suggestions = [
                {'text': 'Auto-fix syntax errors', 'action': 'auto_fix', 'icon': '🔧', 'prompt': 'Fix the syntax errors automatically'},
                {'text': 'Show me the errors', 'action': 'show_errors', 'icon': '📋', 'prompt': 'Show me the syntax errors'},
                {'text': 'Review the code', 'action': 'review_code', 'icon': '👀', 'prompt': 'Review the code for issues'}
            ]
            metadata['error_category'] = 'syntax_error'
        else:
            suggestions = [
                {'text': 'Try again', 'action': 'retry', 'icon': '🔄', 'prompt': 'Try the deployment again'},
                {'text': 'Show detailed logs', 'action': 'show_logs', 'icon': '📋', 'prompt': 'Show me the detailed logs'},
                {'text': 'Describe the issue', 'action': 'clarify', 'icon': '💬', 'prompt': None}
            ]
            metadata['error_category'] = 'general'
        
        report(msg, code=app_log, suggestions=suggestions, metadata=metadata, summary=f"Deployment failed: {reason[:50]}")
    else:
        report('⚠️ We ran into some trouble getting your app running. You can try sending your request again.',
               suggestions=[
                   {'text': 'Try again', 'action': 'retry', 'icon': '🔄', 'prompt': 'Try the deployment again'},
                   {'text': 'Start fresh', 'action': 'restart', 'icon': '🆕', 'prompt': 'Start with a new deployment'}
               ],
               metadata={'status': 'failed', 'error_type': 'unknown'},
               summary='Deployment failed')
        
    return False


def _collect_runtime_diagnostics(app_port: int = None, workspace_discovery: dict = None) -> dict:
    """
    Collect all available runtime diagnostics:
    - Nginx error log
    - App process stdout/stderr (via /tmp/app_stdout.log if the script redirects there)
    - Port binding status
    - Recent system errors
    - Workspace discovery results
    Returns a dict with all findings.
    """
    diag = {}

    # Nginx errors
    diag['nginx_errors'] = get_nginx_errors()

    # App stdout log (deployment scripts redirect output here)
    app_log = Path('/tmp/app_stdout.log')
    if app_log.exists():
        try:
            lines = app_log.read_text().strip().splitlines()
            diag['app_log'] = '\n'.join(lines[-50:])
        except Exception:
            pass

    # Check if app port is actually listening
    if app_port:
        result = subprocess.run(
            f'ss -tlnp | grep :{app_port}',
            shell=True, capture_output=True, text=True
        )
        diag['port_listening'] = bool(result.stdout.strip())
        diag['port_status'] = result.stdout.strip() or f'Port {app_port} not listening'

    # Any Python/Node crash logs
    for log_path in ['/tmp/app.log', '/tmp/server.log', '/tmp/error.log']:
        if Path(log_path).exists():
            try:
                lines = Path(log_path).read_text().strip().splitlines()
                diag[f'log_{Path(log_path).name}'] = '\n'.join(lines[-30:])
            except Exception:
                pass
    
    # Include workspace discovery results
    if workspace_discovery:
        diag['workspace_discovery'] = {
            'manifests_found': len(workspace_discovery.get('manifests', [])),
            'entry_points_found': len(workspace_discovery.get('entry_points', [])),
            'tech_indicators': workspace_discovery.get('tech_indicators', {}),
            'directory_count': len(workspace_discovery.get('directory_structure', {}))
        }

    return diag


def _detect_error_pattern(error_history: list) -> str:
    """
    Analyse the last N error contexts to detect a repeating pattern.
    Returns a plain-English description of the pattern, or empty string if no pattern.
    """
    if len(error_history) < 2:
        return ''

    # Extract key phrases from each error
    all_reasons = [str(e.get('reason', '')) for e in error_history]

    # Check if the same root cause keeps appearing
    patterns = {
        'module not found':    'missing dependency — need to install packages',
        'cannot find module':  'missing dependency — need to install packages',
        'enoent':              'missing file or directory',
        'eaddrinuse':          'port already in use — need to use a different port',
        'syntax error':        'syntax error in source code — need to fix the code',
        'typeerror':           'type error in source code — need to fix the code',
        'permission denied':   'file permission issue',
        '502':                 'app not starting or crashing immediately after start',
        'connection refused':  'app not binding to the expected port',
        'exit code 1':         'build or start script failing',
        'exit code 2':         'command not found or script error',
    }

    matched = []
    for reason in all_reasons[-3:]:
        reason_lower = reason.lower()
        for keyword, description in patterns.items():
            if keyword in reason_lower and description not in matched:
                matched.append(description)

    if len(matched) >= 2 or (len(error_history) >= 2 and matched):
        return f"Repeating issue detected: {'; '.join(matched)}"
    return ''


def _targeted_code_fix(error_history: list, workspace_files: dict) -> bool:
    """
    When the same error keeps repeating, ask the AI to fix the source code directly
    rather than just retrying the deployment strategy.
    Returns True if any files were modified.
    """
    if not workspace_files:
        return False

    pattern = _detect_error_pattern(error_history)
    if not pattern:
        return False

    report(f'🔍 Spotted a repeating issue — fixing the source code directly...')

    # Build context
    file_context = '\n\n'.join(
        f'// FILE: {path}\n{content[:2000]}'
        for path, content in list(workspace_files.items())[:15]
    )
    error_summary = '\n'.join(
        f'Attempt {i+1}: {e.get("reason", "")} | Build: {e.get("build_output", "")[-200:]}'
        for i, e in enumerate(error_history[-3:])
    )

    fix_prompt = f"""You are debugging a web app that keeps failing to deploy with the same error.

PATTERN: {pattern}

ERROR HISTORY:
{error_summary}

CURRENT SOURCE FILES:
{file_context}

Your task: Fix the source code to resolve this repeating error.
- If it's a missing dependency, add it to package.json or requirements.txt
- If it's a syntax/type error, fix the code
- If it's a port conflict, change the app to use a different port (not 80)
- If it's a missing file, create it

Output ONLY the files that need to change using:
// FILE: path/to/file.ext
[complete fixed content]

Or for small changes:
// PATCH: path/to/file.ext
<<<SEARCH
old lines
>>>
<<<REPLACE
new lines
>>>"""

    try:
        response = call_ai([
            {'role': 'system', 'content': 'You are a debugging expert. Fix the code to resolve the repeating deployment error.'},
            {'role': 'user', 'content': fix_prompt},
        ], temperature=0.2, show_thinking=True)  # Show code fix thinking
    except Exception as e:
        log(f'Code fix AI call failed: {e}')
        return False

    # Parse and apply the fix
    file_marker_re = re.compile(
        r'(?://\s*FILE:\s*|#\s*FILE:\s*)([^\n]+)\n', re.IGNORECASE
    )
    patch_marker_re = re.compile(r'//\s*PATCH:\s*([^\n]+)', re.IGNORECASE)

    file_matches  = list(file_marker_re.finditer(response))
    patch_matches = list(patch_marker_re.finditer(response))

    files_fixed = 0
    for i, match in enumerate(file_matches):
        filename = _clean_filename(match.group(1))
        start = match.end()
        end = file_matches[i + 1].start() if i + 1 < len(file_matches) else len(response)
        content = response[start:end].strip()
        if content:
            _write_file(WORKSPACE_DIR / filename, content)
            files_fixed += 1

    patches_fixed = _apply_patches(response, patch_matches)

    total = files_fixed + patches_fixed
    if total > 0:
        report(f'✅ Applied {total} fix(es) to the source code. Retrying deployment...')
        return True

    return False


def _discover_workspace() -> dict:
    """
    Thoroughly explore and map the complete workspace structure.
    Returns comprehensive data for AI to understand the project layout.
    
    Returns:
        dict with keys:
            - full_tree: Complete directory tree with visual structure
            - files_by_type: Files grouped by extension
            - manifests: Configuration files with content previews
            - entry_points: Detected entry point files
            - tech_stack: Detected technologies
            - directory_map: Directory structure with file counts
            - file_sizes: Size information for key files
            - total_files: Total file count
            - total_size: Total workspace size
    """
    try:
        if not WORKSPACE_DIR.exists():
            return {
                'error': 'workspace does not exist',
                'full_tree': '',
                'files_by_type': {},
                'manifests': [],
                'entry_points': [],
                'tech_stack': {},
                'directory_map': {},
                'file_sizes': {},
                'total_files': 0,
                'total_size': 0
            }
        
        log('🔍 Exploring workspace structure...')
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 1: Get complete file tree with tree command (visual structure)
        # ═══════════════════════════════════════════════════════════════════
        tree_result = subprocess.run(
            ['tree', '-a', '-L', '10', '--noreport',
             '-I', 'node_modules|.git|venv|.venv|dist|build|__pycache__|*.pyc'],
            cwd=str(WORKSPACE_DIR),
            capture_output=True, text=True, timeout=10
        )
        
        full_tree = tree_result.stdout if tree_result.returncode == 0 else ''
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 2: Get all files with find (for detailed analysis)
        # ═══════════════════════════════════════════════════════════════════
        find_result = subprocess.run(
            ['find', '.', '-type', 'f',
             '-not', '-path', '*/node_modules/*',
             '-not', '-path', '*/.git/*',
             '-not', '-path', '*/venv/*',
             '-not', '-path', '*/.venv/*',
             '-not', '-path', '*/dist/*',
             '-not', '-path', '*/build/*',
             '-not', '-path', '*/__pycache__/*',
             '-not', '-name', '*.pyc'],
            cwd=str(WORKSPACE_DIR),
            capture_output=True, text=True, timeout=10
        )
        
        if find_result.returncode != 0:
            return {
                'error': 'find command failed',
                'full_tree': full_tree,
                'files_by_type': {},
                'manifests': [],
                'entry_points': [],
                'tech_stack': {},
                'directory_map': {},
                'file_sizes': {},
                'total_files': 0,
                'total_size': 0
            }
        
        all_files = [line.strip() for line in find_result.stdout.splitlines() if line.strip()]
        log(f'📊 Found {len(all_files)} files in workspace')
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 3: Group files by extension
        # ═══════════════════════════════════════════════════════════════════
        files_by_type = {}
        total_size = 0
        file_sizes = {}
        
        for file_path in all_files:
            ext = Path(file_path).suffix.lower() or 'no_extension'
            if ext not in files_by_type:
                files_by_type[ext] = []
            files_by_type[ext].append(file_path)
            
            # Get file size
            try:
                full_path = WORKSPACE_DIR / file_path.lstrip('./')
                if full_path.exists():
                    size = full_path.stat().st_size
                    total_size += size
                    file_sizes[file_path] = size
            except:
                pass
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 4: Identify and read manifest files + key server files
        # ═══════════════════════════════════════════════════════════════════
        manifest_patterns = {
            'package.json': 'nodejs',
            'package-lock.json': 'nodejs',
            'yarn.lock': 'nodejs',
            'requirements.txt': 'python',
            'Pipfile': 'python',
            'pyproject.toml': 'python',
            'setup.py': 'python',
            'Gemfile': 'ruby',
            'Cargo.toml': 'rust',
            'go.mod': 'go',
            'composer.json': 'php',
            'pom.xml': 'java',
            'build.gradle': 'java',
            'Dockerfile': 'docker',
            'docker-compose.yml': 'docker',
            '.env': 'config',
            '.env.example': 'config',
            'tsconfig.json': 'typescript',
            'vite.config.js': 'vite',
            'vite.config.ts': 'vite',
            'webpack.config.js': 'webpack',
            'next.config.js': 'nextjs',
            'nuxt.config.js': 'nuxtjs',
        }
        
        # Also read server files to understand dependencies
        server_file_patterns = {
            'server.js': 'nodejs_server',
            'app.js': 'nodejs_server',
            'index.js': 'nodejs_server',
            'main.js': 'nodejs_server',
            'server.ts': 'nodejs_server',
            'app.py': 'python_server',
            'main.py': 'python_server',
            'wsgi.py': 'python_server',
        }
        
        manifests = []
        tech_stack = {}
        server_files_content = {}
        
        for file_path in all_files:
            filename = Path(file_path).name
            
            # Check if it's a manifest file
            if filename in manifest_patterns:
                depth = len(Path(file_path).parts) - 1
                tech = manifest_patterns[filename]
                
                # Read file content (first 1000 chars for preview)
                content_preview = ''
                try:
                    full_path = WORKSPACE_DIR / file_path.lstrip('./')
                    if full_path.exists():
                        content = full_path.read_text(encoding='utf-8', errors='ignore')
                        content_preview = content[:1000]
                except:
                    pass
                
                manifests.append({
                    'path': file_path,
                    'name': filename,
                    'depth': depth,
                    'tech': tech,
                    'size': file_sizes.get(file_path, 0),
                    'preview': content_preview
                })
                
                if tech not in tech_stack:
                    tech_stack[tech] = []
                tech_stack[tech].append(file_path)
            
            # Check if it's a server file - READ FULL CONTENT for analysis
            if filename in server_file_patterns:
                try:
                    full_path = WORKSPACE_DIR / file_path.lstrip('./')
                    if full_path.exists():
                        content = full_path.read_text(encoding='utf-8', errors='ignore')
                        server_files_content[file_path] = content[:3000]  # First 3000 chars
                        log(f'📖 Read server file: {file_path} ({len(content)} chars)')
                except Exception as e:
                    log(f'Failed to read server file {file_path}: {e}')
        
        manifests.sort(key=lambda m: m['depth'])
        
        # Deduplicate manifests by path (in case of symlinks or duplicates)
        seen_paths = set()
        unique_manifests = []
        for m in manifests:
            if m['path'] not in seen_paths:
                seen_paths.add(m['path'])
                unique_manifests.append(m)
        manifests = unique_manifests
        
        log(f'📦 Found {len(manifests)} manifest files:')
        for m in manifests:
            log(f'   - {m["path"]} ({m["tech"]})')
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 5: Identify entry points
        # ═══════════════════════════════════════════════════════════════════
        entry_point_patterns = {
            'index.html': 'html',
            'index.htm': 'html',
            'main.py': 'python',
            'app.py': 'python',
            'server.py': 'python',
            'wsgi.py': 'python',
            'manage.py': 'django',
            'index.js': 'javascript',
            'server.js': 'javascript',
            'app.js': 'javascript',
            'main.js': 'javascript',
            'index.ts': 'typescript',
            'server.ts': 'typescript',
            'app.ts': 'typescript',
            'main.ts': 'typescript',
            'index.jsx': 'react',
            'App.jsx': 'react',
            'index.tsx': 'react',
            'App.tsx': 'react',
            'main.go': 'go',
            'main.rs': 'rust',
            'Main.java': 'java',
        }
        
        entry_points = []
        for file_path in all_files:
            filename = Path(file_path).name
            if filename in entry_point_patterns:
                entry_points.append({
                    'path': file_path,
                    'name': filename,
                    'type': entry_point_patterns[filename],
                    'depth': len(Path(file_path).parts) - 1,
                    'size': file_sizes.get(file_path, 0)
                })
        
        entry_points.sort(key=lambda e: e['depth'])
        
        # Deduplicate entry points by path
        seen_paths = set()
        unique_entry_points = []
        for e in entry_points:
            if e['path'] not in seen_paths:
                seen_paths.add(e['path'])
                unique_entry_points.append(e)
        entry_points = unique_entry_points
        
        log(f'🎯 Found {len(entry_points)} entry points:')
        for e in entry_points:
            log(f'   - {e["path"]} ({e["type"]})')
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 6: Build directory map
        # ═══════════════════════════════════════════════════════════════════
        directory_map = {}
        for file_path in all_files:
            parts = Path(file_path).parts
            if len(parts) > 1:
                dir_path = '/'.join(parts[:-1])
                if dir_path not in directory_map:
                    directory_map[dir_path] = {
                        'file_count': 0,
                        'files': [],
                        'depth': len(parts) - 1
                    }
                directory_map[dir_path]['file_count'] += 1
                directory_map[dir_path]['files'].append(parts[-1])
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 7: Detect tech stack from file extensions and patterns
        # ═══════════════════════════════════════════════════════════════════
        if '.html' in files_by_type or '.htm' in files_by_type:
            if 'nodejs' not in tech_stack and 'python' not in tech_stack:
                tech_stack['static_html'] = files_by_type.get('.html', []) + files_by_type.get('.htm', [])
        
        if '.jsx' in files_by_type or '.tsx' in files_by_type:
            tech_stack['react'] = files_by_type.get('.jsx', []) + files_by_type.get('.tsx', [])
        
        if '.vue' in files_by_type:
            tech_stack['vue'] = files_by_type.get('.vue', [])
        
        if '.svelte' in files_by_type:
            tech_stack['svelte'] = files_by_type.get('.svelte', [])
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 8: Create intelligent summary with deployment hints
        # ═══════════════════════════════════════════════════════════════════
        
        # Analyze project structure to provide deployment hints
        deployment_hints = []
        
        # Check for monorepo or multi-project structure
        root_manifests = [m for m in manifests if m['depth'] == 0]
        nested_manifests = [m for m in manifests if m['depth'] > 0]
        
        if len(nested_manifests) > 0 and len(root_manifests) == 0:
            deployment_hints.append("Project has nested structure - manifests are in subdirectories")
            
            # Group by directory
            manifest_dirs = {}
            for m in manifests:
                dir_path = str(Path(m['path']).parent)
                if dir_path not in manifest_dirs:
                    manifest_dirs[dir_path] = []
                manifest_dirs[dir_path].append(m['name'])
            
            deployment_hints.append(f"Manifest locations: {manifest_dirs}")
        
        # Detect common patterns
        has_client_server = any('client' in m['path'].lower() for m in manifests) and any('server' in m['path'].lower() for m in manifests)
        has_frontend_backend = any('frontend' in m['path'].lower() for m in manifests) and any('backend' in m['path'].lower() for m in manifests)
        
        if has_client_server:
            deployment_hints.append("Detected client/server architecture - build client first, then start server")
            deployment_hints.append("CRITICAL: Build client with 'cd /project/workspace/client && npm run build', then check server.js for where it expects dist/ folder")
        elif has_frontend_backend:
            deployment_hints.append("Detected frontend/backend architecture - deploy both separately")
        
        # Check for build tools
        if 'vite' in tech_stack:
            deployment_hints.append("Vite detected - use 'npm run build' and serve dist/ folder with try_files for SPA routing")
        if 'react' in tech_stack and 'vite' not in tech_stack:
            deployment_hints.append("React detected - check package.json for build script, serve with try_files for SPA routing")
        
        # Check for Python frameworks
        for m in manifests:
            if m['name'] == 'requirements.txt' and m['preview']:
                if 'flask' in m['preview'].lower():
                    deployment_hints.append(f"Flask detected in {m['path']} - use 'python app.py' or 'flask run'")
                elif 'django' in m['preview'].lower():
                    deployment_hints.append(f"Django detected in {m['path']} - use 'python manage.py runserver'")
                elif 'fastapi' in m['preview'].lower():
                    deployment_hints.append(f"FastAPI detected in {m['path']} - use 'uvicorn' or 'python -m uvicorn'")
        
        # Create a clear file listing for AI with full paths
        manifest_list = [f"{m['path']} ({m['tech']})" for m in manifests]
        entry_point_list = [f"{e['path']} ({e['type']})" for e in entry_points]
        
        # Create directory-based view for AI
        files_by_directory = {}
        for file_path in all_files:
            parts = Path(file_path).parts
            if len(parts) > 1:
                dir_path = '/'.join(parts[:-1])
                filename = parts[-1]
                if dir_path not in files_by_directory:
                    files_by_directory[dir_path] = []
                files_by_directory[dir_path].append(filename)
        
        summary = {
            'full_tree': full_tree,
            'manifest_list': manifest_list,  # NEW: Clear list with full paths
            'entry_point_list': entry_point_list,  # NEW: Clear list with full paths
            'files_by_directory': files_by_directory,  # NEW: Directory-based view
            'server_files_content': server_files_content,  # NEW: Server file contents for analysis
            'files_by_type': {k: v[:20] for k, v in files_by_type.items()},
            'manifests': manifests,  # Detailed manifest data
            'entry_points': entry_points,  # Detailed entry point data
            'tech_stack': tech_stack,
            'directory_map': directory_map,
            'file_sizes': {k: v for k, v in sorted(file_sizes.items(), key=lambda x: x[1], reverse=True)[:20]},
            'total_files': len(all_files),
            'total_size': total_size,
            'total_size_mb': round(total_size / 1024 / 1024, 2),
            'deployment_hints': deployment_hints
        }
        
        log(f'✅ Workspace exploration complete: {len(all_files)} files, {summary["total_size_mb"]} MB')
        log(f'🔧 Tech stack detected: {list(tech_stack.keys())}')
        if server_files_content:
            log(f'📖 Read {len(server_files_content)} server files for analysis')
        if deployment_hints:
            log(f'💡 Deployment hints: {deployment_hints[0]}')
        
        return summary
        
    except Exception as e:
        log(f'❌ Workspace discovery error: {e}')
        import traceback
        traceback.print_exc()
        return {
            'error': f'discovery failed: {e}',
            'full_tree': '',
            'files_by_type': {},
            'manifests': [],
            'entry_points': [],
            'tech_stack': {},
            'directory_map': {},
            'file_sizes': {},
            'total_files': 0,
            'total_size': 0
        }


def _read_referenced_logs(build_output: str) -> str:
    """
    Scan build output for referenced log file paths (e.g. npm debug logs).
    For each path found, read the most relevant section using tail/head.
    """
    # Broader patterns for log files
    log_path_patterns = [
        r'A complete log of this run can be found in:\s*([^\n]+)',
        r'npm error.*?([/\w._-]*\w+\.log)',
        r'error log.*?([/\w._-]*\w+\.log)',
        r'see ([/\w._-]*\w+\.log) for details',
        r'logfile\s*=\s*([/\w._-]*\w+\.log)',
        r'results in:?\s*([/\w._-]*\w+\.log)',
    ]

    found_logs = []
    for pattern in log_path_patterns:
        for match in re.finditer(pattern, build_output, re.IGNORECASE):
            path = match.group(1).strip()
            if not path: continue
            
            # Try to resolve relative paths if possible
            p = Path(path)
            if not p.is_absolute():
                # Check relative to root and workspace
                candidates = [Path('/project/workspace') / path, Path('/root') / path, Path('/') / path]
                for c in candidates:
                    if c.exists():
                        p = c
                        break
            
            if p.exists() and p.is_file():
                found_logs.append(str(p))

    return found_logs


def _harvest_dynamic_logs(window_minutes: int = 5) -> list:
    """
    Search for ANY recently modified log files in standard system paths
    and the workspace. This captures 'silent' errors from background services.
    """
    search_paths = ['/var/log', '/root', '/tmp', str(WORKSPACE_DIR)]
    found = []
    now = time.time()
    
    for base in search_paths:
        if not os.path.exists(base): continue
        try:
            # Look for *.log, *.err, *.out, *-log, *-err
            for fp in Path(base).rglob('*'):
                if fp.is_file() and any(ext in fp.name.lower() for ext in ['.log', '.err', '.out', '-log', '-err']):
                    # Ignore known noise
                    if any(noise in str(fp) for noise in ['/node_modules/', '/.git/', '/venv/']):
                        continue
                        
                    # Check modification time
                    mtime = os.path.getmtime(str(fp))
                    if (now - mtime) < (window_minutes * 60):
                        found.append(str(fp))
        except:
            pass
            
    return found


def _detect_previous_deployment() -> dict:
    """
    Detect if there was a previous successful deployment by checking for:
    - Running processes (PM2, Gunicorn, Uvicorn, serve, node, python)
    - Nginx configuration
    - Built artifacts (dist/, build/, .next/)
    
    Returns:
        dict with:
            - has_deployment: bool
            - app_port: int or None
            - process_info: str
            - nginx_config: str or None
            - built_artifacts: list of paths
    """
    result = {
        'has_deployment': False,
        'app_port': None,
        'process_info': '',
        'nginx_config': None,
        'built_artifacts': []
    }
    
    try:
        # Check for running app processes
        ps_result = subprocess.run(
            ['ps', 'aux'],
            capture_output=True, text=True, timeout=5
        )
        
        if ps_result.returncode == 0:
            process_keywords = ['pm2', 'gunicorn', 'uvicorn', 'serve', 'node', 'python', 'flask', 'fastapi']
            app_processes = []
            
            for line in ps_result.stdout.splitlines():
                line_lower = line.lower()
                if any(kw in line_lower for kw in process_keywords):
                    # Skip grep and ps itself
                    if 'grep' not in line_lower and 'ps aux' not in line_lower:
                        app_processes.append(line.strip())
            
            if app_processes:
                result['process_info'] = '\n'.join(app_processes[:5])
                result['has_deployment'] = True
        
        # Check for listening ports (app ports)
        ss_result = subprocess.run(
            ['ss', '-tlnp'],
            capture_output=True, text=True, timeout=5
        )
        
        if ss_result.returncode == 0:
            for line in ss_result.stdout.splitlines():
                # Look for non-80 ports (app ports)
                match = re.search(r':(\d+)\s', line)
                if match:
                    port = int(match.group(1))
                    if port != 80 and 3000 <= port <= 9000:
                        result['app_port'] = port
                        result['has_deployment'] = True
                        break
        
        # Check nginx config
        nginx_conf_path = Path('/etc/nginx/sites-available/default')
        if nginx_conf_path.exists():
            try:
                nginx_content = nginx_conf_path.read_text()
                # Check if it's not just the baseline loading page
                if 'proxy_pass' in nginx_content:
                    result['nginx_config'] = nginx_content
                    result['has_deployment'] = True
                    
                    # Extract app port from nginx config
                    port_match = re.search(r'proxy_pass\s+http://[^:]+:(\d+)', nginx_content)
                    if port_match and not result['app_port']:
                        result['app_port'] = int(port_match.group(1))
            except:
                pass
        
        # Check for built artifacts
        artifact_dirs = ['dist', 'build', '.next', 'out', 'public']
        for dir_name in artifact_dirs:
            artifact_path = WORKSPACE_DIR / dir_name
            if artifact_path.exists() and artifact_path.is_dir():
                # Check if it has files
                try:
                    files = list(artifact_path.iterdir())
                    if files:
                        result['built_artifacts'].append(str(artifact_path.relative_to(PROJECT_DIR)))
                        result['has_deployment'] = True
                except:
                    pass
        
        log(f'Previous deployment detection: {result["has_deployment"]}, port: {result["app_port"]}, artifacts: {result["built_artifacts"]}')
        
    except Exception as e:
        log(f'Previous deployment detection error: {e}')
    
    return result


def _get_combined_logs(build_output: str) -> str:
    """
    Combine logs found via reference in output AND logs found via dynamic search.
    """
    referenced = _read_referenced_logs(build_output)
    dynamic    = _harvest_dynamic_logs()
    
    all_paths = list(set(referenced + dynamic))
    if not all_paths:
        return ''
        
    results = []
    # Cap at 5 most relevant logs to avoid context bloat
    for log_path in all_paths[:5]:
        try:
            p = Path(log_path)
            if not p.exists(): continue
            
            # Read tail of the log
            res = subprocess.run(['tail', '-n', '60', str(p)], capture_output=True, text=True, timeout=3)
            content = res.stdout.strip()
            if content:
                results.append(f"--- LOG: {log_path} (Last 60 lines) ---\n{content}")
        except:
            pass
            
    return '\n\n'.join(results)


def _read_manifests() -> dict:
    """
    Find and read key configuration files with metadata.
    
    Returns:
        dict mapping file paths to dict with:
            - content: file content (first 4KB)
            - depth: depth from workspace root
            - size: file size in bytes
            - tech: detected tech stack
    """
    if not WORKSPACE_DIR.exists():
        return {}
    
    targets = [
        'package.json', 'package-lock.json', 'yarn.lock',
        'requirements.txt', 'Pipfile', 'Pipfile.lock', 'pyproject.toml',
        'main.py', 'app.py', 'server.py', 'wsgi.py',
        'index.html', 'index.htm',
        'vite.config.js', 'next.config.js', 'nuxt.config.js',
        'server.js', 'app.js', 'index.js',
        'Gemfile', 'Cargo.toml', 'go.mod', 'composer.json',
        'pom.xml', 'build.gradle', 'Makefile', 'Dockerfile'
    ]
    
    # Tech stack detection mapping
    tech_map = {
        'package.json': 'nodejs',
        'package-lock.json': 'nodejs',
        'yarn.lock': 'nodejs',
        'requirements.txt': 'python',
        'Pipfile': 'python',
        'pyproject.toml': 'python',
        'Gemfile': 'ruby',
        'Cargo.toml': 'rust',
        'go.mod': 'go',
        'composer.json': 'php',
        'pom.xml': 'java',
        'build.gradle': 'java'
    }
    
    found_files = []
    
    # Search recursively without depth limits (but skip heavy directories)
    try:
        for fp in WORKSPACE_DIR.rglob('*'):
            # Skip excluded directories
            if any(excluded in fp.parts for excluded in ['node_modules', '.git', 'venv', '.venv', 'dist', 'build', '__pycache__']):
                continue
            
            if fp.is_file() and fp.name in targets:
                found_files.append(fp)
    except Exception as e:
        log(f'Manifest search error: {e}')
    
    # Build manifest dictionary with metadata
    manifests = {}
    for fp in found_files:
        try:
            rel_path = str(fp.relative_to(WORKSPACE_DIR))
            depth = len(Path(rel_path).parts)
            size = fp.stat().st_size
            
            # Read content (first 4KB)
            content = fp.read_text(encoding='utf-8', errors='replace')[:4000]
            
            # Detect tech stack
            tech = tech_map.get(fp.name, 'unknown')
            
            # Special case: detect static HTML
            if fp.name in ['index.html', 'index.htm']:
                # Check if there's a package.json nearby
                has_package_json = (fp.parent / 'package.json').exists()
                if not has_package_json:
                    tech = 'static_html'
            
            manifests[rel_path] = {
                'content': content,
                'depth': depth,
                'size': size,
                'tech': tech
            }
        except Exception as e:
            log(f'Error reading manifest {fp}: {e}')
    
    # Sort by depth (root-level first) and return
    sorted_manifests = dict(sorted(manifests.items(), key=lambda item: item[1]['depth']))
    
    return sorted_manifests


def _health_check(app_port: int = None) -> tuple:
    """
    Perform health check on the deployed application.
    
    Args:
        app_port: Internal port the application should be listening on
    
    Returns:
        tuple: (healthy: bool, status_message: str)
    """
    try:
        # Check nginx response (port 80)
        res = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', '--max-time', '4', 'http://127.0.0.1'],
            capture_output=True, text=True
        )
        nginx_code = res.stdout.strip()
        nginx_healthy = nginx_code in ('200', '301', '302', '304')
        
        # If app_port is provided, verify app is actually listening on that port
        if app_port:
            try:
                port_check = subprocess.run(
                    ['ss', '-tlnp'],
                    capture_output=True, text=True, timeout=3
                )
                
                if port_check.returncode == 0:
                    # Check if app_port is in the listening ports
                    app_listening = f':{app_port}' in port_check.stdout
                    
                    if not app_listening:
                        return False, f'Nginx: HTTP {nginx_code}, App: not listening on port {app_port}'
                    
                    # Both nginx and app are healthy
                    if nginx_healthy:
                        return True, f'Nginx: HTTP {nginx_code}, App: listening on port {app_port}'
                    else:
                        return False, f'Nginx: HTTP {nginx_code}, App: listening on port {app_port}'
                else:
                    # Can't verify port, fall back to nginx check only
                    log(f'Port check failed, falling back to nginx-only health check')
                    if nginx_healthy:
                        return True, f'HTTP {nginx_code} (port check unavailable)'
                    return False, f'HTTP {nginx_code}'
            except Exception as e:
                log(f'App port verification error: {e}')
                # Fall back to nginx check only
                if nginx_healthy:
                    return True, f'HTTP {nginx_code} (port verification failed)'
                return False, f'HTTP {nginx_code}'
        else:
            # No app_port provided, use nginx check only (backward compatibility)
            if nginx_healthy:
                return True, f'HTTP {nginx_code}'
            return False, f'HTTP {nginx_code}'
            
    except Exception as e:
        return False, str(e)


def _test_changes_automatically(changed_files: list, user_prompt: str, app_port: int) -> dict:
    """
    Automatically test the changes made to the application.
    
    1. Analyze what changed (endpoints, components, features)
    2. Generate test cases (GET/POST requests with payloads)
    3. Execute tests against the running app
    4. Verify responses match expectations
    5. Auto-fix if tests fail OR ask user if uncertain
    
    Args:
        changed_files: List of files that were modified
        user_prompt: Original user request
        app_port: Internal port the app is running on
    
    Returns:
        dict with:
            - success: bool
            - tests_passed: int
            - tests_failed: int
            - test_results: list of test results
            - needs_user_input: bool
            - fix_applied: bool
    """
    report('🧪 Testing your changes automatically...')
    log(f'Changed files: {changed_files}')
    log(f'User request: {user_prompt}')
    
    # Read the changed files to understand what was modified
    changed_content = {}
    for filepath in changed_files:
        try:
            full_path = WORKSPACE_DIR / filepath
            if full_path.exists():
                changed_content[filepath] = full_path.read_text(encoding='utf-8')[:2000]
        except Exception as e:
            log(f'Could not read {filepath}: {e}')
    
    # Format file context for AI without using backslashes in f-string expression
    file_list_str = []
    for path, content in changed_content.items():
        snippet = content[:500]
        file_list_str.append(f"// {path}\n{snippet}")
    formatted_files = "\n\n".join(file_list_str)

    # Ask AI to generate test cases based on the changes
    test_generation_prompt = f"""You are a QA engineer. Analyze the code changes and generate test cases.

USER REQUEST: {user_prompt}

CHANGED FILES:
{formatted_files}

YOUR TASK:
1. Identify what endpoints/features were modified
2. Generate test cases to verify the changes work correctly
3. Include both positive and negative test cases
4. Start with a brief explanation of what you're testing and why (1-2 sentences)

OUTPUT FORMAT (JSON):
{{
  "thinking": "I'm testing the new /api/stats endpoint to verify it returns the correct user count and responds with valid JSON.",
  "endpoints_to_test": [
    {{
      "method": "GET",
      "path": "/api/endpoint",
      "description": "Test description",
      "payload": null,
      "expected_status": 200,
      "expected_response_contains": ["key1", "key2"]
    }},
    {{
      "method": "POST",
      "path": "/api/endpoint",
      "description": "Test description",
      "payload": {{"key": "value"}},
      "expected_status": 201,
      "expected_response_contains": ["success"]
    }}
  ],
  "ui_tests": [
    {{
      "description": "Check if button color changed to blue",
      "selector": "button",
      "expected_style": {{"background": "blue"}}
    }}
  ]
}}

If no API endpoints were changed, return empty endpoints_to_test array.
If only UI was changed, focus on ui_tests.
ALWAYS include "thinking" field explaining what you're testing.
Output ONLY valid JSON, no explanations."""

    try:
        response = call_ai([
            {'role': 'system', 'content': 'You are a QA engineer generating test cases. Output only valid JSON.'},
            {'role': 'user', 'content': test_generation_prompt},
        ], temperature=0.1, show_thinking=True)  # Show test generation thinking
        
        # Parse JSON response
        response = re.sub(r'^```[a-z]*\n?', '', response.strip(), flags=re.MULTILINE)
        response = re.sub(r'\n?```$', '', response.strip(), flags=re.MULTILINE)
        m = re.search(r'\{.*\}', response, re.DOTALL)
        if not m:
            log('⚠️ AI did not return valid JSON for test cases')
            return {'success': False, 'tests_passed': 0, 'tests_failed': 0, 'test_results': [], 'needs_user_input': False, 'fix_applied': False}
        
        test_plan = json.loads(m.group(0))
        log(f'Generated test plan: {len(test_plan.get("endpoints_to_test", []))} endpoint tests, {len(test_plan.get("ui_tests", []))} UI tests')
        
    except Exception as e:
        log(f'Failed to generate test cases: {e}')
        return {'success': False, 'tests_passed': 0, 'tests_failed': 0, 'test_results': [], 'needs_user_input': False, 'fix_applied': False}
    
    # Execute endpoint tests
    test_results = []
    tests_passed = 0
    tests_failed = 0
    
    for test in test_plan.get('endpoints_to_test', []):
        log(f'🧪 Testing: {test["method"]} {test["path"]}')
        report(f'🧪 Testing: {test["description"]}')
        
        try:
            url = f'http://127.0.0.1:{app_port}{test["path"]}'
            method = test['method'].upper()
            payload = test.get('payload')
            expected_status = test.get('expected_status', 200)
            expected_contains = test.get('expected_response_contains', [])
            
            # Execute request
            if method == 'GET':
                result = subprocess.run(
                    ['curl', '-s', '-w', '\\n%{http_code}', '-X', 'GET', url],
                    capture_output=True, text=True, timeout=10
                )
            elif method == 'POST':
                payload_json = json.dumps(payload) if payload else '{}'
                result = subprocess.run(
                    ['curl', '-s', '-w', '\\n%{http_code}', '-X', 'POST', '-H', 'Content-Type: application/json', '-d', payload_json, url],
                    capture_output=True, text=True, timeout=10
                )
            else:
                log(f'⚠️ Unsupported method: {method}')
                continue
            
            if result.returncode != 0:
                log(f'❌ Request failed: {result.stderr}')
                tests_failed += 1
                test_results.append({
                    'test': test['description'],
                    'status': 'failed',
                    'reason': f'Request failed: {result.stderr}'
                })
                continue
            
            # Parse response
            output = result.stdout.strip()
            lines = output.split('\n')
            status_code = lines[-1] if lines else '000'
            response_body = '\n'.join(lines[:-1]) if len(lines) > 1 else ''
            
            log(f'Response status: {status_code}')
            log(f'Response body preview: {response_body[:200]}')
            
            # Verify status code
            if status_code != str(expected_status):
                log(f'❌ Status code mismatch: expected {expected_status}, got {status_code}')
                tests_failed += 1
                test_results.append({
                    'test': test['description'],
                    'status': 'failed',
                    'reason': f'Status code mismatch: expected {expected_status}, got {status_code}',
                    'response': response_body[:500]
                })
                continue
            
            # Verify response contains expected keys/values
            all_found = True
            for expected in expected_contains:
                if expected not in response_body:
                    log(f'❌ Expected "{expected}" not found in response')
                    all_found = False
            
            if not all_found:
                tests_failed += 1
                test_results.append({
                    'test': test['description'],
                    'status': 'failed',
                    'reason': f'Expected content not found in response',
                    'response': response_body[:500]
                })
                continue
            
            # Test passed!
            log(f'✅ Test passed: {test["description"]}')
            tests_passed += 1
            test_results.append({
                'test': test['description'],
                'status': 'passed',
                'response': response_body[:200]
            })
            
        except Exception as e:
            log(f'❌ Test error: {e}')
            tests_failed += 1
            test_results.append({
                'test': test['description'],
                'status': 'error',
                'reason': str(e)
            })
    
    # Report results
    total_tests = tests_passed + tests_failed
    if total_tests == 0:
        report('ℹ️ No API endpoint tests were needed for this change.')
        return {'success': True, 'tests_passed': 0, 'tests_failed': 0, 'test_results': [], 'needs_user_input': False, 'fix_applied': False}
    
    if tests_failed == 0:
        report(f'✅ All {tests_passed} tests passed! Your changes are working correctly.')
        return {'success': True, 'tests_passed': tests_passed, 'tests_failed': 0, 'test_results': test_results, 'needs_user_input': False, 'fix_applied': False}
    
    # Some tests failed - try to auto-fix
    report(f'⚠️ {tests_failed} out of {total_tests} tests failed. Analyzing failures...')
    
    # Format file context for AI without using backslashes in f-string expression
    file_list_str = []
    for path, content in changed_content.items():
        snippet = content[:500]
        file_list_str.append(f"// {path}\n{snippet}")
    formatted_files = "\n\n".join(file_list_str)

    # Ask AI to analyze failures and suggest fixes
    failure_analysis_prompt = f"""You are debugging test failures. Analyze the failures and suggest fixes.

USER REQUEST: {user_prompt}

CHANGED FILES:
{formatted_files}

TEST RESULTS:
{json.dumps([r for r in test_results if r['status'] == 'failed'], indent=2)}

YOUR TASK:
1. Analyze why the tests failed
2. Determine if you can fix it automatically OR if you need user input
3. If fixable: provide the fix using // PATCH: format
4. If not fixable: explain what you need from the user

OUTPUT FORMAT:
{{
  "can_auto_fix": true/false,
  "analysis": "Explanation of what went wrong",
  "fix": "// PATCH: file.ext\\n<<<SEARCH\\n...\\n>>>\\n<<<REPLACE\\n...\\n>>>",
  "user_question": "What should the endpoint return?" (if can_auto_fix is false)
}}

Output ONLY valid JSON."""

    try:
        fix_response = call_ai([
            {'role': 'system', 'content': 'You are a debugging expert. Output only valid JSON.'},
            {'role': 'user', 'content': failure_analysis_prompt},
        ], temperature=0.2, show_thinking=True)  # Show debugging thinking
        
        # Parse JSON response
        fix_response = re.sub(r'^```[a-z]*\n?', '', fix_response.strip(), flags=re.MULTILINE)
        fix_response = re.sub(r'\n?```$', '', fix_response.strip(), flags=re.MULTILINE)
        m = re.search(r'\{.*\}', fix_response, re.DOTALL)
        if not m:
            log('⚠️ AI did not return valid JSON for fix analysis')
            report(f'⚠️ Tests failed but I need your help. Please check the logs.')
            return {'success': False, 'tests_passed': tests_passed, 'tests_failed': tests_failed, 'test_results': test_results, 'needs_user_input': True, 'fix_applied': False}
        
        fix_plan = json.loads(m.group(0))
        
        if fix_plan.get('can_auto_fix'):
            # Apply the fix
            report(f'🔧 I found the issue: {fix_plan["analysis"]}')
            report(f'🔧 Applying automatic fix...')
            
            fix_code = fix_plan.get('fix', '')
            if fix_code:
                # Parse and apply the fix
                patch_marker_re = re.compile(r'//\s*PATCH:\s*([^\n]+)', re.IGNORECASE)
                patch_matches = list(patch_marker_re.finditer(fix_code))
                
                if patch_matches:
                    patches_applied = _apply_patches(fix_code, patch_matches)
                    if patches_applied > 0:
                        report(f'✅ Fix applied! Rebuilding to test again...')
                        return {'success': False, 'tests_passed': tests_passed, 'tests_failed': tests_failed, 'test_results': test_results, 'needs_user_input': False, 'fix_applied': True}
        
        # Can't auto-fix - ask user
        user_question = fix_plan.get('user_question', 'The tests failed. Can you provide more details about what you expected?')
        
        suggestions = [
            {'text': 'Provide more details', 'action': 'clarify', 'icon': '💬', 'prompt': None},
            {'text': 'Fix it automatically', 'action': 'auto_fix', 'icon': '🤖', 'prompt': 'Fix it based on your best judgment'},
            {'text': 'Show test results', 'action': 'show_tests', 'icon': '📊', 'prompt': 'Show me the detailed test results'},
            {'text': 'Skip tests', 'action': 'skip_tests', 'icon': '⏭️', 'prompt': 'Skip the tests and continue'}
        ]
        
        metadata = {
            'type': 'question',
            'requires_response': True,
            'context': 'test_failure',
            'tests_passed': tests_passed,
            'tests_failed': tests_failed
        }
        
        report(f'❓ {fix_plan["analysis"]}', 
               suggestions=suggestions, 
               metadata=metadata,
               summary='Tests failed - need your input')
        report(f'❓ {user_question}',
               suggestions=suggestions,
               metadata=metadata,
               summary=user_question[:100])
        
        return {'success': False, 'tests_passed': tests_passed, 'tests_failed': tests_failed, 'test_results': test_results, 'needs_user_input': True, 'fix_applied': False}
        
    except Exception as e:
        log(f'Failed to analyze test failures: {e}')
        report(f'⚠️ {tests_failed} tests failed. Please review and let me know what to fix.')
        return {'success': False, 'tests_passed': tests_passed, 'tests_failed': tests_failed, 'test_results': test_results, 'needs_user_input': True, 'fix_applied': False}


def _detect_available_ports() -> list:
    """
    Detect available internal ports for application binding.
    
    Returns:
        list of available port numbers
    """
    candidate_ports = [3000, 5000, 8000, 8080, 4000, 5001, 8001, 3001, 9000]
    available = []
    
    try:
        # Get list of listening ports
        result = subprocess.run(
            ['ss', '-tlnp'],
            capture_output=True, text=True, timeout=3
        )
        
        if result.returncode == 0:
            listening_ports = set()
            for line in result.stdout.splitlines():
                # Extract port from lines like "LISTEN 0 128 *:3000 *:*"
                match = re.search(r':(\d+)\s', line)
                if match:
                    listening_ports.add(int(match.group(1)))
            
            # Filter out ports that are already in use
            available = [p for p in candidate_ports if p not in listening_ports and p != 80]
        else:
            # If ss command fails, return all candidate ports except 80
            available = [p for p in candidate_ports if p != 80]
    except Exception as e:
        log(f'Port detection error: {e}')
        # Fallback to default ports
        available = [3000, 5000, 8000, 8080]
    
    # Ensure we always have at least some ports available
    if not available:
        available = [3000, 5000, 8000]
    
    return available


def _auto_fix_syntax_error(error_output: str, workspace_discovery: dict) -> dict:
    """
    Automatically fix syntax errors in code files.
    
    Args:
        error_output: Build error output containing syntax error details
        workspace_discovery: Workspace structure data
    
    Returns:
        dict with:
            - fixed: bool (whether fix was applied)
            - file: str (file that was fixed)
            - error: str (error message if failed)
    """
    try:
        # Clean the error output - remove emoji prefixes and extra whitespace
        cleaned_error = re.sub(r'^[📦🛠️✅⚠️💬🔧]+\s*', '', error_output, flags=re.MULTILINE)
        
        log(f'Analyzing syntax error (cleaned output length: {len(cleaned_error)} chars)')
        log(f'Error preview: {cleaned_error[:300]}')
        
        # Extract file path and line number from error
        # Python: File "/path/to/file.py", line 76
        # JavaScript: /path/to/file.js:76:10
        
        file_match = re.search(r'File "([^"]+)", line (\d+)', cleaned_error)
        if not file_match:
            file_match = re.search(r'([^\s]+\.(?:py|js|jsx|ts|tsx)):(\d+):', cleaned_error)
        
        if not file_match:
            log('Could not extract file path from error')
            log(f'Tried to match in: {cleaned_error[:500]}')
            return {'fixed': False, 'error': 'Could not parse error location'}
        
        error_file = file_match.group(1)
        error_line = int(file_match.group(2))
        
        # Convert to relative path
        if error_file.startswith('/project/workspace/'):
            error_file = error_file.replace('/project/workspace/', '')
        
        log(f'Syntax error detected in {error_file} at line {error_line}')
        
        # Read the problematic file
        file_path = WORKSPACE_DIR / error_file
        if not file_path.exists():
            log(f'File not found: {file_path}')
            return {'fixed': False, 'error': f'File not found: {error_file}'}
        
        file_content = file_path.read_text(encoding='utf-8')
        lines = file_content.splitlines()
        
        # Validate line number
        if error_line > len(lines):
            log(f'Error line {error_line} exceeds file length {len(lines)}')
            error_line = len(lines)
        
        # Get context around the error (30 lines before and after for better context)
        start_line = max(0, error_line - 30)
        end_line = min(len(lines), error_line + 30)
        context = '\n'.join(lines[start_line:end_line])
        
        # Extract the specific error type from the output
        error_type = 'SyntaxError'
        if 'IndentationError' in cleaned_error:
            error_type = 'IndentationError'
        elif 'TabError' in cleaned_error:
            error_type = 'TabError'
        
        log(f'Error type: {error_type}')
        log(f'Providing context: lines {start_line+1} to {end_line}')
        
        # Ask AI to fix the syntax error
        fix_prompt = f"""You are a code repair expert. Fix the {error_type} in this code.

ERROR OUTPUT:
{cleaned_error[:1500]}

FILE: {error_file}
ERROR LINE: {error_line}
ERROR TYPE: {error_type}

CODE CONTEXT (lines {start_line+1} to {end_line}):
```
{context}
```

CRITICAL INSTRUCTIONS:
1. Identify the exact syntax error at or near line {error_line}
2. Fix it with minimal changes (only fix the error, don't refactor)
3. PRESERVE EXACT INDENTATION - copy spaces/tabs exactly as shown
4. PRESERVE EXACT FORMATTING - copy every character exactly
5. Include 5-10 lines of context before and after the error line
6. The SEARCH block must match the file EXACTLY (character-by-character including spaces)

COMMON MISTAKES TO AVOID:
- Missing leading spaces/indentation
- Missing colons, quotes, or other punctuation
- Changing variable names or code structure
- Not including enough context

OUTPUT FORMAT (use EXACTLY this format):
// PATCH: {error_file}
<<<SEARCH
[EXACT lines from the code above, including ALL indentation and 5-10 lines of context]
>>>
<<<REPLACE
[Same lines with ONLY the syntax error fixed, preserve everything else]
>>>

Output ONLY the patch, no explanations."""

        log('Calling AI to generate fix...')
        response = call_ai([
            {'role': 'system', 'content': 'You are a code repair expert. Fix syntax errors with minimal changes. Always use the PATCH format with SEARCH/REPLACE blocks.'},
            {'role': 'user', 'content': fix_prompt},
        ], temperature=0.1, show_thinking=True)
        
        log(f'AI response length: {len(response)} chars')
        log(f'AI response preview: {response[:300]}')
        
        # Apply the patch
        patch_marker_re = re.compile(r'//\s*PATCH:\s*([^\n]+)', re.IGNORECASE)
        patch_matches = list(patch_marker_re.finditer(response))
        
        log(f'Found {len(patch_matches)} PATCH markers')
        
        if patch_matches:
            # First, check if the AI returned identical SEARCH/REPLACE (no actual fix)
            hunk_re = re.compile(r'<<<SEARCH\n(.*?)\n>>>\n<<<REPLACE\n(.*?)\n>>>', re.DOTALL)
            hunks = list(hunk_re.finditer(response))
            
            if hunks:
                search_text = hunks[0].group(1)
                replace_text = hunks[0].group(2)
                
                # Check for truncated/corrupted patches
                search_lines = search_text.splitlines()
                replace_lines = replace_text.splitlines()
                
                # Validation 1: Check for incomplete lines (truncated mid-word)
                for line in replace_lines:
                    # Check if line ends with incomplete word (no space, colon, paren, etc.)
                    stripped = line.rstrip()
                    if stripped and len(stripped) > 2:
                        last_chars = stripped[-4:]
                        # If ends with partial word (letters only, no punctuation)
                        if last_chars.isalpha() and len(stripped) < 10:
                            log(f'⚠️ Detected truncated line in REPLACE: "{line}"')
                            log(f'This looks like an incomplete/corrupted patch')
                            return {'fixed': False, 'error': 'AI returned truncated/corrupted patch'}
                
                # Validation 2: Check if REPLACE is significantly shorter than SEARCH (likely truncated)
                if len(replace_text) < len(search_text) * 0.5 and len(search_text) > 50:
                    log(f'⚠️ REPLACE block is much shorter than SEARCH ({len(replace_text)} vs {len(search_text)} chars)')
                    log(f'This suggests the AI response was truncated')
                    return {'fixed': False, 'error': 'AI response appears truncated'}
                
                # Validation 3: Check for identical blocks
                if search_text == replace_text:
                    log('⚠️ AI returned identical SEARCH and REPLACE blocks - no actual fix')
                    log(f'This means the AI thinks the code is already correct')
                    log(f'The syntax error might be elsewhere or misidentified')
                    
                    # Try to give more context and ask again
                    log('Attempting second fix with more explicit instructions...')
                    
                    retry_prompt = f"""CRITICAL: The previous fix attempt returned identical SEARCH/REPLACE blocks.

The syntax error is REAL and needs to be fixed. Look carefully at line {error_line}.

ERROR OUTPUT:
{cleaned_error[:1500]}

FILE: {error_file}
ERROR LINE: {error_line}
ERROR TYPE: {error_type}

FULL FILE CONTENT:
```
{file_content}
```

The error is at or near line {error_line}. Find the ACTUAL syntax error and fix it.

Common Python syntax errors:
- Missing colon after if/def/class/for/while
- Missing closing parenthesis/bracket/brace
- Incorrect indentation
- Missing quotes

OUTPUT FORMAT:
// PATCH: {error_file}
<<<SEARCH
[EXACT lines with the error, including context]
>>>
<<<REPLACE
[CORRECTED lines]
>>>

The SEARCH and REPLACE blocks MUST be DIFFERENT. Output ONLY the patch."""

                    retry_response = call_ai([
                        {'role': 'system', 'content': 'You are a code repair expert. The SEARCH and REPLACE blocks must be different - you must actually fix something.'},
                        {'role': 'user', 'content': retry_prompt},
                    ], temperature=0.2, show_thinking=True)
                    
                    # Try to apply the retry response
                    retry_patch_matches = list(patch_marker_re.finditer(retry_response))
                    if retry_patch_matches:
                        patches_applied = _apply_patches(retry_response, retry_patch_matches)
                        if patches_applied > 0:
                            log(f'✅ Applied {patches_applied} patches from retry')
                            return {'fixed': True, 'file': error_file}
                    
                    # If retry also failed, continue to fallback
                    log('Retry also failed, trying fallback...')
            
            patches_applied = _apply_patches(response, patch_matches)
            if patches_applied > 0:
                log(f'✅ Applied {patches_applied} patches to fix syntax error')
                return {'fixed': True, 'file': error_file}
            else:
                log('⚠️ Patches found but none applied successfully - trying direct fix approach')
                
                # FALLBACK: If patch didn't match, try to fix the specific line directly
                # This handles cases where AI didn't preserve exact formatting
                try:
                    # Extract what the AI thinks the fix should be
                    hunk_re = re.compile(r'<<<SEARCH\n(.*?)\n>>>\n<<<REPLACE\n(.*?)\n>>>', re.DOTALL)
                    hunks = list(hunk_re.finditer(response))
                    
                    if hunks:
                        search_text = hunks[0].group(1)
                        replace_text = hunks[0].group(2)
                        
                        # Try to identify what changed between search and replace
                        search_lines = search_text.splitlines()
                        replace_lines = replace_text.splitlines()
                        
                        log(f'Fallback: Analyzing {len(search_lines)} search lines vs {len(replace_lines)} replace lines')
                        
                        # Read the actual file
                        file_content = file_path.read_text(encoding='utf-8')
                        file_lines = file_content.splitlines()
                        
                        # Strategy 1: Find what changed and apply to error line directly
                        # Compare search vs replace to understand the fix
                        for i, (s_line, r_line) in enumerate(zip(search_lines, replace_lines)):
                            if s_line.strip() != r_line.strip():
                                log(f'Fallback: Found difference at line {i}')
                                log(f'  Search:  "{s_line.strip()}"')
                                log(f'  Replace: "{r_line.strip()}"')
                                
                                # Python often reports syntax errors on the NEXT line
                                # So check error_line AND error_line-1
                                lines_to_check = []
                                if error_line <= len(file_lines):
                                    lines_to_check.append((error_line, file_lines[error_line - 1]))
                                if error_line > 1:
                                    lines_to_check.append((error_line - 1, file_lines[error_line - 2]))
                                
                                for line_num, actual_line in lines_to_check:
                                    log(f'Fallback: Checking line {line_num}: "{actual_line.strip()}"')
                                    
                                    # If the actual line matches the search pattern (stripped), apply the fix
                                    if actual_line.strip() == s_line.strip():
                                        log(f'Fallback: Line {line_num} matches search pattern - applying fix')
                                        original_indent = len(actual_line) - len(actual_line.lstrip())
                                        fixed_line = ' ' * original_indent + r_line.strip()
                                        file_lines[line_num - 1] = fixed_line
                                        
                                        # Write back
                                        file_path.write_text('\n'.join(file_lines), encoding='utf-8')
                                        log(f'✅ Fallback fix applied to line {line_num}')
                                        return {'fixed': True, 'file': error_file}
                                
                                # Strategy 2: Search nearby lines for the pattern
                                search_start = max(0, error_line - 10)
                                search_end = min(len(file_lines), error_line + 10)
                                
                                log(f'Fallback: Searching lines {search_start+1} to {search_end} for pattern')
                                for j in range(search_start, search_end):
                                    if file_lines[j].strip() == s_line.strip():
                                        log(f'Fallback: Found matching line at file line {j+1}')
                                        # Preserve the original indentation
                                        original_indent = len(file_lines[j]) - len(file_lines[j].lstrip())
                                        fixed_line = ' ' * original_indent + r_line.strip()
                                        file_lines[j] = fixed_line
                                        
                                        # Write back
                                        file_path.write_text('\n'.join(file_lines), encoding='utf-8')
                                        log(f'✅ Fallback fix applied to line {j+1}')
                                        return {'fixed': True, 'file': error_file}
                                
                                break  # Only process first difference
                        
                        # Strategy 3: If no differences found, maybe it's a simple character addition
                        # Try to understand what was added/removed
                        if len(search_lines) == len(replace_lines):
                            log('Fallback: Trying character-level diff')
                            for i, (s_line, r_line) in enumerate(zip(search_lines, replace_lines)):
                                if s_line != r_line:
                                    # Find what was added
                                    if r_line.startswith(s_line):
                                        added = r_line[len(s_line):]
                                        log(f'Fallback: Detected addition: "{added}"')
                                    elif s_line in r_line:
                                        log(f'Fallback: Detected character insertion')
                                    
                                    # Apply to error line
                                    if error_line <= len(file_lines):
                                        actual_line = file_lines[error_line - 1]
                                        # Try simple replacement
                                        if s_line.strip() in actual_line:
                                            fixed_line = actual_line.replace(s_line.strip(), r_line.strip())
                                            file_lines[error_line - 1] = fixed_line
                                            file_path.write_text('\n'.join(file_lines), encoding='utf-8')
                                            log(f'✅ Fallback fix applied via replacement to line {error_line}')
                                            return {'fixed': True, 'file': error_file}
                        
                        log('⚠️ Fallback: Could not identify the specific line to fix')
                except Exception as e:
                    log(f'⚠️ Fallback fix failed: {e}')
                
                return {'fixed': False, 'error': 'Patch did not match file content and fallback failed'}
        
        log('⚠️ AI did not return valid patch markers')
        log(f'Response was: {response[:500]}')
        return {'fixed': False, 'error': 'No valid patch returned'}
        
    except Exception as e:
        log(f'Auto-fix syntax error failed: {e}')
        import traceback
        log(f'Traceback: {traceback.format_exc()}')
        return {'fixed': False, 'error': str(e)}




# ── Agent orchestrator ─────────────────────────────────────────────────────────
class Agent:
    """
    Processes prompts from a queue in a dedicated worker thread.
    The watchdog enqueues prompts; the worker processes them one at a time.
    Queue position is reported to the user so they know their request is waiting.
    """

    def __init__(self):
        self._queue  = queue.Queue()
        self._busy   = False
        self._lock   = threading.Lock()
        
        # Initialize task-based development components
        self.task_planner = TaskPlanner(str(WORKSPACE_DIR), call_ai)
        self.task_executor = TaskExecutor(str(WORKSPACE_DIR), call_ai)
        self.task_mode = False  # Flag to indicate if we're in task-based mode
        
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()

    def enqueue(self, prompt: str):
        """Add a prompt to the queue and tell the user if they have to wait."""
        self._queue.put(prompt)
        queue_size = self._queue.qsize()
        with self._lock:
            currently_busy = self._busy

        if currently_busy or queue_size > 1:
            position = queue_size
            report(
                f'📋 Got your request! I\'m still working on the previous one, '
                f'so yours is #{position} in line. I\'ll get to it as soon as I\'m done — '
                f'usually just a minute or two.'
            )
        log(f'Queued prompt (queue size: {queue_size})')

    def is_idle(self) -> bool:
        with self._lock:
            return not self._busy and self._queue.empty()

    def _worker(self):
        while True:
            try:
                prompt = self._queue.get(timeout=1)
            except queue.Empty:
                continue
            with self._lock:
                self._busy = True

            # Tell the user we're starting their queued request
            remaining = self._queue.qsize()
            if remaining > 0:
                report(f'▶️ Starting your request now! ({remaining} more waiting after this)')
            else:
                report(f'▶️ Working on your request now...')

            try:
                self._handle(prompt)
            except Exception as e:
                report(f'⚠️ Something unexpected went wrong. Please try sending your request again.')
                log(f'Unhandled exception: {e}')
            finally:
                with self._lock:
                    self._busy = False
                self._queue.task_done()

    def _handle(self, prompt: str):
        """
        Main prompt handler with task-based workflow support
        
        Workflow:
        1. Detect if this is a large requirement (triggers task planning)
        2. If task planning needed: generate task breakdown → ask user to select tasks
        3. If task execution: execute selected task with full context
        4. If simple request: use legacy direct generation
        """
        existing = read_workspace_files()
        is_empty = len(existing) == 0
        
        # Check if this is a task-related command
        if prompt.startswith('TASK:'):
            self._handle_task_command(prompt)
            return
        
        # Check if this is a deployment fix
        deploy_only_keywords = [
            '502', 'fix deployment', 'fix the deployment', 'restart', 'redeploy',
            'not loading', 'broken', 'fix nginx', 'server error'
        ]
        is_deploy_fix = (
            not is_empty and
            any(kw in prompt.lower() for kw in deploy_only_keywords)
        )
        
        if is_deploy_fix:
            # Just redeploy without code generation
            deploy(error_context={'reason': prompt})
            return
        
        # Detect if this is a large/complex requirement
        is_large_requirement = self._is_large_requirement(prompt)
        
        if is_large_requirement and is_empty:
            # Generate task plan for large new projects
            self._handle_task_planning(prompt)
        elif not is_empty and len(existing) > 0:
            # Existing project - use incremental task-based approach
            self._handle_incremental_development(prompt, existing)
        else:
            # Simple request - use legacy direct generation
            self._handle_direct_generation(prompt, existing, is_empty)
    
    def _is_large_requirement(self, prompt: str) -> bool:
        """Detect if a requirement is large enough to need task breakdown"""
        # Heuristics for detecting large requirements
        indicators = [
            len(prompt) > 500,  # Long description
            'platform' in prompt.lower(),
            'system' in prompt.lower(),
            'management' in prompt.lower(),
            'enterprise' in prompt.lower(),
            'multi-tenant' in prompt.lower(),
            'full-stack' in prompt.lower(),
            prompt.count('\n') > 5,  # Multiple sections
            'module' in prompt.lower() and prompt.count('module') > 2,
        ]
        
        return sum(indicators) >= 2
    
    def _handle_task_planning(self, prompt: str):
        """Generate and present task breakdown to user"""
        report('🧠 Analyzing your requirement and breaking it down into manageable tasks...',
               message_type='thinking')
        
        try:
            # Generate task plan
            plan = self.task_planner.generate_task_plan(prompt)
            
            # Present tasks to user
            self._present_task_plan(plan)
            
        except Exception as e:
            log(f'Task planning failed: {e}')
            report(f'⚠️ Had trouble breaking down the requirement. Trying direct generation instead...')
            self._handle_direct_generation(prompt, {}, True)
    
    def _present_task_plan(self, plan: Dict[str, Any]):
        """Present task breakdown to user and automatically start execution"""
        summary = plan.get('project_summary', '')
        tasks = plan.get('tasks', [])
        
        # Build user-friendly task list for display
        task_list = []
        for i, task in enumerate(tasks, 1):
            task_dict = task if isinstance(task, dict) else task.to_dict()
            priority_emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(task_dict['priority'], '⚪')
            task_list.append(
                f"{i}. {priority_emoji} **{task_dict['title']}**\n"
                f"   {task_dict['description'][:100]}...\n"
                f"   Files: {len(task_dict['files_to_create'])} to create, "
                f"{len(task_dict['files_to_modify'])} to modify"
            )
        
        message = f"""📋 **Task Breakdown Complete!**

{summary}

I've broken this down into **{len(tasks)} tasks**. Starting execution automatically...
"""
        
        # Send task plan with metadata for UI rendering
        report(
            message, 
            message_type='status',
            metadata={
                'task_plan': plan,
                'awaiting_task_selection': False,  # Changed to False since we auto-execute
                'type': 'task_breakdown'
            },
            summary='Task breakdown ready'
        )
        
        # Automatically start task execution after a brief delay
        # This gives the UI time to render the task breakdown
        time.sleep(1)
        log('🚀 Auto-starting task execution...')
        self._execute_tasks_sequentially()
    
    def _handle_task_command(self, prompt: str):
        """Handle task-related commands"""
        command = prompt[5:].strip().upper()  # Remove 'TASK:' prefix
        
        if command == 'START' or 'start building' in prompt.lower():
            self._execute_tasks_sequentially()
        elif command.startswith('EXECUTE:'):
            task_ids = command[8:].split(',')
            self._execute_specific_tasks(task_ids)
        elif command.startswith('SHOW:'):
            task_id = command[5:].strip()
            self._show_task_details(task_id)
        elif command == 'STATUS':
            self._show_task_status()
        else:
            report('❓ Unknown task command. Try: TASK:START, TASK:EXECUTE:1, or TASK:STATUS')
    
    def _execute_tasks_sequentially(self):
        """Execute all pending tasks in order with real-time updates"""
        # Don't send task_plan here - it was already sent in _present_task_plan
        report(f'🚀 Starting task execution...',
               message_type='action',
               metadata={'type': 'task_execution_start'})
        
        while True:
            executable_tasks = self.task_planner.get_executable_tasks()
            
            if not executable_tasks:
                # Check if all tasks are complete or if we're stuck
                progress = self.task_planner.get_progress_summary()
                if progress['completed'] == progress['total_tasks']:
                    # All tasks complete!
                    report(f'🎉 All {progress["total_tasks"]} tasks completed! Your application is ready.',
                           message_type='success',
                           metadata={
                               'task_plan': {
                                   'project_summary': self.task_planner.context.get('project_summary', ''),
                                   'tasks': [t.to_dict() for t in self.task_planner.tasks],
                                   'total_tasks': len(self.task_planner.tasks)
                               },
                               'type': 'task_execution_complete'
                           })
                    # Deploy the completed application
                    deploy()
                    break
                else:
                    # Some tasks are pending but not executable (dependency issue)
                    report(f"⚠️ {progress['pending']} tasks remaining but cannot execute (dependency issues).",
                           message_type='error',
                           metadata={
                               'task_plan': {
                                   'project_summary': self.task_planner.context.get('project_summary', ''),
                                   'tasks': [t.to_dict() for t in self.task_planner.tasks],
                                   'total_tasks': len(self.task_planner.tasks)
                               },
                               'type': 'task_execution_blocked'
                           })
                    break
            
            # Execute the next task
            task = executable_tasks[0]  # Get highest priority task
            self._execute_single_task(task)
            
            # Check if we should continue
            if task.status == 'failed':
                # Send final task plan with error state
                progress = self.task_planner.get_progress_summary()
                report(f'⚠️ Task {task.task_id} failed. Stopping execution.',
                       message_type='error',
                       metadata={
                           'task_plan': {
                               'project_summary': self.task_planner.context.get('project_summary', ''),
                               'tasks': [t.to_dict() for t in self.task_planner.tasks],
                               'total_tasks': len(self.task_planner.tasks)
                           },
                           'type': 'task_execution_failed'
                       })
                break
            
            # Continue to next iteration to get newly executable tasks
    
    def _execute_specific_tasks(self, task_ids: List[str]):
        """Execute specific tasks by ID"""
        for task_id_str in task_ids:
            task_id = f"task_{task_id_str.strip().zfill(3)}"
            task = self.task_planner.get_task_by_id(task_id)
            
            if not task:
                report(f'❌ Task {task_id} not found')
                continue
            
            if task.status == 'completed':
                report(f'✅ Task {task_id} already completed')
                continue
            
            # Check dependencies
            deps_met = all(
                self.task_planner.get_task_by_id(dep_id).status == 'completed'
                for dep_id in task.dependencies
            )
            
            if not deps_met:
                report(f'⚠️ Task {task_id} has unmet dependencies: {", ".join(task.dependencies)}')
                continue
            
            self._execute_single_task(task)
    
    def _execute_single_task(self, task: Task):
        """Execute a single task with full context"""
        # Mark task as in progress without sending full task plan
        report(f'▶️ Executing: **{task.title}**',
               message_type='action',
               metadata={'executing_task_id': task.task_id, 'type': 'task_execution_start'})
        
        # Send thinking log without task plan
        report(f'💡 Analyzing task requirements and building context...',
               message_type='thinking',
               metadata={'type': 'thinking'})
        
        task.status = 'in_progress'
        self.task_planner._save_state()
        
        try:
            # Build project context
            context = self.task_planner._build_project_context()
            context['project_summary'] = self.task_planner.context.get('project_summary', '')
            
            # Send thinking log without task plan
            report(f'💡 Generating code for {len(task.files_to_create)} new files and modifying {len(task.files_to_modify)} existing files...',
                   message_type='thinking',
                   metadata={'type': 'thinking'})
            
            # Execute task
            result = self.task_executor.execute_task(task, context)
            
            if result['success']:
                task.status = 'completed'
                task.completed_at = datetime.now().isoformat()
                self.task_planner._save_state()
                
                # Send completion message WITH task plan for UI update
                progress = self.task_planner.get_progress_summary()
                report(f'✅ Task completed: {task.title}',
                       message_type='success',
                       metadata={
                           'task_plan': {
                               'project_summary': self.task_planner.context.get('project_summary', ''),
                               'tasks': [t.to_dict() for t in self.task_planner.tasks],
                               'total_tasks': len(self.task_planner.tasks),
                               'completed_count': progress['completed'],
                               'pending_count': progress['pending'],
                               'failed_count': progress['failed']
                           },
                           'type': 'task_update',
                           'completed_task_id': task.task_id
                       })
            else:
                task.status = 'failed'
                task.error = result['error']
                self.task_planner._save_state()
                
                # Send error message WITH task plan for UI update
                report(f'❌ Task failed: {task.title}\n   Error: {result["error"]}',
                       message_type='error',
                       metadata={
                           'task_plan': {
                               'project_summary': self.task_planner.context.get('project_summary', ''),
                               'tasks': [t.to_dict() for t in self.task_planner.tasks],
                               'total_tasks': len(self.task_planner.tasks)
                           },
                           'type': 'task_update',
                           'failed_task_id': task.task_id
                       })
        
        except Exception as e:
            task.status = 'failed'
            task.error = str(e)
            self.task_planner._save_state()
            
            report(f'❌ Task execution error: {str(e)}', 
                   message_type='error',
                   metadata={
                       'task_plan': {
                           'project_summary': self.task_planner.context.get('project_summary', ''),
                           'tasks': [t.to_dict() for t in self.task_planner.tasks],
                           'total_tasks': len(self.task_planner.tasks)
                       },
                       'type': 'task_update',
                       'failed_task_id': task.task_id
                   })
    
    def _show_task_details(self, task_id: str):
        """Show detailed information about a task"""
        task = self.task_planner.get_task_by_id(f"task_{task_id.zfill(3)}")
        
        if not task:
            report(f'❌ Task {task_id} not found')
            return
        
        status_emoji = {
            'pending': '⏳',
            'in_progress': '▶️',
            'completed': '✅',
            'failed': '❌'
        }.get(task.status, '❓')
        
        message = f"""
{status_emoji} **Task {task.task_id}: {task.title}**

**Description:**
{task.description}

**Files to Create:** ({len(task.files_to_create)})
{chr(10).join(f'  • {f}' for f in task.files_to_create[:10])}

**Files to Modify:** ({len(task.files_to_modify)})
{chr(10).join(f'  • {f}' for f in task.files_to_modify[:10])}

**Dependencies:** {', '.join(task.dependencies) if task.dependencies else 'None'}
**Priority:** {task.priority}
**Status:** {task.status}
**Estimated Tokens:** {task.estimated_tokens}
"""
        
        report(message)
    
    def _show_task_status(self):
        """Show overall task execution status"""
        progress = self.task_planner.get_progress_summary()
        executable = self.task_planner.get_executable_tasks()
        
        message = f"""
📊 **Task Execution Status**

**Progress:** {progress['completed']}/{progress['total_tasks']} tasks completed ({progress['progress_percentage']}%)
**Pending:** {progress['pending']} tasks
**Failed:** {progress['failed']} tasks

**Next Executable Tasks:** {len(executable)}
{chr(10).join(f'  {i+1}. {t.title}' for i, t in enumerate(executable[:5]))}

Use `TASK:START` to continue execution.
"""
        
        report(message)
    
    def _handle_incremental_development(self, prompt: str, existing_files: dict):
        """Handle incremental development on existing project"""
        # Check if this is a large requirement that needs task breakdown
        is_large_requirement = self._is_large_requirement(prompt)
        
        if is_large_requirement:
            # Even for existing projects, use task-based approach for large changes
            self._handle_task_planning(prompt)
        else:
            # For small changes, use direct generation
            self._handle_direct_generation(prompt, existing_files, False)
    
    def _handle_direct_generation(self, prompt: str, existing_files: dict, is_empty: bool):
        """Legacy direct code generation (for simple requests)"""
        deploy_only_keywords = [
            '502', 'fix deployment', 'fix the deployment', 'restart', 'redeploy',
            'not loading', 'broken', 'fix nginx', 'server error'
        ]
        is_deploy_fix = (
            not is_empty and
            any(kw in prompt.lower() for kw in deploy_only_keywords)
        )

        changed_files = []
        user_prompt = prompt
        
        if is_empty or not is_deploy_fix:
            result = generate_code(prompt, existing_files=existing_files if not is_empty else None)
            if not result:
                return
            
            # Check if this was an edit that returned change info
            if isinstance(result, dict) and result.get('success'):
                changed_files = result.get('changed_files', [])
                user_prompt = result.get('user_prompt', prompt)

        # Deploy with testing enabled for edits
        deploy_result = deploy(
            error_context={'reason': prompt} if is_deploy_fix else None,
            test_changes=bool(changed_files),
            changed_files=changed_files,
            user_prompt=user_prompt
        )


# ── Watchdog ───────────────────────────────────────────────────────────────────
def watchdog(agent: Agent):
    """
    Runs forever: reads the mailbox for new user prompts and self-heals on errors.
    Monitors for:
    - 502 errors (app not responding)
    - 404 errors on static assets (missing proxy_pass)
    Never blocks — prompt handling runs in the Agent's worker thread.
    """
    log('Watchdog active.')
    log(f'Mailbox path: {MAILBOX}')
    last_502_time = 0
    last_404_fix_time = 0
    asset_404_count = 0
    check_count = 0

    while True:
        try:
            check_count += 1
            if check_count % 12 == 0:  # Log every minute (12 * 5 seconds)
                log(f'Watchdog check #{check_count}: mailbox exists={MAILBOX.exists()}, agent idle={agent.is_idle()}')
            
            # ═══════════════════════════════════════════════════════════════
            # Check mailbox for user prompts
            # ═══════════════════════════════════════════════════════════════
            if MAILBOX.exists():
                try:
                    prompt = MAILBOX.read_text().strip()
                    MAILBOX.unlink()
                    if prompt:
                        log(f'Mailbox: received prompt ({len(prompt)} chars)')
                        log(f'Prompt preview: {prompt[:200]}...')
                        agent.enqueue(prompt)
                    else:
                        log('Mailbox: file exists but empty')
                except Exception as e:
                    log(f'Mailbox error: {e}')

            if agent.is_idle():
                # ═══════════════════════════════════════════════════════════
                # Monitor for 502 errors (app not responding)
                # ═══════════════════════════════════════════════════════════
                nginx_errors = get_nginx_errors()
                now = time.time()
                if nginx_errors and (now - last_502_time) > 30:
                    last_502_time = now
                    report('🔧 Noticed your app stopped responding. Automatically fixing it...')
                    agent.enqueue('Fix the deployment — the app is returning 502 errors.')
                
                # ═══════════════════════════════════════════════════════════
                # Monitor for 404 errors on static assets (missing proxy_pass)
                # ═══════════════════════════════════════════════════════════
                asset_404s = _detect_asset_404_errors()
                if asset_404s and (now - last_404_fix_time) > 60:
                    asset_404_count += 1
                    
                    # Only auto-fix once, then require manual intervention
                    if asset_404_count == 1:
                        log(f'🔍 Detected {len(asset_404s)} 404 errors on static assets')
                        log(f'   Assets: {", ".join(asset_404s[:5])}')
                        
                        # Attempt automatic fix
                        if _auto_fix_asset_404():
                            last_404_fix_time = now
                            report('🔧 Fixed missing asset configuration. Your app should load correctly now.')
                        else:
                            log('⚠️ Auto-fix failed - nginx config may need manual review')

        except Exception as e:
            log(f'Watchdog error: {e}')

        time.sleep(5)


def _detect_asset_404_errors() -> list:
    """
    Scan nginx access log for 404 errors on static assets (JS, CSS, images).
    Returns list of asset paths that returned 404.
    """
    try:
        access_log = Path('/var/log/nginx/access.log')
        if not access_log.exists():
            return []
        
        # Read last 100 lines
        result = subprocess.run(
            ['tail', '-n', '100', str(access_log)],
            capture_output=True, text=True, timeout=3
        )
        
        if result.returncode != 0:
            return []
        
        # Look for 404 errors on asset files
        asset_extensions = ['.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.woff', '.woff2', '.ttf', '.eot', '.ico']
        asset_404s = []
        
        for line in result.stdout.splitlines():
            # Nginx log format: ... "GET /path HTTP/1.1" 404 ...
            if ' 404 ' in line:
                # Extract path
                match = re.search(r'"GET\s+([^\s]+)\s+HTTP', line)
                if match:
                    path = match.group(1)
                    # Check if it's an asset file
                    if any(path.endswith(ext) for ext in asset_extensions):
                        if path not in asset_404s:
                            asset_404s.append(path)
        
        return asset_404s
        
    except Exception as e:
        log(f'Asset 404 detection error: {e}')
        return []


def _auto_fix_asset_404() -> bool:
    """
    Automatically fix nginx configuration when static assets return 404.
    This happens when location blocks have caching headers but no proxy_pass.
    
    Returns True if fix was applied successfully.
    """
    try:
        nginx_conf_path = Path(NGINX_CONF)
        if not nginx_conf_path.exists():
            return False
        
        # Read current config
        current_conf = nginx_conf_path.read_text()
        
        # Apply auto-fix
        fixed_conf = _auto_fix_nginx_config(current_conf)
        
        # Check if anything changed
        if fixed_conf == current_conf:
            log('No nginx fixes needed - config already correct')
            return False
        
        # Write fixed config
        nginx_conf_path.write_text(fixed_conf)
        
        # Reload nginx
        if nginx_reload():
            log('✅ Nginx config auto-fixed and reloaded successfully')
            return True
        else:
            log('❌ Nginx reload failed after auto-fix')
            return False
            
    except Exception as e:
        log(f'Auto-fix error: {e}')
        return False


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    def _handle_sig(sig, frame):
        log('Shutdown signal received.')
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    # 🚀 Start the version supervisor in the background
    # This enables the 'switch workspace' and 'versioning' features from the host
    try:
        sys.path.append('/usr/local/bin')
        import supervisor
        t = threading.Thread(target=supervisor.run, daemon=True)
        t.start()
        log('Supervisor launched in background.')
    except Exception as e:
        log(f'Failed to launch supervisor: {e}')

    agent = Agent()

    report('👋 VibeCoding Agent is online and ready!')

    # Serve a friendly loading page immediately
    apply_baseline_gateway()

    # If workspace already has files (container restart), redeploy them
    existing = read_workspace_files()
    if existing:
        file_count = len(existing)
        log(f'Container restart detected - workspace has {file_count} files')
        
        # Check if there's a previous deployment we can restore
        prev_deployment = _detect_previous_deployment()
        
        if prev_deployment['has_deployment']:
            # Previous deployment detected - try to restore it
            app_port = prev_deployment['app_port']
            artifacts = prev_deployment['built_artifacts']
            
            log(f'Previous deployment found: port={app_port}, artifacts={artifacts}')
            report(f'🔄 Restoring your app (found previous deployment on port {app_port})...')
            
            # Check if app is already healthy
            if app_port:
                healthy, msg = _health_check(app_port=app_port)
                if healthy:
                    report('✅ Your app is already running and healthy!')
                    # Skip redeployment, go straight to watchdog
                    watchdog(agent)
                    # watchdog runs forever, so we never reach here
            
            # App not healthy - attempt redeployment
            report(f'🔄 Restarting your app ({file_count} files found)...')
        else:
            # No previous deployment - fresh deploy
            log('No previous deployment detected - performing fresh deployment')
            report(f'🔄 Deploying your app ({file_count} files found)...')
        
        # Attempt immediate redeployment without going through the queue
        try:
            success = deploy(error_context=None, max_retries=3)
            if success:
                report('✅ Your app is back online!')
            else:
                report('⚠️ Had trouble restarting the app. You can send me a message to fix it, or I\'ll keep trying automatically.')
        except Exception as e:
            log(f'Auto-redeploy on restart failed: {e}')
            report('⚠️ Had trouble restarting the app. Send me a message if you need help!')
    else:
        report('💡 Ready to build! Send me your first message to get started.')

    watchdog(agent)
