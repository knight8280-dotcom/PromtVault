import { format } from 'date-fns';
import { Prompt, PromptVariable } from '../types';

export const formatDate = (dateString: string): string => {
  return format(new Date(dateString), 'MMM d, yyyy');
};

export const formatRelativeTime = (dateString: string): string => {
  const date = new Date(dateString);
  const now = new Date();
  const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (diffInSeconds < 60) return 'just now';
  if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}m ago`;
  if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}h ago`;
  if (diffInSeconds < 604800) return `${Math.floor(diffInSeconds / 86400)}d ago`;
  return formatDate(dateString);
};

export const copyToClipboard = async (text: string): Promise<boolean> => {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (err) {
    // Fallback for older browsers
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.opacity = '0';
    document.body.appendChild(textArea);
    textArea.select();
    try {
      document.execCommand('copy');
      document.body.removeChild(textArea);
      return true;
    } catch (err) {
      document.body.removeChild(textArea);
      return false;
    }
  }
};

export const replaceVariables = (content: string, variables: PromptVariable[], values: Record<string, string>): string => {
  let result = content;
  variables.forEach((variable) => {
    const value = values[variable.name] || variable.defaultValue || '';
    const regex = new RegExp(`{{\\s*${variable.name}\\s*}}`, 'g');
    result = result.replace(regex, value);
  });
  return result;
};

export const extractVariables = (content: string): PromptVariable[] => {
  const regex = /{{\s*(\w+)\s*}}/g;
  const matches = [...content.matchAll(regex)];
  const uniqueVars = new Map<string, PromptVariable>();

  matches.forEach((match) => {
    const varName = match[1];
    if (!uniqueVars.has(varName)) {
      uniqueVars.set(varName, {
        name: varName,
        placeholder: `Enter ${varName}`,
        required: false,
      });
    }
  });

  return Array.from(uniqueVars.values());
};

export const generateId = (): string => {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
};

export const exportPrompts = (prompts: Prompt[]): string => {
  return JSON.stringify(prompts, null, 2);
};

export const importPrompts = (json: string): Prompt[] => {
  try {
    const parsed = JSON.parse(json);
    return Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    throw new Error('Invalid JSON format');
  }
};

export const validateEmail = (email: string): boolean => {
  const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return regex.test(email);
};

export const validatePassword = (password: string): { valid: boolean; message?: string } => {
  if (password.length < 6) {
    return { valid: false, message: 'Password must be at least 6 characters' };
  }
  return { valid: true };
};
