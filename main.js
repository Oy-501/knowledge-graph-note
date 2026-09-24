/**
 * Electron 主进程
 *
 * 职责：
 * 1. 创建 BrowserWindow 加载 index.html
 * 2. 通过 IPC 接收渲染进程的文件操作请求
 * 3. 用 Node.js fs 模块直接扫描目录、读取文件（突破浏览器安全限制）
 * 4. 监控文件夹变化，新文件自动通知渲染进程
 */

const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');

// 将用户数据目录重定向到项目内，避免沙箱限制
app.setPath('userData', path.join(__dirname, '.userdata'));

// 支持的文本文件扩展名
const TEXT_EXTENSIONS = new Set([
  '.md', '.txt', '.markdown', '.text', '.json', '.yaml', '.yml',
  '.xml', '.csv', '.tsv', '.log', '.ini', '.conf', '.cfg', '.toml',
  '.env', '.sh', '.bash', '.zsh', '.fish', '.bat', '.ps1',
  '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp', '.cc',
  '.h', '.hpp', '.cs', '.go', '.rs', '.rb', '.php', '.pl',
  '.swift', '.kt', '.scala', '.lua', '.sql', '.html', '.htm',
  '.css', '.scss', '.less', '.vue', '.svelte', '.r', '.dart',
]);

// 跳过的目录名
const SKIP_DIRS = new Set([
  'node_modules', '.git', '.idea', '.vscode', '__pycache__',
  '.next', '.nuxt', 'dist', 'build', '.cache', 'vendor',
]);

function isTextFile(fileName) {
  const ext = path.extname(fileName).toLowerCase();
  if (!ext) return true; // 无扩展名文件也尝试读取（如 Dockerfile）
  return TEXT_EXTENSIONS.has(ext);
}

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile('index.html');
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

// ============ IPC 处理器 ============

// 选择文件夹（原生对话框）
ipcMain.handle('select-directory', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    title: '选择要扫描的文件夹',
  });
  if (result.canceled) return null;
  return result.filePaths[0];
});

// 选择文件（原生对话框）
ipcMain.handle('select-files', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile', 'multiSelections'],
    title: '选择文档文件',
  });
  if (result.canceled) return [];
  return result.filePaths;
});

// 递归扫描目录，返回所有文本文件
ipcMain.handle('scan-directory', async (event, dirPath) => {
  const files = [];

  function scan(dir) {
    try {
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      for (const entry of entries) {
        const fullPath = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          if (SKIP_DIRS.has(entry.name)) continue;
          scan(fullPath);
        } else if (entry.isFile() && isTextFile(entry.name)) {
          const stat = fs.statSync(fullPath);
          files.push({
            name: entry.name,
            path: fullPath,
            size: stat.size,
          });
        }
      }
    } catch (e) {
      console.error('扫描目录失败:', dir, e.message);
    }
  }

  scan(dirPath);
  return files;
});

// 直接读取文件内容
ipcMain.handle('read-file', async (event, filePath) => {
  try {
    const content = fs.readFileSync(filePath, 'utf-8');
    return { success: true, content };
  } catch (e) {
    return { success: false, error: e.message };
  }
});

// 监控文件夹
let watcher = null;
ipcMain.handle('watch-directory', async (event, dirPath) => {
  if (watcher) watcher.close();

  try {
    watcher = fs.watch(dirPath, { recursive: true }, (eventType, filename) => {
      if (!filename || eventType !== 'rename') return;
      const fullPath = path.join(dirPath, filename);
      try {
        if (fs.existsSync(fullPath) && fs.statSync(fullPath).isFile() && isTextFile(filename)) {
          // 通知渲染进程发现新文件
          mainWindow.webContents.send('new-file', {
            path: fullPath,
            name: path.basename(filename),
          });
        }
      } catch (e) {
        // 文件可能正在写入，忽略
      }
    });
    return true;
  } catch (e) {
    console.error('监控失败:', e.message);
    return false;
  }
});

// 停止监控
ipcMain.handle('stop-watch', () => {
  if (watcher) {
    watcher.close();
    watcher = null;
  }
  return true;
});