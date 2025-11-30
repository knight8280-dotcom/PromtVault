import { Prompt, User, Category, Notification } from '../types';

const DB_NAME = 'PromptVaultDB';
const DB_VERSION = 1;

// Initialize IndexedDB
export const initDB = (): Promise<IDBDatabase> => {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);

    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;

      // Create object stores
      if (!db.objectStoreNames.contains('prompts')) {
        const promptStore = db.createObjectStore('prompts', { keyPath: 'id' });
        promptStore.createIndex('category', 'category', { unique: false });
        promptStore.createIndex('authorId', 'authorId', { unique: false });
        promptStore.createIndex('createdAt', 'createdAt', { unique: false });
      }

      if (!db.objectStoreNames.contains('users')) {
        const userStore = db.createObjectStore('users', { keyPath: 'id' });
        userStore.createIndex('email', 'email', { unique: true });
        userStore.createIndex('username', 'username', { unique: true });
      }

      if (!db.objectStoreNames.contains('categories')) {
        db.createObjectStore('categories', { keyPath: 'id' });
      }

      if (!db.objectStoreNames.contains('notifications')) {
        const notifStore = db.createObjectStore('notifications', { keyPath: 'id' });
        notifStore.createIndex('timestamp', 'timestamp', { unique: false });
      }
    };
  });
};

// Generic CRUD operations
export const dbOperation = async <T>(
  storeName: string,
  operation: (store: IDBObjectStore) => IDBRequest
): Promise<T> => {
  const db = await initDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction([storeName], 'readwrite');
    const store = transaction.objectStore(storeName);
    const request = operation(store);

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
};

// Prompt operations
export const savePrompt = async (prompt: Prompt): Promise<void> => {
  await dbOperation('prompts', (store) => store.put(prompt));
};

export const getPrompt = async (id: string): Promise<Prompt | undefined> => {
  return await dbOperation<Prompt | undefined>('prompts', (store) => store.get(id));
};

export const getAllPrompts = async (): Promise<Prompt[]> => {
  const db = await initDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(['prompts'], 'readonly');
    const store = transaction.objectStore('prompts');
    const request = store.getAll();

    request.onsuccess = () => resolve(request.result || []);
    request.onerror = () => reject(request.error);
  });
};

export const deletePrompt = async (id: string): Promise<void> => {
  await dbOperation('prompts', (store) => store.delete(id));
};

// User operations
export const saveUser = async (user: User): Promise<void> => {
  await dbOperation('users', (store) => store.put(user));
};

export const getUser = async (id: string): Promise<User | undefined> => {
  return await dbOperation<User | undefined>('users', (store) => store.get(id));
};

export const getUserByEmail = async (email: string): Promise<User | undefined> => {
  const db = await initDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(['users'], 'readonly');
    const store = transaction.objectStore('users');
    const index = store.index('email');
    const request = index.get(email);

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
};

export const getAllUsers = async (): Promise<User[]> => {
  const db = await initDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(['users'], 'readonly');
    const store = transaction.objectStore('users');
    const request = store.getAll();

    request.onsuccess = () => resolve(request.result || []);
    request.onerror = () => reject(request.error);
  });
};

export const deleteUser = async (id: string): Promise<void> => {
  await dbOperation('users', (store) => store.delete(id));
};

// Category operations
export const saveCategory = async (category: Category): Promise<void> => {
  await dbOperation('categories', (store) => store.put(category));
};

export const getAllCategories = async (): Promise<Category[]> => {
  const db = await initDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(['categories'], 'readonly');
    const store = transaction.objectStore('categories');
    const request = store.getAll();

    request.onsuccess = () => resolve(request.result || []);
    request.onerror = () => reject(request.error);
  });
};

// Notification operations
export const saveNotification = async (notification: Notification): Promise<void> => {
  await dbOperation('notifications', (store) => store.put(notification));
};

export const getNotifications = async (): Promise<Notification[]> => {
  const db = await initDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(['notifications'], 'readonly');
    const store = transaction.objectStore('notifications');
    const index = store.index('timestamp');
    const request = index.getAll();

    request.onsuccess = () => {
      const notifications = request.result || [];
      resolve(notifications.sort((a, b) => 
        new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
      ));
    };
    request.onerror = () => reject(request.error);
  });
};

// LocalStorage fallback for current user
export const getCurrentUser = (): User | null => {
  const userStr = localStorage.getItem('currentUser');
  return userStr ? JSON.parse(userStr) : null;
};

export const setCurrentUser = (user: User | null): void => {
  if (user) {
    localStorage.setItem('currentUser', JSON.stringify(user));
  } else {
    localStorage.removeItem('currentUser');
  }
};

export const getTheme = (): 'light' | 'dark' => {
  const theme = localStorage.getItem('theme');
  return (theme as 'light' | 'dark') || 'dark';
};

export const setTheme = (theme: 'light' | 'dark'): void => {
  localStorage.setItem('theme', theme);
  document.documentElement.classList.toggle('dark', theme === 'dark');
};

// Initialize default data
export const initializeDefaultData = async (): Promise<void> => {
  // Check if data already exists
  const existingPrompts = await getAllPrompts();
  if (existingPrompts.length > 0) return;

  // Create default admin user
  const adminUser: User = {
    id: 'admin-1',
    username: 'admin',
    email: 'admin@promptvault.com',
    password: 'admin123', // In production, hash this
    role: 'admin',
    createdAt: new Date().toISOString(),
    favorites: [],
    savedPrompts: [],
  };
  await saveUser(adminUser);

  // Create default categories
  const defaultCategories: Category[] = [
    { id: 'cat-1', name: 'Writing', description: 'Writing and content creation prompts', icon: 'PenTool', color: '#3b82f6' },
    { id: 'cat-2', name: 'Coding', description: 'Programming and development prompts', icon: 'Code', color: '#10b981' },
    { id: 'cat-3', name: 'Marketing', description: 'Marketing and advertising prompts', icon: 'Megaphone', color: '#f59e0b' },
    { id: 'cat-4', name: 'Education', description: 'Educational and learning prompts', icon: 'GraduationCap', color: '#8b5cf6' },
    { id: 'cat-5', name: 'Business', description: 'Business and strategy prompts', icon: 'Briefcase', color: '#ef4444' },
    { id: 'cat-6', name: 'Creative', description: 'Creative and artistic prompts', icon: 'Palette', color: '#ec4899' },
  ];

  for (const category of defaultCategories) {
    await saveCategory(category);
  }

  // Create sample prompts
  const samplePrompts: Prompt[] = [
    {
      id: 'prompt-1',
      title: 'Professional Email Writer',
      description: 'Generate professional, well-structured emails for any business context',
      content: 'You are an expert email writer. Write a professional email with the following details:\n\nSubject: {{subject}}\nRecipient: {{recipient}}\nPurpose: {{purpose}}\nTone: {{tone}}\n\nPlease ensure the email is:\n- Clear and concise\n- Professional yet friendly\n- Well-structured with proper greeting and closing\n- Free of grammatical errors',
      category: 'Writing',
      tags: ['email', 'business', 'professional'],
      authorId: adminUser.id,
      authorName: adminUser.username,
      createdAt: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
      updatedAt: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
      views: 1250,
      likes: 89,
      rating: 4.7,
      ratingCount: 45,
      reviews: [],
      isTemplate: true,
      variables: [
        { name: 'subject', placeholder: 'Email subject line', required: true },
        { name: 'recipient', placeholder: 'Recipient name', required: true },
        { name: 'purpose', placeholder: 'Purpose of the email', required: true },
        { name: 'tone', placeholder: 'Formal, Casual, or Friendly', defaultValue: 'Professional', required: false },
      ],
      isPublic: true,
    },
    {
      id: 'prompt-2',
      title: 'Code Review Assistant',
      description: 'Get detailed code reviews with suggestions for improvement',
      content: 'You are an expert code reviewer. Review the following code and provide:\n\n1. Code quality assessment\n2. Potential bugs or issues\n3. Performance improvements\n4. Best practices suggestions\n5. Security concerns\n\nCode to review:\n```\n{{code}}\n```\n\nLanguage: {{language}}\nContext: {{context}}',
      category: 'Coding',
      tags: ['code-review', 'development', 'best-practices'],
      authorId: adminUser.id,
      authorName: adminUser.username,
      createdAt: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
      updatedAt: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
      views: 980,
      likes: 67,
      rating: 4.8,
      ratingCount: 32,
      reviews: [],
      isTemplate: true,
      variables: [
        { name: 'code', placeholder: 'Code snippet to review', required: true },
        { name: 'language', placeholder: 'Programming language', required: true },
        { name: 'context', placeholder: 'Project context (optional)', required: false },
      ],
      isPublic: true,
    },
    {
      id: 'prompt-3',
      title: 'Social Media Post Generator',
      description: 'Create engaging social media posts for any platform',
      content: 'Create a compelling social media post with the following requirements:\n\nPlatform: {{platform}}\nTopic: {{topic}}\nTarget Audience: {{audience}}\nTone: {{tone}}\nCall to Action: {{cta}}\n\nInclude:\n- Attention-grabbing headline\n- Engaging content (2-3 sentences)\n- Relevant hashtags\n- Clear call to action',
      category: 'Marketing',
      tags: ['social-media', 'marketing', 'content'],
      authorId: adminUser.id,
      authorName: adminUser.username,
      createdAt: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
      updatedAt: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
      views: 1450,
      likes: 112,
      rating: 4.6,
      ratingCount: 58,
      reviews: [],
      isTemplate: true,
      variables: [
        { name: 'platform', placeholder: 'Twitter, LinkedIn, Instagram, etc.', required: true },
        { name: 'topic', placeholder: 'Post topic', required: true },
        { name: 'audience', placeholder: 'Target audience', required: true },
        { name: 'tone', placeholder: 'Professional, Casual, Humorous', defaultValue: 'Engaging', required: false },
        { name: 'cta', placeholder: 'Call to action', required: false },
      ],
      isPublic: true,
    },
  ];

  for (const prompt of samplePrompts) {
    await savePrompt(prompt);
  }
};
