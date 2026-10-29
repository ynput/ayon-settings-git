import SettingsGitPage from './remote/SettingsGitPage'

/**
 * Standalone dev harness only - lets the real page be exercised against
 * a running AYON server (via the vite proxy) without needing the shell.
 */
function App() {
  return (
    <div style={{ height: '100vh' }}>
      <SettingsGitPage />
    </div>
  )
}

export default App
