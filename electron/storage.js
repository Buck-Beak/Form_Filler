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

export function loadDB() {
  initDB();
  return JSON.parse(fs.readFileSync(dbPath, "utf8"));
}

function saveDB(data) {
  fs.writeFileSync(dbPath, JSON.stringify(data, null, 2));
}

/*export function saveUser(receivedJSON) {
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
}*/


export function saveUser(receivedJSON) {
  const db = loadDB();
  const telegramId = receivedJSON.telegram_id;

  if (!telegramId) return null;

  const index = db.findIndex(u => u.telegram_id === telegramId);

  // ❌ Do NOT create new user
  if (index === -1) {
    console.warn("User not found, skipping update:", telegramId);
    return null;
  }

  const incomingFields = receivedJSON.extracted_fields || {};
  const existingFields = db[index].extracted_fields || {};

  // ✅ Patch only valid fields
  Object.entries(incomingFields).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      existingFields[key] = value;
    }
  });

  // Assign back
  db[index].extracted_fields = existingFields;

  // Update count
  db[index].fields_count = Object.keys(existingFields).length;

  saveDB(db);
  return db[index];
}
