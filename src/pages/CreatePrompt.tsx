import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Save, X } from 'lucide-react';
import { Card } from '../components/UI/Card';
import { Button } from '../components/UI/Button';
import { Input } from '../components/UI/Input';
import { Textarea } from '../components/UI/Textarea';
import { useApp } from '../context/AppContext';
import { getPrompt, savePrompt, getAllPrompts } from '../utils/storage';
import { extractVariables, generateId } from '../utils/helpers';
import { Prompt, PromptVariable } from '../types';

export const CreatePrompt: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user, categories, setPrompts, addNotification } = useApp();
  const [loading, setLoading] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [content, setContent] = useState('');
  const [category, setCategory] = useState('');
  const [tags, setTags] = useState('');
  const [isTemplate, setIsTemplate] = useState(false);
  const [isPublic, setIsPublic] = useState(true);
  const [variables, setVariables] = useState<PromptVariable[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!user) {
      addNotification({ type: 'info', message: 'Please login to create prompts' });
      navigate('/login');
      return;
    }

    if (id) {
      // Edit mode
      const loadPrompt = async () => {
        const prompt = await getPrompt(id);
        if (!prompt || (prompt.authorId !== user.id && user.role !== 'admin')) {
          addNotification({ type: 'error', message: 'Prompt not found or unauthorized' });
          navigate('/library');
          return;
        }
        setTitle(prompt.title);
        setDescription(prompt.description);
        setContent(prompt.content);
        setCategory(prompt.category);
        setTags(prompt.tags.join(', '));
        setIsTemplate(prompt.isTemplate);
        setIsPublic(prompt.isPublic);
        setVariables(prompt.variables || []);
      };
      loadPrompt();
    }
  }, [id, user, navigate, addNotification]);

  useEffect(() => {
    if (isTemplate && content) {
      const extracted = extractVariables(content);
      setVariables(extracted);
    }
  }, [content, isTemplate]);

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!title.trim()) newErrors.title = 'Title is required';
    if (!description.trim()) newErrors.description = 'Description is required';
    if (!content.trim()) newErrors.content = 'Content is required';
    if (!category) newErrors.category = 'Category is required';

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate() || !user) return;

    setLoading(true);
    try {
      const tagArray = tags
        .split(',')
        .map((t) => t.trim())
        .filter((t) => t.length > 0);

      const promptData: Prompt = {
        id: id || generateId(),
        title: title.trim(),
        description: description.trim(),
        content: content.trim(),
        category,
        tags: tagArray,
        authorId: user.id,
        authorName: user.username,
        createdAt: id ? (await getPrompt(id))?.createdAt || new Date().toISOString() : new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        views: id ? (await getPrompt(id))?.views || 0 : 0,
        likes: id ? (await getPrompt(id))?.likes || 0 : 0,
        rating: id ? (await getPrompt(id))?.rating || 0 : 0,
        ratingCount: id ? (await getPrompt(id))?.ratingCount || 0 : 0,
        reviews: id ? (await getPrompt(id))?.reviews || [] : [],
        isTemplate,
        variables: isTemplate && variables.length > 0 ? variables : undefined,
        isPublic,
      };

      await savePrompt(promptData);
      
      // Update local state
      const allPrompts = await getAllPrompts();
      setPrompts(allPrompts);

      addNotification({
        type: 'success',
        message: id ? 'Prompt updated successfully!' : 'Prompt created successfully!',
      });
      navigate(`/prompt/${promptData.id}`);
    } catch (error) {
      console.error('Failed to save prompt:', error);
      addNotification({ type: 'error', message: 'Failed to save prompt' });
    } finally {
      setLoading(false);
    }
  };

  const handleVariableChange = (index: number, field: keyof PromptVariable, value: string | boolean) => {
    const updated = [...variables];
    updated[index] = { ...updated[index], [field]: value };
    setVariables(updated);
  };

  const removeVariable = (index: number) => {
    setVariables(variables.filter((_, i) => i !== index));
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <Card className="p-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-6">
            {id ? 'Edit Prompt' : 'Create New Prompt'}
          </h1>

          <form onSubmit={handleSubmit} className="space-y-6">
            <Input
              label="Title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Enter prompt title"
              error={errors.title}
              required
            />

            <Textarea
              label="Description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief description of what this prompt does"
              rows={3}
              error={errors.description}
              required
            />

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Category
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className={`w-full px-4 py-2 bg-gray-50 dark:bg-gray-800 border ${
                  errors.category
                    ? 'border-red-300 dark:border-red-700'
                    : 'border-gray-300 dark:border-gray-600'
                } rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-gray-900 dark:text-gray-100`}
                required
              >
                <option value="">Select a category</option>
                {categories.map((cat) => (
                  <option key={cat.id} value={cat.name}>
                    {cat.name}
                  </option>
                ))}
              </select>
              {errors.category && (
                <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.category}</p>
              )}
            </div>

            <Input
              label="Tags (comma-separated)"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="tag1, tag2, tag3"
            />

            <Textarea
              label="Prompt Content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Enter your prompt content here. Use {{variableName}} for template variables."
              rows={12}
              error={errors.content}
              required
              className="font-mono text-sm"
            />

            {/* Template Variables */}
            {isTemplate && variables.length > 0 && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Template Variables
                </label>
                <div className="space-y-3">
                  {variables.map((variable, index) => (
                    <Card key={index} className="p-4">
                      <div className="grid md:grid-cols-3 gap-3">
                        <Input
                          label="Variable Name"
                          value={variable.name}
                          onChange={(e) => handleVariableChange(index, 'name', e.target.value)}
                          placeholder="variableName"
                        />
                        <Input
                          label="Placeholder"
                          value={variable.placeholder}
                          onChange={(e) => handleVariableChange(index, 'placeholder', e.target.value)}
                          placeholder="Enter value"
                        />
                        <div className="flex items-end gap-2">
                          <div className="flex-1">
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                              <input
                                type="checkbox"
                                checked={variable.required}
                                onChange={(e) => handleVariableChange(index, 'required', e.target.checked)}
                                className="mr-2"
                              />
                              Required
                            </label>
                          </div>
                          <button
                            type="button"
                            onClick={() => removeVariable(index)}
                            className="p-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    </Card>
                  ))}
                </div>
              </div>
            )}

            <div className="flex items-center gap-6">
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={isTemplate}
                  onChange={(e) => setIsTemplate(e.target.checked)}
                  className="mr-2 w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">Template with variables</span>
              </label>
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={isPublic}
                  onChange={(e) => setIsPublic(e.target.checked)}
                  className="mr-2 w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">Make public</span>
              </label>
            </div>

            <div className="flex justify-end gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
              <Button
                type="button"
                variant="outline"
                onClick={() => navigate('/library')}
                disabled={loading}
              >
                Cancel
              </Button>
              <Button type="submit" isLoading={loading}>
                <Save className="w-4 h-4 mr-2" />
                {id ? 'Update Prompt' : 'Create Prompt'}
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </div>
  );
};
