// AI Service for enhancing prompts with detailed responses
// Supports multiple AI providers

export interface AIProvider {
  name: string;
  generate(prompt: string, options?: AIGenerateOptions): Promise<string>;
  testConnection?(): Promise<boolean>;
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

  async testConnection(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/models`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${this.apiKey}`,
        },
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  async generate(prompt: string, options: AIGenerateOptions = {}): Promise<string> {
    const systemPrompt = `You are an expert AI assistant with deep analytical capabilities. Your role is to:

1. **Deeply Analyze the User's Intent**: 
   - Understand what they're really trying to achieve, not just what they explicitly asked for
   - Identify underlying goals, motivations, and desired outcomes
   - Consider the context and use case behind the request

2. **Think Comprehensively**:
   - Explore angles the user might not have considered
   - Identify potential gaps, edge cases, or important factors they may have overlooked
   - Consider best practices, industry standards, and expert recommendations
   - Think about potential challenges, risks, or obstacles

3. **Provide Enhanced, Detailed Responses**:
   - Expand on the original prompt with rich detail and depth
   - Add valuable information, insights, and considerations the user may not have thought about
   - Structure the response clearly with sections, examples, and actionable guidance
   - Include relevant context, background information, and expert perspectives
   - Suggest improvements, alternatives, or complementary approaches

4. **Be Proactive and Insightful**:
   - Don't just answer what was asked - anticipate what they need to know
   - Add considerations like: timing, resources needed, potential pitfalls, success metrics
   - Include examples, templates, or frameworks that could be helpful
   - Think about the "why" behind recommendations, not just the "what"

Your responses should be comprehensive, well-reasoned, and add significant value beyond the original prompt.`;

    const userPrompt = `Analyze this prompt deeply and provide a comprehensive, enhanced response that:

1. Understands the true intent and goals behind this request
2. Adds valuable information, considerations, and insights the user may not have thought about
3. Provides detailed, actionable guidance with examples
4. Includes best practices, potential challenges, and expert recommendations
5. Goes beyond the surface level to deliver real depth and value

Original Prompt:
${prompt}

Now provide your enhanced, comprehensive response:`;

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
            content: systemPrompt,
          },
          {
            role: 'user',
            content: userPrompt,
          },
        ],
        temperature: options.temperature ?? 0.8,
        max_tokens: options.maxTokens ?? 3000,
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

  async testConnection(): Promise<boolean> {
    try {
      // Test with a minimal request
      const response = await fetch(`${this.baseUrl}/messages`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': this.apiKey,
          'anthropic-version': '2023-06-01',
        },
        body: JSON.stringify({
          model: 'claude-3-5-sonnet-20241022',
          max_tokens: 10,
          messages: [{ role: 'user', content: 'test' }],
        }),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  async generate(prompt: string, options: AIGenerateOptions = {}): Promise<string> {
    const systemPrompt = `You are an expert AI assistant with deep analytical capabilities. Your role is to:

1. **Deeply Analyze the User's Intent**: 
   - Understand what they're really trying to achieve, not just what they explicitly asked for
   - Identify underlying goals, motivations, and desired outcomes
   - Consider the context and use case behind the request

2. **Think Comprehensively**:
   - Explore angles the user might not have considered
   - Identify potential gaps, edge cases, or important factors they may have overlooked
   - Consider best practices, industry standards, and expert recommendations
   - Think about potential challenges, risks, or obstacles

3. **Provide Enhanced, Detailed Responses**:
   - Expand on the original prompt with rich detail and depth
   - Add valuable information, insights, and considerations the user may not have thought about
   - Structure the response clearly with sections, examples, and actionable guidance
   - Include relevant context, background information, and expert perspectives
   - Suggest improvements, alternatives, or complementary approaches

4. **Be Proactive and Insightful**:
   - Don't just answer what was asked - anticipate what they need to know
   - Add considerations like: timing, resources needed, potential pitfalls, success metrics
   - Include examples, templates, or frameworks that could be helpful
   - Think about the "why" behind recommendations, not just the "what"

Your responses should be comprehensive, well-reasoned, and add significant value beyond the original prompt.`;

    const userPrompt = `Analyze this prompt deeply and provide a comprehensive, enhanced response that:

1. Understands the true intent and goals behind this request
2. Adds valuable information, considerations, and insights the user may not have thought about
3. Provides detailed, actionable guidance with examples
4. Includes best practices, potential challenges, and expert recommendations
5. Goes beyond the surface level to deliver real depth and value

Original Prompt:
${prompt}

Now provide your enhanced, comprehensive response:`;

    const response = await fetch(`${this.baseUrl}/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': this.apiKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: options.model || 'claude-3-5-sonnet-20241022',
        max_tokens: options.maxTokens ?? 3000,
        temperature: options.temperature ?? 0.8,
        messages: [
          {
            role: 'user',
            content: userPrompt,
          },
        ],
        system: systemPrompt,
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
  
  async generate(_prompt: string, _options: AIGenerateOptions = {}): Promise<string> {
    // Simulate API delay
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    // Generate a more thoughtful mock enhanced response
    return `# Deep Analysis & Enhanced Response

## Understanding Your Intent

After analyzing your prompt, I can see you're looking for: [The AI would identify the core goal here]

But let me dig deeper into what you might really need:

### What You Asked For
${_prompt}

### What You Might Also Need (Things You May Not Have Considered)

1. **Context & Background**: 
   - What's the broader context or situation?
   - Are there industry-specific considerations?
   - What's the timeline or urgency?

2. **Potential Challenges**:
   - Common pitfalls others have encountered
   - Resource requirements you might need
   - Dependencies or prerequisites

3. **Success Metrics**:
   - How will you measure success?
   - What does "good" look like?
   - What are the key indicators?

## Comprehensive Enhanced Response

### 1. Core Requirements (What You Asked)
[Detailed breakdown of the original request with expanded context]

### 2. Additional Considerations (What You Might Not Have Thought About)

**Important Factors:**
- [Factor 1]: Why this matters and how it impacts the outcome
- [Factor 2]: Potential implications and how to address them
- [Factor 3]: Best practices from industry experts

**Edge Cases & Scenarios:**
- What happens in different situations?
- How to handle exceptions or variations?
- What if circumstances change?

**Resources & Prerequisites:**
- What you'll need to succeed
- Skills, tools, or knowledge required
- Time and effort estimates

### 3. Best Practices & Expert Recommendations

Based on industry standards and expert knowledge:

- **Recommended Approach**: [Why this works best]
- **Alternative Methods**: [Other viable options]
- **Common Mistakes to Avoid**: [What to watch out for]

### 4. Actionable Steps & Examples

**Step-by-Step Guide:**
1. [Detailed step with reasoning]
2. [Detailed step with reasoning]
3. [Detailed step with reasoning]

**Real-World Examples:**
- Example scenario 1: [How it applies]
- Example scenario 2: [Variation and adaptation]

### 5. Advanced Considerations

**Going Deeper:**
- Long-term implications
- Scalability considerations
- Integration with other systems/processes
- Future-proofing strategies

**Expert Insights:**
- What industry leaders do differently
- Emerging trends to be aware of
- Research-backed recommendations

## Summary & Next Steps

**Key Takeaways:**
- [Main insight 1]
- [Main insight 2]
- [Main insight 3]

**Recommended Next Actions:**
1. [Action item]
2. [Action item]
3. [Action item]

**Questions to Consider:**
- [Thought-provoking question]
- [Question to refine approach]
- [Question to validate assumptions]

---
*Note: This is a demo response showing the depth of analysis. Connect an AI API key in settings for real, personalized AI-generated content that deeply understands your specific needs.*`;
  }
}

// Get the active AI provider
export const getAIProvider = (): AIProvider | null => {
  // Check for API keys in environment or localStorage
  const openAIKey = import.meta.env.VITE_OPENAI_API_KEY || localStorage.getItem('openai_api_key');
  const anthropicKey = import.meta.env.VITE_ANTHROPIC_API_KEY || localStorage.getItem('anthropic_api_key');

  if (openAIKey && openAIKey.trim()) {
    return new OpenAIProvider(openAIKey.trim());
  }
  
  if (anthropicKey && anthropicKey.trim()) {
    return new AnthropicProvider(anthropicKey.trim());
  }

  // Return mock provider for demo
  return new MockAIProvider();
};

// Test API connection
export const testAPIConnection = async (provider: 'openai' | 'anthropic', apiKey: string): Promise<{ success: boolean; message: string }> => {
  try {
    let aiProvider: AIProvider;
    
    if (provider === 'openai') {
      aiProvider = new OpenAIProvider(apiKey.trim());
    } else {
      aiProvider = new AnthropicProvider(apiKey.trim());
    }

    if (aiProvider.testConnection) {
      const isConnected = await aiProvider.testConnection();
      if (isConnected) {
        return { success: true, message: `${provider === 'openai' ? 'OpenAI' : 'Anthropic'} API connection successful!` };
      } else {
        return { success: false, message: 'API key is invalid or connection failed. Please check your key.' };
      }
    }

    // Fallback: try a minimal generation request
    try {
      await aiProvider.generate('test', { maxTokens: 10 });
      return { success: true, message: `${provider === 'openai' ? 'OpenAI' : 'Anthropic'} API connection successful!` };
    } catch (error) {
      return { success: false, message: error instanceof Error ? error.message : 'API key validation failed' };
    }
  } catch (error) {
    return { success: false, message: error instanceof Error ? error.message : 'Failed to test connection' };
  }
};

// Generate enhanced response with deep analysis
export const generateEnhancedResponse = async (
  prompt: string,
  options: AIGenerateOptions = {}
): Promise<string> => {
  const provider = getAIProvider();
  
  if (!provider) {
    throw new Error('No AI provider configured');
  }

  // Use higher temperature for more creative/exploratory thinking
  const enhancedOptions = {
    ...options,
    temperature: options.temperature ?? 0.8, // Higher for more exploratory thinking
    maxTokens: options.maxTokens ?? 3000, // More tokens for comprehensive responses
  };

  return provider.generate(prompt, enhancedOptions);
};

// Save API key to localStorage
export const saveAPIKey = (provider: 'openai' | 'anthropic', key: string): void => {
  if (provider === 'openai') {
    localStorage.setItem('openai_api_key', key.trim());
  } else {
    localStorage.setItem('anthropic_api_key', key.trim());
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
