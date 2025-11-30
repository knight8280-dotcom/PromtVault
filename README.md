# PromptVault - AI Prompts Marketplace

A premium, fully-featured AI prompts marketplace and library built with React, TypeScript, and Tailwind CSS. Discover, create, share, and manage AI prompts with a beautiful, modern interface.

## ✨ Features

### Core Functionality
- **Complete CRUD Operations** - Create, read, update, and delete prompts
- **Advanced Search & Filtering** - Real-time search with category, tag, rating, and popularity filters
- **Category & Tag System** - Organize prompts with categories and multiple tags
- **Favorites & Bookmarks** - Save your favorite prompts for quick access
- **Rating & Reviews** - Rate and review prompts to help the community
- **Copy to Clipboard** - One-click copy with visual feedback
- **Prompt Templates** - Create reusable templates with variable placeholders
- **AI-Enhanced Responses** - Generate detailed, in-depth AI responses based on your prompts (OpenAI/Anthropic)
- **Export/Import** - Export your prompts collection or import from JSON
- **Share Prompts** - Share prompts via unique URLs
- **Trending & Popular** - Discover trending and recently added prompts

### User Features
- **User Authentication** - Sign up, login, and logout
- **User Profiles** - View your favorites, created prompts, and saved items
- **Admin Panel** - Manage prompts and users (admin only)
- **Dark/Light Mode** - Beautiful dark mode with light mode toggle
- **Responsive Design** - Works perfectly on mobile, tablet, and desktop

### Design & UX
- **Premium UI** - Modern, professional design that looks like a million-dollar SaaS product
- **Smooth Animations** - Micro-interactions and transitions throughout
- **Glassmorphism Effects** - Subtle gradient and glass effects
- **Professional Typography** - Clean, readable font hierarchy
- **Loading States** - Proper loading indicators and error handling
- **Form Validation** - Helpful error messages and validation

## 🚀 Getting Started

### Prerequisites
- Node.js 18+ and npm/yarn/pnpm

### Installation

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Start development server:**
   ```bash
   npm run dev
   ```

3. **Build for production:**
   ```bash
   npm run build
   ```

4. **Preview production build:**
   ```bash
   npm run preview
   ```

## 📁 Project Structure

```
src/
├── components/          # Reusable UI components
│   ├── Layout/         # Layout components (Navbar, etc.)
│   └── UI/             # Basic UI components (Button, Card, etc.)
├── context/            # React context providers
├── pages/              # Page components
├── types/              # TypeScript type definitions
└── utils/              # Utility functions (storage, search, helpers)
```

## 🎯 Key Technologies

- **React 18** - Modern React with hooks
- **TypeScript** - Type-safe development
- **Tailwind CSS** - Utility-first CSS framework
- **React Router** - Client-side routing
- **IndexedDB** - Client-side database for data persistence
- **Fuse.js** - Powerful fuzzy search
- **Lucide React** - Beautiful icon library
- **Vite** - Fast build tool and dev server

## 🔐 Default Credentials

For testing purposes, a default admin account is created:

- **Email:** admin@promptvault.com
- **Password:** admin123

## 🤖 AI Enhancement Feature

The app includes an AI enhancement feature that generates detailed, in-depth responses based on your prompts. This goes beyond simple text replacement - the AI actually processes your prompt and creates comprehensive, thoughtful content.

### Setting Up AI Integration

1. **Go to any prompt detail page**
2. **Click the settings icon** in the AI-Enhanced Response section
3. **Choose your AI provider:**
   - **OpenAI (GPT-4)**: Get API key from [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
   - **Anthropic (Claude)**: Get API key from [console.anthropic.com](https://console.anthropic.com/)
4. **Enter your API key** (stored locally, never sent to our servers)
5. **Click "Save API Key"**

### Using AI Enhancement

1. View any prompt (with or without template variables filled in)
2. Scroll to the **"AI-Enhanced Response"** section
3. Click **"Generate Enhanced Response"**
4. The AI will create a detailed, in-depth response based on your prompt
5. Copy the enhanced response or regenerate for variations

### Demo Mode

If no API key is configured, the app runs in **demo mode** with mock responses so you can see how the feature works. Add an API key for real AI-generated content.

### Environment Variables (Optional)

You can also set API keys via environment variables:
- `VITE_OPENAI_API_KEY` for OpenAI
- `VITE_ANTHROPIC_API_KEY` for Anthropic

## 📝 Usage

### Creating a Prompt

1. Sign up or log in to your account
2. Click "Create Prompt" in the navigation
3. Fill in the prompt details:
   - Title and description
   - Category and tags
   - Prompt content
   - Enable template mode for variables
4. Save your prompt

### Using Template Variables

When creating a template prompt, use `{{variableName}}` syntax in your prompt content. The system will automatically detect these variables and allow users to fill them in when viewing the prompt.

Example:
```
Write a professional email about {{topic}} for {{recipient}}.
```

### Searching & Filtering

- Use the search bar to find prompts by title, description, or content
- Filter by category, tags, minimum rating
- Sort by newest, oldest, popularity, rating, or views
- View trending or recently added prompts

### Exporting/Importing

- Go to your Profile page
- Click "Export" to download your prompts as JSON
- Click "Import" to upload prompts from a JSON file

## 🎨 Customization

### Theme Colors

Edit `tailwind.config.js` to customize the color scheme:

```javascript
colors: {
  primary: { /* Your primary colors */ },
  accent: { /* Your accent colors */ }
}
```

### Adding Categories

Categories are stored in IndexedDB. You can add new categories through the admin panel or by modifying the default data in `src/utils/storage.ts`.

## 🛠️ Development

### Code Quality

- TypeScript for type safety
- ESLint for code linting
- Component-based architecture
- Reusable utility functions

### Data Persistence

All data is stored locally using IndexedDB. No backend required! Data persists across browser sessions.

## 📄 License

This project is open source and available for use.

## 🙏 Acknowledgments

Built with modern web technologies and best practices for a premium user experience.

---

**Enjoy building amazing AI prompts with PromptVault! 🚀**
