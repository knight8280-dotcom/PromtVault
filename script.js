// Prompt generation logic
async function generatePrompt() {
    const promptType = document.getElementById('promptType').value;
    const mainGoal = document.getElementById('mainGoal').value.trim();
    const context = document.getElementById('context').value.trim();
    const requirements = document.getElementById('requirements').value.trim();
    const outputFormat = document.getElementById('outputFormat').value.trim();
    const tone = document.getElementById('tone').value;
    const examples = document.getElementById('examples').value.trim();
    const avoid = document.getElementById('avoid').value.trim();
    const apiKey = document.getElementById('apiKey').value.trim();

    // Validation
    if (!mainGoal) {
        alert('Please describe what you want to accomplish!');
        return;
    }

    const btn = document.querySelector('.btn-primary');
    const originalBtnText = btn.textContent;
    btn.disabled = true;

    try {
        let result = "";

        // Strategy: 
        // 1. If user provides a key in the UI, use it (Client-side Call).
        // 2. If NO key is in UI, try to call our Backend Proxy (Server-side Key).
        // 3. If Backend fails, fall back to Template Mode.

        btn.innerHTML = '<span class="loading-spinner"></span> Thinking...';

        if (apiKey) {
            // User provided their own key in the UI -> Client Side Call
            result = await generateWithAnthropicDirect(apiKey, {
                promptType, mainGoal, context, requirements, outputFormat, tone, examples, avoid
            });
        } else {
            // No UI key -> Try Backend Proxy
            try {
                result = await generateWithBackendProxy({
                    promptType, mainGoal, context, requirements, outputFormat, tone, examples, avoid
                });
            } catch (proxyError) {
                console.warn("Backend proxy failed or not available, falling back to template:", proxyError);
                // Fallback to Template
                result = buildPrompt({
                    promptType, mainGoal, context, requirements, outputFormat, tone, examples, avoid
                });
                
                // Only alert if it's not a "network error" which is expected on static hosting
                if (!proxyError.message.includes('Failed to fetch')) {
                   // alert("Note: Using template mode (Backend API unavailable).");
                }
            }
        }

        // Display the generated prompt
        document.getElementById('generatedPrompt').textContent = result;
        document.getElementById('outputSection').style.display = 'block';
        document.getElementById('outputSection').scrollIntoView({ behavior: 'smooth' });

    } catch (error) {
        alert("Error generating prompt: " + error.message);
    } finally {
        btn.disabled = false;
        btn.textContent = originalBtnText;
    }
}

async function generateWithBackendProxy(data) {
    const response = await fetch('/api/generate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            model: "claude-3-sonnet-20240229",
            max_tokens: 2000,
            system: getSystemPrompt(),
            messages: [
                { role: "user", content: getUserMessage(data) }
            ]
        })
    });

    if (!response.ok) {
        throw new Error(`Server returned ${response.status}`);
    }

    const responseData = await response.json();
    return responseData.content[0].text;
}

async function generateWithAnthropicDirect(apiKey, data) {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
            'x-api-key': apiKey,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
            'dangerously-allow-browser': 'true'
        },
        body: JSON.stringify({
            model: "claude-3-sonnet-20240229",
            max_tokens: 2000,
            system: getSystemPrompt(),
            messages: [
                { role: "user", content: getUserMessage(data) }
            ]
        })
    });

    if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.error?.message || `API Error: ${response.status}`);
    }

    const responseData = await response.json();
    return responseData.content[0].text;
}

function getSystemPrompt() {
    return "You are an expert Prompt Engineer. Your goal is to take a basic user request and transform it into a highly detailed, professional prompt optimized for LLMs (like Claude, GPT-4). The user wants 'original thinking', so do not just fill in a template. Analyze the request, identify missing constraints, and generate a comprehensive prompt that would yield the best possible result from an AI.";
}

function getUserMessage(data) {
    return `
    I need a detailed prompt for the following task:
    
    TYPE: ${data.promptType}
    GOAL: ${data.mainGoal}
    CONTEXT: ${data.context}
    REQUIREMENTS: ${data.requirements}
    TONE: ${data.tone}
    AVOID: ${data.avoid}
    OUTPUT FORMAT: ${data.outputFormat}
    EXAMPLES: ${data.examples}

    Please generate a robust, structured prompt that I can copy and paste into an AI model.
    `;
}

function buildPrompt(data) {
    // Legacy Template Mode (Fallback)
    const roles = {
        general: "You are an expert AI assistant capable of handling a wide range of tasks with precision and clarity.",
        creative: "You are a visionary creative writer and storyteller, known for crafting engaging narratives and original content.",
        code: "You are a Senior Software Engineer with deep expertise in clean code, architecture, and performance optimization.",
        analysis: "You are a Lead Data Analyst and Strategist, skilled in breaking down complex information into actionable insights.",
        brainstorm: "You are an Innovation Consultant and Ideation Expert, specialized in generating diverse and novel solutions.",
        learning: "You are an Expert Educator and Tutor, able to explain complex concepts in simple, digestible terms.",
        editing: "You are a Senior Editor and Proofreader with an eagle eye for detail, grammar, and style flow."
    };

    const instructions = {
        general: "Your task is to provide a comprehensive answer to the following request.",
        creative: "Your task is to write creative content that meets the following criteria.",
        code: "Your task is to write, refactor, or explain code as requested, following industry best practices.",
        analysis: "Your task is to analyze the provided topic or data and deliver a structured assessment.",
        brainstorm: "Your task is to generate a wide variety of ideas and options for the specific challenge.",
        learning: "Your task is to teach and explain the subject matter effectively to the learner.",
        editing: "Your task is to review, edit, and improve the provided text."
    };

    let prompt = "";

    // 1. Role & Persona
    prompt += `### ROLE\n${roles[data.promptType] || roles.general}\n\n`;

    // 2. Core Task
    prompt += `### TASK\n${instructions[data.promptType] || instructions.general}\n`;
    prompt += `Specific Goal: ${data.mainGoal}\n\n`;

    // 3. Context & Background
    if (data.context) {
        prompt += `### CONTEXT\n${data.context}\n\n`;
    }

    // 4. Requirements & Constraints
    if (data.requirements || data.avoid || data.tone) {
        prompt += `### REQUIREMENTS & CONSTRAINTS\n`;
        if (data.requirements) prompt += `- Must adhere to: ${data.requirements}\n`;
        if (data.tone) prompt += `- Tone/Style: ${getToneDescription(data.tone)}\n`;
        if (data.avoid) prompt += `- Strictly Avoid: ${data.avoid}\n`;
        prompt += "\n";
    }

    // 5. Examples (Few-Shot)
    if (data.examples) {
        prompt += `### REFERENCE EXAMPLES\nUse these examples as a guide for the expected output style/format:\n${data.examples}\n\n`;
    }

    // 6. Format
    if (data.outputFormat) {
        prompt += `### OUTPUT FORMAT\n${data.outputFormat}\n\n`;
    }

    // 7. Advanced Guidelines (The "Detailed" part)
    prompt += `### GUIDELINES\n`;
    prompt += getGuidelines(data.promptType);
    prompt += "\n\n";

    // 8. Chain of Thought / Final Instruction
    prompt += `### INSTRUCTIONS\n`;
    prompt += "1. Take a deep breath and analyze the request step-by-step.\n";
    prompt += "2. Identify any missing information or ambiguities (make reasonable assumptions if necessary, but state them).\n";
    prompt += "3. Draft the response according to the specified format and constraints.\n";
    prompt += "4. Review your response to ensure it directly answers the core goal.";

    return prompt;
}

function getToneDescription(toneKey) {
    const toneDescriptions = {
        professional: 'Professional, objective, and business-appropriate',
        casual: 'Casual, friendly, and conversational',
        technical: 'Technical, precise, and using industry-standard terminology',
        creative: 'Creative, expressive, and engaging',
        formal: 'Formal, academic, and structured',
        concise: 'Concise, direct, and to-the-point'
    };
    return toneDescriptions[toneKey] || toneKey;
}

function getGuidelines(type) {
    const guidelines = {
        general: "- Ensure accuracy and relevance.\n- Organize information logically.\n- Address all parts of the user's query.",
        creative: "- Use vivid imagery and sensory details.\n- Focus on 'show, don't tell'.\n- Ensure a consistent voice and perspective.",
        code: "- Write clean, modular, and well-documented code.\n- Handle edge cases and errors gracefully.\n- Explain the logic behind your solution.\n- Suggest optimizations where possible.",
        analysis: "- Support claims with reasoning or evidence.\n- Consider multiple perspectives or counter-arguments.\n- Distinguish between fact and opinion.",
        brainstorm: "- Prioritize quantity and diversity of ideas first.\n- Encourage out-of-the-box thinking.\n- Briefly explain the 'why' behind each idea.",
        learning: "- Use analogies and examples to clarify abstract concepts.\n- Check for understanding (rhetorically).\n- Structure the explanation from simple to complex.",
        editing: "- Maintain the author's original voice where possible.\n- Explain significant changes.\n- Focus on clarity, flow, and grammar."
    };
    return guidelines[type] || guidelines.general;
}

function copyPrompt() {
    const promptText = document.getElementById('generatedPrompt').textContent;

    // Copy to clipboard
    navigator.clipboard.writeText(promptText).then(() => {
        // Show feedback
        const feedback = document.getElementById('copyFeedback');
        feedback.textContent = '✓ Copied to clipboard!';
        feedback.style.display = 'block';

        setTimeout(() => {
            feedback.style.display = 'none';
        }, 3000);
    }).catch(err => {
        alert('Failed to copy. Please select and copy manually.');
    });
}

function resetForm() {
    // Reset all form fields
    document.getElementById('promptType').value = 'general';
    document.getElementById('mainGoal').value = '';
    document.getElementById('context').value = '';
    document.getElementById('requirements').value = '';
    document.getElementById('outputFormat').value = '';
    document.getElementById('tone').value = '';
    document.getElementById('examples').value = '';
    document.getElementById('avoid').value = '';

    // Hide output section
    document.getElementById('outputSection').style.display = 'none';
    updateFields(); // Reset placeholders

    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function updateFields() {
    const type = document.getElementById('promptType').value;
    const mainGoal = document.getElementById('mainGoal');
    const context = document.getElementById('context');

    const placeholders = {
        general: {
            goal: 'e.g., Explain the concept of machine learning',
            context: 'e.g., I\'m a beginner with basic programming knowledge'
        },
        creative: {
            goal: 'e.g., Write a short story about a time traveler',
            context: 'e.g., Target audience: young adults, Genre: sci-fi adventure'
        },
        code: {
            goal: 'e.g., Create a function to validate email addresses',
            context: 'e.g., Using JavaScript, needs to handle edge cases'
        },
        analysis: {
            goal: 'e.g., Analyze the pros and cons of remote work',
            context: 'e.g., Focus on productivity and work-life balance'
        },
        brainstorm: {
            goal: 'e.g., Generate ideas for a mobile app',
            context: 'e.g., Target market: college students, Budget: limited'
        },
        learning: {
            goal: 'e.g., Teach me about blockchain technology',
            context: 'e.g., I understand basic programming but not cryptocurrency'
        },
        editing: {
            goal: 'e.g., Improve this paragraph for clarity and impact',
            context: 'e.g., Academic essay, needs to be more concise'
        }
    };

    if (placeholders[type]) {
        mainGoal.placeholder = placeholders[type].goal;
        context.placeholder = placeholders[type].context;
    }
}

function useDemoKey(event) {
    event.preventDefault();
    document.getElementById('apiKey').value = ''; // Clear it to force template mode
    alert("Demo Mode Active: The app will now use the built-in logic template instead of the API.");
}

// Toggle Settings
document.addEventListener('DOMContentLoaded', function() {
    const toggleBtn = document.getElementById('toggleSettings');
    const panel = document.getElementById('settingsPanel');
    
    if (toggleBtn && panel) {
        toggleBtn.addEventListener('click', () => {
            panel.classList.toggle('hidden');
        });
    }

    updateFields();
});
