/**
 * Electron 预加载脚本（安全桥接层）
 *
 * 通过 contextBridge 暴露受限的 IPC 接口给渲染进程，
 * 避免直接暴露 Node.js API，保证安全性。
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electron', {
  isElectron: true,

  // 打开文件夹选择对话框
  selectDirectory: () => ipcRenderer.invoke('select-directory'),

  // 打开文件选择对话框
  selectFiles: () => ipcRenderer.invoke('select-files'),

  // 递归扫描目录，返回所有文本文件列表
  scanDirectory: (dirPath) => ipcRenderer.invoke('scan-directory', dirPath),

  // 直接读取文件内容
  readFile: (filePath) => ipcRenderer.invoke('read-file', filePath),

  // 监控文件夹变化
  watchDirectory: (dirPath) => ipcRenderer.invoke('watch-directory', dirPath),

  // 停止监控
  stopWatch: () => ipcRenderer.invoke('stop-watch'),

  // 接收新文件通知
  onNewFile: (callback) => {
    ipcRenderer.on('new-file', (event, file) => callback(file));
  },
});