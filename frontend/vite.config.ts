import { fileURLToPath, URL } from 'url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
export default ({ mode }) => {
  Object.assign(process?.env, loadEnv(mode, process?.cwd(), ''))

  const SERVER_URL = process?.env?.SERVER_URL || 'http://localhost:5000'

  return defineConfig({
    // Settings-scope addons are embedded by the AYON shell as a plain
    // iframe pointing at this addon's own `index.html` (server serves
    // `frontend/dist/index.html` at `/addons/settings_git/<version>/frontend/`)
    // - not Module Federation, which is for project/dashboard-scoped
    // remotes only. See `src/main.tsx`.
    plugins: [react()],
    base: '',
    server: {
      proxy: {
        '/api': {
          target: SERVER_URL,
          changeOrigin: true,
        },
        '/addons': {
          target: SERVER_URL,
          changeOrigin: false,
        },
      },
    },
    resolve: {
      alias: [
        {
          find: '@',
          replacement: fileURLToPath(new URL('./src', import.meta.url)),
        },
      ],
    },
    build: {
      target: 'chrome111',
      outDir: path.resolve(__dirname, `./dist`),
      emptyOutDir: true,
      cssCodeSplit: false,
      minify: true,
    },
  })
}
