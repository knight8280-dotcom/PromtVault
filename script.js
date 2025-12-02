// Store current prompt data globally
let currentPromptData = {
    userInput: '',
    generatedPrompt: ''
};

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

        // Store user input
        currentPromptData.userInput = userInput;

        // Generate structured prompt from simple input
        const generatedPrompt = buildPromptFromInput(userInput);
        currentPromptData.generatedPrompt = generatedPrompt;

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

// Prompt Storage Functions
function getSavedPrompts() {
    try {
        const saved = localStorage.getItem('promptVault_savedPrompts');
        return saved ? JSON.parse(saved) : [];
    } catch (error) {
        console.error('Error loading saved prompts:', error);
        return [];
    }
}

function savePromptsToStorage(prompts) {
    try {
        localStorage.setItem('promptVault_savedPrompts', JSON.stringify(prompts));
    } catch (error) {
        console.error('Error saving prompts:', error);
        alert('Error saving prompt. Your browser may not support local storage.');
    }
}

function showSaveDialog() {
    const saveDialog = document.getElementById('saveDialog');
    const promptNameInput = document.getElementById('promptName');
    
    if (saveDialog && promptNameInput) {
        saveDialog.style.display = 'block';
        promptNameInput.value = '';
        promptNameInput.focus();
    }
}

function hideSaveDialog() {
    const saveDialog = document.getElementById('saveDialog');
    if (saveDialog) {
        saveDialog.style.display = 'none';
    }
}

function savePrompt() {
    try {
        const promptNameEl = document.getElementById('promptName');
        if (!promptNameEl) return;

        const promptName = promptNameEl.value.trim();
        
        if (!promptName) {
            alert('Please enter a name for your prompt!');
            promptNameEl.focus();
            return;
        }

        if (!currentPromptData.generatedPrompt) {
            alert('No prompt to save. Please generate a prompt first.');
            return;
        }

        const savedPrompts = getSavedPrompts();
        
        // Check if name already exists
        const existingIndex = savedPrompts.findIndex(p => p.name.toLowerCase() === promptName.toLowerCase());
        
        const promptToSave = {
            id: existingIndex >= 0 ? savedPrompts[existingIndex].id : Date.now().toString(),
            name: promptName,
            userInput: currentPromptData.userInput,
            generatedPrompt: currentPromptData.generatedPrompt,
            createdAt: existingIndex >= 0 ? savedPrompts[existingIndex].createdAt : new Date().toISOString(),
            updatedAt: new Date().toISOString()
        };

        if (existingIndex >= 0) {
            // Update existing
            savedPrompts[existingIndex] = promptToSave;
        } else {
            // Add new
            savedPrompts.push(promptToSave);
        }

        // Sort by updated date (newest first)
        savedPrompts.sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt));

        savePromptsToStorage(savedPrompts);
        hideSaveDialog();
        displaySavedPrompts();
        
        // Show success feedback
        const feedback = document.getElementById('copyFeedback');
        if (feedback) {
            feedback.textContent = existingIndex >= 0 ? '✓ Prompt updated!' : '✓ Prompt saved!';
            feedback.style.display = 'block';
            setTimeout(() => {
                feedback.style.display = 'none';
            }, 3000);
        }
    } catch (error) {
        console.error('Error saving prompt:', error);
        alert('An error occurred while saving the prompt.');
    }
}

function displaySavedPrompts() {
    const savedPromptsList = document.getElementById('savedPromptsList');
    const emptyState = document.getElementById('emptyState');
    
    if (!savedPromptsList) return;

    const savedPrompts = getSavedPrompts();

    if (savedPrompts.length === 0) {
        if (emptyState) emptyState.style.display = 'block';
        savedPromptsList.innerHTML = '<p class="empty-state">No saved prompts yet. Generate and save your first prompt to get started!</p>';
        return;
    }

    if (emptyState) emptyState.style.display = 'none';

    savedPromptsList.innerHTML = savedPrompts.map(prompt => `
        <div class="saved-prompt-card" data-id="${prompt.id}">
            <div class="saved-prompt-header">
                <h3>${escapeHtml(prompt.name)}</h3>
                <div class="saved-prompt-actions">
                    <button class="btn-icon" onclick="loadPrompt('${prompt.id}')" title="Load">📂</button>
                    <button class="btn-icon" onclick="copySavedPrompt('${prompt.id}')" title="Copy">📋</button>
                    <button class="btn-icon" onclick="deletePrompt('${prompt.id}')" title="Delete">🗑️</button>
                </div>
            </div>
            <div class="saved-prompt-preview">
                <p class="saved-prompt-user-input">${escapeHtml(prompt.userInput.substring(0, 100))}${prompt.userInput.length > 100 ? '...' : ''}</p>
                <div class="saved-prompt-meta">
                    <span>Created: ${formatDate(prompt.createdAt)}</span>
                    ${prompt.updatedAt !== prompt.createdAt ? `<span>Updated: ${formatDate(prompt.updatedAt)}</span>` : ''}
                </div>
            </div>
        </div>
    `).join('');
}

function loadPrompt(id) {
    try {
        const savedPrompts = getSavedPrompts();
        const prompt = savedPrompts.find(p => p.id === id);
        
        if (!prompt) {
            alert('Prompt not found.');
            return;
        }

        // Load into form
        const userInputEl = document.getElementById('userInput');
        if (userInputEl) {
            userInputEl.value = prompt.userInput;
        }

        // Display the generated prompt
        const generatedPromptEl = document.getElementById('generatedPrompt');
        const outputSectionEl = document.getElementById('outputSection');
        
        if (generatedPromptEl && outputSectionEl) {
            generatedPromptEl.textContent = prompt.generatedPrompt;
            outputSectionEl.style.display = 'block';
            currentPromptData = {
                userInput: prompt.userInput,
                generatedPrompt: prompt.generatedPrompt
            };
            outputSectionEl.scrollIntoView({ behavior: 'smooth' });
        }
    } catch (error) {
        console.error('Error loading prompt:', error);
        alert('An error occurred while loading the prompt.');
    }
}

function copySavedPrompt(id) {
    try {
        const savedPrompts = getSavedPrompts();
        const prompt = savedPrompts.find(p => p.id === id);
        
        if (!prompt) {
            alert('Prompt not found.');
            return;
        }

        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(prompt.generatedPrompt).then(() => {
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
                alert('Failed to copy. Please try again.');
            });
        } else {
            alert('Clipboard not available. Please copy manually.');
        }
    } catch (error) {
        console.error('Error copying prompt:', error);
        alert('An error occurred while copying the prompt.');
    }
}

function deletePrompt(id) {
    if (!confirm('Are you sure you want to delete this prompt?')) {
        return;
    }

    try {
        const savedPrompts = getSavedPrompts();
        const filtered = savedPrompts.filter(p => p.id !== id);
        savePromptsToStorage(filtered);
        displaySavedPrompts();
    } catch (error) {
        console.error('Error deleting prompt:', error);
        alert('An error occurred while deleting the prompt.');
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateString) {
    try {
        const date = new Date(dateString);
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (error) {
        return dateString;
    }
}

// Allow Enter key to generate (Ctrl+Enter for new line)
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

    // Load saved prompts on page load
    displaySavedPrompts();

    // Allow Enter key in save dialog to save
    const promptNameInput = document.getElementById('promptName');
    if (promptNameInput) {
        promptNameInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                savePrompt();
            } else if (e.key === 'Escape') {
                e.preventDefault();
                hideSaveDialog();
            }
        });
    }
});
