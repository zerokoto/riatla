const { app, BrowserWindow } = require('electron');
const path = require('path');

let win;

app.on('ready', () => {
  win = new BrowserWindow({
    fullscreen: true
  });
  
  win.loadFile('index.html');
  //win.webContents.openDevTools();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
