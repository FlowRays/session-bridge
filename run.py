"""Run the OAuth bridge through this host's named Cloudflare Tunnel."""

import os
from pathlib import Path
import secrets
import subprocess


root = Path(__file__).resolve().parent
runtime = root / ".runtime"
runtime.mkdir(exist_ok=True)
password = runtime / "password"
if not password.exists():
    password.write_text(secrets.token_urlsafe(32) + "\n")
    password.chmod(0o600)

url = (runtime / "public-url").read_text().strip()
tunnel = proxy = None
try:
    with (runtime / "tunnel.log").open("a") as log:
        tunnel = subprocess.Popen(
            [str(runtime / "bin/cloudflared"), "--config", "/dev/null",
             "--no-autoupdate", "tunnel", "run",
             "--token-file", str(runtime / "tunnel-token")],
            stdout=log, stderr=log,
        )
    (runtime / "tunnel.pid").write_text(str(tunnel.pid))
    env = os.environ | {
        "PASSWORD": password.read_text().strip(),
        "EXTERNAL_URL": url,
        "NO_AUTO_TLS": "true",
        "LISTEN": "127.0.0.1:8779",
        "DATA_PATH": str(runtime / "oauth"),
    }
    with (runtime / "proxy.log").open("a") as log:
        proxy = subprocess.Popen(
            [str(runtime / "bin/mcp-auth-proxy"), "--",
             str(root / ".venv/bin/python"), str(root / "server.py")],
            env=env, stdout=log, stderr=log,
        )
    (runtime / "proxy.pid").write_text(str(proxy.pid))
    print(f"ChatGPT MCP URL: {url}/mcp", flush=True)
    print(f"OAuth login password is in {password}", flush=True)
    print("Keep this process running. Ctrl-C stops the bridge; agent sessions remain.", flush=True)
    raise SystemExit(proxy.wait())
except KeyboardInterrupt:
    pass
finally:
    for process in (proxy, tunnel):
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait()
