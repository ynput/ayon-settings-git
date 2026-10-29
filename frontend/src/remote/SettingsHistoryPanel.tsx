import { useEffect, useState } from 'react'
import ReactDiffViewer from 'react-diff-viewer-continued'
import { Button, Panel } from '@ynput/ayon-react-components'
import { getHistory, getRevisionYaml, HistoryEntry, HistoryQuery } from '../api'
import '../global.css'

export interface SettingsHistoryPanelProps {
  /** Name of the addon whose settings history is being browsed
   * (NOT this addon - the one the settings belong to). */
  addonName: string
  addonVersion: string
  variant?: string
  /** Omit for studio-level settings. */
  projectName?: string
}

export default function SettingsHistoryPanel({
  addonName,
  addonVersion,
  variant = 'production',
  projectName,
}: SettingsHistoryPanelProps) {
  const query: HistoryQuery = { addonName, addonVersion, variant, projectName }

  const [history, setHistory] = useState<HistoryEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [oldYaml, setOldYaml] = useState('')
  const [newYaml, setNewYaml] = useState('')
  const [loadingDiff, setLoadingDiff] = useState(false)

  useEffect(() => {
    setHistory(null)
    setSelected(null)
    setError(null)
    getHistory(query)
      .then((entries) => {
        setHistory(entries)
        if (entries.length > 0) {
          setSelected(entries[0].revision)
        }
      })
      .catch((err) => setError(String(err)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [addonName, addonVersion, variant, projectName])

  useEffect(() => {
    if (!history || !selected) return

    const index = history.findIndex((entry) => entry.revision === selected)
    const previous = history[index + 1]

    setLoadingDiff(true)
    setError(null)

    Promise.all([
      previous ? getRevisionYaml(query, previous.revision) : Promise.resolve(''),
      getRevisionYaml(query, selected),
    ])
      .then(([oldContent, newContent]) => {
        setOldYaml(oldContent)
        setNewYaml(newContent)
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoadingDiff(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [history, selected])

  if (error) {
    return <div className="settings-git-error">Settings Git: {error}</div>
  }

  if (!history) {
    return <div className="settings-git-loading">Loading history…</div>
  }

  if (history.length === 0) {
    return (
      <div className="settings-git-empty">
        No tracked history yet for {addonName} {addonVersion} ({variant}
        {projectName ? `, project ${projectName}` : ''}).
      </div>
    )
  }

  return (
    <div className="settings-git-panel">
      <Panel className="settings-git-history-list">
        {history.map((entry) => (
          <Button
            key={entry.revision}
            className="settings-git-history-entry"
            variant="text"
            selected={entry.revision === selected}
            onClick={() => setSelected(entry.revision)}
          >
            <div className="revision-content">
              <div className="revision-message">{entry.message}</div>
              <div className="revision-meta">
                {entry.author} · {new Date(entry.authored_at).toLocaleString()} ·{' '}
                {entry.revision.slice(0, 8)}
              </div>
            </div>
          </Button>
        ))}
      </Panel>

      <div className="settings-git-diff">
        {loadingDiff ? (
          <div className="settings-git-loading">Loading diff…</div>
        ) : (
          <ReactDiffViewer
            oldValue={oldYaml}
            newValue={newYaml}
            splitView
            leftTitle={oldYaml ? 'previous revision' : '(none - first revision)'}
            rightTitle="selected revision"
            useDarkTheme={
              window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
            }
          />
        )}
      </div>
    </div>
  )
}
