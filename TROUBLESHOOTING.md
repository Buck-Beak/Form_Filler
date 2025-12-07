# Troubleshooting Guide - "Failed to fetch" Error

## Problem: "Failed to fetch" when trying to register/login

This error means the frontend cannot connect to the backend server on port 5000.

---

## ✅ Solution 1: Verify Electron is Running

When you run `npm run dev`, you should see:
1. **Vite dev server** starting (usually shows `http://localhost:5173`)
2. **Electron window** opening automatically
3. **Console message**: "Backend running inside Electron on port 5000"

**If Electron window doesn't open:**
- Check the terminal/console for errors
- Make sure you're in the project directory
- Try closing and restarting the terminal

---

## ✅ Solution 2: Check Backend Server Status

### Method 1: Check Console Output
When Electron starts, you should see in the console:
```
User data path: [path]
Backend running inside Electron on port 5000
```

If you don't see "Backend running inside Electron on port 5000", the Express server didn't start.

### Method 2: Check Port 5000
Open a browser and go to: `http://localhost:5000/admin/users`

You should see JSON data or an error. If you see "Cannot connect", the server isn't running.

---

## ✅ Solution 3: Restart Everything

1. **Stop the current process** (Ctrl+C in terminal)
2. **Close Electron window** if it's still open
3. **Run again:**
   ```bash
   npm run dev
   ```

---

## ✅ Solution 4: Check for Port Conflicts

If port 5000 is already in use:

1. **Find what's using port 5000:**
   - Windows: `netstat -ano | findstr :5000`
   - Mac/Linux: `lsof -i :5000`

2. **Kill the process** or change the port in `electron/main.js`

---

## ✅ Solution 5: Verify Dependencies

Make sure all dependencies are installed:

```bash
npm install
```

Especially check:
- `express` is in `dependencies` (not devDependencies)
- All packages installed correctly

---

## ✅ Solution 6: Check Electron Window Console

1. Open Electron window
2. Press `F12` or `Ctrl+Shift+I` to open DevTools
3. Check the Console tab for errors
4. Check the Network tab to see if requests are being made

---

## ✅ Solution 7: Manual Backend Start (Alternative)

If Electron isn't starting the backend automatically, you can test the backend separately:

1. Create a test file `test-server.js`:
```javascript
import express from "express";
const app = express();
app.use(express.json());
app.get("/test", (req, res) => res.json({ status: "ok" }));
app.listen(5000, () => console.log("Test server on 5000"));
```

2. Run: `node test-server.js`
3. Test: Open `http://localhost:5000/test` in browser

If this works, the issue is with Electron integration.

---

## 🔍 Common Issues

### Issue: "Cannot find module 'express'"
**Solution:** Run `npm install` again

### Issue: Electron window opens but backend doesn't start
**Solution:** Check `electron/main.js` - the Express server should start in `app.whenReady()`

### Issue: CORS errors
**Solution:** Backend already has CORS enabled. If still seeing errors, check the CORS headers in `electron/main.js`

### Issue: Port 5000 already in use
**Solution:** 
- Change port in `electron/main.js` (line 141)
- Update `src/api.js` with new port

---

## 📝 Expected Behavior

When everything works correctly:

1. **Terminal shows:**
   ```
   VITE v5.x.x  ready in xxx ms
   ➜  Local:   http://localhost:5173/
   User data path: [path]
   Backend running inside Electron on port 5000
   ```

2. **Electron window opens** with login screen

3. **Registration works** without "Failed to fetch" error

4. **Admin dashboard loads** with user list

---

## 🆘 Still Not Working?

1. **Check Node.js version:** Should be v16 or higher
   ```bash
   node --version
   ```

2. **Clear node_modules and reinstall:**
   ```bash
   rm -rf node_modules package-lock.json
   npm install
   ```

3. **Check for syntax errors:**
   ```bash
   npm run lint
   ```

4. **Verify file structure:**
   - `electron/main.js` exists
   - `electron/storage.js` exists
   - `src/api.js` exists

---

## 💡 Quick Fix Checklist

- [ ] Ran `npm install`
- [ ] Running `npm run dev` (not just `vite`)
- [ ] Electron window opened
- [ ] See "Backend running" message in console
- [ ] Port 5000 is not in use by another app
- [ ] No errors in Electron DevTools console
- [ ] Express is in dependencies (not devDependencies)

