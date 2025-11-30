import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { UserPlus } from 'lucide-react';
import { Card } from '../components/UI/Card';
import { Button } from '../components/UI/Button';
import { Input } from '../components/UI/Input';
import { useApp } from '../context/AppContext';
import { getUserByEmail, saveUser, setCurrentUser } from '../utils/storage';
import { validateEmail, validatePassword, generateId } from '../utils/helpers';

export const Signup: React.FC = () => {
  const navigate = useNavigate();
  const { setUser, addNotification } = useApp();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const newErrors: Record<string, string> = {};

    if (!username.trim()) {
      newErrors.username = 'Username is required';
    } else if (username.length < 3) {
      newErrors.username = 'Username must be at least 3 characters';
    }

    if (!email.trim()) {
      newErrors.email = 'Email is required';
    } else if (!validateEmail(email)) {
      newErrors.email = 'Invalid email format';
    }

    const passwordValidation = validatePassword(password);
    if (!password.trim()) {
      newErrors.password = 'Password is required';
    } else if (!passwordValidation.valid) {
      newErrors.password = passwordValidation.message || 'Invalid password';
    }

    if (password !== confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
    }

    setErrors(newErrors);
    if (Object.keys(newErrors).length > 0) return;

    setLoading(true);
    try {
      // Check if user already exists
      const existingUser = await getUserByEmail(email);
      if (existingUser) {
        setErrors({ email: 'Email already registered' });
        setLoading(false);
        return;
      }

      const newUser = {
        id: generateId(),
        username: username.trim(),
        email: email.trim(),
        password: password, // In production, hash this
        role: 'user' as const,
        createdAt: new Date().toISOString(),
        favorites: [],
        savedPrompts: [],
      };

      await saveUser(newUser);
      setCurrentUser(newUser);
      setUser(newUser);
      addNotification({ type: 'success', message: 'Account created successfully!' });
      navigate('/library');
    } catch (error) {
      console.error('Signup error:', error);
      addNotification({ type: 'error', message: 'Failed to create account' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-gray-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md p-8">
        <div className="text-center mb-8">
          <h2 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">Create Account</h2>
          <p className="text-gray-600 dark:text-gray-400">Join PromptVault today</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <Input
            label="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Choose a username"
            error={errors.username}
            required
          />

          <Input
            label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            error={errors.email}
            required
          />

          <Input
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 6 characters"
            error={errors.password}
            required
          />

          <Input
            label="Confirm Password"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Re-enter your password"
            error={errors.confirmPassword}
            required
          />

          <Button type="submit" className="w-full" isLoading={loading}>
            <UserPlus className="w-4 h-4 mr-2" />
            Create Account
          </Button>
        </form>

        <div className="mt-6 text-center">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Already have an account?{' '}
            <Link to="/login" className="text-primary-600 dark:text-primary-400 hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </Card>
    </div>
  );
};
