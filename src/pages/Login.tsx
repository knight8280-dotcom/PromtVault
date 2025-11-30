import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { LogIn } from 'lucide-react';
import { Card } from '../components/UI/Card';
import { Button } from '../components/UI/Button';
import { Input } from '../components/UI/Input';
import { useApp } from '../context/AppContext';
import { getUserByEmail, setCurrentUser } from '../utils/storage';
import { validateEmail } from '../utils/helpers';

export const Login: React.FC = () => {
  const navigate = useNavigate();
  const { setUser, addNotification } = useApp();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const newErrors: Record<string, string> = {};

    if (!email.trim()) {
      newErrors.email = 'Email is required';
    } else if (!validateEmail(email)) {
      newErrors.email = 'Invalid email format';
    }

    if (!password.trim()) {
      newErrors.password = 'Password is required';
    }

    setErrors(newErrors);
    if (Object.keys(newErrors).length > 0) return;

    setLoading(true);
    try {
      const user = await getUserByEmail(email);
      if (!user) {
        setErrors({ email: 'User not found' });
        setLoading(false);
        return;
      }

      if (user.password !== password) {
        setErrors({ password: 'Incorrect password' });
        setLoading(false);
        return;
      }

      setCurrentUser(user);
      setUser(user);
      addNotification({ type: 'success', message: 'Logged in successfully!' });
      navigate('/library');
    } catch (error) {
      console.error('Login error:', error);
      addNotification({ type: 'error', message: 'Failed to login' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-gray-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md p-8">
        <div className="text-center mb-8">
          <h2 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">Welcome Back</h2>
          <p className="text-gray-600 dark:text-gray-400">Sign in to your account</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
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
            placeholder="Enter your password"
            error={errors.password}
            required
          />

          <Button type="submit" className="w-full" isLoading={loading}>
            <LogIn className="w-4 h-4 mr-2" />
            Sign In
          </Button>
        </form>

        <div className="mt-6 text-center">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Don't have an account?{' '}
            <Link to="/signup" className="text-primary-600 dark:text-primary-400 hover:underline">
              Sign up
            </Link>
          </p>
        </div>

        <div className="mt-4 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
          <p className="text-xs text-blue-800 dark:text-blue-300">
            <strong>Demo:</strong> Use admin@promptvault.com / admin123 to login as admin
          </p>
        </div>
      </Card>
    </div>
  );
};
