def _generate_frontend_structure(frontend_type: str, features: List[str]) -> List[Dict[str, Any]]:
                {"name": "Footer.jsx"},
                {"name": "Layout.jsx"},
                {"name": "Sidebar.jsx"},
                {"name": "Modal.jsx"}
            ])
    
    elif frontend_type == "vue":
        structure.append({
            "name": "frontend",
            "children": [
                {"name": "package.json"},
                {"name": "vite.config.js"},
                {"name": "src", "children": [
                    {"name": "App.vue"},
                    {"name": "main.js"},
                    {"name": "style.css"},
                    {"name": "components", "children": []},
                    {"name": "views", "children": []},
                    {"name": "composables", "children": []},
                    {"name": "services", "children": []},
                    {"name": "router", "children": [{"name": "index.js"}]},
                    {"name": "store", "children": []}
                ]},
                {"name": "public", "children": [
                    {"name": "index.html"}
                ]}
            ]
        })
        
        if "authentication" in features:
            structure[0]["children"][2]["children"][3]["children"].extend([
                {"name": "LoginForm.vue"},
                {"name": "RegisterForm.vue"}
            ])
            structure[0]["children"][2]["children"][4]["children"].extend([
                {"name": "LoginView.vue"},
                {"name": "DashboardView.vue"}
            ])
            structure[0]["children"][2]["children"][6]["children"].append({"name": "authService.js"})
    
    elif frontend_type == "angular":
        structure.append({
            "name": "frontend",
            "children": [
                {"name": "package.json"},
                {"name": "angular.json"},
                {"name": "tsconfig.json"},
                {"name": "src", "children": [
                    {"name": "main.ts"},
                    {"name": "styles.css"},
                    {"name": "app", "children": [
                        {"name": "app.component.ts"},
                        {"name": "app.component.html"},
                        {"name": "app.component.css"},
                        {"name": "app.module.ts"},
                        {"name": "app-routing.module.ts"},
                        {"name": "components", "children": []},
                        {"name": "services", "children": []},
                        {"name": "guards", "children": []},
                        {"name": "models", "children": []}
                    ]}
                ]}
            ]
        })
        
        if "authentication" in features:
            structure[0]["children"][3]["children"][2]["children"][5]["children"].extend([
                {"name": "login.component.ts"},
                {"name": "login.component.html"},
                {"name": "register.component.ts"},
                {"name": "register.component.html"}
            ])
            structure[0]["children"][3]["children"][2]["children"][6]["children"].append({"name": "auth.service.ts"})
            structure[0]["children"][3]["children"][2]["children"][7]["children"].append({"name": "auth.guard.ts"})
    
    elif frontend_type == "vanilla":
        structure.append({
            "name": "frontend",
            "children": [
                {"name": "index.html"},
                {"name": "style.css"},
                {"name": "script.js"},
                {"name": "assets", "children": [
                    {"name": "css", "children": []},
                    {"name": "js", "children": []},
                    {"name": "images", "children": []}
                ]}
            ]
        })
    
    return structure


