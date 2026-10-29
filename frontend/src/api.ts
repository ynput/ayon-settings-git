import addonVersion from './addonVersion'

const ADDON_NAME = 'settings_git'

function addonUrl(path: string): string {
  return `/api/addons/${ADDON_NAME}/${addonVersion}${path}`
}

export interface HistoryEntry {
  revision: string
  authored_at: string
  author: string
  message: string
}

export interface HistoryQuery {
  addonName: string
  addonVersion: string
  variant?: string
  projectName?: string
}

function toQueryString(query: HistoryQuery): string {
  const params = new URLSearchParams({
    addon_name: query.addonName,
    addon_version: query.addonVersion,
    variant: query.variant ?? 'production',
  })
  if (query.projectName) {
    params.set('project_name', query.projectName)
  }
  return params.toString()
}

export async function getHistory(query: HistoryQuery): Promise<HistoryEntry[]> {
  const res = await fetch(`${addonUrl('/history')}?${toQueryString(query)}`)
  if (!res.ok) {
    throw new Error(`Failed to load history: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

export async function getRevisionYaml(
  query: HistoryQuery,
  revision: string,
): Promise<string> {
  const params = toQueryString(query)
  const res = await fetch(`${addonUrl('/diff')}?${params}&revision=${revision}`)
  if (!res.ok) {
    throw new Error(`Failed to load revision ${revision}: ${res.status} ${res.statusText}`)
  }
  const data = await res.json()
  return data.yaml as string
}

export async function getBundleDefinitionYaml(
  bundleName: string,
  revision: string,
): Promise<string> {
  const params = new URLSearchParams({ bundle_name: bundleName, revision })
  const res = await fetch(`${addonUrl('/diff')}?${params.toString()}`)
  if (!res.ok) {
    throw new Error(`Failed to load revision ${revision}: ${res.status} ${res.statusText}`)
  }
  const data = await res.json()
  return data.yaml as string
}

/** Sentinel `addon_name` used by `BundleHistoryEntry.changed` for commits
 * that changed the bundle's own pin file rather than an addon's settings. */
export const BUNDLE_SENTINEL = '__bundle__'

export interface BundleHistoryChange {
  addon_name: string
  addon_version: string | null
}

export interface BundleHistoryEntry {
  revision: string
  authored_at: string
  author: string
  message: string
  changed: BundleHistoryChange[]
}

export interface BundleHistoryResponse {
  bundle_name: string
  variant: string | null
  addons: Array<{ addon_name: string; addon_version: string }>
  entries: BundleHistoryEntry[]
}

export interface BundleHistoryQuery {
  bundleName: string
  projectName?: string
}

export async function getBundleHistory(
  query: BundleHistoryQuery,
): Promise<BundleHistoryResponse> {
  const params = new URLSearchParams({ bundle_name: query.bundleName })
  if (query.projectName) {
    params.set('project_name', query.projectName)
  }
  const res = await fetch(`${addonUrl('/bundle_history')}?${params.toString()}`)
  if (!res.ok) {
    throw new Error(`Failed to load bundle history: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

export interface AddonListItem {
  name: string
  title: string
  versions: string[]
}

export async function listAddons(): Promise<AddonListItem[]> {
  const res = await fetch('/api/addons')
  if (!res.ok) {
    throw new Error(`Failed to load addons: ${res.status} ${res.statusText}`)
  }
  const data = await res.json()
  return (data.addons as Array<{ name: string; title: string; versions: Record<string, unknown> }>)
    .map((addon) => ({
      name: addon.name,
      title: addon.title,
      versions: Object.keys(addon.versions),
    }))
}

export interface ProjectListItem {
  name: string
}

export async function listProjects(): Promise<ProjectListItem[]> {
  const res = await fetch('/api/projects?active=true')
  if (!res.ok) {
    throw new Error(`Failed to load projects: ${res.status} ${res.statusText}`)
  }
  const data = await res.json()
  return (data.projects as Array<{ name: string }>).map((project) => ({ name: project.name }))
}

export async function listDevBundleNames(): Promise<string[]> {
  const res = await fetch('/api/bundles')
  if (!res.ok) {
    throw new Error(`Failed to load bundles: ${res.status} ${res.statusText}`)
  }
  const data = await res.json()
  return (data.bundles as Array<{ name: string; isDev?: boolean }>)
    .filter((bundle) => bundle.isDev)
    .map((bundle) => bundle.name)
}

export interface BundleListItem {
  name: string
  isProduction?: boolean
  isStaging?: boolean
  isDev?: boolean
  /** Addon name -> pinned version (null when the bundle unpins it). */
  addons: Record<string, string | null>
}

export async function listBundles(): Promise<BundleListItem[]> {
  const res = await fetch('/api/bundles')
  if (!res.ok) {
    throw new Error(`Failed to load bundles: ${res.status} ${res.statusText}`)
  }
  const data = await res.json()
  return (data.bundles as BundleListItem[]).map((bundle) => ({
    name: bundle.name,
    isProduction: bundle.isProduction,
    isStaging: bundle.isStaging,
    isDev: bundle.isDev,
    addons: bundle.addons ?? {},
  }))
}

export interface LiveSettingsQuery {
  addonName: string
  addonVersion: string
  variant: string
  /** Omit for studio-level settings. */
  projectName?: string
}

/** Current settings straight from AYON's own settings API (not the git
 * mirror), so any addon version / variant can be compared, including
 * ones the mirror never recorded. Project settings are fetched without
 * a site id, i.e. without any site overrides. */
export async function getLiveSettings(
  query: LiveSettingsQuery,
): Promise<Record<string, unknown>> {
  const base =
    `/api/addons/${encodeURIComponent(query.addonName)}` +
    `/${encodeURIComponent(query.addonVersion)}/settings`
  const url = query.projectName ? `${base}/${encodeURIComponent(query.projectName)}` : base
  const params = new URLSearchParams({ variant: query.variant })
  const res = await fetch(`${url}?${params.toString()}`)
  if (!res.ok) {
    throw new Error(
      `Failed to load ${query.addonName} ${query.addonVersion} (${query.variant}) settings: ` +
        `${res.status} ${res.statusText}`,
    )
  }
  return res.json()
}
