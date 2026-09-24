import os
import json
import logging
import asyncio
import tempfile
import subprocess
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from datetime import datetime
from app.integrations.llm import llm_gateway

logger = logging.getLogger(__name__)

@dataclass
class BackendBlueprintEntry:
    file_path: str              # e.g. 'backend/app/routes/auth.py'
    purpose: str                # e.g. 'Implement POST /api/auth/login and POST /api/auth/register'
    api_endpoints: List[Dict]   # [{method, path, request_schema, response_schema}]
    data_model_refs: List[str]  # Data model names this file uses
    dependencies: List[str]     # Other backend files this depends on
    implementation_notes: str   # Specific implementation guidance

@dataclass
class BackendBlueprint:
    entries: Dict[str, BackendBlueprintEntry]  # file_path -> entry
    db_setup_instructions: str     # How to set up the database
    auth_setup_instructions: str   # How to set up authentication
    dependency_install_commands: List[str]  # pip install X, npm install Y
    environment_variables: Dict[str, str]   # .env keys needed
    raw_markdown: str              # Full blueprint as readable markdown

@dataclass
class IntegrationFileTask:
    frontend_file: str             # File to modify
    mock_imports_to_remove: List[str]  # Import lines to remove
    api_hooks_to_add: List[Dict]   # [{hook_name, endpoint, method, response_type}]
    env_vars_needed: List[str]     # Environment variables this file needs
    notes: str                     # Integration-specific notes

@dataclass
class IntegrationBlueprint:
    file_tasks: Dict[str, IntegrationFileTask]  # frontend_file -> task
    proxy_config: Dict             # Dev server proxy settings
    cors_config: Dict              # CORS settings for backend
    env_file_template: str         # .env template content
    raw_markdown: str              # Full blueprint as readable markdown


class MasterBlueprintService:
    """
    Generates phase-transition blueprints by analyzing completed work.
    Called at phase gates by the coordination service.
    """

    async def generate_backend_blueprint(
        self,
        project_token: str,
        plan: Any,  # Expected to be MasterTechnicalPlan
        completed_frontend_files: Dict[str, str],  # {path: content} from container
    ) -> BackendBlueprint:
        """
        Phase 1 → Phase 2 gate.
        
        1. Read the MasterTechnicalPlan's api_contracts and data_models
        2. Read completed frontend files to understand:
           - What mock data shapes are used
           - What API call patterns exist (fetch URLs, hook names)
           - What form submission handlers expect
        3. Generate a Backend Blueprint with:
           - File-by-file implementation instructions
           - API endpoint details (request/response matching frontend expectations)
           - Database model implementations
           - Auth strategy implementation details
           - Dependency installation commands
        4. Write blueprint as markdown to container
        
        The LLM prompt must reference the ACTUAL tech stack from plan.tech_stack,
        not assume FastAPI/Django/Express.
        """
        prompt = f"""
        You are a senior backend architect generating a Backend Blueprint.
        The tech stack for this project is:
        {json.dumps(getattr(plan, 'tech_stack', {{}}), indent=2)}
        
        The API Contracts are:
        {json.dumps(getattr(plan, 'api_contracts', []), indent=2)}
        
        The Data Models are:
        {json.dumps(getattr(plan, 'data_models', []), indent=2)}
        
        The frontend has been completed. Here are the completed frontend files to see how mock data is used:
        {json.dumps(completed_frontend_files, indent=2)}
        
        Based on this, generate a complete backend blueprint in JSON matching exactly this schema:
        {{
            "entries": {{
                "file_path": {{
                    "file_path": "str",
                    "purpose": "str",
                    "api_endpoints": [{{"method": "str", "path": "str", "request_schema": {{}}, "response_schema": {{}}}}],
                    "data_model_refs": ["str"],
                    "dependencies": ["str"],
                    "implementation_notes": "str"
                }}
            }},
            "db_setup_instructions": "str",
            "auth_setup_instructions": "str",
            "dependency_install_commands": ["str"],
            "environment_variables": {{
                "KEY": "VALUE"
            }}
        }}
        
        DO NOT include markdown block markers for JSON (no ```json). Just return raw JSON.
        Make it specific to the chosen backend tech stack, DB, and Auth specified in the technical plan.
        """
        
        response_text = await llm_gateway.generate_text(
            prompt=prompt, 
            system_prompt="You are a JSON generating backend architect."
        )
        
        try:
            # Strip potential markdown blocks just in case
            if response_text.startswith("```"):
                response_text = "\n".join(response_text.split("\n")[1:-1])
            data = json.loads(response_text)
        except Exception as e:
            logger.error(f"Failed to parse LLM response for Backend Blueprint: {e}\nResponse: {response_text}")
            raise

        entries = {}
        for path, entry_data in data.get("entries", {}).items():
            entries[path] = BackendBlueprintEntry(
                file_path=entry_data.get("file_path", path),
                purpose=entry_data.get("purpose", ""),
                api_endpoints=entry_data.get("api_endpoints", []),
                data_model_refs=entry_data.get("data_model_refs", []),
                dependencies=entry_data.get("dependencies", []),
                implementation_notes=entry_data.get("implementation_notes", "")
            )
            
        blueprint = BackendBlueprint(
            entries=entries,
            db_setup_instructions=data.get("db_setup_instructions", ""),
            auth_setup_instructions=data.get("auth_setup_instructions", ""),
            dependency_install_commands=data.get("dependency_install_commands", []),
            environment_variables=data.get("environment_variables", {}),
            raw_markdown=""
        )
        
        blueprint.raw_markdown = self._format_blueprint_as_markdown(blueprint, plan)
        return blueprint


    async def generate_integration_blueprint(
        self,
        project_token: str,
        plan: Any, # Expected to be MasterTechnicalPlan
        completed_frontend_files: Dict[str, str],  # Phase 1 files
        completed_backend_files: Dict[str, str],   # Phase 2 files  
    ) -> IntegrationBlueprint:
        """
        Phase 2 → Phase 3 gate.
        
        1. Read completed backend files to find actual API routes/endpoints
        2. Cross-reference with frontend mock data usage
        3. For each frontend file that uses mocks:
           - Identify which mock import to remove
           - Identify which API endpoint to call
           - Generate the replacement code pattern (hooks, fetch, axios, etc.)
        4. Generate proxy/CORS configuration
        5. Generate .env template
        
        The replacement code must match the ACTUAL frontend framework.
        """
        prompt = f"""
        You are a senior integration architect generating an Integration Blueprint.
        The tech stack for this project is:
        {json.dumps(getattr(plan, 'tech_stack', {{}}), indent=2)}
        
        Completed Frontend Files:
        {json.dumps(completed_frontend_files, indent=2)}
        
        Completed Backend Files:
        {json.dumps(completed_backend_files, indent=2)}
        
        The frontend currently uses mock data. You need to provide instructions to replace mocks with real API calls using the real backend routes.
        
        Generate an Integration Blueprint in JSON matching exactly this schema:
        {{
            "file_tasks": {{
                "frontend_file_path": {{
                    "frontend_file": "str",
                    "mock_imports_to_remove": ["str"],
                    "api_hooks_to_add": [{{"hook_name": "str", "endpoint": "str", "method": "str", "response_type": "str"}}],
                    "env_vars_needed": ["str"],
                    "notes": "str"
                }}
            }},
            "proxy_config": {{"config_key": "config_value"}},
            "cors_config": {{"config_key": "config_value"}},
            "env_file_template": "str"
        }}
        
        DO NOT include markdown block markers for JSON (no ```json). Just return raw JSON.
        Make sure instructions match the EXACT frontend framework specified in the tech stack (e.g., React Query for React, or HttpClient for Angular, etc.).
        """
        
        response_text = await llm_gateway.generate_text(
            prompt=prompt, 
            system_prompt="You are a JSON generating integration architect."
        )
        
        try:
            if response_text.startswith("```"):
                response_text = "\n".join(response_text.split("\n")[1:-1])
            data = json.loads(response_text)
        except Exception as e:
            logger.error(f"Failed to parse LLM response for Integration Blueprint: {e}\nResponse: {response_text}")
            raise

        file_tasks = {}
        for path, task_data in data.get("file_tasks", {}).items():
            file_tasks[path] = IntegrationFileTask(
                frontend_file=task_data.get("frontend_file", path),
                mock_imports_to_remove=task_data.get("mock_imports_to_remove", []),
                api_hooks_to_add=task_data.get("api_hooks_to_add", []),
                env_vars_needed=task_data.get("env_vars_needed", []),
                notes=task_data.get("notes", "")
            )
            
        blueprint = IntegrationBlueprint(
            file_tasks=file_tasks,
            proxy_config=data.get("proxy_config", {}),
            cors_config=data.get("cors_config", {}),
            env_file_template=data.get("env_file_template", ""),
            raw_markdown=""
        )
        
        blueprint.raw_markdown = self._format_blueprint_as_markdown(blueprint, plan)
        return blueprint

    async def _read_files_from_container(
        self, 
        container_name: str,
        file_paths: List[str],
        project_root: str,
    ) -> Dict[str, str]:
        """Read multiple files from the Docker container. Returns {path: content}."""
        results = {}
        for file_path in file_paths:
            try:
                # Construct path relative to project root
                full_path = f"{project_root.rstrip('/')}/{file_path.lstrip('/')}"
                result = subprocess.run(
                    ['docker', 'exec', container_name, 'cat', full_path],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    results[file_path] = result.stdout
                else:
                    logger.warning(f"Failed to read {full_path} from container {container_name}: {result.stderr}")
            except Exception as e:
                logger.error(f"Error reading file {file_path} from container: {e}")
        return results

    def _format_blueprint_as_markdown(
        self, blueprint: Union[BackendBlueprint, IntegrationBlueprint],
        plan: Any,
    ) -> str:
        """Format blueprint as readable markdown for storage in repo."""
        md = f"# Phase Gate Blueprint\n\nGenerated on {datetime.now().isoformat()}\n\n"
        tech_stack = getattr(plan, 'tech_stack', {})
        md += f"**Tech Stack**: {json.dumps(tech_stack, indent=2)}\n\n"
        
        if isinstance(blueprint, BackendBlueprint):
            md += "## Backend Blueprint\n\n"
            md += "### Setup Instructions\n"
            md += f"**Database**: {blueprint.db_setup_instructions}\n\n"
            md += f"**Auth**: {blueprint.auth_setup_instructions}\n\n"
            md += "### Dependencies\n"
            for cmd in blueprint.dependency_install_commands:
                md += f"- `{cmd}`\n"
            md += "\n### Environment Variables\n"
            for k, v in blueprint.environment_variables.items():
                md += f"- `{k}`: {v}\n"
            md += "\n### File Implementations\n"
            for path, entry in blueprint.entries.items():
                md += f"#### {path}\n"
                md += f"- **Purpose**: {entry.purpose}\n"
                md += f"- **Dependencies**: {', '.join(entry.dependencies)}\n"
                md += f"- **Models**: {', '.join(entry.data_model_refs)}\n"
                md += f"- **Notes**: {entry.implementation_notes}\n"
                if entry.api_endpoints:
                    md += "- **Endpoints**:\n"
                    for ep in entry.api_endpoints:
                        md += f"  - `{ep.get('method')} {ep.get('path')}`\n"
                md += "\n"
        else:
            md += "## Integration Blueprint\n\n"
            md += "### Configuration\n"
            md += f"**Proxy**: {json.dumps(blueprint.proxy_config)}\n\n"
            md += f"**CORS**: {json.dumps(blueprint.cors_config)}\n\n"
            md += f"### Environment Template\n```env\n{blueprint.env_file_template}\n```\n\n"
            
            md += "### Frontend File Updates\n"
            for path, task in blueprint.file_tasks.items():
                md += f"#### {path}\n"
                if task.mock_imports_to_remove:
                    md += "**Remove Mocks**:\n"
                    for imp in task.mock_imports_to_remove:
                        md += f"- `{imp}`\n"
                if task.api_hooks_to_add:
                    md += "**Add Hooks/Calls**:\n"
                    for hook in task.api_hooks_to_add:
                        md += f"- `{hook.get('hook_name')} ({hook.get('method')} {hook.get('endpoint')})`\n"
                if task.env_vars_needed:
                    md += f"**Env Vars**: {', '.join(task.env_vars_needed)}\n"
                md += f"**Notes**: {task.notes}\n\n"
                
        return md

    async def write_blueprint_to_container(
        self,
        container_name: str,
        blueprint_markdown: str,
        blueprint_type: str,  # 'backend' or 'integration'
        project_root: str,
    ) -> bool:
        """Write blueprint markdown to /workspace/docs/ in the container."""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"blueprint_{blueprint_type}_{timestamp}.md"
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write(blueprint_markdown)
                temp_path = f.name
                
            docs_dir = f"{project_root.rstrip('/')}/docs"
            
            # Create docs directory if it doesn't exist
            subprocess.run(['docker', 'exec', container_name, 'mkdir', '-p', docs_dir], check=True)
            
            # Copy temp file to container
            subprocess.run(['docker', 'cp', temp_path, f'{container_name}:{docs_dir}/{filename}'], check=True)
            
            # Clean up temp file
            os.unlink(temp_path)
            
            logger.info(f"Successfully wrote {blueprint_type} blueprint to container {container_name} at {docs_dir}/{filename}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Docker command failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to write blueprint to container: {e}")
            return False

    async def push_blueprint_to_github(
        self,
        container_name: str,
        blueprint_markdown: str,
        blueprint_name: str = "MASTER_TECHNICAL_PLAN.md",
        project_root: str = "/workspace",
        git_repo_url: Optional[str] = None,
        git_token: Optional[str] = None,
    ) -> bool:
        """
        Write blueprint markdown to /workspace/docs/{blueprint_name} and push it directly to GitHub as an .md file.
        """
        try:
            clean_name = blueprint_name if blueprint_name.endswith(".md") else f"{blueprint_name}.md"
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
                f.write(blueprint_markdown)
                temp_path = f.name
                
            docs_dir = f"{project_root.rstrip('/')}/docs"
            target_path = f"{docs_dir}/{clean_name}"
            
            # 1. Create docs dir inside container
            subprocess.run(['docker', 'exec', container_name, 'mkdir', '-p', docs_dir], check=True)
            
            # 2. Copy temp markdown file to container
            subprocess.run(['docker', 'cp', temp_path, f'{container_name}:{target_path}'], check=True)
            
            # Also write to root docs directory if inside nested project_root
            if project_root.rstrip('/') != "/workspace":
                root_docs = "/workspace/docs"
                subprocess.run(['docker', 'exec', container_name, 'mkdir', '-p', root_docs], check=True)
                subprocess.run(['docker', 'cp', temp_path, f'{container_name}:{root_docs}/{clean_name}'], check=True)
                
            os.unlink(temp_path)
            
            # 3. Git commit & push inside container
            git_cmd = (
                f"cd /workspace && "
                f"git config user.name 'Master Agent' && "
                f"git config user.email 'master-agent@dsuite.ai' && "
                f"git add docs/*.md 2>/dev/null || true && "
                f"git commit -m 'docs: add Master Agent technical blueprint ({clean_name})' 2>/dev/null || true && "
                f"git push origin HEAD 2>/dev/null || true"
            )
            
            res = subprocess.run(['docker', 'exec', container_name, 'sh', '-c', git_cmd], capture_output=True, text=True, timeout=30)
            logger.info(f"Blueprint {clean_name} git push output: returncode={res.returncode}, stdout={res.stdout[:200]}")
            return True
        except Exception as e:
            logger.error(f"Failed to push blueprint {blueprint_name} to GitHub: {e}")
            return False

# Module-level singleton
blueprint_service = MasterBlueprintService()

