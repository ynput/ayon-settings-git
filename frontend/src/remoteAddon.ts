/**
 * Minimal local copy of the shapes the real AYON frontend shell expects
 * from a Module Federation "page" module, confirmed by installing and
 * inspecting `@ynput/ayon-frontend-shared@0.4.3`'s own type declarations
 * (`dist/types/context/AddonContext.d.ts`,
 * `dist/types/components/RemotePage/RemotePageWrapper.d.ts`) rather than
 * guessing. Kept as a local copy instead of an actual dependency on that
 * package so this addon doesn't pull in its (large) runtime just for two
 * type shapes - only `component`/`path`/`module`/`id` are used here.
 */
import type { FC } from 'react'

// The real type (see @ynput/ayon-frontend-shared's RouterTypes) binds
// these to the shell's own react-router-dom hook instances. Typed
// loosely here (rather than depending on react-router-dom just for
// types) since this addon's page doesn't read dynamic route params.
export type RouterTypes = {
  useParams: (...args: unknown[]) => unknown
  useNavigate: (...args: unknown[]) => unknown
  useLocation: (...args: unknown[]) => unknown
  useSearchParams: (...args: unknown[]) => unknown
}

export interface RemoteAddonProps {
  router: RouterTypes
  toast?: unknown
}

export type RemoteAddonComponent = FC<RemoteAddonProps>

export type RemoteAddon = {
  id: string
  component: RemoteAddonComponent
  path: string
  module: string
}
