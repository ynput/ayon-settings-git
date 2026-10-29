import { useEffect, useState } from 'react'
import ReactDiffViewer from 'react-diff-viewer-continued'
import { Button, Panel } from '@ynput/ayon-react-components'
import {
  BUNDLE_SENTINEL,
  BundleHistoryEntry,
  getBundleDefinitionYaml,
  getBundleHistory,
  getRevisionYaml,
} from '../api'
import '../global.css'

export interface BundleHistoryPanelProps {
  bundleName: string
  /** Omit for studio-level settings. */
  projectName?: string
}

interface DiffItem {
  label: string
  oldYaml: string
  newYaml: string
}

/** For a given merged entry, find the nearest earlier entry (in the
 * newest-first list) that also changed the same addon (or the bundle's
 * own pin file, for `BUNDLE_SENTINEL`) - that's this item's actual
 * previous revision, which may not be the very next merged entry since
 * other addons can have changed in between. */
function findPreviousRevision(
  entries: BundleHistoryEntry[],
  fromIndex: number,
  addonName: string,
): string | undefined {
  for (let i = fromIndex + 1; i < entries.length; i += 1) {
    if (entries[i].changed.some((change) => change.addon_name === addonName)) {
      return entries[i].revision
    }
  }
  return undefined
}

export default function BundleHistoryPanel({ bundleName, projectName }: BundleHistoryPanelProps) {
  const [entries, setEntries] = useState<BundleHistoryEntry[] | null>(null)
  const [variant, setVariant] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [diffs, setDiffs] = useState<DiffItem[]>([])
  const [loadingDiff, setLoadingDiff] = useState(false)

  useEffect(() => {
    setEntries(null)
    setSelected(null)
    setError(null)
    getBundleHistory({ bundleName, projectName })
      .then((res) => {
        setEntries(res.entries)
        setVariant(res.variant)
        if (res.entries.length > 0) {
          setSelected(res.entries[0].revision)
        }
      })
      .catch((err) => setError(String(err)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bundleName, projectName])

  useEffect(() => {
    if (!entries || !selected) return

    const index = entries.findIndex((entry) => entry.revision === selected)
    const changed = entries[index]?.changed ?? []

    setLoadingDiff(true)
    setError(null)

    Promise.all(
      changed.map((change) => {
        const previous = findPreviousRevision(entries, index, change.addon_name)

        if (change.addon_name === BUNDLE_SENTINEL) {
          return Promise.all([
            previous ? getBundleDefinitionYaml(bundleName, previous) : Promise.resolve(''),
            getBundleDefinitionYaml(bundleName, selected),
          ]).then(([oldYaml, newYaml]) => ({ label: 'bundle pins', oldYaml, newYaml }))
        }

        const query = {
          addonName: change.addon_name,
          addonVersion: change.addon_version ?? '',
          variant: variant ?? 'production',
          projectName,
        }
        return Promise.all([
          previous ? getRevisionYaml(query, previous) : Promise.resolve(''),
          getRevisionYaml(query, selected),
        ]).then(([oldYaml, newYaml]) => ({
          label: `${change.addon_name} ${change.addon_version ?? ''}`,
          oldYaml,
          newYaml,
        }))
      }),
    )
      .then(setDiffs)
      .catch((err) => setError(String(err)))
      .finally(() => setLoadingDiff(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entries, selected])

  if (error) {
    return <div className="settings-git-error">Settings Git: {error}</div>
  }

  if (!entries) {
    return <div className="settings-git-loading">Loading history…</div>
  }

  if (variant === null) {
    return (
      <div className="settings-git-empty">
        Bundle "{bundleName}" is not the active production/staging bundle and is not a
        dev bundle either, so no per-addon settings are tracked for it (only its own pin
        file, shown below).
      </div>
    )
  }

  if (entries.length === 0) {
    return <div className="settings-git-empty">No tracked history yet for bundle {bundleName}.</div>
  }

  return (
    <div className="settings-git-panel">
      <Panel className="settings-git-history-list">
        {entries.map((entry) => (
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
              <div className="revision-meta">
                {entry.changed
                  .map((change) =>
                    change.addon_name === BUNDLE_SENTINEL ? 'bundle pins' : change.addon_name,
                  )
                  .join(', ')}
              </div>
            </div>
          </Button>
        ))}
      </Panel>

      <div className="settings-git-diff">
        {loadingDiff ? (
          <div className="settings-git-loading">Loading diff…</div>
        ) : (
          diffs.map((diff) => (
            <div key={diff.label} style={{ marginBottom: 16 }}>
              <div className="revision-meta">{diff.label}</div>
              <ReactDiffViewer
                oldValue={diff.oldYaml}
                newValue={diff.newYaml}
                splitView
                leftTitle={diff.oldYaml ? 'previous revision' : '(none - first revision)'}
                rightTitle="selected revision"
                useDarkTheme={
                  window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
                }
              />
            </div>
          ))
        )}
      </div>
    </div>
  )
}
