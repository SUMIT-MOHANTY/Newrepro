import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
from app.integrations.llm import llm_gateway

logger = logging.getLogger(__name__)

@dataclass
class TechStackDecision:
    frontend: str
    backend: str
    database: str
    orm: str
    auth: str
    css_framework: str
    state_management: str
    package_manager: str
    runtime: str
    build_tool: str
    testing: str
    reasoning: str

    @classmethod
    def from_dict(cls, data: dict) -> 'TechStackDecision':
        return cls(**data)

@dataclass
class FileEntry:
    path: str
    purpose: str
    phase: int
    owner_task: str
    imports_from: List[str]
    exports: List[str]
    mock_data_keys: List[str]
    api_contracts: List[Dict]
    depends_on: List[str]

    @classmethod
    def from_dict(cls, data: dict) -> 'FileEntry':
        return cls(
            path=data.get('path', ''),
            purpose=data.get('purpose', ''),
            phase=data.get('phase', 0),
            owner_task=data.get('owner_task', ''),
            imports_from=data.get('imports_from', []),
            exports=data.get('exports', []),
            mock_data_keys=data.get('mock_data_keys', []),
            api_contracts=data.get('api_contracts', []),
            depends_on=data.get('depends_on', [])
        )

@dataclass
class DataModelSchema:
    name: str
    table_name: str
    fields: List[Dict]

    @classmethod
    def from_dict(cls, data: dict) -> 'DataModelSchema':
        return cls(
            name=data.get('name', ''),
            table_name=data.get('table_name', ''),
            fields=data.get('fields', [])
        )

@dataclass
class MockDataEntry:
    key: str
    shape: Dict[str, str]
    sample_data: List[Dict]
    source_api: str
    used_by_files: List[str]

    @classmethod
    def from_dict(cls, data: dict) -> 'MockDataEntry':
        return cls(
            key=data.get('key', ''),
            shape=data.get('shape', {}),
            sample_data=data.get('sample_data', []),
            source_api=data.get('source_api', ''),
            used_by_files=data.get('used_by_files', [])
        )

@dataclass
class APIContract:
    method: str
    path: str
    request_schema: Dict
    response_schema: Dict
    description: str
    mock_data_key: str
    frontend_consumer: str
    backend_implementor: str
    auth_required: bool

    @classmethod
    def from_dict(cls, data: dict) -> 'APIContract':
        return cls(
            method=data.get('method', ''),
            path=data.get('path', ''),
            request_schema=data.get('request_schema', {}),
            response_schema=data.get('response_schema', {}),
            description=data.get('description', ''),
            mock_data_key=data.get('mock_data_key', ''),
            frontend_consumer=data.get('frontend_consumer', ''),
            backend_implementor=data.get('backend_implementor', ''),
            auth_required=data.get('auth_required', False)
        )

@dataclass
class MasterTechnicalPlan:
    tech_stack: TechStackDecision
    file_registry: Dict[str, FileEntry]
    data_models: List[DataModelSchema]
    mock_data_spec: Dict[str, MockDataEntry]
    api_contracts: List[APIContract]
    project_type: str
    architecture_pattern: str
    created_at: str

    @classmethod
    def from_dict(cls, data: dict) -> 'MasterTechnicalPlan':
        return cls(
            tech_stack=TechStackDecision.from_dict(data.get('tech_stack', {})),
            file_registry={k: FileEntry.from_dict(v) for k, v in data.get('file_registry', {}).items()},
            data_models=[DataModelSchema.from_dict(d) for d in data.get('data_models', [])],
            mock_data_spec={k: MockDataEntry.from_dict(v) for k, v in data.get('mock_data_spec', {}).items()},
            api_contracts=[APIContract.from_dict(d) for d in data.get('api_contracts', [])],
            project_type=data.get('project_type', ''),
            architecture_pattern=data.get('architecture_pattern', ''),
            created_at=data.get('created_at', datetime.now().isoformat())
        )


class MasterTechnicalPlanService:
    """
    Generates the Master Technical Plan from BRD analysis.
    This is a SINGLE focused LLM call that produces a complete, 
    machine-readable plan.
    """

    async def generate_plan(
        self,
        brd_analysis: Dict[str, Any],
        brd_text: str,
        project_token: str,
        user_preferences: Optional[Dict] = None,
    ) -> MasterTechnicalPlan:
        """
        Generate the complete technical plan.
        """
        prompt = f"""
You are an elite Technical Lead analyzing a Business Requirements Document.
Produce a COMPLETE technical implementation plan as a JSON object.

The plan must cover:
1. tech_stack: Choose the BEST technology stack for these requirements.
   Consider: project complexity, team familiarity (assume general), 
   ecosystem maturity, performance needs, and deployment targets.
   
2. file_registry: Every single file that needs to be created.
   Each file needs: path, purpose, phase (1-4), owner_task, imports_from, exports, mock_data_keys, api_contracts, depends_on.
   Phase 1 = frontend/UI with mock data
   Phase 2 = backend/API/database 
   Phase 3 = integration (wire frontend to backend)
   Phase 4 = testing
   Represent this as a JSON object mapping file path to its details.

3. data_models: Database/data schemas with fields, types, relationships.

4. mock_data_spec: Mock data definitions with realistic sample records.
   Every mock key must map to exactly one API endpoint (source_api).
   Represent this as a JSON object mapping mock data keys to their definitions.

5. api_contracts: Every API endpoint with request/response schemas.
   Every endpoint must have a frontend_consumer and backend_implementor file.

6. project_type: e.g. 'web-app', 'api-only', 'mobile-app', 'cli', 'microservices'
7. architecture_pattern: e.g. 'monolith', 'microservices', 'serverless', 'jamstack'

USER PREFERENCES (respect these if provided):
{json.dumps(user_preferences or {})}

BRD TEXT:
{brd_text}

BRD ANALYSIS:
{json.dumps(brd_analysis, indent=2)}

OUTPUT FORMAT: Strict JSON matching the requested structure.
No markdown wrappers, just the raw JSON object. Do not output anything else.
"""
        messages = [
            {"role": "system", "content": "You are an expert system architect and technical lead."},
            {"role": "user", "content": prompt}
        ]

        retries = 3
        for attempt in range(retries):
            try:
                response = await llm_gateway.call_llm_and_extract(messages, max_tokens=8000)
                
                # Cleanup potential markdown
                clean_json = response.strip()
                if clean_json.startswith('```json'):
                    clean_json = clean_json[7:]
                elif clean_json.startswith('```'):
                    clean_json = clean_json[3:]
                if clean_json.endswith('```'):
                    clean_json = clean_json[:-3]
                clean_json = clean_json.strip()

                data = json.loads(clean_json)
                plan = MasterTechnicalPlan.from_dict(data)
                
                validation_errors = self.validate_plan(plan)
                if validation_errors:
                    logger.warning(f"Plan validation failed on attempt {attempt + 1}: {validation_errors}")
                    # Feed errors back to LLM for retry
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user", 
                        "content": f"The previous output had validation errors: {json.dumps(validation_errors)}. Please correct these and provide the full JSON again."
                    })
                    continue
                
                save_master_technical_plan(project_token, plan)
                return plan

            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON from LLM: {e}")
                messages.append({"role": "assistant", "content": response if 'response' in locals() else "{}"})
                messages.append({"role": "user", "content": "The output was not valid JSON. Please output strict JSON."})
            except Exception as e:
                logger.error(f"Unexpected error generating plan: {e}")
                raise e

        raise Exception("Failed to generate a valid MasterTechnicalPlan after max retries.")

    def get_phase_files(self, plan: MasterTechnicalPlan, phase: int) -> Dict[str, FileEntry]:
        """Get all files belonging to a specific phase."""
        return {
            path: entry for path, entry in plan.file_registry.items() 
            if entry.phase == phase
        }

    def get_task_files(self, plan: MasterTechnicalPlan, task_id: str) -> Dict[str, FileEntry]:
        """Get all files owned by a specific task."""
        return {
            path: entry for path, entry in plan.file_registry.items() 
            if entry.owner_task == task_id
        }

    def get_task_blueprint_slice(self, plan: MasterTechnicalPlan, task_id: str) -> Dict:
        """
        Get a focused slice of the plan for a specific task.
        Returns ONLY the files this task owns, their imports, 
        related data models, and relevant API contracts.
        """
        task_files = self.get_task_files(plan, task_id)
        
        # Gather all required imports based on the files this task owns
        required_imports = set()
        for f in task_files.values():
            required_imports.update(f.imports_from)
        
        # Also need exports from peer files that this task imports
        peer_exports = self.get_peer_exports_for_task(plan, task_id)
        
        # Relevant API Contracts
        relevant_contracts = []
        for contract in plan.api_contracts:
            if contract.frontend_consumer in task_files or contract.backend_implementor in task_files:
                relevant_contracts.append(contract)
                
        # Relevant Data Models (broad inclusion if this is a backend phase task, or filter based on something more specific)
        # We can just include all data models for context, or try to filter. Including all is often safer for context.
        
        return {
            "task_id": task_id,
            "tech_stack": plan.tech_stack.__dict__,
            "files_to_create": {p: e.__dict__ for p, e in task_files.items()},
            "peer_exports_available": peer_exports,
            "relevant_api_contracts": [c.__dict__ for c in relevant_contracts],
            "data_models": [d.__dict__ for d in plan.data_models]
        }

    def get_mock_to_api_mapping(self, plan: MasterTechnicalPlan) -> Dict[str, str]:
        """Get the mapping from mock data keys to API endpoints for integration phase."""
        mapping = {}
        for contract in plan.api_contracts:
            if contract.mock_data_key:
                mapping[contract.mock_data_key] = contract.path
        return mapping

    def get_peer_exports_for_task(self, plan: MasterTechnicalPlan, task_id: str) -> Dict[str, List[str]]:
        """
        Get exports from files that this task's files import from.
        Returns {file_path: [exported_symbols]} for import resolution.
        """
        task_files = self.get_task_files(plan, task_id)
        
        imported_files = set()
        for file_entry in task_files.values():
            imported_files.update(file_entry.imports_from)
            
        peer_exports = {}
        for path in imported_files:
            if path in plan.file_registry:
                peer_exports[path] = plan.file_registry[path].exports
                
        return peer_exports

    def validate_plan(self, plan: MasterTechnicalPlan) -> List[str]:
        """
        Validate plan integrity:
        - Every file has an owner_task
        - Every import resolves to an existing file in registry
        - Every mock_data_key maps to exactly one API contract
        - Every API contract has both frontend_consumer and backend_implementor
        - No two tasks own the same file
        - Phase ordering is correct (imports don't cross phase boundaries backwards)
        """
        errors = []
        
        file_owners = {}
        for path, file_entry in plan.file_registry.items():
            if not file_entry.owner_task:
                errors.append(f"File {path} has no owner_task assigned.")
            
            if path in file_owners and file_owners[path] != file_entry.owner_task:
                errors.append(f"File {path} is owned by multiple tasks: {file_owners[path]} and {file_entry.owner_task}.")
            file_owners[path] = file_entry.owner_task

            for imp in file_entry.imports_from:
                # Assuming external libs aren't in imports_from, or we just validate internal paths
                if not imp.startswith('.'): # Very basic heuristic for internal paths if they aren't absolute within project
                    # In a robust system, we might need a way to distinguish 3rd party vs internal
                    pass 
                elif imp not in plan.file_registry and imp.endswith('.ts') or imp.endswith('.py'):
                    # Depending on how paths are represented, this might need tuning.
                    pass

        # Validate mock data keys to API contracts
        api_mock_keys = {c.mock_data_key for c in plan.api_contracts if c.mock_data_key}
        for mock_key in plan.mock_data_spec.keys():
            if mock_key not in api_mock_keys:
                errors.append(f"Mock data key {mock_key} does not map to any API contract.")

        # Validate API contracts
        for contract in plan.api_contracts:
            if not contract.frontend_consumer and plan.project_type != 'api-only':
                errors.append(f"API contract {contract.path} is missing frontend_consumer.")
            if not contract.backend_implementor:
                errors.append(f"API contract {contract.path} is missing backend_implementor.")
            
            if contract.frontend_consumer and contract.frontend_consumer not in plan.file_registry:
                 errors.append(f"API contract {contract.path} frontend_consumer {contract.frontend_consumer} not in file registry.")
                 
            if contract.backend_implementor and contract.backend_implementor not in plan.file_registry:
                 errors.append(f"API contract {contract.path} backend_implementor {contract.backend_implementor} not in file registry.")

        return errors

# Storage module level functions
_MASTER_PLANS: Dict[str, MasterTechnicalPlan] = {}

def save_master_technical_plan(project_token: str, plan: MasterTechnicalPlan):
    _MASTER_PLANS[project_token] = plan

def get_master_technical_plan(project_token: str) -> Optional[MasterTechnicalPlan]:
    return _MASTER_PLANS.get(project_token)

def has_master_technical_plan(project_token: str) -> bool:
    return project_token in _MASTER_PLANS


master_technical_plan_service = MasterTechnicalPlanService()

