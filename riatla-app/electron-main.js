const { app, BrowserWindow } = require('electron');
const path = require('path');

console.log('[Electron] Iniciando aplicación...');
console.log('[Electron] __dirname:', __dirname);

let mainWindow;

function createWindow() {
  console.log('[Electron] Creando ventana principal...');
  
  try {
    mainWindow = new BrowserWindow({
      width: 1920,
      height: 1080,
      fullscreen: true,
      webPreferences: {
        nodeIntegration: false,
        contextIsolation: true,
        preload: path.join(__dirname, 'preload.js')
      }
    });

    const indexPath = path.join(__dirname, 'index.html');
    console.log('[Electron] Cargando:', indexPath);
    
    mainWindow.loadFile(indexPath);
    //mainWindow.webContents.openDevTools();
    
    mainWindow.on('closed', () => {
      console.log('[Electron] Ventana cerrada');
      mainWindow = null;
    });
    
    mainWindow.webContents.on('crashed', () => {
      console.error('[Electron] Contenido web crasheó');
    });

  } catch (error) {
    console.error('[Electron] Error creando ventana:', error);
    process.exit(1);
  }
}

app.on('ready', () => {
  console.log('[Electron] App ready');
  globalShortcut.register('Escape', () => {
    if (mainWindow) mainWindow.setFullScreen(false);
  });
  createWindow();
});

app.on('window-all-closed', () => {
  console.log('[Electron] Todas las ventanas cerradas');
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});

process.on('uncaughtException', (error) => {
  console.error('[Electron] Excepción no capturada:', error);
});
