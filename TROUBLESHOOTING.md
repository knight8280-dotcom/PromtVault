# Troubleshooting Guide

## Common Issues and Solutions

### Issue: "I can't generate prompts"

This could mean different things. Let's identify which one:

#### 1. Can't CREATE new prompts (Create Prompt page)

**Symptoms:**
- Can't access the "Create Prompt" page
- Form doesn't submit
- Error messages appear

**Solutions:**

1. **Make sure you're logged in:**
   - Click "Login" in the navigation
   - Use: `admin@promptvault.com` / `admin123`
   - Or create a new account

2. **Check browser console for errors:**
   - Press F12 (or right-click → Inspect)
   - Go to "Console" tab
   - Look for red error messages
   - Share these errors if you need help

3. **Clear browser cache:**
   - Press Ctrl+Shift+Delete (or Cmd+Shift+Delete on Mac)
   - Clear cached images and files
   - Reload the page

4. **Check if IndexedDB is working:**
   - Open browser DevTools (F12)
   - Go to "Application" tab (Chrome) or "Storage" tab (Firefox)
   - Check if "IndexedDB" → "PromptVaultDB" exists
   - If not, the database might not be initialized

#### 2. Can't GENERATE AI-enhanced responses

**Symptoms:**
- "Generate Enhanced Response" button doesn't work
- Error messages appear
- Nothing happens when clicking

**Solutions:**

1. **Check if you have an API key:**
   - Go to any prompt detail page
   - Scroll to "AI-Enhanced Response" section
   - Click the settings icon (⚙️)
   - Check if an API key is configured
   - If not, add one (see API_KEYS_SETUP.md)

2. **Test the API key:**
   - In settings, click "Test Connection"
   - If it fails, your API key might be invalid
   - Get a new key from OpenAI or Anthropic

3. **Check browser console:**
   - Press F12 → Console tab
   - Look for CORS errors or API errors
   - Common errors:
     - "Failed to fetch" → Network issue or CORS
     - "Invalid API key" → Key is wrong
     - "Rate limit exceeded" → Too many requests

4. **Try demo mode:**
   - Without an API key, it should work in demo mode
   - If demo mode doesn't work, there's a code issue

#### 3. Can't SEE prompts in library

**Symptoms:**
- Library page is empty
- No prompts showing up

**Solutions:**

1. **Check if data exists:**
   - The app should auto-create sample prompts on first load
   - If not, try refreshing the page
   - Or clear IndexedDB and reload (will reset all data)

2. **Check browser storage:**
   - F12 → Application/Storage tab
   - Check IndexedDB → PromptVaultDB → prompts
   - Should see at least 3 sample prompts

3. **Try creating a prompt manually:**
   - Login → Create Prompt
   - Fill in the form
   - Save it
   - Check if it appears in library

### Issue: "App won't load / Blank page"

**Solutions:**

1. **Check Vercel deployment:**
   - Go to Vercel dashboard
   - Check if deployment succeeded
   - Look for build errors

2. **Check browser console:**
   - F12 → Console
   - Look for JavaScript errors
   - Common: "Cannot read property of undefined"

3. **Try different browser:**
   - Test in Chrome, Firefox, or Safari
   - Some browsers have different IndexedDB support

4. **Disable browser extensions:**
   - Ad blockers might interfere
   - Privacy extensions might block IndexedDB

### Issue: "404 errors on routes"

**Solutions:**

1. **Make sure vercel.json is correct:**
   - Should have rewrites rule
   - Check if file exists in repo

2. **Redeploy on Vercel:**
   - Go to Vercel dashboard
   - Click "Redeploy"

### Issue: "TypeScript/Build errors"

**Solutions:**

1. **Check build locally:**
   ```bash
   npm install
   npm run build
   ```
   - Fix any errors shown
   - Commit and push

2. **Check Vercel build logs:**
   - Go to Vercel → Deployments
   - Click on failed deployment
   - Check build logs for errors

## Quick Diagnostic Steps

1. **Open browser console (F12)**
2. **Check for errors** (red text)
3. **Check Network tab** for failed requests
4. **Check Application/Storage tab** for IndexedDB
5. **Try in incognito/private mode** (rules out extensions)
6. **Try different browser**

## Getting Help

If nothing works, provide:
1. Browser console errors (screenshot or copy text)
2. What you're trying to do (create prompt? generate AI response?)
3. What happens vs. what should happen
4. Browser and version (Chrome 120, Firefox 121, etc.)

## Reset Everything

If all else fails, you can reset:

1. **Clear all site data:**
   - F12 → Application tab
   - Click "Clear site data"
   - Reload page
   - App will reinitialize with sample data

2. **Or manually clear IndexedDB:**
   - F12 → Application → IndexedDB
   - Right-click "PromptVaultDB" → Delete
   - Reload page
