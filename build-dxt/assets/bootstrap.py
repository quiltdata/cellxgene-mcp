import os, subprocess, sys, shutil, json, pathlib, stat

HERE = pathlib.Path(__file__).resolve().parent
VENV = HERE / ".venv"
SERVER = HERE / "dxt_main.py"

def run(cmd, env=None, check=True, capture_output=False):
  """Run a command, redirecting output to stderr to avoid MCP protocol interference."""
  if capture_output:
    return subprocess.run(cmd, env=env, check=check, capture_output=True, text=True)
  else:
    # Redirect stdout to stderr to avoid interfering with MCP protocol
    return subprocess.run(cmd, env=env, check=check, stdout=sys.stderr, stderr=sys.stderr)

def main():
  # Create virtual environment if it doesn't exist
  if not VENV.exists():
    print("Creating virtual environment...", file=sys.stderr)
    run([sys.executable, "-m", "venv", str(VENV)])
  
  # Determine venv python path
  venv_python = VENV / ("Scripts/python.exe" if os.name == 'nt' else "bin/python")
  
  # Ensure the Python executable has execute permissions
  if venv_python.exists():
    try:
      current_mode = venv_python.stat().st_mode
      # Add execute permissions for user, group, and others
      new_mode = current_mode | stat.S_IEXEC | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
      venv_python.chmod(new_mode)
      print(f"Set permissions on {venv_python}: {oct(new_mode)}", file=sys.stderr)
    except Exception as e:
      print(f"Warning: Could not set permissions on {venv_python}: {e}", file=sys.stderr)
  else:
    print(f"Warning: Python executable not found at {venv_python}", file=sys.stderr)
  
  # Upgrade pip and install wheel (suppress output)
  print("Installing dependencies...", file=sys.stderr)
  run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "wheel", "--quiet"])
  
  # Install dependencies (suppress output)
  req = HERE / "requirements.txt"
  if req.exists():
    run([str(venv_python), "-m", "pip", "install", "-r", str(req), "--quiet"])
  else:
    # Install basic dependencies needed for the server (suppress output)
    run([str(venv_python), "-m", "pip", "install", "--quiet",
         "eliot>=1.17.5",
         "pycomfort>=0.0.18", 
         "fastmcp>=2.8.0",
         "fastapi>=0.115.12",
         "cellxgene-census>=1.17.0",
         "pandas>=2.0.0",
         "numpy>=1.24.0,<2.0",
         "anndata>=0.8.0,<1.0",
         "h5py>=3.0.0,<4.0",
         "boto3>=1.26.0",
         "botocore>=1.29.0"])
  
  print("Starting CELLxGENE Census MCP server...", file=sys.stderr)
  # Exec the server with the venv's python
  os.execv(str(venv_python), [str(venv_python), str(SERVER)])

if __name__ == "__main__":
  main()
