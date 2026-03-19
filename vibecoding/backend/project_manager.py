import os
import uuid
import zipfile
import shutil
import re
import docker
import asyncio
import time
import requests
import threading
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
import json
import logging
from git_manager import git_manager
from ai_config import ai_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def sanitize_html(content: str) -> str:
    """Remove stray '>' characters that appear after closing tags (AI generation artifact)."""
    # Remove stray > after closing tags like </nav>>, </ul>>, </section>>, </footer>>
    content = re.sub(r'(</\w+>)>+', r'\1', content)
    # Remove stray > after opening tag closers like id="features">>
    content = re.sub(r'(">)>+', r'\1', content)
    # Remove stray > at end of </html>
    content = re.sub(r'(</html>)>*\s*$', r'\1', content.rstrip())
    return content

EDITOR_INJECTION_SCRIPT = """
<script id="__vibe_editor__">
(function() {
  var hoveredEl = null;
  var selectedEl = null;
  var editMode = false;

  window.addEventListener('message', function(e) {
    if (!e.data || !e.data.type) return;
    
    if (e.data.type === 'set-edit-mode') {
      editMode = e.data.value;
      if (!editMode) { clearHover(); clearSelection(); }
    } else if (e.data.type === 'update-element-property') {
      if (selectedEl && e.data.property) {
        if (e.data.property === 'textContent' || e.data.property === 'innerHTML' || e.data.property === 'innerText') {
          selectedEl[e.data.property] = e.data.value;
        } else {
          selectedEl.style[e.data.property] = e.data.value;
        }
      }
    }
  });

  function getElementInfo(el) {
    var rect = el.getBoundingClientRect();
    return {
      tagName: el.tagName,
      id: el.id || '',
      className: (typeof el.className === 'string' ? el.className : ''),
      textContent: (el.textContent || '').substring(0, 150),
      rect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height }
    };
  }

  function clearHover() { window.parent.postMessage({ type: 'element-hover', data: null }, '*'); }
  function clearSelection() { selectedEl = null; window.parent.postMessage({ type: 'element-deselect' }, '*'); }

  document.addEventListener('mouseover', function(e) {
    if (!editMode) return;
    var el = e.target;
    if (!el || el.tagName === 'HTML' || el.tagName === 'BODY') { clearHover(); return; }
    hoveredEl = el;
    window.parent.postMessage({ type: 'element-hover', data: getElementInfo(el) }, '*');
  }, true);

  document.addEventListener('mouseout', function(e) {
    if (!editMode) return;
    hoveredEl = null;
    clearHover();
  }, true);

  document.addEventListener('click', function(e) {
    if (!editMode) return;
    e.preventDefault();
    e.stopPropagation();
    var el = e.target;
    if (!el || el.tagName === 'HTML' || el.tagName === 'BODY') return;
    selectedEl = el;
    var info = getElementInfo(el);
    info.mouseX = e.clientX;
    info.mouseY = e.clientY;
    window.parent.postMessage({ type: 'element-selected', data: info }, '*');
  }, true);

  document.addEventListener('scroll', function() {
    if (!editMode || !hoveredEl) return;
    window.parent.postMessage({ type: 'element-hover', data: getElementInfo(hoveredEl) }, '*');
  }, true);
})();
</script>
"""

class ProjectManager:
    """Manages container-based code execution and project artifacts"""
    
    DEFAULT_IMAGE = os.environ.get("AGENT_IMAGE", "vibecoding-agent-runtime:latest")
    DEFAULT_PORT = int(os.environ.get("AGENT_PORT", "8080"))
    DEFAULT_RUNTIME = os.environ.get("DEFAULT_RUNTIME", "universal")

    def __init__(self, artifacts_dir: str = os.environ.get("ARTIFACTS_DIR", "project_artifacts")):
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(exist_ok=True)
        self._docker_client = None
        self._current_user_prompt = ''
        self.running_containers: Dict[str, docker.models.containers.Container] = {}
        self.log_threads: Dict[str, threading.Thread] = {}
    
    @property
    def docker_client(self):
        """Lazy load Docker client on first access"""
        if self._docker_client is None:
            try:
                self._docker_client = docker.from_env()
                logger.info("✅ Docker client initialized successfully")
            except docker.errors.DockerException as e:
                logger.warning(f"⚠️ Docker is not available: {str(e)}")
                logger.warning("Preview functionality will be disabled")
                return None
        return self._docker_client
    
    def _build_runtime_image(self, image_name: str) -> bool:
        """Build the runtime image from Dockerfile"""
        try:
            dockerfile_path = Path(__file__).parent / "docker" / "agent-runtime.Dockerfile"
            if not dockerfile_path.exists():
                logger.error(f"❌ Dockerfile not found at {dockerfile_path}")
                return False
            
            logger.info(f"🏗️ Building image {image_name} from {dockerfile_path}...")
            # Use the docker/ folder as context
            image, build_logs = self.docker_client.images.build(
                path=str(dockerfile_path.parent),
                dockerfile=dockerfile_path.name,
                tag=image_name,
                rm=True
            )
            logger.info(f"✅ Successfully built {image_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to build image: {e}")
            return False

    def _ensure_image_exists(self, image_name: str) -> bool:
        """Check if image exists, build if it's the standard runtime"""
        if self.docker_client is None:
            return False
            
        try:
            self.docker_client.images.get(image_name)
            return True
        except docker.errors.ImageNotFound:
            if "vibecoding-agent-runtime" in image_name:
                return self._build_runtime_image(image_name)
            return False
        except Exception as e:
            logger.error(f"Error checking image: {e}")
            return False

    def _stream_container_logs(self, container, container_name: str):
        """Stream container logs to console in a separate thread"""
        try:
            logger.info(f"📋 Starting log stream for {container_name}")
            for log_line in container.logs(stream=True, follow=True):
                try:
                    decoded_line = log_line.decode('utf-8').strip()
                    if decoded_line:
                        logger.info(f"[{container_name}] {decoded_line}")
                except Exception as e:
                    logger.debug(f"Error decoding log line: {e}")
        except Exception as e:
            logger.debug(f"Log streaming ended for {container_name}: {e}")
        
    def generate_project_id(self) -> str:
        """Generate unique project ID"""
        return str(uuid.uuid4())[:8]
    
    def create_project_directory(self, project_id: str, metadata: dict = None) -> Path:
        """Create project directory with version subdirectories"""
        project_dir = self.artifacts_dir / project_id
        project_dir.mkdir(exist_ok=True)
        
        # Create versions directory
        versions_dir = project_dir / "versions"
        versions_dir.mkdir(exist_ok=True)
        
        # Create project metadata
        project_meta = {
            "project_id": project_id,
            "name": metadata.get("name") if metadata else f"Project {project_id[:8]}",
            "description": metadata.get("description") if metadata else "",
            "owner_id": metadata.get("owner_id") if metadata else None,
            "created_at": datetime.now().isoformat(),
            "versions": [],
            "current_version": None
        }
        
        with open(project_dir / "metadata.json", "w") as f:
            json.dump(project_meta, f, indent=2)
        
        return project_dir
    
    def save_code_version(self, project_id: str, code: str, prompt: str) -> Tuple[str, Path]:
        """Save code version and return version ID and file path"""
        project_dir = self.artifacts_dir / project_id
        if not project_dir.exists():
            project_dir = self.create_project_directory(project_id)
        
        # Generate version ID
        version_id = f"v{len(list(project_dir.glob('versions/*'))) + 1:03d}"
        version_dir = project_dir / "versions" / version_id
        version_dir.mkdir(parents=True, exist_ok=True)
        
        # Check if code contains file markers
        import re
        file_marker_regex = r'//\s*FILE:\s*([^\n]+)|#\s*FILE:\s*([^\n]+)|<!--\s*FILE:\s*([^\n]+)\s*-->'
        matches = list(re.finditer(file_marker_regex, code))
        
        main_file_path = None
        runtime_name = None
        runtime_config = None
        
        if matches and len(matches) > 0:
            # Multi-file structure - parse and save each file
            logger.info(f"📁 Multi-file structure detected: {len(matches)} files")
            
            for i, match in enumerate(matches):
                filename = (match.group(1) or match.group(2) or match.group(3)).strip()
                start_pos = match.end()
                end_pos = matches[i + 1].start() if i < len(matches) - 1 else len(code)
                file_content = code[start_pos:end_pos].strip()
                
                # Create file path
                file_path = version_dir / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Inject editor script into HTML files for cross-origin visual editing capability
                if filename.endswith('.html'):
                    if '</body>' in file_content:
                        file_content = file_content.replace('</body>', f'{EDITOR_INJECTION_SCRIPT}</body>')
                    else:
                        file_content += EDITOR_INJECTION_SCRIPT

                # Save file
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(file_content)
                
                logger.info(f"  ✅ Saved: {filename}")
                
                # Set universal defaults
                if runtime_name is None:
                    runtime_name = self.DEFAULT_RUNTIME
                    runtime_config = {'image': self.DEFAULT_IMAGE, 'port': self.DEFAULT_PORT}
                
                # Set main file
                if main_file_path is None:
                    if filename.endswith(('.py', '.js', '.html', '.jsx', '.tsx', '.go', '.rs', '.java')):
                        main_file_path = file_path
            
            # If no main file found, use first file
            if main_file_path is None:
                filename = (matches[0].group(1) or matches[0].group(2) or matches[0].group(3)).strip()
                main_file_path = version_dir / filename
        else:
            # Single file - use universal defaults
            runtime_name = "universal"
            runtime_config = {'image': self.DEFAULT_IMAGE, 'port': self.DEFAULT_PORT}
            filename = "app.py" if any(k in code for k in ["import ", "def ", "class "]) else "index.html"
            
            logger.info(f"📄 Single file detected")
            logger.info(f"🔍 Detected runtime: {runtime_name}")
            logger.info(f"📝 Using filename: {filename}")
            
            # Inject editor script if it's an HTML single file
            if filename.endswith('.html'):
                if '</body>' in code:
                    code = code.replace('</body>', f'{EDITOR_INJECTION_SCRIPT}</body>')
                else:
                    code += EDITOR_INJECTION_SCRIPT

            # Save code file
            main_file_path = version_dir / filename
            with open(main_file_path, 'w', encoding='utf-8') as f:
                f.write(code)
        
        logger.info(f"🔍 Detected runtime: {runtime_name}")
        logger.info(f"🐳 Docker image: {runtime_config['image']}")
        logger.info(f"🔌 Port: {runtime_config['port']}")
        
        # Save version metadata
        version_metadata = {
            "version_id": version_id,
            "prompt": prompt,
            "created_at": datetime.now().isoformat(),
            "runtime": runtime_name,
            "main_file": str(main_file_path.relative_to(version_dir)),
            "docker_image": runtime_config['image'],
            "port": runtime_config['port'],
            "is_multi_file": len(matches) > 0 if matches else False,
            "file_count": len(matches) if matches else 1,
        }
        
        with open(version_dir / "metadata.json", "w") as f:
            json.dump(version_metadata, f, indent=2)
        
        # Update project metadata
        self._update_project_metadata(project_id, version_id, prompt)
        
        # Automatically create ZIP after saving
        self.create_project_zip(project_id)
        
        # Sync to git workspace for version control
        try:
            git_manager.sync_workspace(project_id, version_dir)
            # Auto-commit the new version
            git_manager.auto_commit_version(project_id, version_id, prompt)
        except Exception as e:
            logger.error(f"Failed to sync or commit git workspace: {e}")

        logger.info(f"✅ Saved version {version_id} for project {project_id}")
        return version_id, main_file_path

    def archive_workspace_to_version(self, project_id: str, prompt: str = "Chat Session Snapshot") -> str:
        """Create a permanent version folder from the current workspace state."""
        project_dir = self.artifacts_dir / project_id
        workspace_dir = project_dir / "workspace"
        
        if not workspace_dir.exists():
            return "v000"

        # 1. Determine next version ID
        versions_dir = project_dir / "versions"
        versions_dir.mkdir(exist_ok=True)
        version_id = f"v{len(list(versions_dir.iterdir())) + 1:03d}"
        version_dir = versions_dir / version_id
        version_dir.mkdir(parents=True, exist_ok=True)
        
        # 2. Copy files (excluding .git)
        import shutil
        for item in workspace_dir.iterdir():
            if item.name == ".git":
                continue
            if item.is_dir():
                shutil.copytree(item, version_dir / item.name, dirs_exist_ok=True)
            else:
                shutil.copy2(item, version_dir / item.name)
        
        # 3. Save metadata
        metadata = {
            "version_id": version_id,
            "prompt": prompt,
            "created_at": datetime.now().isoformat(),
            "is_archive": True
        }
        with open(version_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)
            
        # Update project metadata
        self._update_project_metadata(project_id, version_id, prompt)
        
        logger.info(f"📁 Archived workspace to version {version_id}")
        return version_id

    def get_workspace_files(self, project_id: str, max_files: int = 20, max_chars_per_file: int = 2000) -> dict:
        """Get all files from the workspace as a dictionary {filepath: content}
        
        Args:
            project_id: Project identifier
            max_files: Maximum number of files to return (to avoid token overflow)
            max_chars_per_file: Maximum characters per file (to avoid token overflow)
        """
        project_dir = self.artifacts_dir / project_id
        workspace_dir = project_dir / "workspace"
        
        if not workspace_dir.exists():
            return {}
        
        files = {}
        file_count = 0
        
        # Directories to skip (common large/binary directories)
        skip_dirs = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build', '.next', '.cache'}
        # Files to skip (internal system files)
        skip_files = {'metadata.json'}
        
        for file_path in sorted(workspace_dir.rglob('*')):
            if file_count >= max_files:
                break
            
            # Skip if any parent directory is in skip_dirs
            if any(part in skip_dirs for part in file_path.parts):
                continue
            
            # Skip internal system files
            if file_path.name in skip_files:
                continue
            
            try:
                # Use exists() first to avoid symlink issues, then check if it's a file
                if file_path.exists() and file_path.is_file():
                    rel_path = str(file_path.relative_to(workspace_dir)).replace('\\', '/')
                    content = file_path.read_text(encoding='utf-8')
                    
                    # Truncate large files
                    if len(content) > max_chars_per_file:
                        content = content[:max_chars_per_file] + f"\n... [truncated, {len(content) - max_chars_per_file} more chars]"
                    
                    files[rel_path] = content
                    file_count += 1
            except (OSError, UnicodeDecodeError, PermissionError) as e:
                # Skip files that can't be accessed (symlinks, binary files, permission issues)
                logger.debug(f"Skipping {file_path}: {e}")
                continue
        
        return files

    def _ensure_workspace_metadata(self, project_id: str, workspace_dir: Path, commit_hash: str):
        """Write metadata.json only if it doesn't exist or needs updating."""
        metadata_file = workspace_dir / "metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file) as f:
                    meta = json.load(f)
                meta["commit_hash"] = commit_hash
                with open(metadata_file, 'w') as f:
                    json.dump(meta, f, indent=2)
                return
            except Exception:
                pass
        # Create fresh metadata
        has_py = any(workspace_dir.rglob('*.py'))
        has_pkg = any(workspace_dir.rglob('package.json'))
        metadata = {
            "runtime": "multi-stack" if (has_py and has_pkg) else ("python" if has_py else "node" if has_pkg else "universal"),
            "docker_image": "vibecoding-agent-runtime:latest",
            "port": 80,
            "additional_ports": [],
            "created_at": datetime.now().isoformat(),
            "commit_hash": commit_hash
        }
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

    def apply_patch_response(self, project_id: str, code: str) -> Tuple[bool, list]:
        """
        Parse and apply PATCH hunks from AI response.
        Returns (any_applied: bool, patched_files: list)
        """
        import difflib
        workspace_dir = self.artifacts_dir / project_id / "workspace"

        # ── Check for frozen file violations BEFORE applying patches ──────
        frozen_files = self.get_frozen_files(project_id)
        if frozen_files:
            # Extract target files from PATCH blocks
            patch_targets = re.findall(r'//\s*PATCH:\s*([^\n<]+)', code)
            patch_targets = [f.strip() for f in patch_targets]
            
            # Check if any patch targets are frozen
            frozen_violations = [f for f in patch_targets if f in frozen_files]
            if frozen_violations:
                logger.error(f"❌ Cannot apply patches: frozen files detected: {frozen_violations}")
                return False, []

        # ── Normalize malformed AI output before parsing ──────────────────
        # Fix: "// PATCH: index.html <<<SEARCH" → "// PATCH: index.html\n<<<SEARCH"
        code = re.sub(r'(//\s*PATCH:\s*[^\n<]+?)\s*(<<<+\s*SEARCH)', r'\1\n\2', code)
        # Fix: git-style "<<<<<<< SEARCH" → "<<<SEARCH"
        code = re.sub(r'<{4,7}\s*SEARCH', '<<<SEARCH', code)
        # Fix: git-style ">>>>>>> REPLACE" → "<<<REPLACE"
        code = re.sub(r'>{4,7}\s*REPLACE', '<<<REPLACE', code)
        # Fix: "=======" separator between search/replace → ">>>\n<<<REPLACE"
        code = re.sub(r'={4,7}', '>>>\n<<<REPLACE', code)
        # Fix: missing >>> between SEARCH content and <<<REPLACE
        code = re.sub(
            r'(<<<SEARCH\n(?:(?!>>>|<<<).)*?)\n(<<<REPLACE)',
            r'\1\n>>>\n\2', code, flags=re.DOTALL
        )
        # Fix: ">>><<<REPLACE" or ">>> <<<REPLACE" (missing newline between close and open)
        code = re.sub(r'>>>\s*<<<REPLACE', '>>>\n<<<REPLACE', code)
        # Fix: "<<<REPLACE" immediately followed by content on same line → add newline
        code = re.sub(r'(<<<REPLACE)([^\n])', r'\1\n\2', code)
        # Fix: "<<<SEARCH" immediately followed by content on same line → add newline
        code = re.sub(r'(<<<SEARCH)([^\n])', r'\1\n\2', code)
        # Fix: content immediately followed by ">>>" without newline → add newline
        code = re.sub(r'([^\n])(>>>)', r'\1\n\2', code)
        # Fix: "// PATCH: file.ext" immediately followed by next PATCH block (missing close >>>)
        code = re.sub(r'(<<<REPLACE\n(?:(?!>>>|<<<PATCH).)*?)\n(//\s*PATCH:)', r'\1\n>>>\n\2', code, flags=re.DOTALL)
        # Fix: last <<<REPLACE block missing closing >>>
        if '<<<REPLACE' in code:
            last_replace_idx = code.rfind('<<<REPLACE')
            after_last = code[last_replace_idx:]
            if '>>>' not in after_last:
                code = code.rstrip() + '\n>>>'

        # ── Auto-infer // PATCH: filename when headers are missing ──────
        if '<<<SEARCH' in code and not re.search(r'//\s*PATCH:\s*', code):
            logger.info("🔍 Detected <<<SEARCH blocks without // PATCH: headers — auto-inferring filenames")
            search_blocks = re.findall(r'<<<SEARCH\n(.*?)\n>>>', code, re.DOTALL)
            inferred_file = None

            for search_text in search_blocks:
                search_trimmed = search_text.strip()
                if not search_trimmed:
                    continue
                first_line = search_trimmed.split('\n')[0].strip()
                if not first_line:
                    continue

                best_match = None
                for fpath in workspace_dir.rglob('*'):
                    if fpath.is_dir() or '.git' in fpath.parts:
                        continue
                    try:
                        content = fpath.read_text(encoding='utf-8', errors='ignore')
                    except Exception:
                        continue
                    if first_line in content:
                        rel = str(fpath.relative_to(workspace_dir))
                        if search_trimmed in content:
                            best_match = rel
                            break
                        if best_match is None:
                            best_match = rel

                if best_match:
                    inferred_file = best_match
                    break

            if inferred_file:
                logger.info(f"🔍 Inferred target file: {inferred_file}")
                patched_code = ""
                remaining = code
                first_search = True
                while '<<<SEARCH' in remaining:
                    pre, _, rest = remaining.partition('<<<SEARCH')
                    if first_search or '\n// PATCH:' not in pre:
                        patched_code += pre + f"// PATCH: {inferred_file}\n<<<SEARCH"
                    else:
                        patched_code += pre + '<<<SEARCH'
                    remaining = rest
                    first_search = False
                patched_code += remaining
                code = patched_code
            else:
                logger.warning("⚠️ Could not infer target file for <<<SEARCH blocks")
                return False, []

        patch_block_re = re.compile(
            r'//\s*PATCH:\s*([^\n<]+)\n\s*<<<SEARCH\n(.*?)\n\s*>>>\n\s*<<<REPLACE\n(.*?)\n\s*>>>',
            re.DOTALL
        )
        matches = list(patch_block_re.finditer(code))
        if not matches:
            if '// PATCH:' in code or '//PATCH:' in code or '<<<SEARCH' in code:
                logger.warning("⚠️ Found PATCH/SEARCH markers but no hunks could be parsed after normalization")
                logger.debug(f"Normalized patch text (first 500 chars):\n{code[:500]}")
            return False, []

        import tempfile as _tempfile

        def _detect_line_sep(text):
            crlf = text.count('\r\n')
            lf = text.count('\n') - crlf
            return '\r\n' if (crlf > 0 and crlf >= lf) else '\n'

        def _validate_syntax(content, fpath):
            suffix = fpath.suffix.lower()
            if suffix == '.py':
                try:
                    compile(content, str(fpath), 'exec')
                    return True, None
                except SyntaxError as e:
                    return False, f"line {e.lineno}: {e.msg}"
            if suffix == '.json':
                try:
                    json.loads(content)
                    return True, None
                except json.JSONDecodeError as e:
                    return False, f"line {e.lineno}: {e.msg}"
            return True, None

        def _atomic_write(fpath, content):
            tmp_fd, tmp_path = _tempfile.mkstemp(dir=str(fpath.parent), suffix='.tmp')
            try:
                with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                    f.write(content)
                os.replace(tmp_path, str(fpath))
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

        def _match_hunk(content, search_text, replace_text, line_sep):
            """4-tier matching. Returns (new_content, tier_name) or (None, reason)."""
            # Tier 1: exact
            if search_text in content:
                return content.replace(search_text, replace_text, 1), "exact"

            srch_lines = search_text.splitlines()
            repl_lines = replace_text.splitlines()
            cont_lines = content.split(line_sep) if line_sep != '\n' else content.splitlines()
            trailing = content.endswith(line_sep) or content.endswith('\n')

            def rejoin(lines):
                joined = line_sep.join(lines)
                if trailing:
                    joined = joined.rstrip(line_sep) + line_sep
                return joined

            # Tier 2: whitespace-normalised
            def norm(s):
                return re.sub(r'\s+', ' ', s).strip()

            norm_search = [norm(l) for l in srch_lines]
            for idx in range(len(cont_lines) - len(srch_lines) + 1):
                if [norm(l) for l in cont_lines[idx:idx + len(srch_lines)]] == norm_search:
                    cont_lines[idx:idx + len(srch_lines)] = repl_lines
                    return rejoin(cont_lines), "whitespace-norm"

            # Tier 3: indent-flexible with relative indent preservation
            stripped_search = [l.strip() for l in srch_lines]
            search_base = min(
                (len(l) - len(l.lstrip()) for l in srch_lines if l.strip()),
                default=0
            )
            for idx in range(len(cont_lines) - len(stripped_search) + 1):
                window = cont_lines[idx:idx + len(stripped_search)]
                if [l.strip() for l in window] == stripped_search:
                    win_base = min(
                        (len(l) - len(l.lstrip()) for l in window if l.strip()),
                        default=0
                    )
                    delta = win_base - search_base
                    new_lines = []
                    for l in repl_lines:
                        if not l.strip():
                            new_lines.append(l)
                        else:
                            new_indent = max(0, (len(l) - len(l.lstrip())) + delta)
                            new_lines.append(" " * new_indent + l.lstrip())
                    cont_lines[idx:idx + len(stripped_search)] = new_lines
                    return rejoin(cont_lines), f"indent-flex(delta={delta:+d})"

            # Tier 4: fuzzy with variable window (±2 lines)
            base_win = len(srch_lines)
            best_score, best_idx, best_size = 0.0, -1, base_win
            for size_delta in (0, -1, 1, -2, 2):
                ws = base_win + size_delta
                if ws < 1 or ws > len(cont_lines):
                    continue
                for idx in range(len(cont_lines) - ws + 1):
                    score = difflib.SequenceMatcher(
                        None, search_text, "\n".join(cont_lines[idx:idx + ws])
                    ).ratio()
                    if score > best_score:
                        best_score, best_idx, best_size = score, idx, ws

            if best_score >= 0.85:
                cont_lines[best_idx:best_idx + best_size] = repl_lines
                return rejoin(cont_lines), f"fuzzy(score={best_score:.2f})"

            return None, f"no-match(best={best_score:.2f})"

        # Group hunks by file for all-or-nothing application per file
        file_hunks = {}
        for m in matches:
            rel_path = m.group(1).strip()
            rel_path = re.sub(r'[<>]+', '', rel_path).strip()
            file_hunks.setdefault(rel_path, []).append((m.group(2), m.group(3)))

        patched_files = []
        for rel_path, hunks in file_hunks.items():
            filepath = workspace_dir / rel_path
            if not filepath.exists():
                logger.warning(f"⚠️ Patch target not found: {rel_path}")
                continue

            original = filepath.read_text(encoding='utf-8')
            line_sep = _detect_line_sep(original)
            content = original
            all_ok = True

            for search_text, replace_text in hunks:
                new_content, tier = _match_hunk(content, search_text, replace_text, line_sep)
                if new_content is None:
                    logger.warning(f"⚠️ Hunk failed in {rel_path}: {tier} — rolling back file")
                    all_ok = False
                    break
                logger.info(f"  ✅ Hunk matched in {rel_path}: {tier}")
                content = new_content

            if not all_ok or content == original:
                continue

            is_valid, err = _validate_syntax(content, filepath)
            if not is_valid:
                logger.warning(f"⚠️ Post-patch syntax error in {rel_path}: {err} — skipping file")
                continue

            try:
                _atomic_write(filepath, content)
            except Exception as e:
                logger.error(f"❌ Atomic write failed for {rel_path}: {e}")
                continue

            logger.info(f"🩹 Patched: {rel_path}")
            if rel_path not in patched_files:
                patched_files.append(rel_path)

        return len(patched_files) > 0, patched_files

    def update_workspace_from_code(self, project_id: str, code: str, prompt: str, is_incremental: bool = None) -> Tuple[str, Path]:
        """Update the git workspace directly with new code and commit it."""
        project_dir = self.artifacts_dir / project_id
        workspace_dir = project_dir / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        
        # Ensure git is initialized
        if not (workspace_dir / ".git").exists():
            git_manager.init_repo(project_id)
            git_manager._run_git_command(project_id, ["config", "user.email", "vibe@engineer.com"])
            git_manager._run_git_command(project_id, ["config", "user.name", "Vibe Engineer"])

        # Ensure metadata.json is always gitignored (never committed)
        gitignore_path = workspace_dir / ".gitignore"
        gitignore_entry = "metadata.json\n"
        existing_gitignore = gitignore_path.read_text() if gitignore_path.exists() else ""
        if "metadata.json" not in existing_gitignore:
            with open(gitignore_path, 'a') as f:
                f.write(gitignore_entry)
        # Untrack metadata.json if it was previously committed
        git_manager._run_git_command(project_id, ["rm", "--cached", "metadata.json", "--ignore-unmatch", "-q"])

        # ── Patch mode: AI returned PATCH hunks — apply surgically ──────
        has_patches = bool(re.search(r'//\s*PATCH:\s*', code))
        has_raw_search = (
            not has_patches
            and bool(re.search(r'<<<\s*SEARCH', code))
            and bool(re.search(r'<<<\s*REPLACE', code))
        )
        if has_patches or has_raw_search:
            applied, patched_files = self.apply_patch_response(project_id, code)
            
            # Check if patches were rejected due to frozen files
            if not applied and patched_files == []:
                # Check if it was due to frozen files
                frozen_files = self.get_frozen_files(project_id)
                if frozen_files:
                    patch_targets = re.findall(r'//\s*PATCH:\s*([^\n]+)', code)
                    patch_targets = [f.strip() for f in patch_targets]
                    frozen_violations = [f for f in patch_targets if f in frozen_files]
                    if frozen_violations:
                        # Raise exception to be caught by main.py
                        raise ValueError(f"FROZEN_FILES_VIOLATION:{','.join(frozen_violations)}")
            
            if applied:
                logger.info(f"🩹 Applied patches to: {', '.join(patched_files)}")
                # Also handle any FILE: blocks mixed in (new files)
                file_marker_regex = r'//\s*FILE:\s*([^\n]+)|#\s*FILE:\s*([^\n]+)|<!--\s*FILE:\s*([^\n]+)\s*-->'
                file_matches = list(re.finditer(file_marker_regex, code))
                for i, match in enumerate(file_matches):
                    filename = (match.group(1) or match.group(2) or match.group(3)).strip()
                    start_pos = match.end()
                    end_pos = file_matches[i + 1].start() if i < len(file_matches) - 1 else len(code)
                    file_content = code[start_pos:end_pos].strip()
                    file_path = workspace_dir / filename
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(file_content)
                    logger.info(f"  📄 Created/updated: {filename}")

                git_manager.add_files(project_id)
                status = git_manager.get_status(project_id)
                has_changes = status.get("modified_files") or status.get("added_files") or status.get("deleted_files") or status.get("untracked_files")
                if has_changes:
                    git_manager.commit(project_id, f"[Patch] {prompt}")
                hash_res = git_manager._run_git_command(project_id, ["rev-parse", "HEAD"])
                commit_hash = hash_res["stdout"].strip() if hash_res["status"] == "success" else f"commit_{int(time.time())}"
                # Preserve existing metadata
                self._ensure_workspace_metadata(project_id, workspace_dir, commit_hash)
                return commit_hash, workspace_dir / patched_files[0]
            else:
                logger.warning("⚠️ Patch parsing found no applicable hunks — returning without writing raw patch text as file")
                # Do NOT fall through — writing raw patch markers as a file would corrupt the workspace
                hash_res = git_manager._run_git_command(project_id, ["rev-parse", "HEAD"])
                commit_hash = hash_res["stdout"].strip() if hash_res["status"] == "success" else f"commit_{int(time.time())}"
                return commit_hash, workspace_dir

        # Auto-detect incremental mode if not specified
        if is_incremental is None:
            skip_dirs = {'node_modules', '.git', '__pycache__', '.venv', 'venv', 'dist', 'build'}
            existing_file_count = 0
            try:
                for f in workspace_dir.rglob('*'):
                    if any(part in skip_dirs for part in f.parts):
                        continue
                    try:
                        if f.exists() and f.is_file():
                            existing_file_count += 1
                    except (OSError, PermissionError):
                        continue
            except Exception as e:
                logger.warning(f"Error counting existing files: {e}")
                existing_file_count = 0
            
            file_marker_regex = r'//\s*FILE:\s*([^\n]+)|#\s*FILE:\s*([^\n]+)|<!--\s*FILE:\s*([^\n]+)\s*-->'
            generated_file_count = len(re.findall(file_marker_regex, code))
            
            if existing_file_count > 0 and generated_file_count > 0:
                if generated_file_count < existing_file_count * 0.5:
                    is_incremental = True
                    logger.info(f"✏️ Auto-detected incremental mode: {generated_file_count} files generated vs {existing_file_count} existing")
                else:
                    is_incremental = False
                    logger.info(f"🔄 Auto-detected full regeneration: {generated_file_count} files generated vs {existing_file_count} existing")
            else:
                is_incremental = False
                logger.info(f"🆕 New project or full generation")

        # If not incremental, clear workspace (except .git)
        if not is_incremental:
            logger.info(f"🔄 Full workspace replacement for {project_id}")
            for item in workspace_dir.iterdir():
                if item.name != '.git':
                    if item.is_dir():
                        import shutil
                        shutil.rmtree(item)
                    else:
                        item.unlink()
        else:
            logger.info(f"✏️ Incremental update for {project_id}")

        # 1. Parse code into files and write to workspace
        file_marker_regex = r'//\s*FILE:\s*([^\n]+)|#\s*FILE:\s*([^\n]+)|<!--\s*FILE:\s*([^\n]+)\s*-->'
        matches = list(re.finditer(file_marker_regex, code))
        
        # Check for frozen file violations in FILE: markers
        if matches:
            frozen_files = self.get_frozen_files(project_id)
            if frozen_files:
                generated_files = []
                for match in matches:
                    filename = (match.group(1) or match.group(2) or match.group(3)).strip()
                    generated_files.append(filename)
                
                frozen_violations = [f for f in generated_files if f in frozen_files]
                if frozen_violations:
                    # Remove duplicates
                    frozen_violations = list(set(frozen_violations))
                    raise ValueError(f"FROZEN_FILES_VIOLATION:{','.join(frozen_violations)}")
        
        main_file_path = None
        
        if matches and len(matches) > 0:
            for i, match in enumerate(matches):
                filename = (match.group(1) or match.group(2) or match.group(3)).strip()
                start_pos = match.end()
                end_pos = matches[i + 1].start() if i < len(matches) - 1 else len(code)
                file_content = code[start_pos:end_pos].strip()
                
                file_path = workspace_dir / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Inject editor script into HTML files
                if filename.endswith('.html'):
                    if '</body>' in file_content:
                        file_content = file_content.replace('</body>', f'{EDITOR_INJECTION_SCRIPT}</body>')
                    else:
                        file_content += EDITOR_INJECTION_SCRIPT

                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(file_content)
                
                logger.info(f"  {'📝 Updated' if is_incremental else '📄 Created'}: {filename}")
                
                if main_file_path is None and filename.endswith(('.py', '.js', '.html', '.jsx', '.tsx')):
                    main_file_path = file_path
            
            if main_file_path is None:
                filename = (matches[0].group(1) or matches[0].group(2) or matches[0].group(3)).strip()
                main_file_path = workspace_dir / filename
        else:
            # Single file
            filename = "app.py" if any(k in code for k in ["import ", "def ", "class "]) else "index.html"
            if filename.endswith('.html'):
                if '</body>' in code:
                    code = code.replace('</body>', f'{EDITOR_INJECTION_SCRIPT}</body>')
                else:
                    code += EDITOR_INJECTION_SCRIPT
            
            main_file_path = workspace_dir / filename
            with open(main_file_path, 'w', encoding='utf-8') as f:
                f.write(code)

        # 2. Commit the changes
        git_manager.add_files(project_id)
        # Check if there are changes to commit
        status = git_manager.get_status(project_id)
        has_changes = status.get("modified_files") or status.get("added_files") or status.get("deleted_files") or status.get("untracked_files")
        
        if has_changes:
            commit_msg = f"{'[Incremental] ' if is_incremental else ''}{prompt}"
            git_manager.commit(project_id, commit_msg)
        
        # Get the commit hash to use as version_id/checkpoint_id
        hash_res = git_manager._run_git_command(project_id, ["rev-parse", "HEAD"])
        commit_hash = hash_res["stdout"].strip() if hash_res["status"] == "success" else f"commit_{int(time.time())}"
        
        logger.info(f"✅ Committed workspace changes: {commit_hash[:8]}")
        
        # 3. Create metadata.json for container creation
        # This is needed for create_container_for_code to work
        metadata = {
            "runtime": "universal",
            "docker_image": "vibecoding-agent-runtime:latest",
            "port": 80,
            "additional_ports": [],
            "created_at": datetime.now().isoformat(),
            "commit_hash": commit_hash
        }

        # Detect runtime by walking the full workspace tree (handles multi-stack subdirs)
        has_py = False
        has_package_json = False
        has_requirements = False
        for root, dirs, fnames in os.walk(workspace_dir):
            dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__', 'venv', 'dist', 'build')]
            for fname in fnames:
                if fname.endswith('.py'):
                    has_py = True
                if fname == 'package.json':
                    has_package_json = True
                if fname == 'requirements.txt':
                    has_requirements = True

        if has_py and has_package_json:
            # Multi-stack: backend + frontend — agent handles via nginx
            metadata["runtime"] = "multi-stack"
            metadata["port"] = 80
        elif has_py:
            metadata["runtime"] = "python"
            metadata["port"] = 80
        elif has_package_json:
            metadata["runtime"] = "node"
            metadata["port"] = 80

        metadata_file = workspace_dir / "metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        return commit_hash, main_file_path
    
    def update_project_metadata(self, project_id: str, metadata: dict):
        """Update existing project metadata"""
        project_dir = self.artifacts_dir / project_id
        metadata_file = project_dir / "metadata.json"
        
        if not metadata_file.exists():
            return False
            
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        return True

    def _update_project_metadata(self, project_id: str, version_id: str, prompt: str):
        """Update project metadata with new version"""
        project_dir = self.artifacts_dir / project_id
        metadata_file = project_dir / "metadata.json"
        
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        
        metadata["versions"].append({
            "version_id": version_id,
            "prompt": prompt,
            "created_at": datetime.now().isoformat()
        })
        metadata["current_version"] = version_id
        
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
    
    SUPERVISOR_SOCKET = os.environ.get("SUPERVISOR_SOCKET", "/tmp/supervisor.sock")

    def _send_switch_command(self, container, version_id: str) -> bool:
        """Send version switch command to supervisor inside container"""
        try:
            # Create a Python script to send the command properly via the supervisor socket
            python_cmd = f"""
import socket, json, sys
try:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect('{self.SUPERVISOR_SOCKET}')
        s.send(json.dumps({{'action': 'switch', 'version_id': '{version_id}'}}).encode())
        print(s.recv(1024).decode())
except Exception as e:
    print(f'Error: {{e}}', file=sys.stderr)
    sys.exit(1)
"""
            exec_result = container.exec_run(
                ['python3', '-c', python_cmd],
                demux=True
            )
            
            if exec_result.exit_code == 0:
                response = exec_result.output[0].decode() if exec_result.output[0] else ""
                logger.info(f"📨 Supervisor response: {response}")
                return True
            else:
                error = exec_result.output[1].decode() if exec_result.output[1] else ""
                logger.error(f"❌ Failed to send switch command: {error}")
                return False
        except Exception as e:
            logger.error(f"❌ Error sending switch command: {e}")
            return False

    async def switch_to_workspace(self, project_id: str) -> bool:
        """Switch the container to run from the workspace directory (Git state)
        Creates container if it doesn't exist"""
        container_name = f"vibecoding_{project_id}"
        
        if self.docker_client is None:
            return False
            
        try:
            # Try to get existing container
            try:
                container = self.docker_client.containers.get(container_name)
                if container.status != 'running':
                    container.start()
                    await asyncio.sleep(2)
                    
                return self._send_switch_command(container, "workspace")
            except docker.errors.NotFound:
                # Container doesn't exist, create it
                logger.info(f"🆕 Container not found, creating for project {project_id}")
                preview_url = await self.create_container_for_code(project_id, "workspace")
                return preview_url is not None
                
        except Exception as e:
            logger.error(f"Failed to switch to workspace: {e}")
            return False
    
    async def create_container_for_code(self, project_id: str, version_id: str) -> Optional[str]:
        """Create or reuse Docker container and switch to the specified version"""
        project_dir = self.artifacts_dir / project_id
        
        # Handle workspace vs versioned code differently
        if version_id == "workspace":
            # For workspace, metadata is in workspace directory
            version_dir = project_dir / "workspace"
            metadata_file = version_dir / "metadata.json"
        else:
            # For versioned code, metadata is in versions/{version_id}
            version_dir = project_dir / "versions" / version_id
            metadata_file = version_dir / "metadata.json"
        
        # Read version metadata to get runtime info
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            runtime = metadata.get('runtime', 'static-html')
            docker_image = metadata.get('docker_image', 'vibecoding-agent-runtime:latest')
            
            # Support multiple ports
            primary_port = metadata.get('port', 80)
            additional_ports = metadata.get('additional_ports', [])
            all_ports = [primary_port] + [p for p in additional_ports if p != primary_port]
            
            logger.info(f"🚀 Switching to version {version_id}")
            logger.info(f"🔍 Runtime: {runtime}")
            logger.info(f"🔌 Ports: {all_ports}")
            
        except Exception as e:
            logger.error(f"Failed to read metadata: {e}")
            return None
        
        # Use project_id only for container name (one container per project)
        container_name = f"vibecoding_{project_id}"
        
        # Check if Docker is available
        if self.docker_client is None:
            logger.error("❌ Docker client not available - cannot create container")
            logger.error("Please ensure Docker Desktop is installed and running")
            return None
        
        # Ensure image exists before running
        if not self._ensure_image_exists(docker_image):
            logger.error(f"❌ Image {docker_image} not found and could not be built")
            return None
        
        try:
            # Check if container already exists
            existing_container = None
            
            try:
                existing_container = self.docker_client.containers.get(container_name)
                logger.info(f"♻️ Found existing container: {container_name}")
                
                # Container exists - send version switch command
                if existing_container.status != 'running':
                    existing_container.start()
                    logger.info(f"▶️ Started stopped container")
                    # Wait longer for supervisor to be ready after a cold start
                    await asyncio.sleep(5)
                
                # Send switch command to supervisor — retry a few times if just started
                logger.info(f"📡 Sending switch command to version {version_id}")
                success = False
                for attempt in range(3):
                    success = self._send_switch_command(existing_container, version_id)
                    if success:
                        break
                    logger.warning(f"⚠️ Switch attempt {attempt+1} failed, retrying...")
                    await asyncio.sleep(2)
                
                if success:
                    logger.info(f"✅ Switched to version {version_id}")
                    container = existing_container
                else:
                    logger.warning(f"⚠️ Failed to switch version, recreating container")
                    existing_container.stop()
                    existing_container.remove()
                    existing_container = None
                
            except docker.errors.NotFound:
                logger.info(f"🆕 Creating new container: {container_name}")
            
            # Create new container only if doesn't exist or switch failed
            if existing_container is None:
                # Prepare port bindings for all required ports
                port_bindings = {f'{p}/tcp': None for p in all_ports}
                
                # Mount the ENTIRE project directory so all versions are accessible
                container = self.docker_client.containers.run(
                    docker_image,
                    name=container_name,
                    ports=port_bindings,
                    volumes={
                        str(project_dir.absolute()): {
                            'bind': '/project',
                            'mode': 'rw'
                        }
                    },
                    working_dir='/app',
                    detach=True,
                    remove=False,
                    environment={
                        'PYTHONUNBUFFERED': '1',
                        'PORT': str(primary_port),
                        'ADDITIONAL_PORTS': ','.join(map(str, additional_ports)),
                        'INITIAL_VERSION': version_id,
                        'AI_API_KEY': ai_config.api_key,
                        'AI_API_URL': ai_config.base_url,
                        'AI_MODEL': ai_config.model,
                        'USER_PROMPT': self._current_user_prompt or '',
                    }
                )
                
                logger.info(f"🏗️ Created container with initial version {version_id}")
                
                # Wait for supervisor to start
                await asyncio.sleep(3)
            
            # Store container reference
            self.running_containers[container_name] = container
            
            # Start log streaming in a separate thread
            log_thread = threading.Thread(
                target=self._stream_container_logs,
                args=(container, container_name),
                daemon=True
            )
            log_thread.start()
            self.log_threads[container_name] = log_thread
            
            # Get assigned host port for the primary port
            container.reload()
            primary_port_bindings = container.ports.get(f'{primary_port}/tcp', [])
            if not primary_port_bindings:
                logger.error(f"No port binding found for {primary_port}/tcp")
                return None
            
            host_port = primary_port_bindings[0].get('HostPort')
            if not host_port:
                logger.error(f"Failed to get host port")
                return None
            
            # Save container port mapping to registry for proxy
            self._save_container_registry(project_id, host_port)
            
            # Use PUBLIC_HOST env var for AWS deployments, fallback to localhost
            public_host = os.getenv('PUBLIC_HOST', 'http://localhost').rstrip('/')
            
            # If using proxy mode, return proxy URL instead of direct port
            use_proxy = os.getenv('USE_PREVIEW_PROXY', 'true').lower() == 'true'
            if use_proxy:
                url = f"{public_host}/app/{project_id}/"
            else:
                url = f"{public_host}:{host_port}"
            
            logger.info(f"✅ Container running at: {url}")
            
            # Wait for server to be ready (check Docker health status)
            max_wait_time = 30  # 30 seconds
            start_time = asyncio.get_event_loop().time()
            
            while (asyncio.get_event_loop().time() - start_time) < max_wait_time:
                try:
                    # Reload container to get latest health status
                    container.reload()
                    
                    # Check if container has health check configured
                    health_status = container.attrs.get('State', {}).get('Health', {}).get('Status')
                    
                    if health_status == 'healthy':
                        logger.info(f"🎉 Container health check passed - server ready at {url}")
                        return url
                    elif health_status == 'unhealthy':
                        logger.warning(f"⚠️ Container health check failed")
                        break
                    
                    # If no health check, try HTTP request
                    if health_status is None:
                        try:
                            response = requests.get(url, timeout=2)
                            if response.status_code < 500:
                                logger.info(f"🎉 Server responding at {url}")
                                return url
                        except:
                            pass
                    
                except Exception as e:
                    logger.debug(f"Health check attempt failed: {e}")
                
                await asyncio.sleep(1)
            
            logger.info(f"⏱️ Health check timeout - container may still be starting. URL: {url}")
            return url
            
        except Exception as e:
            logger.error(f"Failed to create container: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def stop_container(self, project_id: str, version_id: str = None):
        """Stop and remove container (version_id is ignored, one container per project)"""
        container_name = f"vibecoding_{project_id}"
        
        if container_name in self.running_containers:
            try:
                container = self.running_containers[container_name]
                container.stop()
                container.remove()
                del self.running_containers[container_name]
                
                # Clean up log thread reference (thread will exit automatically)
                if container_name in self.log_threads:
                    del self.log_threads[container_name]
                
                logger.info(f"Stopped container {container_name}")
            except Exception as e:
                logger.error(f"Failed to stop container {container_name}: {str(e)}")
    
    def create_project_zip(self, project_id: str) -> Optional[Path]:
        """Create ZIP archive of entire project"""
        project_dir = self.artifacts_dir / project_id
        
        if not project_dir.exists():
            logger.error(f"Project directory not found: {project_dir}")
            return None
        
        zip_path = self.artifacts_dir / f"{project_id}_complete.zip"
        
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in project_dir.rglob('*'):
                    if file_path.is_file():
                        # Skip huge, problematic folders like node_modules
                        if "node_modules" in file_path.parts:
                            continue
                        arcname = file_path.relative_to(project_dir)
                        zipf.write(file_path, arcname)
            
            logger.info(f"Created project ZIP: {zip_path}")
            return zip_path
        except Exception as e:
            logger.error(f"Failed to create ZIP: {str(e)}")
            return None
    
    async def save_chat_version(self, project_id: str, version_id: str, messages: List[Dict]):
        """Save chat history for a specific project version"""
        project_dir = self.artifacts_dir / project_id
        chats_dir = project_dir / "chats"
        chats_dir.mkdir(exist_ok=True)
        
        chat_file = chats_dir / f"{version_id}.json"
        with open(chat_file, 'w', encoding='utf-8') as f:
            json.dump(messages, f, indent=2)
        return True

    async def get_chat_version(self, project_id: str, version_id: str) -> Optional[List[Dict]]:
        """Get chat history for a specific project version"""
        project_dir = self.artifacts_dir / project_id
        chat_file = project_dir / "chats" / f"{version_id}.json"
        
        if not chat_file.exists():
            return None
            
        with open(chat_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_project_info(self, project_id: str) -> Optional[Dict]:
        """Get project information"""
        project_dir = self.artifacts_dir / project_id
        metadata_file = project_dir / "metadata.json"
        
        if not metadata_file.exists():
            return None
        
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            # Fallback for missing fields in legacy projects
            if "name" not in metadata:
                metadata["name"] = f"Project {metadata.get('project_id', 'Unknown')[:8]}"
            if "description" not in metadata:
                metadata["description"] = ""
                
            return metadata
        except Exception as e:
            print(f"Error loading metadata for {project_id}: {e}")
            return None
    
    def get_version_code(self, project_id: str, version_id: str) -> Optional[str]:
        """Get code for specific version"""
        project_dir = self.artifacts_dir / project_id
        
        if version_id == "workspace":
            version_dir = project_dir / "workspace"
        else:
            version_dir = project_dir / "versions" / version_id
        
        if not version_dir.exists():
            return None
        
        # Try metadata first to find the main file or entrypoint
        metadata_file = version_dir / "metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                main_file = metadata.get('entrypoint') or metadata.get('main_file')
            except Exception:
                main_file = None
            
            if main_file:
                code_file = version_dir / main_file
                if code_file.exists():
                    with open(code_file, 'r', encoding='utf-8') as f:
                        return f.read()

        # Final fallback: return the first text-like file found in the root
        for p in version_dir.iterdir():
            if p.is_file() and not p.name.startswith(('.', 'metadata.json', 'package-lock.json', 'yarn.lock')):
                try:
                    return p.read_text(encoding='utf-8')
                except Exception:
                    continue
        
        return None

    def get_version_all_files(self, project_id: str, version_id: str) -> Optional[Dict]:
        """Get ALL files for a specific version as { filepath: content }"""
        project_dir = self.artifacts_dir / project_id
        
        if version_id == "workspace":
            version_dir = project_dir / "workspace"
        else:
            version_dir = project_dir / "versions" / version_id
        
        if not version_dir.exists():
            return None
        
        files = {}
        for file_path in version_dir.rglob('*'):
            if file_path.is_file() and file_path.name != 'metadata.json':
                try:
                    rel_path = str(file_path.relative_to(version_dir)).replace('\\', '/')
                    files[rel_path] = file_path.read_text(encoding='utf-8')
                except Exception:
                    continue
        
        return files

    def get_all_versions(self, project_id: str) -> List[Dict]:
        """Get metadata for all versions of a project, sorted by version_id"""
        project_dir = self.artifacts_dir / project_id
        versions_dir = project_dir / "versions"
        
        if not versions_dir.exists():
            return []
        
        versions = []
        for vdir in sorted(versions_dir.iterdir()):
            if vdir.is_dir():
                meta_file = vdir / "metadata.json"
                if meta_file.exists():
                    try:
                        with open(meta_file, 'r') as f:
                            meta = json.load(f)
                        versions.append(meta)
                    except Exception:
                        # Fallback: create basic metadata from directory name
                        versions.append({
                            "version_id": vdir.name,
                            "prompt": "",
                            "created_at": datetime.fromtimestamp(vdir.stat().st_mtime).isoformat()
                        })
                else:
                    # No metadata file, create basic entry
                    versions.append({
                        "version_id": vdir.name,
                        "prompt": "",
                        "created_at": datetime.fromtimestamp(vdir.stat().st_mtime).isoformat()
                    })
        
        return versions
    
    def list_projects(self, owner_id: Optional[int] = None) -> List[Dict]:
        """List projects, optionally filtered by owner_id"""
        projects = []
        
        for project_dir in self.artifacts_dir.iterdir():
            if project_dir.is_dir():
                metadata_file = project_dir / "metadata.json"
                if metadata_file.exists():
                    try:
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                        
                        # Fallback for missing fields in legacy projects
                        if "name" not in metadata:
                            metadata["name"] = f"Project {metadata.get('project_id', 'Unknown')[:8]}"
                        if "description" not in metadata:
                            metadata["description"] = ""
                        
                        # Filter by owner_id if specified (STRICT)
                        if owner_id is not None:
                            project_owner = metadata.get("owner_id")
                            # Only show if owner matches
                            if project_owner != owner_id:
                                continue
                            
                        projects.append(metadata)
                    except Exception as e:
                        print(f"Error loading metadata for {project_dir.name}: {e}")
        
        return projects
    
    def cleanup_old_containers(self):
        """Clean up old containers"""
        try:
            if self.docker_client is None:
                logger.info("Docker not available, skipping container cleanup")
                return
                
            containers = self.docker_client.containers.list(
                all=True,
                filters={"name": "vibecoding_"}
            )
            
            for container in containers:
                try:
                    container.remove(force=True)
                    logger.info(f"Removed old container: {container.name}")
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Failed to cleanup containers: {str(e)}")
    
    def get_frozen_files(self, project_id: str) -> List[str]:
        """Get list of frozen (read-only) files for a project"""
        project_dir = self.artifacts_dir / project_id
        frozen_file = project_dir / "frozen_files.json"
        
        if not frozen_file.exists():
            return []
        
        try:
            with open(frozen_file, 'r') as f:
                data = json.load(f)
                return data.get("frozen_files", [])
        except Exception as e:
            logger.error(f"Error reading frozen files: {e}")
            return []
    
    def set_file_frozen(self, project_id: str, file_path: str, frozen: bool) -> bool:
        """Set or unset frozen status for a file"""
        project_dir = self.artifacts_dir / project_id
        frozen_file = project_dir / "frozen_files.json"
        
        # Load existing frozen files
        frozen_files = self.get_frozen_files(project_id)
        
        # Update the list
        if frozen:
            if file_path not in frozen_files:
                frozen_files.append(file_path)
                logger.info(f"🔒 Froze file: {file_path}")
        else:
            if file_path in frozen_files:
                frozen_files.remove(file_path)
                logger.info(f"🔓 Unfroze file: {file_path}")
        
        # Save updated list
        try:
            with open(frozen_file, 'w') as f:
                json.dump({"frozen_files": frozen_files}, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving frozen files: {e}")
            return False
    
    def is_file_frozen(self, project_id: str, file_path: str) -> bool:
        """Check if a file is frozen"""
        frozen_files = self.get_frozen_files(project_id)
        return file_path in frozen_files
    
    def _save_container_registry(self, project_id: str, host_port: str):
        """Save container port mapping to registry for proxy access"""
        registry_file = self.artifacts_dir / '.container_registry.json'
        
        # Load existing registry
        registry = {}
        if registry_file.exists():
            try:
                with open(registry_file, 'r') as f:
                    registry = json.load(f)
            except Exception:
                pass
        
        # Update registry
        container_name = f"vibecoding_{project_id}"
        registry[container_name] = {
            'project_id': project_id,
            'port': host_port,
            'updated_at': datetime.now().isoformat()
        }
        
        # Save registry
        try:
            with open(registry_file, 'w') as f:
                json.dump(registry, f, indent=2)
            logger.info(f"📝 Saved container registry: {project_id} -> port {host_port}")
        except Exception as e:
            logger.error(f"Failed to save container registry: {e}")

# Global project manager instance
project_manager = ProjectManager()
