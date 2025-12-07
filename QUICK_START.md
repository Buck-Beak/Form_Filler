# Quick Start Guide

## 🚀 How to Run the Application

### Step 1: Install Dependencies (One Time)
```bash
npm install
```

### Step 2: Start the Application
```bash
npm run dev
```

**What should happen:**
1. ✅ Terminal shows Vite starting
2. ✅ Electron window opens automatically
3. ✅ Console shows: "Backend running inside Electron on port 5000"
4. ✅ Login screen appears in Electron window

---

## ⚠️ If You See "Failed to fetch" Error

### Check 1: Is Electron Window Open?
- The Electron desktop window must be open
- If it didn't open, check terminal for errors

### Check 2: Is Backend Running?
Look in the terminal/console for this message:
```
Backend running inside Electron on port 5000
```

**If you DON'T see this message:**
- The Express server didn't start
- Close everything and run `npm run dev` again
- Check for errors in the terminal

### Check 3: Wait a Few Seconds
- Backend might take 2-3 seconds to start
- Try registering again after waiting

---

## 🔍 Verify Everything is Working

### Test 1: Check Backend
1. Open browser
2. Go to: `http://localhost:5000/admin/users`
3. Should see JSON (even if empty array `{"users":[],"count":0}`)

### Test 2: Check Frontend
1. Electron window should show login screen
2. No errors in DevTools console (F12)

---

## 📝 Registration Steps

1. **Click "Register"** (or it might already be in register mode)
2. **Enter Telegram ID**: Any unique identifier (e.g., "admin123")
3. **Enter Name**: Your name (optional)
4. **Enter Email**: Your email (optional)
5. **Enter Password**: Optional for registration
6. **Click "Register"**

**If successful:**
- You'll see the Admin Dashboard
- Your user will be saved

**If "Failed to fetch":**
- Follow troubleshooting steps above
- Make sure backend is running

---

## 🛠️ Common Fixes

### Fix 1: Restart Everything
```bash
# Press Ctrl+C to stop
# Then run again:
npm run dev
```

### Fix 2: Reinstall Dependencies
```bash
npm install
npm run dev
```

### Fix 3: Check Port 5000
If another app is using port 5000:
- Close that app, OR
- Change port in `electron/main.js` (line 141)

---

## ✅ Success Indicators

You know it's working when:
- ✅ Electron window opens
- ✅ Console shows "Backend running inside Electron on port 5000"
- ✅ Login screen appears
- ✅ Registration works without errors
- ✅ Admin dashboard shows after login

---

## 🆘 Still Having Issues?

See `TROUBLESHOOTING.md` for detailed solutions.

