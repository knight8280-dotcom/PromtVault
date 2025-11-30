import Fuse from 'fuse.js';
import { Prompt } from '../types';

export const searchPrompts = (prompts: Prompt[], query: string): Prompt[] => {
  if (!query.trim()) return prompts;

  const fuse = new Fuse(prompts, {
    keys: ['title', 'description', 'content', 'tags', 'category', 'authorName'],
    threshold: 0.3,
    includeScore: true,
  });

  const results = fuse.search(query);
  return results.map((result) => result.item);
};

export const filterPrompts = (
  prompts: Prompt[],
  filters: {
    category?: string;
    tags?: string[];
    minRating?: number;
    sortBy?: 'newest' | 'oldest' | 'popular' | 'rating' | 'views';
    searchQuery?: string;
  }
): Prompt[] => {
  let filtered = [...prompts];

  // Search filter
  if (filters.searchQuery) {
    filtered = searchPrompts(filtered, filters.searchQuery);
  }

  // Category filter
  if (filters.category) {
    filtered = filtered.filter((p) => p.category === filters.category);
  }

  // Tags filter
  if (filters.tags && filters.tags.length > 0) {
    filtered = filtered.filter((p) =>
      filters.tags!.some((tag) => p.tags.includes(tag))
    );
  }

  // Rating filter
  if (filters.minRating) {
    filtered = filtered.filter((p) => p.rating >= filters.minRating!);
  }

  // Sorting
  switch (filters.sortBy) {
    case 'newest':
      filtered.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
      break;
    case 'oldest':
      filtered.sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
      break;
    case 'popular':
      filtered.sort((a, b) => b.views - a.views);
      break;
    case 'rating':
      filtered.sort((a, b) => b.rating - a.rating);
      break;
    case 'views':
      filtered.sort((a, b) => b.views - a.views);
      break;
    default:
      break;
  }

  return filtered;
};

export const getTrendingPrompts = (prompts: Prompt[]): Prompt[] => {
  return [...prompts]
    .sort((a, b) => {
      // Trending score: views + likes + rating
      const scoreA = a.views + a.likes * 10 + a.rating * 100;
      const scoreB = b.views + b.likes * 10 + b.rating * 100;
      return scoreB - scoreA;
    })
    .slice(0, 10);
};

export const getRecentPrompts = (prompts: Prompt[]): Prompt[] => {
  return [...prompts]
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
    .slice(0, 10);
};
