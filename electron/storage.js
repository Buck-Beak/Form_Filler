import fs from "fs";
import path from "path";
import pkg from 'electron';
const { app } = pkg;

const dbPath = path.join(app.getPath("userData"), "users.json");

function initDB() {
  if (!fs.existsSync(dbPath)) {
    fs.writeFileSync(dbPath, JSON.stringify([]));
  }
}

function loadDB() {
  initDB();
  return JSON.parse(fs.readFileSync(dbPath, "utf8"));
}

function saveDB(data) {
  fs.writeFileSync(dbPath, JSON.stringify(data, null, 2));
}

export function saveUser(receivedJSON) {
  const db = loadDB();
  const telegramId = receivedJSON.telegram_id;

  const index = db.findIndex(u => u.telegram_id === telegramId);
  if (index === -1) {
    db.push(receivedJSON);
  } else {
    db[index] = { ...db[index], ...receivedJSON };
  }
  saveDB(db);
  return receivedJSON;
}
