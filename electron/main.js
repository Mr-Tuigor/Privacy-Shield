import { app, BrowserWindow, ipcMain } from 'electron';
import path from 'path';
import { scrubText } from '../src/scrubber.js';

function createWindow() {
    const win = new BrowserWindow({
        width: 800,
        height: 600,
        webPreferences: {
            // Load preload.js to create the secure bridge
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true
        }
    });

    // In development, load the Vite dev server
    win.loadURL('http://localhost:5173');
}

app.whenReady().then(() => {
    // 1. Set up the IPC Listener BEFORE creating the window
    ipcMain.handle('api:scrub-text', async (event, textPayload) => {
        try {
            // Call the JavaScript scrubbing function
            const sanitizedText = scrubText(textPayload);
            return sanitizedText;
        } catch (error) {
            console.error("Scrubbing Error:", error);
            return "Error processing text.";
        }
    });

    createWindow();
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});