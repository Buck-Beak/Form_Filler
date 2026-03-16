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

  const incomingFields = receivedJSON.extracted_fields || {};

  // If the user doesn't exist in the DB yet, create it so we can store Telegram data.
  if (index === -1) {
    const userRecord = {
      telegram_id: telegramId,
      extracted_fields: {},
      fields_count: 0,
      ...receivedJSON,
    };

    // If incoming JSON already contains extracted_fields, normalize
    if (userRecord.extracted_fields && typeof userRecord.extracted_fields === "object") {
      const filteredFields = {};
      Object.entries(userRecord.extracted_fields).forEach(([key, value]) => {
        if (value !== null && value !== undefined && value !== "") {
          filteredFields[key] = value;
        }
      });
      userRecord.extracted_fields = filteredFields;
      userRecord.fields_count = Object.keys(filteredFields).length;
    }

    db.push(userRecord);
    saveDB(db);
    return userRecord;
  }

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

//reads users.json and returns the stored user entry for that telegram_id

export function getUser(telegramId) {
  if (!telegramId) return null;
  const db = loadDB();
  console.log("Database of user: ",db)
  console.log("database:",db.find((u) => u.telegram_id === telegramId))
  return db.find((u) => u.telegram_id === Number(telegramId)) || null;
}
