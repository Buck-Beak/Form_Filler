"use strict";
const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("ipcRenderer", {
  on(channel, listener) {
    return ipcRenderer.on(channel, (event, ...args) => listener(event, ...args));
  },
  off(channel, listener) {
    return ipcRenderer.off(channel, listener);
  },
  send(channel, ...args) {
    return ipcRenderer.send(channel, ...args);
  },
  invoke(channel, ...args) {
    return ipcRenderer.invoke(channel, ...args);
  }
  // Add more APIs here if needed
});
