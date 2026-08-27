import os
import sys
import subprocess

def main():
    # Setup paths
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    migrations_dir = os.path.join(backend_dir, "migrations")

    if not os.path.isdir(migrations_dir):
        print(f"Error: Migrations directory not found at {migrations_dir}")
        sys.exit(1)

    print(f"Found migrations directory: {migrations_dir}")
    print("=" * 60)

    # Get all python scripts in the migrations directory
    migration_scripts = []
    has_init_db = False
    for file in os.listdir(migrations_dir):
        if file.endswith(".py") and file != "__init__.py":
            if file == "initialize_fresh_db.py":
                has_init_db = True
            else:
                migration_scripts.append(file)

    # Sort scripts to run them in a consistent alphabetical order
    migration_scripts.sort()
    
    # Always run initialize_fresh_db.py first if it exists
    if has_init_db:
        migration_scripts.insert(0, "initialize_fresh_db.py")

    if not migration_scripts:
        print("No migration scripts found.")
        sys.exit(0)

    success_count = 0
    failure_count = 0

    for script in migration_scripts:
        script_path = os.path.join(migrations_dir, script)
        print(f"[{success_count + failure_count + 1}/{len(migration_scripts)}] Running migration: {script}")
        
        try:
            # Add backend_dir to PYTHONPATH so scripts can import database.py
            env = os.environ.copy()
            env["PYTHONPATH"] = backend_dir + os.pathsep + env.get("PYTHONPATH", "")
            env["PYTHONUTF8"] = "1"  # Force UTF-8 encoding to avoid Windows charmap errors

            # Run the script using the current Python executable
            result = subprocess.run(
                [sys.executable, script_path],
                cwd=backend_dir,  # Run in backend/ so it can import database.py
                env=env,
                capture_output=True,
                text=True,
                check=True
            )
            print(f"SUCCESS: {script}")
            if result.stdout.strip():
                # Print stdout with an indent
                for line in result.stdout.strip().split('\n'):
                    print(f"    {line}")
            success_count += 1
        except subprocess.CalledProcessError as e:
            print(f"FAILED: {script} (Exit Code: {e.returncode})")
            if e.stdout.strip():
                print("--- stdout ---")
                print(e.stdout.strip())
            if e.stderr.strip():
                print("--- stderr ---")
                print(e.stderr.strip())
            failure_count += 1
            # Some migrations might fail because they were already applied or due to errors.
            # We continue execution if possible, but you could add a break here.
            # break
        print("-" * 60)

    print("=" * 60)
    print(f"Migrations Summary: {success_count} succeeded, {failure_count} failed out of {len(migration_scripts)} total.")
    if failure_count > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
