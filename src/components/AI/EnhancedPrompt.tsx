import React, { useState } from 'react';
import { Sparkles, Loader2, Copy, Check, Settings, X } from 'lucide-react';
import { Card } from '../UI/Card';
import { Button } from '../UI/Button';
import { Modal } from '../UI/Modal';
import { Input } from '../UI/Input';
import { generateEnhancedResponse, getAIProvider, saveAPIKey, getAPIKey, clearAPIKey } from '../../services/aiService';
import { copyToClipboard } from '../../utils/helpers';

interface EnhancedPromptProps {
  prompt: string;
  onEnhanced?: (enhanced: string) => void;
}

export const EnhancedPrompt: React.FC<EnhancedPromptProps> = ({ prompt, onEnhanced }) => {
  const [enhanced, setEnhanced] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [selectedProvider, setSelectedProvider] = useState<'openai' | 'anthropic'>('openai');
  const [showEnhanced, setShowEnhanced] = useState(false);

  const provider = getAIProvider();
  const hasAPIKey = provider && provider.name !== 'Mock (Demo)';

  const handleGenerate = async () => {
    if (!prompt.trim()) {
      setError('Prompt is empty');
      return;
    }

    setLoading(true);
    setError(null);
    setEnhanced(null);

    try {
      const response = await generateEnhancedResponse(prompt, {
        temperature: 0.8, // Higher for more exploratory, creative thinking
        maxTokens: 3000, // More tokens for comprehensive, detailed responses
      });
      
      setEnhanced(response);
      setShowEnhanced(true);
      if (onEnhanced) {
        onEnhanced(response);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate enhanced response');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async () => {
    if (enhanced) {
      const success = await copyToClipboard(enhanced);
      if (success) {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }
    }
  };

  const handleSaveAPIKey = () => {
    if (apiKey.trim()) {
      saveAPIKey(selectedProvider, apiKey.trim());
      setShowSettings(false);
      setApiKey('');
      window.location.reload(); // Reload to use new API key
    }
  };

  const handleClearAPIKey = () => {
    clearAPIKey(selectedProvider);
    setShowSettings(false);
    window.location.reload();
  };

  return (
    <>
      <Card className="p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-gradient-to-br from-primary-500 to-accent-500 rounded-lg">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                AI-Enhanced Response
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Deep analysis that understands your intent and adds insights you may not have considered
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowSettings(true)}
              title="AI Settings"
            >
              <Settings className="w-4 h-4" />
            </Button>
            {!hasAPIKey && (
              <span className="text-xs text-yellow-600 dark:text-yellow-400 px-2 py-1 bg-yellow-50 dark:bg-yellow-900/20 rounded">
                Demo Mode
              </span>
            )}
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
          </div>
        )}

        {!showEnhanced ? (
          <div className="text-center py-8">
            <p className="text-gray-600 dark:text-gray-400 mb-2">
              Get a deep, comprehensive analysis that:
            </p>
            <ul className="text-sm text-gray-600 dark:text-gray-400 mb-4 text-left max-w-md mx-auto space-y-1">
              <li>• Understands your true intent and goals</li>
              <li>• Adds valuable insights you may not have considered</li>
              <li>• Includes best practices and expert recommendations</li>
              <li>• Explores edge cases and potential challenges</li>
              <li>• Provides actionable guidance with examples</li>
            </ul>
            <Button
              onClick={handleGenerate}
              isLoading={loading}
              disabled={loading || !prompt.trim()}
              className="mx-auto"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4 mr-2" />
                  Generate Enhanced Response
                </>
              )}
            </Button>
            {!hasAPIKey && (
              <p className="mt-4 text-xs text-gray-500 dark:text-gray-400">
                Currently using demo mode. Add an API key in settings for real AI responses.
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="font-medium text-gray-900 dark:text-white">Enhanced Response:</h4>
              <Button
                variant={copied ? 'secondary' : 'outline'}
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
            <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 max-h-96 overflow-y-auto">
              <div className="prose dark:prose-invert max-w-none">
                <pre className="whitespace-pre-wrap font-sans text-sm text-gray-900 dark:text-gray-100">
                  {enhanced}
                </pre>
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setShowEnhanced(false);
                  setEnhanced(null);
                }}
              >
                Generate New
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleGenerate}
                isLoading={loading}
              >
                Regenerate
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Settings Modal */}
      <Modal
        isOpen={showSettings}
        onClose={() => setShowSettings(false)}
        title="AI Settings"
      >
        <div className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              AI Provider
            </label>
            <select
              value={selectedProvider}
              onChange={(e) => setSelectedProvider(e.target.value as 'openai' | 'anthropic')}
              className="w-full px-4 py-2 bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-gray-900 dark:text-gray-100"
            >
              <option value="openai">OpenAI (GPT-4)</option>
              <option value="anthropic">Anthropic (Claude)</option>
            </select>
          </div>

          <div>
            <Input
              label={`${selectedProvider === 'openai' ? 'OpenAI' : 'Anthropic'} API Key`}
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={`Enter your ${selectedProvider === 'openai' ? 'OpenAI' : 'Anthropic'} API key`}
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Your API key is stored locally and never sent to our servers.
            </p>
          </div>

          {getAPIKey(selectedProvider) && (
            <div className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
              <p className="text-sm text-green-700 dark:text-green-300">
                ✓ API key configured for {selectedProvider === 'openai' ? 'OpenAI' : 'Anthropic'}
              </p>
            </div>
          )}

          <div className="flex gap-2">
            <Button
              onClick={handleSaveAPIKey}
              disabled={!apiKey.trim()}
              className="flex-1"
            >
              Save API Key
            </Button>
            {getAPIKey(selectedProvider) && (
              <Button
                variant="danger"
                onClick={handleClearAPIKey}
              >
                Clear
              </Button>
            )}
          </div>

          <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
            <p className="text-sm text-blue-800 dark:text-blue-300 mb-2">
              <strong>How to get an API key:</strong>
            </p>
            <ul className="text-xs text-blue-700 dark:text-blue-300 space-y-1 list-disc list-inside">
              {selectedProvider === 'openai' ? (
                <>
                  <li>Go to <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener noreferrer" className="underline">OpenAI API Keys</a></li>
                  <li>Sign up or log in to your account</li>
                  <li>Create a new API key</li>
                  <li>Paste it above</li>
                </>
              ) : (
                <>
                  <li>Go to <a href="https://console.anthropic.com/" target="_blank" rel="noopener noreferrer" className="underline">Anthropic Console</a></li>
                  <li>Sign up or log in to your account</li>
                  <li>Navigate to API Keys section</li>
                  <li>Create a new API key</li>
                  <li>Paste it above</li>
                </>
              )}
            </ul>
          </div>
        </div>
      </Modal>
    </>
  );
};
