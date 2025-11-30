import React, { useState, useEffect, useMemo } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { Grid, List, Filter, X, Star, Eye, Heart, Search } from 'lucide-react';
import { Card } from '../components/UI/Card';
import { Input } from '../components/UI/Input';
import { Button } from '../components/UI/Button';
import { useApp } from '../context/AppContext';
import { filterPrompts, getTrendingPrompts, getRecentPrompts } from '../utils/search';
import { formatRelativeTime } from '../utils/helpers';
import { Prompt } from '../types';

type ViewMode = 'grid' | 'list';
type SortBy = 'newest' | 'oldest' | 'popular' | 'rating' | 'views';

export const Library: React.FC = () => {
  const { prompts, categories, user } = useApp();
  const [searchParams, setSearchParams] = useSearchParams();
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [searchQuery, setSearchQuery] = useState(searchParams.get('search') || '');
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [minRating, setMinRating] = useState<number>(0);
  const [sortBy, setSortBy] = useState<SortBy>('newest');
  const [showFilters, setShowFilters] = useState(false);
  const [showSection, setShowSection] = useState<'all' | 'trending' | 'recent'>('all');

  const allTags = useMemo(() => {
    const tagSet = new Set<string>();
    prompts.forEach((p) => p.tags.forEach((tag) => tagSet.add(tag)));
    return Array.from(tagSet).sort();
  }, [prompts]);

  const filteredPrompts = useMemo(() => {
    let filtered = prompts.filter((p) => p.isPublic || p.authorId === user?.id);

    if (showSection === 'trending') {
      filtered = getTrendingPrompts(filtered);
    } else if (showSection === 'recent') {
      filtered = getRecentPrompts(filtered);
    }

    return filterPrompts(filtered, {
      searchQuery,
      category: selectedCategory || undefined,
      tags: selectedTags.length > 0 ? selectedTags : undefined,
      minRating: minRating > 0 ? minRating : undefined,
      sortBy,
    });
  }, [prompts, searchQuery, selectedCategory, selectedTags, minRating, sortBy, showSection, user]);

  const handleTagToggle = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  };

  const clearFilters = () => {
    setSearchQuery('');
    setSelectedCategory('');
    setSelectedTags([]);
    setMinRating(0);
    setSortBy('newest');
    setSearchParams({});
  };

  useEffect(() => {
    if (searchQuery) {
      setSearchParams({ search: searchQuery });
    } else {
      setSearchParams({});
    }
  }, [searchQuery, setSearchParams]);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-4">
            Prompt Library
          </h1>
          <div className="flex flex-col md:flex-row gap-4 items-start md:items-center justify-between">
            <div className="flex-1 max-w-md">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                <Input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search prompts..."
                  className="pl-10"
                />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant={showSection === 'all' ? 'primary' : 'outline'}
                size="sm"
                onClick={() => setShowSection('all')}
              >
                All
              </Button>
              <Button
                variant={showSection === 'trending' ? 'primary' : 'outline'}
                size="sm"
                onClick={() => setShowSection('trending')}
              >
                Trending
              </Button>
              <Button
                variant={showSection === 'recent' ? 'primary' : 'outline'}
                size="sm"
                onClick={() => setShowSection('recent')}
              >
                Recent
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowFilters(!showFilters)}
              >
                <Filter className="w-4 h-4 mr-2" />
                Filters
              </Button>
              <div className="flex items-center border border-gray-300 dark:border-gray-600 rounded-lg overflow-hidden">
                <button
                  onClick={() => setViewMode('grid')}
                  className={`p-2 ${viewMode === 'grid' ? 'bg-primary-600 text-white' : 'text-gray-600 dark:text-gray-300'}`}
                >
                  <Grid className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setViewMode('list')}
                  className={`p-2 ${viewMode === 'list' ? 'bg-primary-600 text-white' : 'text-gray-600 dark:text-gray-300'}`}
                >
                  <List className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Filters */}
        {showFilters && (
          <Card className="p-6 mb-8 animate-slide-down">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Filters</h3>
              <div className="flex items-center gap-2">
                {(selectedCategory || selectedTags.length > 0 || minRating > 0) && (
                  <Button variant="ghost" size="sm" onClick={clearFilters}>
                    <X className="w-4 h-4 mr-2" />
                    Clear
                  </Button>
                )}
                <Button variant="ghost" size="sm" onClick={() => setShowFilters(false)}>
                  <X className="w-4 h-4" />
                </Button>
              </div>
            </div>
            <div className="grid md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Category
                </label>
                <select
                  value={selectedCategory}
                  onChange={(e) => setSelectedCategory(e.target.value)}
                  className="w-full px-4 py-2 bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-gray-900 dark:text-gray-100"
                >
                  <option value="">All Categories</option>
                  {categories.map((cat) => (
                    <option key={cat.id} value={cat.name}>
                      {cat.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Minimum Rating
                </label>
                <select
                  value={minRating}
                  onChange={(e) => setMinRating(Number(e.target.value))}
                  className="w-full px-4 py-2 bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-gray-900 dark:text-gray-100"
                >
                  <option value="0">Any Rating</option>
                  <option value="3">3+ Stars</option>
                  <option value="4">4+ Stars</option>
                  <option value="4.5">4.5+ Stars</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Sort By
                </label>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as SortBy)}
                  className="w-full px-4 py-2 bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-gray-900 dark:text-gray-100"
                >
                  <option value="newest">Newest First</option>
                  <option value="oldest">Oldest First</option>
                  <option value="popular">Most Popular</option>
                  <option value="rating">Highest Rated</option>
                  <option value="views">Most Views</option>
                </select>
              </div>
            </div>
            {allTags.length > 0 && (
              <div className="mt-4">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Tags
                </label>
                <div className="flex flex-wrap gap-2">
                  {allTags.map((tag) => (
                    <button
                      key={tag}
                      onClick={() => handleTagToggle(tag)}
                      className={`px-3 py-1 rounded-full text-sm transition-colors ${
                        selectedTags.includes(tag)
                          ? 'bg-primary-600 text-white'
                          : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                      }`}
                    >
                      {tag}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </Card>
        )}

        {/* Results Count */}
        <div className="mb-6 text-sm text-gray-600 dark:text-gray-400">
          Showing {filteredPrompts.length} prompt{filteredPrompts.length !== 1 ? 's' : ''}
        </div>

        {/* Prompts Grid/List */}
        {filteredPrompts.length === 0 ? (
          <Card className="p-12 text-center">
            <p className="text-gray-600 dark:text-gray-400 text-lg">
              No prompts found. Try adjusting your filters or create a new prompt!
            </p>
          </Card>
        ) : (
          <div
            className={
              viewMode === 'grid'
                ? 'grid md:grid-cols-2 lg:grid-cols-3 gap-6'
                : 'space-y-4'
            }
          >
            {filteredPrompts.map((prompt) => (
              <PromptCard key={prompt.id} prompt={prompt} viewMode={viewMode} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

const PromptCard: React.FC<{ prompt: Prompt; viewMode: ViewMode }> = ({ prompt, viewMode }) => {
  const { user } = useApp();
  const isFavorite = user?.favorites.includes(prompt.id);

  if (viewMode === 'list') {
    return (
      <Card hover className="p-6">
        <Link to={`/prompt/${prompt.id}`}>
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <h3 className="text-xl font-semibold text-gray-900 dark:text-white">
                  {prompt.title}
                </h3>
                {prompt.isTemplate && (
                  <span className="px-2 py-1 text-xs font-medium bg-accent-100 dark:bg-accent-900/30 text-accent-700 dark:text-accent-300 rounded">
                    Template
                  </span>
                )}
              </div>
              <p className="text-gray-600 dark:text-gray-400 mb-3 line-clamp-2">
                {prompt.description}
              </p>
              <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
                <span className="flex items-center gap-1">
                  <Star className="w-4 h-4 fill-yellow-400 text-yellow-400" />
                  {prompt.rating.toFixed(1)}
                </span>
                <span className="flex items-center gap-1">
                  <Eye className="w-4 h-4" />
                  {prompt.views}
                </span>
                <span>{prompt.category}</span>
                <span>{formatRelativeTime(prompt.createdAt)}</span>
              </div>
              <div className="flex flex-wrap gap-2 mt-3">
                {prompt.tags.slice(0, 3).map((tag) => (
                  <span
                    key={tag}
                    className="px-2 py-1 text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </Link>
      </Card>
    );
  }

  return (
    <Card hover className="p-6">
      <Link to={`/prompt/${prompt.id}`}>
        <div className="flex items-start justify-between mb-3">
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2 line-clamp-1">
              {prompt.title}
            </h3>
            {prompt.isTemplate && (
              <span className="inline-block px-2 py-1 text-xs font-medium bg-accent-100 dark:bg-accent-900/30 text-accent-700 dark:text-accent-300 rounded mb-2">
                Template
              </span>
            )}
          </div>
          {user && (
            <button
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                // Handle favorite toggle
              }}
              className={`p-2 rounded-lg transition-colors ${
                isFavorite
                  ? 'text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20'
                  : 'text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
              }`}
            >
              <Heart className={`w-5 h-5 ${isFavorite ? 'fill-current' : ''}`} />
            </button>
          )}
        </div>
        <p className="text-gray-600 dark:text-gray-400 mb-4 line-clamp-2 text-sm">
          {prompt.description}
        </p>
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-3 text-gray-500 dark:text-gray-400">
            <span className="flex items-center gap-1">
              <Star className="w-4 h-4 fill-yellow-400 text-yellow-400" />
              {prompt.rating.toFixed(1)}
            </span>
            <span className="flex items-center gap-1">
              <Eye className="w-4 h-4" />
              {prompt.views}
            </span>
          </div>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {formatRelativeTime(prompt.createdAt)}
          </span>
        </div>
        <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-primary-600 dark:text-primary-400">
              {prompt.category}
            </span>
            <div className="flex flex-wrap gap-1">
              {prompt.tags.slice(0, 2).map((tag) => (
                <span
                  key={tag}
                  className="px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        </div>
      </Link>
    </Card>
  );
};
