import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { User, Prompt, Category, Notification } from '../types';
import {
  getCurrentUser,
  setCurrentUser,
  getTheme,
  setTheme,
  initializeDefaultData,
  getAllPrompts,
  getAllCategories,
  getNotifications,
  saveNotification,
} from '../utils/storage';

interface AppContextType {
  user: User | null;
  setUser: (user: User | null) => void;
  prompts: Prompt[];
  setPrompts: (prompts: Prompt[]) => void;
  categories: Category[];
  setCategories: (categories: Category[]) => void;
  notifications: Notification[];
  addNotification: (notification: Omit<Notification, 'id' | 'timestamp' | 'read'>) => void;
  removeNotification: (id: string) => void;
  theme: 'light' | 'dark';
  toggleTheme: () => void;
  loading: boolean;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUserState] = useState<User | null>(null);
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [theme, setThemeState] = useState<'light' | 'dark'>('dark');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const init = async () => {
      try {
        await initializeDefaultData();
        const currentUser = getCurrentUser();
        const currentTheme = getTheme();
        
        setUserState(currentUser);
        setThemeState(currentTheme);
        document.documentElement.classList.toggle('dark', currentTheme === 'dark');

        const [allPrompts, allCategories, allNotifications] = await Promise.all([
          getAllPrompts(),
          getAllCategories(),
          getNotifications(),
        ]);

        setPrompts(allPrompts);
        setCategories(allCategories);
        setNotifications(allNotifications);
      } catch (error) {
        console.error('Failed to initialize app:', error);
      } finally {
        setLoading(false);
      }
    };

    init();
  }, []);

  const setUser = (newUser: User | null) => {
    setUserState(newUser);
    setCurrentUser(newUser);
  };

  const toggleTheme = () => {
    const newTheme = theme === 'dark' ? 'light' : 'dark';
    setThemeState(newTheme);
    setTheme(newTheme);
  };

  const addNotification = async (notification: Omit<Notification, 'id' | 'timestamp' | 'read'>) => {
    const newNotification: Notification = {
      ...notification,
      id: `notif-${Date.now()}-${Math.random()}`,
      timestamp: new Date().toISOString(),
      read: false,
    };
    
    await saveNotification(newNotification);
    setNotifications((prev) => [newNotification, ...prev]);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
      removeNotification(newNotification.id);
    }, 5000);
  };

  const removeNotification = (id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  };

  return (
    <AppContext.Provider
      value={{
        user,
        setUser,
        prompts,
        setPrompts,
        categories,
        setCategories,
        notifications,
        addNotification,
        removeNotification,
        theme,
        toggleTheme,
        loading,
      }}
    >
      {children}
    </AppContext.Provider>
  );
};

export const useApp = () => {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useApp must be used within AppProvider');
  }
  return context;
};
