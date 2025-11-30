import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Copy, Check, Share2, Heart, Star, Eye, Calendar, User, Edit, Trash2, ThumbsUp, MessageSquare } from 'lucide-react';
import { Card } from '../components/UI/Card';
import { Button } from '../components/UI/Button';
import { Modal } from '../components/UI/Modal';
import { Input } from '../components/UI/Input';
import { Textarea } from '../components/UI/Textarea';
import { useApp } from '../context/AppContext';
import { getPrompt, savePrompt, deletePrompt, getAllPrompts, saveUser, setCurrentUser } from '../utils/storage';
import { copyToClipboard, replaceVariables, formatDate } from '../utils/helpers';
import ReactMarkdown from 'react-markdown';
import { Prompt, PromptVariable, Review } from '../types';
import { EnhancedPrompt } from '../components/AI/EnhancedPrompt';

export const PromptDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user, setUser, setPrompts, addNotification } = useApp();
  const [prompt, setPrompt] = useState<Prompt | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [showShareModal, setShowShareModal] = useState(false);
  const [showReviewModal, setShowReviewModal] = useState(false);
  const [reviewRating, setReviewRating] = useState(5);
  const [reviewComment, setReviewComment] = useState('');
  const [variableValues, setVariableValues] = useState<Record<string, string>>({});
  const [renderedContent, setRenderedContent] = useState('');

  useEffect(() => {
    const loadPrompt = async () => {
      if (!id) return;
      try {
        const loadedPrompt = await getPrompt(id);
        if (!loadedPrompt) {
          addNotification({ type: 'error', message: 'Prompt not found' });
          navigate('/library');
          return;
        }
        setPrompt(loadedPrompt);
        
        // Initialize variable values
        if (loadedPrompt.variables) {
          const initialValues: Record<string, string> = {};
          loadedPrompt.variables.forEach((v) => {
            if (v.defaultValue) {
              initialValues[v.name] = v.defaultValue;
            }
          });
          setVariableValues(initialValues);
        }
        
        // Increment views
        loadedPrompt.views += 1;
        await savePrompt(loadedPrompt);
        
        // Update prompts in context
        const allPrompts = await getAllPrompts();
        setPrompts(allPrompts);
      } catch (error) {
        console.error('Failed to load prompt:', error);
        addNotification({ type: 'error', message: 'Failed to load prompt' });
      } finally {
        setLoading(false);
      }
    };

    loadPrompt();
  }, [id, navigate, addNotification, setPrompts]);

  useEffect(() => {
    if (prompt && prompt.isTemplate && prompt.variables) {
      const rendered = replaceVariables(prompt.content, prompt.variables, variableValues);
      setRenderedContent(rendered);
    } else if (prompt) {
      setRenderedContent(prompt.content);
    }
  }, [prompt, variableValues]);

  const handleCopy = async () => {
    if (renderedContent) {
      const success = await copyToClipboard(renderedContent);
      if (success) {
        setCopied(true);
        addNotification({ type: 'success', message: 'Copied to clipboard!' });
        setTimeout(() => setCopied(false), 2000);
      }
    }
  };

  const handleLike = async () => {
    if (!prompt || !user) {
      addNotification({ type: 'info', message: 'Please login to like prompts' });
      return;
    }

    const updatedPrompt = { ...prompt };
    const updatedUser = { ...user };
    
    if (updatedUser.favorites.includes(prompt.id)) {
      updatedPrompt.likes = Math.max(0, updatedPrompt.likes - 1);
      updatedUser.favorites = updatedUser.favorites.filter((id) => id !== prompt.id);
    } else {
      updatedPrompt.likes += 1;
      updatedUser.favorites.push(prompt.id);
    }

    await savePrompt(updatedPrompt);
    await saveUser(updatedUser);
    setCurrentUser(updatedUser);
    setUser(updatedUser);
    
    const allPrompts = await getAllPrompts();
    setPrompts(allPrompts);
    setPrompt(updatedPrompt);
    addNotification({ type: 'success', message: 'Favorite updated' });
  };

  const handleDelete = async () => {
    if (!prompt || !user || (user.id !== prompt.authorId && user.role !== 'admin')) {
      return;
    }

    if (window.confirm('Are you sure you want to delete this prompt?')) {
      await deletePrompt(prompt.id);
      const allPrompts = await getAllPrompts();
      setPrompts(allPrompts);
      addNotification({ type: 'success', message: 'Prompt deleted' });
      navigate('/library');
    }
  };

  const handleSubmitReview = async () => {
    if (!prompt || !user || !reviewComment.trim()) return;

    const newReview: Review = {
      id: `review-${Date.now()}`,
      userId: user.id,
      userName: user.username,
      rating: reviewRating,
      comment: reviewComment,
      createdAt: new Date().toISOString(),
    };

    const updatedPrompt = { ...prompt };
    updatedPrompt.reviews.push(newReview);
    
    // Recalculate rating
    const totalRating = updatedPrompt.reviews.reduce((sum, r) => sum + r.rating, 0);
    updatedPrompt.rating = totalRating / updatedPrompt.reviews.length;
    updatedPrompt.ratingCount = updatedPrompt.reviews.length;

    await savePrompt(updatedPrompt);
    const allPrompts = await getAllPrompts();
    setPrompts(allPrompts);
    setPrompt(updatedPrompt);
    setReviewComment('');
    setReviewRating(5);
    setShowReviewModal(false);
    addNotification({ type: 'success', message: 'Review submitted!' });
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto mb-4" />
          <p className="text-gray-600 dark:text-gray-400">Loading prompt...</p>
        </div>
      </div>
    );
  }

  if (!prompt) {
    return null;
  }

  const isFavorite = user?.favorites.includes(prompt.id);
  const canEdit = user && (user.id === prompt.authorId || user.role === 'admin');

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-6">
          <Link
            to="/library"
            className="text-primary-600 dark:text-primary-400 hover:underline mb-4 inline-block"
          >
            ← Back to Library
          </Link>
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-2">
                {prompt.title}
              </h1>
              <div className="flex items-center gap-4 text-sm text-gray-600 dark:text-gray-400">
                <span className="flex items-center gap-1">
                  <User className="w-4 h-4" />
                  {prompt.authorName}
                </span>
                <span className="flex items-center gap-1">
                  <Calendar className="w-4 h-4" />
                  {formatDate(prompt.createdAt)}
                </span>
                <span className="px-2 py-1 bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 rounded">
                  {prompt.category}
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {canEdit && (
                <>
                  <Link to={`/edit/${prompt.id}`}>
                    <Button variant="outline" size="sm">
                      <Edit className="w-4 h-4 mr-2" />
                      Edit
                    </Button>
                  </Link>
                  <Button variant="danger" size="sm" onClick={handleDelete}>
                    <Trash2 className="w-4 h-4 mr-2" />
                    Delete
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Description */}
        <Card className="p-6 mb-6">
          <p className="text-gray-700 dark:text-gray-300">{prompt.description}</p>
          <div className="flex flex-wrap gap-2 mt-4">
            {prompt.tags.map((tag) => (
              <span
                key={tag}
                className="px-3 py-1 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-full"
              >
                {tag}
              </span>
            ))}
          </div>
        </Card>

        {/* Stats */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <Card className="p-4 text-center">
            <div className="flex items-center justify-center gap-1 text-yellow-500 mb-1">
              <Star className="w-5 h-5 fill-current" />
              <span className="text-lg font-semibold">{prompt.rating.toFixed(1)}</span>
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">
              {prompt.ratingCount} reviews
            </div>
          </Card>
          <Card className="p-4 text-center">
            <div className="flex items-center justify-center gap-1 text-blue-500 mb-1">
              <Eye className="w-5 h-5" />
              <span className="text-lg font-semibold">{prompt.views}</span>
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">Views</div>
          </Card>
          <Card className="p-4 text-center">
            <div className="flex items-center justify-center gap-1 text-red-500 mb-1">
              <Heart className="w-5 h-5" />
              <span className="text-lg font-semibold">{prompt.likes}</span>
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">Likes</div>
          </Card>
          <Card className="p-4 text-center">
            <div className="flex items-center justify-center gap-1 text-green-500 mb-1">
              <MessageSquare className="w-5 h-5" />
              <span className="text-lg font-semibold">{prompt.reviews.length}</span>
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">Reviews</div>
          </Card>
        </div>

        {/* Variables Input (if template) */}
        {prompt.isTemplate && prompt.variables && prompt.variables.length > 0 && (
          <Card className="p-6 mb-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Template Variables
            </h3>
            <div className="space-y-4">
              {prompt.variables.map((variable) => (
                <Input
                  key={variable.name}
                  label={variable.name}
                  placeholder={variable.placeholder}
                  value={variableValues[variable.name] || ''}
                  onChange={(e) =>
                    setVariableValues({ ...variableValues, [variable.name]: e.target.value })
                  }
                  required={variable.required}
                />
              ))}
            </div>
          </Card>
        )}

        {/* Prompt Content */}
        <Card className="p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Prompt Content</h3>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => setShowShareModal(true)}>
                <Share2 className="w-4 h-4 mr-2" />
                Share
              </Button>
              <Button
                variant={copied ? 'secondary' : 'primary'}
                size="sm"
                onClick={handleCopy}
              >
                {copied ? (
                  <>
                    <Check className="w-4 h-4 mr-2" />
                    Copied!
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4 mr-2" />
                    Copy
                  </>
                )}
              </Button>
            </div>
          </div>
          <div className="prose dark:prose-invert max-w-none">
            <div className="bg-gray-900 rounded-lg p-4 overflow-x-auto">
              <div className="whitespace-pre-wrap font-mono text-sm text-gray-100">
                {renderedContent}
              </div>
            </div>
          </div>
        </Card>

        {/* AI-Enhanced Response */}
        <div className="mb-6">
          <EnhancedPrompt prompt={renderedContent} />
        </div>

        {/* Actions */}
        <div className="flex items-center gap-4 mb-6">
          <Button
            variant={isFavorite ? 'secondary' : 'outline'}
            onClick={handleLike}
            disabled={!user}
          >
            <Heart className={`w-4 h-4 mr-2 ${isFavorite ? 'fill-current' : ''}`} />
            {isFavorite ? 'Favorited' : 'Favorite'}
          </Button>
          <Button variant="outline" onClick={() => setShowReviewModal(true)} disabled={!user}>
            <Star className="w-4 h-4 mr-2" />
            Write Review
          </Button>
        </div>

        {/* Reviews */}
        <Card className="p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Reviews ({prompt.reviews.length})
          </h3>
          {prompt.reviews.length === 0 ? (
            <p className="text-gray-600 dark:text-gray-400">No reviews yet. Be the first to review!</p>
          ) : (
            <div className="space-y-4">
              {prompt.reviews.map((review) => (
                <div
                  key={review.id}
                  className="border-b border-gray-200 dark:border-gray-700 pb-4 last:border-0"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <div className="font-medium text-gray-900 dark:text-white">
                        {review.userName}
                      </div>
                      <div className="flex items-center gap-1 text-yellow-500">
                        {[...Array(5)].map((_, i) => (
                          <Star
                            key={i}
                            className={`w-4 h-4 ${i < review.rating ? 'fill-current' : ''}`}
                          />
                        ))}
                      </div>
                    </div>
                    <span className="text-sm text-gray-500 dark:text-gray-400">
                      {formatDate(review.createdAt)}
                    </span>
                  </div>
                  <p className="text-gray-700 dark:text-gray-300">{review.comment}</p>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Share Modal */}
        <Modal
          isOpen={showShareModal}
          onClose={() => setShowShareModal(false)}
          title="Share Prompt"
        >
          <div className="space-y-4">
            <Input
              label="Share URL"
              value={window.location.href}
              readOnly
              onClick={(e) => (e.target as HTMLInputElement).select()}
            />
            <Button
              onClick={async () => {
                await copyToClipboard(window.location.href);
                addNotification({ type: 'success', message: 'Link copied!' });
                setShowShareModal(false);
              }}
              className="w-full"
            >
              <Copy className="w-4 h-4 mr-2" />
              Copy Link
            </Button>
          </div>
        </Modal>

        {/* Review Modal */}
        <Modal
          isOpen={showReviewModal}
          onClose={() => setShowReviewModal(false)}
          title="Write a Review"
        >
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Rating
              </label>
              <div className="flex items-center gap-2">
                {[1, 2, 3, 4, 5].map((rating) => (
                  <button
                    key={rating}
                    onClick={() => setReviewRating(rating)}
                    className={`p-2 rounded-lg transition-colors ${
                      rating <= reviewRating
                        ? 'text-yellow-500'
                        : 'text-gray-300 dark:text-gray-600'
                    }`}
                  >
                    <Star className={`w-6 h-6 ${rating <= reviewRating ? 'fill-current' : ''}`} />
                  </button>
                ))}
              </div>
            </div>
            <Textarea
              label="Comment"
              value={reviewComment}
              onChange={(e) => setReviewComment(e.target.value)}
              rows={4}
              placeholder="Share your thoughts about this prompt..."
            />
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowReviewModal(false)}>
                Cancel
              </Button>
              <Button onClick={handleSubmitReview} disabled={!reviewComment.trim()}>
                Submit Review
              </Button>
            </div>
          </div>
        </Modal>
      </div>
    </div>
  );
};
