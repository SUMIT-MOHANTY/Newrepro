"""Living Product Specification Manager.

Maintains an authoritative product_spec.json at the workspace root.
Tracks domain entities, user roles, business workflows, and architecture tier
(PROTOTYPE vs FULLSTACK) across turns so the AI never forgets or regresses functionality.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class ProductSpec:
    title: str
    target_users: list[str] = field(default_factory=list)
    architecture_tier: str = "PROTOTYPE"  # "PROTOTYPE" | "FULLSTACK"
    entities: dict[str, list[str]] = field(default_factory=dict)  # Entity Name -> Fields
    workflows: list[str] = field(default_factory=list)            # Primary business paths
    active_features: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert spec dataclass to a JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def load_or_init(cls, workspace_path: str, prompt: str = "") -> "ProductSpec":
        """Load existing product_spec.json from workspace, or synthesize initial spec from prompt."""
        spec_path = Path(workspace_path) / "product_spec.json"
        if spec_path.exists():
            try:
                data = json.loads(spec_path.read_text(encoding="utf-8"))
                return cls(
                    title=data.get("title", "Application"),
                    target_users=data.get("target_users", ["General Users"]),
                    architecture_tier=data.get("architecture_tier", "PROTOTYPE"),
                    entities=data.get("entities", {}),
                    workflows=data.get("workflows", []),
                    active_features=data.get("active_features", []),
                )
            except Exception as e:
                print(f"[SpecManager] Warning reading existing product_spec.json: {e}")

        # Synthesize initial spec from user prompt
        title = cls._extract_title_from_prompt(prompt)
        entities = cls._extract_initial_entities(prompt)
        tier = "FULLSTACK" if any(k in prompt.lower() for k in ("fullstack", "full-stack", "backend", "database", "sqlite", "postgres", "api")) else "PROTOTYPE"
        
        spec = cls(
            title=title,
            target_users=["Business Users", "Operators"],
            architecture_tier=tier,
            entities=entities,
            workflows=["View primary dashboard", "Filter and search records", "Create and update entries"],
            active_features=["Interactive Dashboard", "Realistic Seed Data", "Filter & Search Engine"],
        )
        spec.save(workspace_path)
        return spec

    @staticmethod
    def _extract_title_from_prompt(prompt: str) -> str:
        if not prompt:
            return "Application Prototype"
        clean = prompt.strip().split("\n")[0]
        match = re.search(r"(?:build|create|make|design)\s+(?:a|an)\s+([a-zA-Z0-9\s\-]+?)(?:\s+with|\s+that|\s+using|\.|$)", clean, re.I)
        if match:
            words = match.group(1).strip().split()
            if len(words) <= 5:
                return " ".join(w.capitalize() for w in words)
        return "Application Prototype"

    @staticmethod
    def _extract_initial_entities(prompt: str) -> dict[str, list[str]]:
        p = prompt.lower()
        if any(k in p for k in ("clinic", "medical", "doctor", "patient")):
            return {
                "Patient": ["id", "name", "dob", "gender", "phone", "criticalAlerts"],
                "Appointment": ["id", "patientId", "doctorName", "date", "time", "status", "notes"],
                "Vitals": ["id", "patientId", "bloodPressure", "heartRate", "temperature", "oxygenLevel", "recordedAt"],
            }
        elif any(k in p for k in ("fleet", "delivery", "vehicle", "truck")):
            return {
                "Vehicle": ["id", "plateNumber", "model", "status", "fuelLevel", "mileage", "driverName"],
                "Delivery": ["id", "vehicleId", "destination", "eta", "status", "priority"],
                "Alert": ["id", "vehicleId", "type", "severity", "timestamp"],
            }
        elif any(k in p for k in ("crm", "sales", "lead", "pipeline")):
            return {
                "Contact": ["id", "name", "company", "email", "phone", "status"],
                "Deal": ["id", "title", "contactId", "value", "stage", "expectedCloseDate"],
                "Activity": ["id", "dealId", "type", "description", "dueDate"],
            }
        return {
            "Item": ["id", "title", "category", "status", "createdAt", "updatedAt"],
            "ActivityLog": ["id", "action", "entityId", "timestamp", "user"],
        }

    def save(self, workspace_path: str) -> None:
        """Persist product spec to product_spec.json."""
        try:
            spec_path = Path(workspace_path) / "product_spec.json"
            spec_path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[SpecManager] Warning saving product_spec.json: {e}")

    def update_spec(
        self,
        workspace_path: str,
        *,
        architecture_tier: str | None = None,
        entities: dict[str, list[str]] | None = None,
        workflows: list[str] | None = None,
        active_features: list[str] | None = None,
    ) -> None:
        """Update fields and persist to disk."""
        if architecture_tier:
            self.architecture_tier = architecture_tier.upper()
        if entities:
            self.entities.update(entities)
        if workflows:
            for w in workflows:
                if w not in self.workflows:
                    self.workflows.append(w)
        if active_features:
            for f in active_features:
                if f not in self.active_features:
                    self.active_features.append(f)
        self.save(workspace_path)

    def to_system_context(self) -> str:
        """Format the authoritative Living Product Spec for prompt injection."""
        return (
            "### 📋 LIVING PRODUCT SPECIFICATION (Authoritative Business Contract)\n"
            f"- **Application Title**: {self.title}\n"
            f"- **Architecture Tier**: `{self.architecture_tier}` (PROTOTYPE uses localStorage mock engine; FULLSTACK uses /api/* backend)\n"
            f"- **Target Users**: {', '.join(self.target_users)}\n"
            f"- **Core Domain Entities**: {json.dumps(self.entities)}\n"
            f"- **Existing Workflows**: {', '.join(self.workflows)}\n"
            f"- **Active Features**: {', '.join(self.active_features)}\n"
            "**Rule**: NEVER delete, break, or regress existing workflows when fulfilling user change requests. "
            "Always update `product_spec.json` when new entities, workflows, or tier promotions occur."
        )
