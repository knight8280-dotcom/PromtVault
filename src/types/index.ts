export interface User {
  id: string;
  username: string;
  email: string;
  password: string; // In production, this would be hashed
  role: 'user' | 'admin';
  createdAt: string;
  favorites: string[];
  savedPrompts: string[];
}

export interface Prompt {
  id: string;
  title: string;
  description: string;
  content: string;
  category: string;
  tags: string[];
  authorId: string;
  authorName: string;
  createdAt: string;
  updatedAt: string;
  views: number;
  likes: number;
  rating: number;
  ratingCount: number;
  reviews: Review[];
  isTemplate: boolean;
  variables?: PromptVariable[];
  isPublic: boolean;
}

export interface PromptVariable {
  name: string;
  placeholder: string;
  defaultValue?: string;
  required: boolean;
}

export interface Review {
  id: string;
  userId: string;
  userName: string;
  rating: number;
  comment: string;
  createdAt: string;
}

export interface Category {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
}

export interface Notification {
  id: string;
  type: 'success' | 'error' | 'info' | 'warning';
  message: string;
  timestamp: string;
  read: boolean;
}

export interface Analytics {
  totalPrompts: number;
  totalUsers: number;
  totalViews: number;
  totalLikes: number;
  trendingPrompts: Prompt[];
  recentPrompts: Prompt[];
  popularCategories: { category: string; count: number }[];
}
