import React, { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider, useApp } from './context/AppContext';
import { Navbar } from './components/Layout/Navbar';
import { NotificationToast } from './components/Layout/NotificationToast';
import { Landing } from './pages/Landing';
import { Library } from './pages/Library';
import { PromptDetail } from './pages/PromptDetail';
import { CreatePrompt } from './pages/CreatePrompt';
import { Login } from './pages/Login';
import { Signup } from './pages/Signup';
import { Profile } from './pages/Profile';
import { Admin } from './pages/Admin';
import { setTheme } from './utils/storage';

const AppRoutes: React.FC = () => {
  const { theme, loading } = useApp();

  useEffect(() => {
    setTheme(theme);
  }, [theme]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto mb-4" />
          <p className="text-gray-600 dark:text-gray-400">Loading PromptVault...</p>
        </div>
      </div>
    );
  }

  return (
    <Router>
      <div className="min-h-screen bg-white dark:bg-gray-900 transition-colors">
        <Navbar />
        <NotificationToast />
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/library" element={<Library />} />
          <Route path="/prompt/:id" element={<PromptDetail />} />
          <Route path="/create" element={<CreatePrompt />} />
          <Route path="/edit/:id" element={<CreatePrompt />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </Router>
  );
};

const App: React.FC = () => {
  return (
    <AppProvider>
      <AppRoutes />
    </AppProvider>
  );
};

export default App;
