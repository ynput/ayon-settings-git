import { useEffect, useMemo, useState } from 'react'
import { Button, Dropdown, FormLayout, FormRow, Toolbar } from '@ynput/ayon-react-components'
import type { RemoteAddonProps } from '../remoteAddon'
import SettingsHistoryPanel from './SettingsHistoryPanel'
import BundleHistoryPanel from './BundleHistoryPanel'
import ComparePanel from './ComparePanel'
import {
  AddonListItem,
  BundleListItem,
  listAddons,
  listBundles,
  listDevBundleNames,
  listProjects,
  ProjectListItem,
} from '../api'
import '../global.css'

type Mode = 'addon' | 'bundle' | 'compare'

/**
 * Settings-scope page, embedded by the AYON shell as a standalone
 * iframe pointing at this addon's own built `index.html` (see
 * `server/addon.py`'s `frontend_scopes` and `frontend/src/main.tsx`),
 * not loaded via Module Federation. `props.router` is accepted (typed
 * optional) for shape-compatibility with `RemoteAddon`/`main.tsx`'s
 * standalone mount, but unused - the page has no dynamic URL segments.
 */
export default function SettingsGitPage(_props: Partial<RemoteAddonProps> = {}) {
  const [addons, setAddons] = useState<AddonListItem[] | null>(null)
  const [projects, setProjects] = useState<ProjectListItem[] | null>(null)
  const [bundles, setBundles] = useState<BundleListItem[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [mode, setMode] = useState<Mode>('addon')
  const [addonName, setAddonName] = useState('')
  const [addonVersion, setAddonVersion] = useState('')
  const [variant, setVariant] = useState('production')
  const [devBundleNames, setDevBundleNames] = useState<string[]>([])
  const [bundleName, setBundleName] = useState('')
  const [projectName, setProjectName] = useState('')

  useEffect(() => {
    Promise.all([listAddons(), listProjects(), listDevBundleNames(), listBundles()])
      .then(([addonList, projectList, devBundles, bundleList]) => {
        setAddons(addonList)
        setProjects(projectList)
        setDevBundleNames(devBundles)
        setBundles(bundleList)
        if (addonList.length > 0) {
          setAddonName(addonList[0].name)
        }
        const activeBundle = bundleList.find((b) => b.isProduction) ?? bundleList[0]
        if (activeBundle) {
          setBundleName(activeBundle.name)
        }
      })
      .catch((err) => setLoadError(String(err)))
  }, [])

  const versions = useMemo(
    () => addons?.find((addon) => addon.name === addonName)?.versions ?? [],
    [addons, addonName],
  )

  useEffect(() => {
    if (versions.length > 0 && !versions.includes(addonVersion)) {
      setAddonVersion(versions[versions.length - 1])
    }
  }, [versions, addonVersion])

  const variantOptions = useMemo(
    () => [
      { value: 'production', label: 'production' },
      { value: 'staging', label: 'staging' },
      ...devBundleNames.map((name) => ({ value: name, label: `${name} (dev)` })),
    ],
    [devBundleNames],
  )

  const projectOptions = useMemo(
    () => [
      { value: '', label: '(studio settings)' },
      ...(projects ?? []).map((project) => ({ value: project.name, label: project.name })),
    ],
    [projects],
  )

  const bundleOptions = useMemo(
    () =>
      (bundles ?? []).map((bundle) => ({
        value: bundle.name,
        label: bundle.isProduction
          ? `${bundle.name} (production)`
          : bundle.isStaging
            ? `${bundle.name} (staging)`
            : bundle.name,
      })),
    [bundles],
  )

  if (loadError) {
    return <div className="settings-git-error">Settings Git: {loadError}</div>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: 12, gap: 12 }}>
      <Toolbar style={{ flexWrap: 'wrap' }}>
        <Button variant={mode === 'addon' ? 'filled' : 'text'} onClick={() => setMode('addon')}>
          Single addon
        </Button>
        <Button variant={mode === 'bundle' ? 'filled' : 'text'} onClick={() => setMode('bundle')}>
          Bundle
        </Button>
        <Button variant={mode === 'compare' ? 'filled' : 'text'} onClick={() => setMode('compare')}>
          Compare
        </Button>

        <FormLayout style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {mode === 'addon' ? (
            <>
              <FormRow label="Addon name">
                <Dropdown
                  value={addonName ? [addonName] : []}
                  options={addons ?? []}
                  dataKey="name"
                  labelKey="title"
                  disabled={!addons}
                  onChange={(added) => {
                    setAddonName(added[0] ?? '')
                    setAddonVersion('')
                  }}
                />
              </FormRow>
              <FormRow label="Addon version">
                <Dropdown
                  value={addonVersion ? [addonVersion] : []}
                  options={versions.map((version) => ({ value: version, label: version }))}
                  disabled={versions.length === 0}
                  onChange={(added) => setAddonVersion(added[0] ?? '')}
                />
              </FormRow>
              <FormRow label="Variant">
                <Dropdown
                  value={[variant]}
                  options={variantOptions}
                  onChange={(added) => setVariant(added[0] ?? 'production')}
                />
              </FormRow>
            </>
          ) : mode === 'bundle' ? (
            <FormRow label="Bundle">
              <Dropdown
                value={bundleName ? [bundleName] : []}
                options={bundleOptions}
                disabled={!bundles}
                onChange={(added) => setBundleName(added[0] ?? '')}
              />
            </FormRow>
          ) : null}
          <FormRow label="Project">
            <Dropdown
              value={[projectName]}
              options={projectOptions}
              onChange={(added) => setProjectName(added[0] ?? '')}
            />
          </FormRow>
        </FormLayout>
      </Toolbar>

      <div style={{ flex: 1, minHeight: 0 }}>
        {mode === 'addon' ? (
          addonVersion ? (
            <SettingsHistoryPanel
              addonName={addonName}
              addonVersion={addonVersion}
              variant={variant}
              projectName={projectName || undefined}
            />
          ) : (
            <p>Loading addons…</p>
          )
        ) : mode === 'compare' ? (
          addons && bundles ? (
            <ComparePanel
              addons={addons}
              bundles={bundles}
              variantOptions={variantOptions}
              projectName={projectName || undefined}
            />
          ) : (
            <p>Loading addons…</p>
          )
        ) : bundleName ? (
          <BundleHistoryPanel bundleName={bundleName} projectName={projectName || undefined} />
        ) : (
          <p>Loading bundles…</p>
        )}
      </div>
    </div>
  )
}
