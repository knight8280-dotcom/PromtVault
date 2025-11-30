import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { User, Heart, BookOpen, Download, Upload } from 'lucide-react';
import { Card } from '../components/UI/Card';
import { Button } from '../components/UI/Button';
import { useApp } from '../context/AppContext';
import { getAllPrompts, savePrompt } from '../utils/storage';
import { exportPrompts, importPrompts } from '../utils/helpers';
import { formatDate } from '../utils/helpers';
import { Prompt } from '../types';

export const Profile: React.FC = () => {
  const navigate = useNavigate();
  const { user, prompts, setPrompts, addNotification } = useApp();
  const [activeTab, setActiveTab] = useState<'favorites' | 'created' | 'saved'>('favorites');

  if (!user) {
    navigate('/login');
    return null;
  }

  const favoritePrompts = prompts.filter((p) => user.favorites.includes(p.id));
  const createdPrompts = prompts.filter((p) => p.authorId === user.id);
  const savedPrompts = prompts.filter((p) => user.savedPrompts.includes(p.id));

  const handleExport = () => {
    const promptsToExport = prompts.filter((p) => 
      user.favorites.includes(p.id) || user.savedPrompts.includes(p.id) || p.authorId === user.id
    );
    const json = exportPrompts(promptsToExport);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `promptvault-export-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    addNotification({ type: 'success', message: 'Prompts exported successfully!' });
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      const text = await file.text();
      const importedPrompts = importPrompts(text);
      
      // Merge with existing prompts, avoiding duplicates
      for (const importedPrompt of importedPrompts) {
        const exists = prompts.find((p) => p.id === importedPrompt.id);
        if (!exists) {
          await savePrompt(importedPrompt);
        }
      }

      const allPrompts = await getAllPrompts();
      setPrompts(allPrompts);
      addNotification({ type: 'success', message: 'Prompts imported successfully!' });
    } catch (error) {
      addNotification({ type: 'error', message: 'Failed to import prompts. Invalid file format.' });
    }
  };

  const renderPrompts = (promptList: Prompt[]) => {
    if (promptList.length === 0) {
      return (
        <Card className="p-12 text-center">
          <p className="text-gray-600 dark:text-gray-400">
            No prompts found. {activeTab === 'favorites' && 'Start favoriting prompts to see them here!'}
            {activeTab === 'created' && 'Create your first prompt to get started!'}
            {activeTab === 'saved' && 'Save prompts to see them here!'}
          </p>
        </Card>
      );
    }

    return (
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
        {promptList.map((prompt) => (
          <Card key={prompt.id} hover className="p-6">
            <div onClick={() => navigate(`/prompt/${prompt.id}`)}>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                {prompt.title}
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4 line-clamp-2">
                {prompt.description}
              </p>
              <div className="flex items-center justify-between text-sm text-gray-500 dark:text-gray-400">
                <span>{prompt.category}</span>
                <span>{formatDate(prompt.createdAt)}</span>
              </div>
            </div>
          </Card>
        ))}
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Profile Header */}
        <Card className="p-8 mb-8">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <div className="w-20 h-20 bg-gradient-to-br from-primary-500 to-accent-500 rounded-full flex items-center justify-center">
                <User className="w-10 h-10 text-white" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
                  {user.username}
                </h1>
                <p className="text-gray-600 dark:text-gray-400">{user.email}</p>
                <span className="inline-block mt-2 px-3 py-1 text-xs font-medium bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 rounded-full">
                  {user.role === 'admin' ? 'Administrator' : 'User'}
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" onClick={handleExport}>
                <Download className="w-4 h-4 mr-2" />
                Export
              </Button>
              <label className="cursor-pointer">
                <span className="inline-flex items-center px-4 py-2 text-sm font-medium border-2 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">
                  <Upload className="w-4 h-4 mr-2" />
                  Import
                </span>
                <input
                  type="file"
                  accept=".json"
                  onChange={handleImport}
                  className="hidden"
                />
              </label>
            </div>
          </div>
        </Card>

        {/* Stats */}
        <div className="grid md:grid-cols-3 gap-6 mb-8">
          <Card className="p-6 text-center">
            <Heart className="w-8 h-8 text-red-500 mx-auto mb-2" />
            <div className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
              {favoritePrompts.length}
            </div>
            <div className="text-sm text-gray-600 dark:text-gray-400">Favorites</div>
          </Card>
          <Card className="p-6 text-center">
            <BookOpen className="w-8 h-8 text-blue-500 mx-auto mb-2" />
            <div className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
              {createdPrompts.length}
            </div>
            <div className="text-sm text-gray-600 dark:text-gray-400">Created</div>
          </Card>
          <Card className="p-6 text-center">
            <User className="w-8 h-8 text-green-500 mx-auto mb-2" />
            <div className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
              {savedPrompts.length}
            </div>
            <div className="text-sm text-gray-600 dark:text-gray-400">Saved</div>
          </Card>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-200 dark:border-gray-700 mb-6">
          <nav className="flex space-x-8">
            <button
              onClick={() => setActiveTab('favorites')}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'favorites'
                  ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
            >
              Favorites ({favoritePrompts.length})
            </button>
            <button
              onClick={() => setActiveTab('created')}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'created'
                  ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
            >
              Created ({createdPrompts.length})
            </button>
            <button
              onClick={() => setActiveTab('saved')}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'saved'
                  ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
            >
              Saved ({savedPrompts.length})
            </button>
          </nav>
        </div>

        {/* Content */}
        {activeTab === 'favorites' && renderPrompts(favoritePrompts)}
        {activeTab === 'created' && renderPrompts(createdPrompts)}
        {activeTab === 'saved' && renderPrompts(savedPrompts)}
      </div>
    </div>
  );
};
