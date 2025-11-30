# API Keys Setup Guide

## Overview

The AI enhancement feature requires an API key from either OpenAI or Anthropic to generate real AI responses. Without an API key, the app runs in demo mode with mock responses.

## Setting Up API Keys

### Option 1: Through the UI (Recommended)

1. **Go to any prompt detail page**
2. **Scroll to the "AI-Enhanced Response" section**
3. **Click the settings icon** (gear icon) in the top right
4. **Choose your provider:**
   - OpenAI (GPT-4)
   - Anthropic (Claude)
5. **Enter your API key**
6. **Click "Test Connection"** to verify it works
7. **Click "Save API Key"** once verified

The API key is stored locally in your browser and never sent to our servers.

### Option 2: Environment Variables (For Development)

You can set API keys via environment variables:

```bash
# .env.local (for local development)
VITE_OPENAI_API_KEY=your_openai_key_here
VITE_ANTHROPIC_API_KEY=your_anthropic_key_here
```

**Note:** Environment variables are only used if no key is set in localStorage.

## Getting API Keys

### OpenAI API Key

1. Go to [platform.openai.com](https://platform.openai.com)
2. Sign up or log in
3. Navigate to [API Keys](https://platform.openai.com/api-keys)
4. Click "Create new secret key"
5. Copy the key (you won't see it again!)
6. Paste it in the app settings

**Pricing:** Pay-as-you-go. GPT-4 costs approximately $0.03 per 1K input tokens and $0.06 per 1K output tokens.

### Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Sign up or log in
3. Navigate to API Keys section
4. Click "Create Key"
5. Copy the key
6. Paste it in the app settings

**Pricing:** Pay-as-you-go. Claude 3.5 Sonnet costs approximately $0.003 per 1K input tokens and $0.015 per 1K output tokens.

## Setting Up in Vercel (Production)

If you want to set API keys as environment variables in Vercel:

1. Go to your Vercel project dashboard
2. Navigate to **Settings** → **Environment Variables**
3. Add:
   - `VITE_OPENAI_API_KEY` = your OpenAI key (optional)
   - `VITE_ANTHROPIC_API_KEY` = your Anthropic key (optional)
4. Redeploy your application

**Note:** Users can still add their own keys via the UI, which will override environment variables.

## Testing the Connection

The app includes a connection test feature:

1. Enter your API key in settings
2. Click "Test Connection"
3. The app will verify the key is valid
4. You'll see a success or error message

## Security Notes

- **API keys are stored locally** in your browser's localStorage
- **Keys are never sent to our servers** - all API calls go directly from your browser to OpenAI/Anthropic
- **Each user manages their own keys** - no shared keys
- **Keys can be cleared** at any time via the settings

## Troubleshooting

### "API key is invalid"
- Double-check you copied the entire key
- Make sure there are no extra spaces
- Verify the key is active in your OpenAI/Anthropic account

### "Connection failed"
- Check your internet connection
- Verify your API key has credits/quota
- Try the other provider (OpenAI vs Anthropic)

### "Rate limit exceeded"
- You've hit your API usage limit
- Wait a bit and try again
- Check your API usage dashboard

### Demo Mode
- If no API key is set, the app uses demo mode
- Demo mode shows example responses but doesn't use real AI
- Add an API key to get real AI-generated content

## Cost Considerations

- **OpenAI GPT-4**: More expensive but very capable
- **Anthropic Claude**: Generally cheaper, also very capable
- **Token Usage**: Each enhanced response uses ~2000-3000 tokens
- **Estimated Cost**: $0.06-$0.18 per enhanced response (GPT-4) or $0.006-$0.045 (Claude)

Monitor your usage in your provider's dashboard!
