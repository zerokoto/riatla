const { app, BrowserWindow } = require('electron');
const path = require('path');

let win;

app.on('ready', () => {
  win = new BrowserWindow({
    width: 800,
    height: 600
  });
  
  win.loadFile('index.html');
  win.webContents.openDevTools();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
