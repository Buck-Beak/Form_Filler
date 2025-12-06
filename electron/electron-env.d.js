// This file is now plain JavaScript. 
// TypeScript-specific declarations (interfaces, namespaces) are removed.

/**
 * Environment variables injected by vite-plugin-electron
 *
 * Example folder structure:
 *
 *  /dist/
 *    ├── index.html
 *  /dist-electron/
 *    ├── main.js
 *    └── preload.js
 */
process.env.APP_ROOT;   // string
process.env.VITE_PUBLIC; // string

// Renderer process: preload exposes ipcRenderer as window.ipcRenderer
// (You must expose it using contextBridge in preload.js)
