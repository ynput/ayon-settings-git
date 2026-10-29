# Required: lower case addon name, otherwise addon will be invalid
name = "settings_git"

# Optional: Addon title shown in UI
title = "Settings Git"

# Required: Valid semantic version (https://semver.org/)
version = "0.1.0"

# Name of client code directory imported in AYON launcher
# - this addon has no launcher-side client code
client_dir = None

# No custom volume config needed here. `ash` (the service runner)
# auto-forwards any of ITS OWN bind mounts whose container-side target
# starts with "/storage" into every service container it spawns (see
# ash/services.py Services.ensure_running). Give the `ash` container
# (the `worker` service in docker-compose.worker.yml) a "/storage" bind
# mount, and the repository at `/storage/settings_git`
# (SettingsGitSettings.repo_path default) persists across service
# restarts. Only the service touches the repository; the server reaches
# it through the service's WebSocket tunnel.
services = {
    "git-settings": {
        "image": "ynput/ayon-settings-git-worker:dev",
    },
}

# Version compatibility with AYON server
ayon_server_version = ">=1.12.5"

# Mapping of addon name to version requirements
ayon_required_addons = {
    "core": ">=0.3.0",
}
ayon_compatible_addons = {}
