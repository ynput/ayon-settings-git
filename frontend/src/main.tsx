import { createRoot } from 'react-dom/client'
import '@ynput/ayon-react-components/dist/style.css'
import SettingsGitPage from './remote/SettingsGitPage'

// Settings-scope addons are embedded by the AYON shell as a plain
// iframe pointing at this addon's own built `index.html` (see
// `server/addon.py`'s `frontend_scopes`), not loaded via Module
// Federation - that mechanism (`frontend_modules`/`Route.tsx`) is for
// project/dashboard-scoped remotes only, confirmed by the shell 404ing
// on `/addons/settings_git/<version>/frontend/` (it defaults to
// `index.html` there) when only a nested `modules/settings_git/`
// federation build existed.
createRoot(document.getElementById('root')!).render(<SettingsGitPage />)
