/**
 * Electron 预加载脚本（安全桥接层）
 */
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('electron', {
  isElectron: true,
  selectDirectory: () => ipcRenderer.invoke('select-directory'),
  selectFiles: () => ipcRenderer.invoke('select-files'),
  scanDirectory: (dirPath) => ipcRenderer.invoke('scan-directory', dirPath),
  readFile: (filePath) => ipcRenderer.invoke('read-file', filePath),
  watchDirectory: (dirPath) => ipcRenderer.invoke('watch-directory', dirPath),
  stopWatch: () => ipcRenderer.invoke('stop-watch'),
  onNewFile: (callback) => { ipcRenderer.on('new-file', (event, file) => callback(file)); },
});
