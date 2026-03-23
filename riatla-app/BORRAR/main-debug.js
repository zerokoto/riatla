const { app, BrowserWindow } = require('electron');
const path = require('path');

console.log('MAIN.JS: Iniciando...');
console.log('MAIN.JS: __dirname =', __dirname);

let mainWindow = null;

app.on('ready', () => {
  console.log('MAIN.JS: App ready!');
  
  try {
    mainWindow = new BrowserWindow({
      width: 1024,
      height: 768,
      fullscreen: true,
      show: false,
      webPreferences: {
        nodeIntegration: false,
        preload: path.join(__dirname, 'preload.js')
      }
    });

    console.log('MAIN.JS: BrowserWindow creado');

    const indexPath = path.join(__dirname, 'index.html');
    console.log('MAIN.JS: Cargando:', indexPath);
    
    mainWindow.loadFile(indexPath);
    
    mainWindow.once('ready-to-show', () => {
      console.log('MAIN.JS: Window ready-to-show');
      mainWindow.show();
    });

    //mainWindow.webContents.openDevTools();
    console.log('MAIN.JS: DevTools abierto');

    mainWindow.on('closed', () => {
      console.log('MAIN.JS: Window cerrada');
      mainWindow = null;
    });

  } catch (err) {
    console.error('MAIN.JS ERROR:', err);
    process.exit(1);
  }
});

app.on('window-all-closed', () => {
  console.log('MAIN.JS: Tomadas todas las ventanas');
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

console.log('MAIN.JS: Script cargado, esperando ready...');
