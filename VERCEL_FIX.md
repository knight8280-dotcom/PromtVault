# Fix 404 Error on Vercel

## Quick Fix Steps

### Step 1: Commit and Push the Updated vercel.json

The `vercel.json` file has been updated with the correct routing configuration. You need to:

```bash
git add vercel.json
git commit -m "Fix Vercel routing for SPA"
git push
```

### Step 2: Redeploy on Vercel

**Option A: Automatic (Recommended)**
- Vercel will automatically detect the push and redeploy
- Go to your Vercel dashboard
- Wait for the new deployment to complete (usually 1-2 minutes)

**Option B: Manual Redeploy**
1. Go to [vercel.com/dashboard](https://vercel.com/dashboard)
2. Click on your project
3. Go to the "Deployments" tab
4. Click the "..." menu on the latest deployment
5. Click "Redeploy"

### Step 3: Verify Settings in Vercel Dashboard

1. Go to your project settings in Vercel
2. Navigate to **Settings** → **General**
3. Make sure:
   - **Framework Preset**: Vite (or Auto-detect)
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
   - **Install Command**: `npm install`

### Step 4: Clear Browser Cache

After redeploying:
- Clear your browser cache or use incognito/private mode
- Try accessing your site again

## What Was Fixed

The `vercel.json` file now includes:
- **Rewrites rule**: All routes (except API routes) redirect to `/index.html`
- This allows React Router to handle client-side routing properly
- Without this, Vercel tries to find actual files for routes like `/library`, causing 404 errors

## Testing

After redeploying, test these URLs:
- `https://your-app.vercel.app/` (should work)
- `https://your-app.vercel.app/library` (should work, not 404)
- `https://your-app.vercel.app/prompt/123` (should work, not 404)
- `https://your-app.vercel.app/login` (should work, not 404)

All routes should now work correctly!

## If Still Getting 404

1. **Check Build Logs**: In Vercel dashboard, check if the build succeeded
2. **Verify Output**: Make sure `dist/index.html` exists after build
3. **Check Console**: Open browser dev tools and check for any JavaScript errors
4. **Try Different Route**: Start from the homepage (`/`) and navigate using links

## Alternative: Use Vercel CLI

If you have Vercel CLI installed:

```bash
vercel --prod
```

This will redeploy with the latest configuration.
