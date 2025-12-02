// Simple prompt generation from user input
function generatePrompt() {
    try {
        const userInputEl = document.getElementById('userInput');
        if (!userInputEl) {
            alert('Error: Input field not found. Please refresh the page.');
            return;
        }

        const userInput = userInputEl.value.trim();

        // Validation
        if (!userInput) {
            alert('Please describe what you want to do!');
            userInputEl.focus();
            return;
        }

        // Generate structured prompt from simple input
        const generatedPrompt = buildPromptFromInput(userInput);

        // Display the generated prompt
        const generatedPromptEl = document.getElementById('generatedPrompt');
        const outputSectionEl = document.getElementById('outputSection');
        
        if (!generatedPromptEl || !outputSectionEl) {
            console.error('Output elements not found');
            alert('Error: Output elements not found. Please refresh the page.');
            return;
        }

        generatedPromptEl.textContent = generatedPrompt;
        outputSectionEl.style.display = 'block';
        outputSectionEl.scrollIntoView({ behavior: 'smooth' });
    } catch (error) {
        console.error('Error generating prompt:', error);
        alert('An error occurred while generating the prompt. Please check the console for details.');
    }
}

function buildPromptFromInput(input) {
    // Analyze the input to extract key information
    const analysis = analyzeInput(input);
    
    let prompt = '';
    
    // Start with a clear task statement
    prompt += `TASK:\n${analysis.task}\n\n`;
    
    // Add context if detected or if the input is complex
    if (analysis.context || analysis.hasContext) {
        prompt += `CONTEXT:\n${analysis.context || 'Please consider the full context of this request.'}\n\n`;
    }
    
    // Add requirements if detected
    if (analysis.requirements.length > 0) {
        prompt += `REQUIREMENTS:\n${analysis.requirements.join('\n')}\n\n`;
    }
    
    // Add output format if detected
    if (analysis.outputFormat) {
        prompt += `OUTPUT FORMAT: ${analysis.outputFormat}\n\n`;
    }
    
    // Add tone if detected
    if (analysis.tone) {
        prompt += `TONE: ${analysis.tone}\n\n`;
    }
    
    // Add any specific instructions
    if (analysis.instructions.length > 0) {
        prompt += `ADDITIONAL INSTRUCTIONS:\n${analysis.instructions.join('\n')}\n\n`;
    }
    
    // Closing statement
    prompt += 'Please provide a comprehensive and well-structured response that addresses all aspects of this request.';
    
    return prompt;
}

function analyzeInput(input) {
    const lowerInput = input.toLowerCase();
    const analysis = {
        task: '',
        context: '',
        hasContext: false,
        requirements: [],
        outputFormat: '',
        tone: '',
        instructions: []
    };
    
    // Extract the main task (usually the first sentence or main clause)
    // Try to identify the core action
    const taskPatterns = [
        /^(write|create|generate|make|build|develop|design|explain|analyze|help me|i need|i want)/i,
        /^(write|create|generate|make|build|develop|design|explain|analyze)/i
    ];
    
    // Find the main task
    let sentences = input.split(/[.!?]\s+/);
    if (sentences.length === 0) sentences = [input];
    
    // The first sentence is usually the main task
    analysis.task = sentences[0].trim();
    if (sentences.length > 1) {
        analysis.hasContext = true;
        analysis.context = sentences.slice(1).join('. ').trim();
    }
    
    // Detect output format preferences
    const formatKeywords = {
        'bullet points': ['bullet', 'bullets', 'list', 'points'],
        'step-by-step guide': ['step by step', 'step-by-step', 'steps', 'guide', 'tutorial'],
        'essay': ['essay', 'article', 'piece'],
        'code with comments': ['code', 'function', 'script', 'program', 'javascript', 'python', 'html', 'css'],
        'table': ['table', 'chart', 'spreadsheet'],
        'outline': ['outline', 'structure', 'framework']
    };
    
    for (const [format, keywords] of Object.entries(formatKeywords)) {
        if (keywords.some(keyword => lowerInput.includes(keyword))) {
            analysis.outputFormat = format;
            break;
        }
    }
    
    // Detect tone preferences
    const toneKeywords = {
        'Professional and business-appropriate': ['professional', 'business', 'formal', 'corporate'],
        'Casual, friendly, and conversational': ['casual', 'friendly', 'conversational', 'relaxed', 'informal'],
        'Technical and precise with proper terminology': ['technical', 'precise', 'detailed', 'accurate'],
        'Creative, engaging, and imaginative': ['creative', 'engaging', 'imaginative', 'fun', 'interesting'],
        'Formal and academic': ['academic', 'scholarly', 'formal', 'research'],
        'Concise and to-the-point': ['concise', 'brief', 'short', 'quick', 'summary']
    };
    
    for (const [tone, keywords] of Object.entries(toneKeywords)) {
        if (keywords.some(keyword => lowerInput.includes(keyword))) {
            analysis.tone = tone;
            break;
        }
    }
    
    // Extract specific requirements
    const requirementPatterns = [
        /(\d+)\s*(words?|characters?|pages?|paragraphs?|sentences?)/gi,
        /(length|long|short|brief|detailed)/gi,
        /(include|must|should|need to|require)/gi
    ];
    
    // Look for explicit requirements
    if (lowerInput.includes('include')) {
        const includeMatch = input.match(/include[^.!?]*/i);
        if (includeMatch) {
            analysis.requirements.push(includeMatch[0].trim());
        }
    }
    
    if (lowerInput.includes('must') || lowerInput.includes('should')) {
        const mustMatch = input.match(/(must|should)[^.!?]*/i);
        if (mustMatch) {
            analysis.requirements.push(mustMatch[0].trim());
        }
    }
    
    // Detect word count or length requirements
    const lengthMatch = input.match(/(\d+)\s*(words?|characters?|pages?|paragraphs?)/i);
    if (lengthMatch) {
        analysis.requirements.push(`Length: ${lengthMatch[0]}`);
    }
    
    // Detect audience mentions
    const audienceMatch = input.match(/(for|target|audience|readers?|users?)\s+([^.!?,]+)/i);
    if (audienceMatch && !analysis.context.includes(audienceMatch[0])) {
        analysis.context = (analysis.context ? analysis.context + '\n' : '') + `Target audience: ${audienceMatch[2].trim()}`;
    }
    
    // Detect topic/domain mentions for context
    const domainKeywords = ['marketing', 'technical', 'business', 'educational', 'creative', 'scientific'];
    for (const domain of domainKeywords) {
        if (lowerInput.includes(domain) && !analysis.context.toLowerCase().includes(domain)) {
            analysis.hasContext = true;
            if (!analysis.context) {
                analysis.context = `Domain: ${domain.charAt(0).toUpperCase() + domain.slice(1)}`;
            }
            break;
        }
    }
    
    // If no specific format detected but it's a writing task, suggest structured format
    if (!analysis.outputFormat && (lowerInput.includes('write') || lowerInput.includes('create') || lowerInput.includes('blog') || lowerInput.includes('article'))) {
        analysis.outputFormat = 'Well-structured and organized';
    }
    
    // If no tone detected, infer from context
    if (!analysis.tone) {
        if (lowerInput.includes('blog') || lowerInput.includes('social media') || lowerInput.includes('casual')) {
            analysis.tone = 'Casual, friendly, and conversational';
        } else if (lowerInput.includes('code') || lowerInput.includes('technical') || lowerInput.includes('function')) {
            analysis.tone = 'Technical and precise with proper terminology';
        } else if (lowerInput.includes('business') || lowerInput.includes('professional') || lowerInput.includes('email')) {
            analysis.tone = 'Professional and business-appropriate';
        }
    }
    
    // Clean up the task - remove redundant words if the input is very simple
    if (analysis.task.length < 50 && !analysis.hasContext) {
        // For very short inputs, use the whole thing as task
        analysis.task = input.trim();
    }
    
    return analysis;
}

function copyPrompt() {
    try {
        const generatedPromptEl = document.getElementById('generatedPrompt');
        if (!generatedPromptEl) {
            alert('Error: Generated prompt not found.');
            return;
        }

        const promptText = generatedPromptEl.textContent;
        if (!promptText || promptText.trim() === '') {
            alert('No prompt to copy. Please generate a prompt first.');
            return;
        }

        // Copy to clipboard
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(promptText).then(() => {
                // Show feedback
                const feedback = document.getElementById('copyFeedback');
                if (feedback) {
                    feedback.textContent = '✓ Copied to clipboard!';
                    feedback.style.display = 'block';

                    setTimeout(() => {
                        feedback.style.display = 'none';
                    }, 3000);
                }
            }).catch(err => {
                console.error('Clipboard error:', err);
                // Fallback: select text for manual copy
                const range = document.createRange();
                range.selectNode(generatedPromptEl);
                window.getSelection().removeAllRanges();
                window.getSelection().addRange(range);
                alert('Failed to copy automatically. Text has been selected - press Ctrl+C to copy.');
            });
        } else {
            // Fallback for browsers without clipboard API
            const range = document.createRange();
            range.selectNode(generatedPromptEl);
            window.getSelection().removeAllRanges();
            window.getSelection().addRange(range);
            alert('Text selected - press Ctrl+C to copy.');
        }
    } catch (error) {
        console.error('Error copying prompt:', error);
        alert('An error occurred while copying. Please select and copy manually.');
    }
}

function resetForm() {
    try {
        const userInputEl = document.getElementById('userInput');
        const outputSectionEl = document.getElementById('outputSection');

        if (userInputEl) {
            userInputEl.value = '';
            userInputEl.focus();
        }

        // Hide output section
        if (outputSectionEl) {
            outputSectionEl.style.display = 'none';
        }

        // Scroll to top
        window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (error) {
        console.error('Error resetting form:', error);
        alert('An error occurred while resetting the form.');
    }
}

// Allow Enter key to generate (Shift+Enter for new line)
document.addEventListener('DOMContentLoaded', function() {
    const userInputEl = document.getElementById('userInput');
    if (userInputEl) {
        userInputEl.addEventListener('keydown', function(e) {
            // Ctrl+Enter or Cmd+Enter to generate
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                generatePrompt();
            }
        });
    }
});
