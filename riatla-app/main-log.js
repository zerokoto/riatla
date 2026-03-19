const fs = require('fs');
const { app, BrowserWindow } = require('electron');
const path = require('path');

const logFile = path.join(__dirname, 'electron-log.txt');

function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}\n`;
  console.log(msg);
  try {
    fs.appendFileSync(logFile, line);
  } catch (e) {
    // ignore
  }
}

log('=== ELECTRON INICIANDO ===');
log('__dirname: ' + __dirname);

let mainWindow = null;

function createWindow() {
  log('Creando BrowserWindow...');
  
  mainWindow = new BrowserWindow({
    width: 1024,
    height: 768,
    webPreferences: {
      nodeIntegration: false,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  log('BrowserWindow creado');

  const indexPath = path.join(__dirname, 'index.html');
  log('Intentando cargar: ' + indexPath);
  
  mainWindow.loadFile(indexPath).catch(err => {
    log('ERROR cargando: ' + err.message);
  });

  mainWindow.webContents.openDevTools();
  log('DevTools abierto');

  mainWindow.on('closed', () => {
    log('Ventana cerrada');
    mainWindow = null;
  });
}

log('Esperando app.on(ready)...');

app.on('ready', () => {
  log('APP READY EVENT RECIBIDO');
  createWindow();
});

app.on('window-all-closed', () => {
  log('Todas las ventanas cerradas');
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('quit', () => {
  log('APP QUIT');
});

log('Script completamente cargado');
