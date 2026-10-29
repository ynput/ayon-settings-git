# AYON Git Settings Addon

AYON addon that mirrors studio and project addon settings, plus bundle
definitions, into a git repository as YAML files. Every settings change
becomes a commit, so you get history, diffs and an off-database backup
through normal git tooling, and a page in AYON's Settings area to browse
that history.

This is an MVP, not production-ready.

## How it works

The mirror is one-way. The AYON database stays the source of truth for
serving settings; the git repository is for history, diff and backup
only. Nothing is ever read back from git into the database.

```
AYON server ── settings.changed / bundle.created / bundle.updated events
     │
     ▼
git-settings service ──► writes YAML, commits ──► /storage/settings_git (git repo)
     ▲   answers history/diff with git ◄──────────────┘   └─► optional push to remote
     │
     │ WebSocket tunnel (opened by the service)
     │
server addon endpoints (/history, /diff, /bundle_history) ◄── Settings page (iframe)
```

All git work happens in the service, which has the `git` binary. The
server addon only checks permissions and forwards the read endpoints to
the service through a WebSocket tunnel, so the server needs neither
`git` nor access to the repository.

### Service (`services/git-settings/`)

A background service run by `ash` like other AYON addon services (the
Python package inside is named `worker`).

- **First start:** if the repository doesn't exist yet, it runs
  `git init`, disables auto-gc (see *Repository format* below) and
  commits an initial import from the database:
  - every bundle's definition, to `bundles/<bundle>.yaml`
  - for the current **production** and **staging** bundles only: the
    studio settings and the per-project overrides of every addon
    version those bundles pin
- **Afterwards:** it enrolls for `settings.changed`, `bundle.created`
  and `bundle.updated` events (sequentially, up to 3 retries) and makes
  one commit per event:
  - `settings.changed` writes the new value from the event payload. If
    the payload has no value (audit trail disabled, or settings reset),
    it fetches the current settings from the API instead. If the
    settings were reset to defaults, the file is deleted.
  - `bundle.*` writes the bundle's current definition.
  - The commit author is the AYON user who triggered the event
    (`<user>@<domain of commit_author_email>`).
- **Push:** if `push_after_commit` is enabled and `remote_url` is set,
  it pushes `HEAD` to `origin` after each commit.
- **Commit-graph:** after each commit it updates the repository's
  commit-graph with changed-path Bloom filters (`git commit-graph write
  --reachable --changed-paths --split`). With them, `git log -- <path>`
  skips commits that didn't touch the path, so history stays fast on
  long histories.
- **Read API:** it connects out to the addon's WebSocket
  (`/api/addons/settings_git/<version>/ws`) and answers the addon's
  read endpoints from the repository with `git log` / `git cat-file`
  (`worker/api.py`, `worker/git_reader.py`). It opens no port. The
  tunnel connects at startup, before the initial import finishes, and
  reconnects with backoff if the server restarts.

### Repository layout

```
bundles/<bundle_name>.yaml
studio/<addon>/<addon_version>/<variant>.yaml
projects/<project>/<addon>/<addon_version>/<variant>.yaml
```

`<variant>` is `production`, `staging`, or a dev bundle's name (AYON
keys dev-bundle settings by bundle name). YAML is written with sorted
keys so diffs stay stable.

### Server addon (`server/`)

Exposes the studio settings (below) and three read-only endpoints under
`/api/addons/settings_git/<version>/`:

| Endpoint | Purpose |
| --- | --- |
| `GET /history` | Commits touching one settings file (`addon_name`, `addon_version`, `variant`, optional `project_name`) |
| `GET /diff` | YAML content of one file at a given `revision`, addressed either by addon/version/variant/project or by `bundle_name` |
| `GET /bundle_history` | Merged history of a bundle's pin file and the settings of every addon it currently pins, for the bundle's variant |

Only managers (and admins) can call them, because the repository holds
every setting verbatim. The addon forwards each request to the service
through the tunnel and streams the answer back. When the service isn't
connected, the endpoints answer `503 Settings Git service is not
connected`.

The tunnel (`server/tunnel/`, `services/git-settings/worker/tunnel.py`)
is copied from the `ayon-mcp` addon. `protocol.py` is byte for byte the
same as there (`tests/test_tunnel.py` checks it). A service's WebSocket
is held by one server worker. A request handled by another worker is
routed to it through the AYON server's Redis, so any number of server
workers and replicas work.

### Frontend (`frontend/`)

A page in AYON's **Settings** area (`frontend_scopes = {"settings": {}}`).
The AYON web UI shows it as an iframe of this addon's built
`frontend/dist/index.html`. It has three modes:

- **Single addon:** pick addon, version, variant (production, staging
  or a dev bundle) and project (or studio). It lists commits for that
  settings file and shows a side-by-side YAML diff
  (`react-diff-viewer-continued`) between the selected revision and the
  one before it.
- **Bundle:** pick a bundle and project. It lists the merged history of
  the bundle and the addons it pins. For the selected commit, it shows
  one diff per changed file, each against that file's own previous
  revision.
- **Compare:** diff two settings states side by side, read live from
  AYON's settings API (not the git mirror), so any version and variant
  works, recorded or not.
  - *Addon:* pick one addon, then a version and variant for each side.
  - *Bundle:* pick a bundle and variant for each side (the variant
    defaults to the bundle's role: production, staging, or its own name
    for a dev bundle). Shows a diff of the bundles' addon pins, then one
    settings diff per addon in either bundle, using each side's pinned
    version.
  - The project picker applies to both sides. Project settings are
    read without site overrides. "Hide unchanged" (on by default)
    hides identical items.

## Settings

Studio settings of the `settings_git` addon:

| Setting | Default | Meaning |
| --- | --- | --- |
| `repo_path` | `/storage/settings_git` | Repository location. Must be the same directory for the service and the server. |
| `remote_url` | empty | Optional git remote. Empty keeps the repo local-only. |
| `push_after_commit` | `false` | Push to `remote_url` after every commit. |
| `poll_interval` | `5` | Seconds between event polls when idle. |
| `commit_author_name` | `AYON Settings Git` | Author of the initial import commit. |
| `commit_author_email` | `settings-git@ayon.local` | Author of the initial import; its domain is also used for per-user commit emails. |

## Deployment

### Storage

Only the service reads and writes the repository, so it must live on
storage that outlives the service container. `ash` forwards any of its
own bind mounts whose container path starts with `/storage` into every
service container it spawns (`ash/services.py`,
`Services.ensure_running`), so with the default `repo_path` it's enough
to give the `worker` (`ash`) container a `/storage` bind mount in
`docker-compose.worker.yml`. The server container doesn't need it.

### Service connection

The service needs nothing beyond what `ash` already sets
(`AYON_SERVER_URL`, `AYON_API_KEY` of a service user,
`AYON_ADDON_NAME`, `AYON_ADDON_VERSION`). It connects to the addon of
its own version, so production and staging services don't mix.
`AYON_SETTINGS_GIT_TUNNEL_URL` overrides the WebSocket URL. A reverse
proxy in front of AYON must pass WebSocket upgrades on
`/api/addons/settings_git/*/ws`, as it already must for `/ws`.

### Building

- **Service image:** build `services/git-settings/Dockerfile` from that
  directory. `package.py` expects the image tag
  `ynput/ayon-settings-git-worker:dev`. The image includes the `git`
  binary.
- **Addon package:** `python create_package.py` builds the frontend with
  `yarn` and writes `package/settings_git-<version>.zip` for upload to
  the server. Use `-o <dir>` to choose the output directory and
  `--skip-zip` to get a folder instead of a zip.
- **Tests:** `uv run pytest` from the repository root. They need the
  `git` binary and run the real tunnel code on both sides, with Redis
  replaced by an in-memory bus.
- **Frontend dev:** `cd frontend && npm run dev` serves the page
  standalone, proxying `/api` and `/addons` to `SERVER_URL` (default
  `http://localhost:5000`).

## Scope decisions

- **No secret redaction.** Settings are dumped as-is. Treat access to
  the repository, and to any configured remote, the same as direct
  database access.
- **Site and user settings are not mirrored** (`site_settings`,
  `project_site_settings`). `settings.changed` events carrying a
  `site_id` are skipped.
- **The bootstrap covers only active bundles.** The initial import
  dumps settings only for addon versions pinned by the current
  production and staging bundles. Dev-bundle settings and other
  versions are tracked from their first change onward, not from
  bootstrap.
- **Restoring is not implemented.** The planned design re-submits an
  old revision through the normal AYON settings API, not by writing to
  the database or git directly. That keeps validation, produces a
  normal audit trail, and lets the service commit the restore as a new
  revision.
- **Bundle history follows current pins.** `/bundle_history` considers
  only addon versions the bundle pins now, not ones it pinned in the
  past.

## Known limitations

- History and diffs need the service to be running. While it is down
  or reconnecting, the Settings page shows the 503 error (event
  mirroring is paused then too, so nothing would be missing for long).
- Push is best-effort: no retry, and no handling of a remote that has
  moved ahead.
- `npm audit` flags `vite@6.2.0` dev-server issues. These don't affect
  the built output.
