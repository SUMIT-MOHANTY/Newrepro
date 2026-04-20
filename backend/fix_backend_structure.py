"""
Patch script: Replace _generate_backend_structure with a fully dynamic,
tech-stack-aware, domain-driven version.
Run from: c:\\BRD\\BRD_Analyzer\\backend
"""

NEW_FUNC = '''def _generate_backend_structure(backend_type: str, features: List[str]) -> List[Dict[str, Any]]:
    """Generate dynamic backend structure using Domain-Driven Agent-Friendly Architecture.
    Fully dynamic: works for FastAPI, Flask, Django, Express, Spring, .NET, Laravel, Go, etc.
    Each detected domain gets its own isolated folder — no shared layer folders.
    """

    structure = []

    # Extract feature-based domains (strip generic cross-cutting flags)
    _CROSS_CUTTING = {"database", "api", "testing", "deployment", "ui_components",
                      "file_handling", "realtime"}
    domains = [f for f in features if f not in _CROSS_CUTTING]
    if not domains:
        domains = ["auth", "core_domain"]

    # Normalize "authentication" to "auth" everywhere
    domains = ["auth" if d == "authentication" else d for d in domains]
    has_ui = "ui_components" in features

    # --- Domain-node builders per technology stack ---------------------------

    def _domain_fastapi(domain):
        children = [
            {"name": "router.py"}, {"name": "service.py"},
            {"name": "models.py"}, {"name": "schemas.py"},
        ]
        if domain == "auth":
            children.append({"name": "dependencies.py"})
        return {"name": domain, "children": children}

    def _domain_flask(domain):
        children = [
            {"name": "routes.py"}, {"name": "service.py"},
            {"name": "models.py"}, {"name": "validators.py"},
        ]
        # Flask/Jinja2: each domain owns its own templates folder
        if has_ui:
            children.append({"name": "templates", "children": [{"name": f"{domain}.html"}]})
        return {"name": domain, "children": children}

    def _domain_django(domain):
        children = [
            {"name": "views.py"}, {"name": "urls.py"},
            {"name": "models.py"}, {"name": "serializers.py"}, {"name": "admin.py"},
        ]
        if has_ui:
            children.append({"name": "templates", "children": [{"name": f"{domain}.html"}]})
        return {"name": domain, "children": children}

    def _domain_express(domain):
        return {"name": domain, "children": [
            {"name": "router.js"}, {"name": "controller.js"},
            {"name": "service.js"}, {"name": "model.js"},
        ]}

    def _domain_spring(domain):
        cap = domain.capitalize()
        return {"name": domain, "children": [
            {"name": f"{cap}Controller.java"},
            {"name": f"{cap}Service.java"},
            {"name": f"{cap}Repository.java"},
            {"name": f"{cap}.java"},
        ]}

    def _domain_dotnet(domain):
        cap = domain.capitalize()
        return {"name": domain, "children": [
            {"name": f"{cap}Controller.cs"},
            {"name": f"{cap}Service.cs"},
            {"name": f"I{cap}Service.cs"},
            {"name": f"{cap}.cs"},
        ]}

    def _domain_laravel(domain):
        cap = domain.capitalize()
        return {"name": domain, "children": [
            {"name": f"{cap}Controller.php"},
            {"name": f"{cap}Service.php"},
            {"name": f"{cap}.php"},
        ]}

    def _domain_generic(domain):
        """Fallback for Go, Rust, or any unknown stack."""
        return {"name": domain, "children": [
            {"name": "controller"},
            {"name": "service"},
            {"name": "model"},
            {"name": "repository"},
        ]}

    # Map backend_type -> domain builder
    _BUILDERS = {
        "fastapi": _domain_fastapi,
        "flask":   _domain_flask,
        "django":  _domain_django,
        "express": _domain_express,
        "spring":  _domain_spring,
        "dotnet":  _domain_dotnet,
        "laravel": _domain_laravel,
    }
    domain_builder = _BUILDERS.get(backend_type, _domain_generic)

    # Build app-level children from detected domains
    app_children = [domain_builder(d) for d in domains]

    # --- Shared infrastructure (config, middleware, services) ----------------
    if backend_type in ("fastapi", "flask", "django"):
        shared_children = [
            {"name": "config", "children": [
                {"name": "database.py"}, {"name": "jwt.py"},
                {"name": "email.py"}, {"name": "logger.py"},
            ]},
            {"name": "middleware", "children": [
                {"name": "auth.py"}, {"name": "validate.py"},
            ]},
            {"name": "services", "children": [{"name": "email.py"}]},
        ]
        if has_ui:
            shared_children.append({"name": "templates", "children": [
                {"name": "base.html"}, {"name": "index.html"},
            ]})
        app_children.append({"name": "shared", "children": shared_children})

        if backend_type in ("fastapi", "flask"):
            app_children.append({"name": "main.py"})
        if backend_type == "flask":
            app_children.append({"name": "static", "children": [
                {"name": "css", "children": []}, {"name": "js", "children": []},
            ]})
            app_children.append({"name": "__init__.py"})

        be_root = [{"name": "app", "children": app_children}, {"name": "requirements.txt"}]
        if backend_type in ("fastapi", "django"):
            be_root += [{"name": "migrations", "children": []}, {"name": "alembic.ini"}]
        if backend_type == "django":
            be_root.append({"name": "manage.py"})

    elif backend_type == "express":
        app_children += [
            {"name": "core", "children": [{"name": "db.js"}, {"name": "config.js"}]},
            {"name": "middleware", "children": []},
            {"name": "app.js"},
        ]
        be_root = [
            {"name": "src", "children": app_children},
            {"name": "package.json"}, {"name": "server.js"},
        ]

    elif backend_type == "spring":
        be_root = [
            {"name": "src", "children": [
                {"name": "main", "children": [
                    {"name": "java", "children": [
                        {"name": "com", "children": [{"name": "app", "children": app_children}]}
                    ]},
                    {"name": "resources", "children": [{"name": "application.properties"}]},
                ]},
                {"name": "test", "children": []},
            ]},
            {"name": "pom.xml"},
        ]

    elif backend_type == "dotnet":
        be_root = [
            {"name": "src", "children": app_children},
            {"name": "tests", "children": []},
            {"name": "appsettings.json"}, {"name": "Program.cs"},
        ]

    elif backend_type == "laravel":
        app_children += [
            {"name": "Http", "children": [{"name": "Middleware", "children": []}]},
            {"name": "Providers", "children": []},
        ]
        be_root = [
            {"name": "app", "children": app_children},
            {"name": "routes", "children": [{"name": "web.php"}, {"name": "api.php"}]},
            {"name": "resources", "children": [{"name": "views", "children": []}]},
            {"name": "database", "children": [{"name": "migrations", "children": []}]},
            {"name": "composer.json"},
        ]

    else:
        # Universal fallback (Go, Rust, anything unrecognized)
        be_root = [
            {"name": "src", "children": app_children},
            {"name": "config", "children": []},
            {"name": "README.md"},
        ]

    structure.append({"name": "backend", "children": be_root})
    return structure
'''

# Read the file
with open("agent_service.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find start and end markers
start_marker = 'def _generate_backend_structure(backend_type: str, features: List[str]) -> List[Dict[str, Any]]:\n'
end_marker = '\ndef _generate_frontend_structure('

start_idx = content.find(start_marker)
end_idx = content.find(end_marker, start_idx)

if start_idx == -1:
    print("ERROR: Could not find _generate_backend_structure")
elif end_idx == -1:
    print("ERROR: Could not find end marker _generate_frontend_structure")
else:
    new_content = content[:start_idx] + NEW_FUNC + content[end_idx:]
    with open("agent_service.py", "w", encoding="utf-8") as f:
        f.write(new_content)
    print("SUCCESS: _generate_backend_structure fully replaced!")
    print(f"Old function span: {start_idx} → {end_idx}")
    print(f"New function length: {len(NEW_FUNC)} chars")
