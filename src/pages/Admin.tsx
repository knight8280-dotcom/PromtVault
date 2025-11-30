import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Users, FileText, Trash2, Edit, Shield } from 'lucide-react';
import { Card } from '../components/UI/Card';
import { Button } from '../components/UI/Button';
import { Input } from '../components/UI/Input';
import { useApp } from '../context/AppContext';
import { getAllUsers, deleteUser, deletePrompt } from '../utils/storage';
import { formatDate } from '../utils/helpers';
import { User as UserType } from '../types';

export const Admin: React.FC = () => {
  const navigate = useNavigate();
  const { user, prompts, setPrompts, addNotification } = useApp();
  const [activeTab, setActiveTab] = useState<'prompts' | 'users'>('prompts');
  const [searchQuery, setSearchQuery] = useState('');
  const [users, setUsers] = useState<UserType[]>([]);

  React.useEffect(() => {
    if (!user || user.role !== 'admin') {
      addNotification({ type: 'error', message: 'Unauthorized access' });
      navigate('/library');
      return;
    }

    const loadUsers = async () => {
      const allUsers = await getAllUsers();
      setUsers(allUsers);
    };
    loadUsers();
  }, [user, navigate, addNotification]);

  const handleDeletePrompt = async (id: string) => {
    if (!window.confirm('Are you sure you want to delete this prompt?')) return;

    try {
      await deletePrompt(id);
      setPrompts(prompts.filter((p) => p.id !== id));
      addNotification({ type: 'success', message: 'Prompt deleted' });
    } catch (error) {
      addNotification({ type: 'error', message: 'Failed to delete prompt' });
    }
  };

  const handleDeleteUser = async (id: string) => {
    if (id === user?.id) {
      addNotification({ type: 'error', message: 'Cannot delete your own account' });
      return;
    }

    if (!window.confirm('Are you sure you want to delete this user?')) return;

    try {
      await deleteUser(id);
      setUsers(users.filter((u) => u.id !== id));
      addNotification({ type: 'success', message: 'User deleted' });
    } catch (error) {
      addNotification({ type: 'error', message: 'Failed to delete user' });
    }
  };

  const filteredPrompts = prompts.filter((p) =>
    p.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredUsers = users.filter((u) =>
    u.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
    u.email.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (!user || user.role !== 'admin') {
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <Shield className="w-8 h-8 text-primary-600 dark:text-primary-400" />
            <h1 className="text-4xl font-bold text-gray-900 dark:text-white">Admin Panel</h1>
          </div>
          <p className="text-gray-600 dark:text-gray-400">
            Manage prompts, users, and system settings
          </p>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-200 dark:border-gray-700 mb-6">
          <nav className="flex space-x-8">
            <button
              onClick={() => setActiveTab('prompts')}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'prompts'
                  ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
            >
              <FileText className="w-4 h-4 inline mr-2" />
              Prompts ({prompts.length})
            </button>
            <button
              onClick={() => setActiveTab('users')}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'users'
                  ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
            >
              <Users className="w-4 h-4 inline mr-2" />
              Users ({users.length})
            </button>
          </nav>
        </div>

        {/* Search */}
        <div className="mb-6">
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={`Search ${activeTab}...`}
          />
        </div>

        {/* Prompts Tab */}
        {activeTab === 'prompts' && (
          <div className="space-y-4">
            {filteredPrompts.length === 0 ? (
              <Card className="p-12 text-center">
                <p className="text-gray-600 dark:text-gray-400">No prompts found</p>
              </Card>
            ) : (
              filteredPrompts.map((prompt) => (
                <Card key={prompt.id} className="p-6">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                        {prompt.title}
                      </h3>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                        {prompt.description}
                      </p>
                      <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
                        <span>Author: {prompt.authorName}</span>
                        <span>Category: {prompt.category}</span>
                        <span>Views: {prompt.views}</span>
                        <span>Created: {formatDate(prompt.createdAt)}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 ml-4">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => navigate(`/edit/${prompt.id}`)}
                      >
                        <Edit className="w-4 h-4 mr-2" />
                        Edit
                      </Button>
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() => handleDeletePrompt(prompt.id)}
                      >
                        <Trash2 className="w-4 h-4 mr-2" />
                        Delete
                      </Button>
                    </div>
                  </div>
                </Card>
              ))
            )}
          </div>
        )}

        {/* Users Tab */}
        {activeTab === 'users' && (
          <div className="space-y-4">
            {filteredUsers.length === 0 ? (
              <Card className="p-12 text-center">
                <p className="text-gray-600 dark:text-gray-400">No users found</p>
              </Card>
            ) : (
              filteredUsers.map((u) => (
                <Card key={u.id} className="p-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">
                        {u.username}
                      </h3>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">{u.email}</p>
                      <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
                        <span className="px-2 py-1 bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 rounded">
                          {u.role}
                        </span>
                        <span>Joined: {formatDate(u.createdAt)}</span>
                        <span>Favorites: {u.favorites.length}</span>
                      </div>
                    </div>
                    {u.id !== user.id && (
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() => handleDeleteUser(u.id)}
                      >
                        <Trash2 className="w-4 h-4 mr-2" />
                        Delete
                      </Button>
                    )}
                  </div>
                </Card>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
};
