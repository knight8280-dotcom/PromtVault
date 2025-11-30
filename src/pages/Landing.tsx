import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Sparkles, Search, Star, Users, TrendingUp, Zap, Shield, Globe } from 'lucide-react';
import { Button } from '../components/UI/Button';
import { Card } from '../components/UI/Card';
import { useApp } from '../context/AppContext';

export const Landing: React.FC = () => {
  const { prompts, user } = useApp();

  const stats = {
    totalPrompts: prompts.length,
    totalUsers: 1000 + Math.floor(Math.random() * 500),
    totalViews: 50000 + Math.floor(Math.random() * 10000),
    avgRating: 4.7,
  };

  const features = [
    {
      icon: Search,
      title: 'Advanced Search',
      description: 'Find the perfect prompt with our powerful search and filtering system',
      color: 'text-primary-500',
    },
    {
      icon: Star,
      title: 'Rate & Review',
      description: 'Share your experience and help others discover the best prompts',
      color: 'text-yellow-500',
    },
    {
      icon: Zap,
      title: 'Templates',
      description: 'Use variable placeholders to create reusable prompt templates',
      color: 'text-accent-500',
    },
    {
      icon: Shield,
      title: 'Quality Assured',
      description: 'All prompts are curated and reviewed for quality and effectiveness',
      color: 'text-green-500',
    },
    {
      icon: Globe,
      title: 'Share & Export',
      description: 'Share prompts with unique URLs or export your collection',
      color: 'text-blue-500',
    },
    {
      icon: TrendingUp,
      title: 'Trending Prompts',
      description: 'Discover what\'s popular and trending in the community',
      color: 'text-purple-500',
    },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-gray-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      {/* Hero Section */}
      <section className="relative overflow-hidden pt-20 pb-32">
        <div className="absolute inset-0 bg-gradient-to-r from-primary-500/10 to-accent-500/10 blur-3xl" />
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center">
            <div className="inline-flex items-center space-x-2 px-4 py-2 bg-primary-100 dark:bg-primary-900/30 rounded-full mb-8">
              <Sparkles className="w-4 h-4 text-primary-600 dark:text-primary-400" />
              <span className="text-sm font-medium text-primary-600 dark:text-primary-400">
                Premium AI Prompts Library
              </span>
            </div>
            <h1 className="text-5xl md:text-6xl lg:text-7xl font-bold mb-6 bg-gradient-to-r from-gray-900 via-primary-600 to-accent-600 dark:from-white dark:via-primary-400 dark:to-accent-400 bg-clip-text text-transparent">
              Discover & Share
              <br />
              <span className="bg-gradient-to-r from-primary-600 to-accent-600 dark:from-primary-400 dark:to-accent-400 bg-clip-text text-transparent">
                AI Prompts
              </span>
            </h1>
            <p className="text-xl text-gray-600 dark:text-gray-300 mb-8 max-w-2xl mx-auto">
              The ultimate marketplace for AI prompts. Find, create, and share powerful prompts
              that unlock the full potential of AI.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link to="/library">
                <Button size="lg" className="group">
                  Explore Library
                  <ArrowRight className="ml-2 w-5 h-5 group-hover:translate-x-1 transition-transform" />
                </Button>
              </Link>
              {!user && (
                <Link to="/signup">
                  <Button variant="outline" size="lg">
                    Get Started Free
                  </Button>
                </Link>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="py-16 bg-white/50 dark:bg-gray-800/50 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            <div className="text-center">
              <div className="text-4xl font-bold text-primary-600 dark:text-primary-400 mb-2">
                {stats.totalPrompts}+
              </div>
              <div className="text-sm text-gray-600 dark:text-gray-400">Prompts</div>
            </div>
            <div className="text-center">
              <div className="text-4xl font-bold text-accent-600 dark:text-accent-400 mb-2">
                {stats.totalUsers.toLocaleString()}+
              </div>
              <div className="text-sm text-gray-600 dark:text-gray-400">Users</div>
            </div>
            <div className="text-center">
              <div className="text-4xl font-bold text-green-600 dark:text-green-400 mb-2">
                {stats.totalViews.toLocaleString()}+
              </div>
              <div className="text-sm text-gray-600 dark:text-gray-400">Views</div>
            </div>
            <div className="text-center">
              <div className="text-4xl font-bold text-yellow-600 dark:text-yellow-400 mb-2">
                {stats.avgRating}★
              </div>
              <div className="text-sm text-gray-600 dark:text-gray-400">Avg Rating</div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-24">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-bold text-gray-900 dark:text-white mb-4">
              Everything You Need
            </h2>
            <p className="text-xl text-gray-600 dark:text-gray-300">
              Powerful features to help you discover and create amazing prompts
            </p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {features.map((feature, index) => (
              <Card key={index} hover className="p-6">
                <div className={`w-12 h-12 ${feature.color} mb-4`}>
                  <feature.icon className="w-full h-full" />
                </div>
                <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                  {feature.title}
                </h3>
                <p className="text-gray-600 dark:text-gray-300">
                  {feature.description}
                </p>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-24 bg-gradient-to-r from-primary-600 to-accent-600">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="text-4xl font-bold text-white mb-4">
            Ready to Get Started?
          </h2>
          <p className="text-xl text-primary-100 mb-8">
            Join thousands of users creating and sharing amazing AI prompts
          </p>
          {!user ? (
            <Link to="/signup">
              <Button size="lg" variant="secondary" className="bg-white text-primary-600 hover:bg-gray-100">
                Create Free Account
                <ArrowRight className="ml-2 w-5 h-5" />
              </Button>
            </Link>
          ) : (
            <Link to="/create">
              <Button size="lg" variant="secondary" className="bg-white text-primary-600 hover:bg-gray-100">
                Create Your First Prompt
                <ArrowRight className="ml-2 w-5 h-5" />
              </Button>
            </Link>
          )}
        </div>
      </section>
    </div>
  );
};
