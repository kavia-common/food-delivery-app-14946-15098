```bash
#!/usr/bin/env bash
set -euo pipefail

# Detect privilege level
if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
else
    SUDO="sudo"
fi

# Set workspace path
WORKSPACE="/home/kavia/workspace/code-generation/food-delivery-app-14946-15098/UserService"
cd "$WORKSPACE"

# === COMMAND: INSTALL ===
echo 'export HEADLESS=true' | $SUDO tee /etc/profile.d/headless.sh > /dev/null
echo 'export NODE_ENV=development' | $SUDO tee /etc/profile.d/user_service_env.sh > /dev/null

# === COMMAND: SCAFFOLD ===
if [ ! -f "$WORKSPACE/package.json" ]; then
    # Allow only empty or default workspace before scaffolding
    shopt -s dotglob nullglob
    files=("$WORKSPACE"/* "$WORKSPACE"/.*)
    allowed=("$WORKSPACE/." "$WORKSPACE/.." )
    if [ "${#files[@]}" -gt 2 ] && \
       ! ( [ "${files[0]}" = "$WORKSPACE/." ] && [ "${files[1]}" = "$WORKSPACE/.." ] ); then
        echo "ERROR: Workspace not empty. Remove files before scaffolding." >&2; exit 1
    fi
    create-react-app . --use-npm --skip-git --quiet
fi

# === COMMAND: DEPS ===
# No local jest install needed; dependencies managed by create-react-app

# === COMMAND: BUILD ===
npm run build --if-present --silent

# === COMMAND: TEST ===
npm test -- --ci --watchAll=false --silent

# === COMMAND: START ===
: > "$WORKSPACE/app.log"
HEADLESS=true npm start -- --port=3000 > "$WORKSPACE/app.log" 2>&1 & echo $! > "$WORKSPACE/app.pid"

# === COMMAND: VALIDATE ===
sleep 7
pid=$(cat "$WORKSPACE/app.pid")
if ! kill -0 "$pid" 2>/dev/null; then
    echo "ERROR: React app failed to start." >&2; exit 1
fi
status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000)
if [ "$status" != "200" ]; then
    echo "ERROR: React app did not respond on port 3000 (HTTP $status)" >&2; exit 2
fi
# Additional check: look for typical React root HTML
if ! curl -s http://localhost:3000 | grep -q '<div id="root">' ; then
    echo "WARNING: App responded but root HTML not found; verify build." >&2
fi

# === COMMAND: STOP ===
[ -f "$WORKSPACE/app.pid" ] && kill "$(cat "$WORKSPACE/app.pid")" 2>/dev/null || true
rm -f "$WORKSPACE/app.pid" "$WORKSPACE/app.log"
```