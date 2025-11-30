// AI Service for enhancing prompts with detailed responses
// Supports multiple AI providers

export interface AIProvider {
  name: string;
  generate(prompt: string, options?: AIGenerateOptions): Promise<string>;
}

export interface AIGenerateOptions {
  temperature?: number;
  maxTokens?: number;
  model?: string;
}

class OpenAIProvider implements AIProvider {
  name = 'OpenAI';
  private apiKey: string;
  private baseUrl = 'https://api.openai.com/v1';

  constructor(apiKey: string) {
    this.apiKey = apiKey;
  }

  async generate(prompt: string, options: AIGenerateOptions = {}): Promise<string> {
    const response = await fetch(`${this.baseUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiKey}`,
      },
      body: JSON.stringify({
        model: options.model || 'gpt-4',
        messages: [
          {
            role: 'system',
            content: 'You are an expert AI assistant that helps enhance and expand prompts with detailed, in-depth thinking and comprehensive responses. Provide thorough, well-structured, and insightful content.',
          },
          {
            role: 'user',
            content: prompt,
          },
        ],
        temperature: options.temperature ?? 0.7,
        max_tokens: options.maxTokens ?? 2000,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.error?.message || 'Failed to generate response');
    }

    const data = await response.json();
    return data.choices[0]?.message?.content || 'No response generated';
  }
}

class AnthropicProvider implements AIProvider {
  name = 'Anthropic';
  private apiKey: string;
  private baseUrl = 'https://api.anthropic.com/v1';

  constructor(apiKey: string) {
    this.apiKey = apiKey;
  }

  async generate(prompt: string, options: AIGenerateOptions = {}): Promise<string> {
    const response = await fetch(`${this.baseUrl}/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': this.apiKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: options.model || 'claude-3-5-sonnet-20241022',
        max_tokens: options.maxTokens ?? 2000,
        temperature: options.temperature ?? 0.7,
        messages: [
          {
            role: 'user',
            content: prompt,
          },
        ],
        system: 'You are an expert AI assistant that helps enhance and expand prompts with detailed, in-depth thinking and comprehensive responses. Provide thorough, well-structured, and insightful content.',
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.error?.message || 'Failed to generate response');
    }

    const data = await response.json();
    return data.content[0]?.text || 'No response generated';
  }
}

// Mock provider for demo/testing without API key
class MockAIProvider implements AIProvider {
  name = 'Mock (Demo)';
  
  async generate(prompt: string, options: AIGenerateOptions = {}): Promise<string> {
    // Simulate API delay
    await new Promise(resolve => setTimeout(resolve, 1500));
    
    // Generate a mock enhanced response
    return `# Enhanced Response

Based on your prompt, here's a comprehensive and detailed response:

## Analysis

${prompt}

## Detailed Breakdown

This prompt requires careful consideration of multiple factors:

1. **Context Understanding**: The prompt addresses a specific need that requires...
2. **Key Components**: Breaking down the requirements reveals several important elements...
3. **Best Practices**: Following industry standards, the approach should include...

## In-Depth Response

The enhanced version of your prompt would include:

- **Expanded Context**: More background information and reasoning
- **Detailed Steps**: Step-by-step breakdown of the process
- **Examples**: Concrete examples to illustrate the concepts
- **Considerations**: Important factors to keep in mind
- **Best Practices**: Recommendations based on experience

## Conclusion

This enhanced approach provides a more comprehensive solution that addresses the core requirements while also considering edge cases and providing actionable insights.

---

*Note: This is a demo response. Connect an AI API key in settings for real AI-generated content.*`;
  }
}

// Get the active AI provider
export const getAIProvider = (): AIProvider | null => {
  // Check for API keys in environment or localStorage
  const openAIKey = import.meta.env.VITE_OPENAI_API_KEY || localStorage.getItem('openai_api_key');
  const anthropicKey = import.meta.env.VITE_ANTHROPIC_API_KEY || localStorage.getItem('anthropic_api_key');

  if (openAIKey) {
    return new OpenAIProvider(openAIKey);
  }
  
  if (anthropicKey) {
    return new AnthropicProvider(anthropicKey);
  }

  // Return mock provider for demo
  return new MockAIProvider();
};

// Generate enhanced response
export const generateEnhancedResponse = async (
  prompt: string,
  options: AIGenerateOptions = {}
): Promise<string> => {
  const provider = getAIProvider();
  
  if (!provider) {
    throw new Error('No AI provider configured');
  }

  return provider.generate(prompt, options);
};

// Save API key to localStorage
export const saveAPIKey = (provider: 'openai' | 'anthropic', key: string): void => {
  if (provider === 'openai') {
    localStorage.setItem('openai_api_key', key);
  } else {
    localStorage.setItem('anthropic_api_key', key);
  }
};

// Get saved API key
export const getAPIKey = (provider: 'openai' | 'anthropic'): string | null => {
  if (provider === 'openai') {
    return localStorage.getItem('openai_api_key');
  }
  return localStorage.getItem('anthropic_api_key');
};

// Clear API key
export const clearAPIKey = (provider: 'openai' | 'anthropic'): void => {
  if (provider === 'openai') {
    localStorage.removeItem('openai_api_key');
  } else {
    localStorage.removeItem('anthropic_api_key');
  }
};
