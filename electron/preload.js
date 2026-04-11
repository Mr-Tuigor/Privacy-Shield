const { contextBridge, ipcRenderer } = require('electron');

// Expose a custom API to the `window` object in React
contextBridge.exposeInMainWorld('electronAPI', {
    // React will call this function, which triggers the backend listener
    scrubText: (text) => ipcRenderer.invoke('api:scrub-text', text)
});