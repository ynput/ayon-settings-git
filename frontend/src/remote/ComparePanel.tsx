import { useEffect, useMemo, useState } from 'react'
import ReactDiffViewer from 'react-diff-viewer-continued'
import { dump } from 'js-yaml'
import { Button, Dropdown, FormLayout, FormRow, Toolbar } from '@ynput/ayon-react-components'
import { AddonListItem, BundleListItem, getLiveSettings } from '../api'
import '../global.css'

type Kind = 'addon' | 'bundle'

interface Option {
  value: string
  label: string
}

export interface ComparePanelProps {
  addons: AddonListItem[]
  bundles: BundleListItem[]
  variantOptions: Option[]
  /** Omit for studio-level settings. */
  projectName?: string
}

interface AddonSide {
  version: string
  variant: string
}

interface BundleSide {
  bundleName: string
  variant: string
}

interface CompareItem {
  label: string
  oldYaml: string
  newYaml: string
  leftTitle: string
  rightTitle: string
}

function toYaml(data: unknown): string {
  return dump(data, { sortKeys: true, noRefs: true })
}

/** The variant a bundle's settings live under: its production/staging
 * role, or its own name for a dev bundle. Bundles with no role have no
 * variant of their own, so they fall back to production. */
function bundleVariant(bundle: BundleListItem | undefined): string {
  if (!bundle) return 'production'
  if (bundle.isProduction) return 'production'
  if (bundle.isStaging) return 'staging'
  if (bundle.isDev) return bundle.name
  return 'production'
}

async function loadSettingsYaml(
  addonName: string,
  addonVersion: string,
  variant: string,
  projectName: string | undefined,
): Promise<string> {
  try {
    const settings = await getLiveSettings({ addonName, addonVersion, variant, projectName })
    return toYaml(settings)
  } catch (err) {
    // Shown inside the diff rather than failing the whole comparison, so
    // one addon without a readable settings model doesn't hide the rest.
    return `# ${String(err)}\n`
  }
}

async function compareAddonSides(
  addonName: string,
  left: AddonSide,
  right: AddonSide,
  projectName: string | undefined,
): Promise<CompareItem[]> {
  const [oldYaml, newYaml] = await Promise.all([
    loadSettingsYaml(addonName, left.version, left.variant, projectName),
    loadSettingsYaml(addonName, right.version, right.variant, projectName),
  ])
  return [
    {
      label: addonName,
      oldYaml,
      newYaml,
      leftTitle: `${left.version} (${left.variant})`,
      rightTitle: `${right.version} (${right.variant})`,
    },
  ]
}

async function compareBundleSides(
  leftBundle: BundleListItem,
  leftVariant: string,
  rightBundle: BundleListItem,
  rightVariant: string,
  projectName: string | undefined,
): Promise<CompareItem[]> {
  const pins: CompareItem = {
    label: 'bundle pins',
    oldYaml: toYaml(leftBundle.addons),
    newYaml: toYaml(rightBundle.addons),
    leftTitle: leftBundle.name,
    rightTitle: rightBundle.name,
  }

  const addonNames = Array.from(
    new Set([...Object.keys(leftBundle.addons), ...Object.keys(rightBundle.addons)]),
  ).sort()

  const addonItems = await Promise.all(
    addonNames.map(async (addonName): Promise<CompareItem> => {
      const leftVersion = leftBundle.addons[addonName] ?? null
      const rightVersion = rightBundle.addons[addonName] ?? null

      const sameSource = leftVersion === rightVersion && leftVariant === rightVariant
      const [oldYaml, newYaml] = await Promise.all([
        leftVersion ? loadSettingsYaml(addonName, leftVersion, leftVariant, projectName) : '',
        // Identical version + variant means identical settings - skip the
        // second request and reuse the left side.
        rightVersion && !sameSource
          ? loadSettingsYaml(addonName, rightVersion, rightVariant, projectName)
          : null,
      ])

      return {
        label: addonName,
        oldYaml,
        newYaml: newYaml ?? (rightVersion ? oldYaml : ''),
        leftTitle: leftVersion
          ? `${leftBundle.name}: ${leftVersion} (${leftVariant})`
          : `${leftBundle.name}: (not in bundle)`,
        rightTitle: rightVersion
          ? `${rightBundle.name}: ${rightVersion} (${rightVariant})`
          : `${rightBundle.name}: (not in bundle)`,
      }
    }),
  )

  return [pins, ...addonItems]
}

export default function ComparePanel({
  addons,
  bundles,
  variantOptions,
  projectName,
}: ComparePanelProps) {
  const [kind, setKind] = useState<Kind>('addon')
  const [hideUnchanged, setHideUnchanged] = useState(true)

  const [addonName, setAddonName] = useState(addons[0]?.name ?? '')
  const versions = useMemo(
    () => addons.find((addon) => addon.name === addonName)?.versions ?? [],
    [addons, addonName],
  )
  const [leftAddon, setLeftAddon] = useState<AddonSide>({ version: '', variant: 'production' })
  const [rightAddon, setRightAddon] = useState<AddonSide>({ version: '', variant: 'production' })

  // Default to "previous version vs latest version" whenever the addon
  // changes or a picked version no longer exists for it.
  useEffect(() => {
    if (versions.length === 0) return
    const latest = versions[versions.length - 1]
    const previous = versions[versions.length - 2] ?? latest
    setLeftAddon((side) => (versions.includes(side.version) ? side : { ...side, version: previous }))
    setRightAddon((side) => (versions.includes(side.version) ? side : { ...side, version: latest }))
  }, [versions])

  const [leftBundle, setLeftBundle] = useState<BundleSide>(() => {
    const bundle = bundles.find((b) => b.isProduction) ?? bundles[0]
    return { bundleName: bundle?.name ?? '', variant: bundleVariant(bundle) }
  })
  const [rightBundle, setRightBundle] = useState<BundleSide>(() => {
    const bundle =
      bundles.find((b) => b.isStaging) ?? bundles.find((b) => !b.isProduction) ?? bundles[0]
    return { bundleName: bundle?.name ?? '', variant: bundleVariant(bundle) }
  })

  const [items, setItems] = useState<CompareItem[] | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    let request: Promise<CompareItem[]> | null = null

    if (kind === 'addon') {
      if (addonName && leftAddon.version && rightAddon.version) {
        request = compareAddonSides(addonName, leftAddon, rightAddon, projectName)
      }
    } else {
      const left = bundles.find((b) => b.name === leftBundle.bundleName)
      const right = bundles.find((b) => b.name === rightBundle.bundleName)
      if (left && right) {
        request = compareBundleSides(
          left,
          leftBundle.variant,
          right,
          rightBundle.variant,
          projectName,
        )
      }
    }

    if (!request) {
      setItems(null)
      return
    }

    setLoading(true)
    request
      .then((result) => {
        if (!cancelled) setItems(result)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [kind, addonName, leftAddon, rightAddon, leftBundle, rightBundle, bundles, projectName])

  const versionOptions = versions.map((version) => ({ value: version, label: version }))
  const bundleOptions = bundles.map((bundle) => ({
    value: bundle.name,
    label: bundle.isProduction
      ? `${bundle.name} (production)`
      : bundle.isStaging
        ? `${bundle.name} (staging)`
        : bundle.isDev
          ? `${bundle.name} (dev)`
          : bundle.name,
  }))

  const renderAddonSide = (
    title: string,
    side: AddonSide,
    setSide: (side: AddonSide) => void,
  ) => (
    <FormLayout className="settings-git-compare-side">
      <div className="revision-message">{title}</div>
      <FormRow label="Version">
        <Dropdown
          value={side.version ? [side.version] : []}
          options={versionOptions}
          disabled={versions.length === 0}
          onChange={(added) => setSide({ ...side, version: added[0] ?? '' })}
        />
      </FormRow>
      <FormRow label="Variant">
        <Dropdown
          value={[side.variant]}
          options={variantOptions}
          onChange={(added) => setSide({ ...side, variant: added[0] ?? 'production' })}
        />
      </FormRow>
    </FormLayout>
  )

  const renderBundleSide = (
    title: string,
    side: BundleSide,
    setSide: (side: BundleSide) => void,
  ) => (
    <FormLayout className="settings-git-compare-side">
      <div className="revision-message">{title}</div>
      <FormRow label="Bundle">
        <Dropdown
          value={side.bundleName ? [side.bundleName] : []}
          options={bundleOptions}
          disabled={bundles.length === 0}
          onChange={(added) => {
            const bundleName = added[0] ?? ''
            const bundle = bundles.find((b) => b.name === bundleName)
            setSide({ bundleName, variant: bundleVariant(bundle) })
          }}
        />
      </FormRow>
      <FormRow label="Variant">
        <Dropdown
          value={[side.variant]}
          options={variantOptions}
          onChange={(added) => setSide({ ...side, variant: added[0] ?? 'production' })}
        />
      </FormRow>
    </FormLayout>
  )

  const unchangedCount = items?.filter((item) => item.oldYaml === item.newYaml).length ?? 0
  const visibleItems =
    items?.filter((item) => !hideUnchanged || item.oldYaml !== item.newYaml) ?? []

  return (
    <div className="settings-git-compare">
      <Toolbar style={{ flexWrap: 'wrap' }}>
        <Button variant={kind === 'addon' ? 'filled' : 'text'} onClick={() => setKind('addon')}>
          Addon
        </Button>
        <Button variant={kind === 'bundle' ? 'filled' : 'text'} onClick={() => setKind('bundle')}>
          Bundle
        </Button>
        {kind === 'addon' && (
          <FormRow label="Addon name">
            <Dropdown
              value={addonName ? [addonName] : []}
              options={addons}
              dataKey="name"
              labelKey="title"
              onChange={(added) => setAddonName(added[0] ?? '')}
            />
          </FormRow>
        )}
        <Button
          variant={hideUnchanged ? 'filled' : 'text'}
          onClick={() => setHideUnchanged((value) => !value)}
        >
          Hide unchanged
        </Button>
      </Toolbar>

      <div className="settings-git-compare-sides">
        {kind === 'addon' ? (
          <>
            {renderAddonSide('Left', leftAddon, setLeftAddon)}
            {renderAddonSide('Right', rightAddon, setRightAddon)}
          </>
        ) : (
          <>
            {renderBundleSide('Left', leftBundle, setLeftBundle)}
            {renderBundleSide('Right', rightBundle, setRightBundle)}
          </>
        )}
      </div>

      <div className="settings-git-diff">
        {loading ? (
          <div className="settings-git-loading">Loading settings…</div>
        ) : !items ? (
          <div className="settings-git-empty">Pick both sides to compare.</div>
        ) : (
          <>
            {hideUnchanged && unchangedCount > 0 && (
              <div className="revision-meta" style={{ marginBottom: 8 }}>
                {unchangedCount} identical {unchangedCount === 1 ? 'item' : 'items'} hidden
              </div>
            )}
            {visibleItems.length === 0 ? (
              <div className="settings-git-empty">Both sides are identical.</div>
            ) : (
              visibleItems.map((item) => (
                <div key={item.label} style={{ marginBottom: 16 }}>
                  <div className="revision-meta">{item.label}</div>
                  <ReactDiffViewer
                    oldValue={item.oldYaml}
                    newValue={item.newYaml}
                    splitView
                    leftTitle={item.leftTitle}
                    rightTitle={item.rightTitle}
                    useDarkTheme={
                      window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
                    }
                  />
                </div>
              ))
            )}
          </>
        )}
      </div>
    </div>
  )
}
