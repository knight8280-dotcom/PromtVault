# Deployment Guide

## Quick Deploy Options

### Option 1: Vercel (Recommended - Easiest)

1. **Push your code to GitHub:**
   ```bash
   git add .
   git commit -m "Initial commit"
   git push origin main
   ```

2. **Deploy to Vercel:**
   - Go to [vercel.com](https://vercel.com)
   - Sign up/login with GitHub
   - Click "New Project"
   - Import your GitHub repository
   - Vercel will auto-detect Vite settings
   - Click "Deploy"
   - Your app will be live in ~2 minutes!

3. **Access on your phone:**
   - Vercel gives you a URL like: `your-app.vercel.app`
   - Open this URL on your phone's browser

### Option 2: Netlify

1. **Push to GitHub** (same as above)

2. **Deploy to Netlify:**
   - Go to [netlify.com](https://netlify.com)
   - Sign up/login with GitHub
   - Click "Add new site" → "Import an existing project"
   - Select your repository
   - Build settings:
     - Build command: `npm run build`
     - Publish directory: `dist`
   - Click "Deploy site"

3. **Access on your phone:**
   - Netlify gives you a URL like: `your-app.netlify.app`

### Option 3: GitHub Pages

1. **Install gh-pages:**
   ```bash
   npm install --save-dev gh-pages
   ```

2. **Add to package.json scripts:**
   ```json
   "predeploy": "npm run build",
   "deploy": "gh-pages -d dist"
   ```

3. **Deploy:**
   ```bash
   npm run deploy
   ```

4. **Enable GitHub Pages:**
   - Go to your repo → Settings → Pages
   - Source: `gh-pages` branch
   - Your site will be at: `username.github.io/repo-name`

### Option 4: Local Network Access (When You Have Your Computer)

1. **Find your computer's IP address:**
   - Windows: `ipconfig` (look for IPv4)
   - Mac/Linux: `ifconfig` or `ip addr`

2. **Run dev server:**
   ```bash
   npm run dev -- --host
   ```

3. **Access from phone:**
   - Make sure phone and computer are on same WiFi
   - Open: `http://YOUR_COMPUTER_IP:5173` on your phone

## Quick Start (When You Get to Your Computer)

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# The app will be available at http://localhost:5173
```

## Production Build

```bash
# Build for production
npm run build

# Preview production build
npm run preview
```
