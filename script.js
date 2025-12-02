// Prompt generation logic
function generatePrompt() {
    try {
        const promptTypeEl = document.getElementById('promptType');
        const mainGoalEl = document.getElementById('mainGoal');
        const contextEl = document.getElementById('context');
        const requirementsEl = document.getElementById('requirements');
        const outputFormatEl = document.getElementById('outputFormat');
        const toneEl = document.getElementById('tone');
        const examplesEl = document.getElementById('examples');
        const avoidEl = document.getElementById('avoid');

        // Check if all required elements exist
        if (!promptTypeEl || !mainGoalEl) {
            console.error('Required form elements not found');
            alert('Error: Form elements not found. Please refresh the page.');
            return;
        }

        const promptType = promptTypeEl.value;
        const mainGoal = mainGoalEl.value.trim();
        const context = contextEl ? contextEl.value.trim() : '';
        const requirements = requirementsEl ? requirementsEl.value.trim() : '';
        const outputFormat = outputFormatEl ? outputFormatEl.value.trim() : '';
        const tone = toneEl ? toneEl.value : '';
        const examples = examplesEl ? examplesEl.value.trim() : '';
        const avoid = avoidEl ? avoidEl.value.trim() : '';

        // Validation
        if (!mainGoal) {
            alert('Please describe what you want to accomplish!');
            return;
        }

        // Build the prompt based on type
        let generatedPrompt = buildPrompt({
            promptType,
            mainGoal,
            context,
            requirements,
            outputFormat,
            tone,
            examples,
            avoid
        });

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

function buildPrompt(data) {
    let prompt = '';

    // Add type-specific introduction
    const typeIntros = {
        general: 'I need your help with the following:',
        creative: 'I need you to help me create creative content:',
        code: 'I need you to help me with code development:',
        analysis: 'I need you to analyze and provide insights on:',
        brainstorm: 'I need you to help me brainstorm ideas for:',
        learning: 'I need you to help me understand and learn about:',
        editing: 'I need you to help me edit and refine:'
    };

    prompt += typeIntros[data.promptType] || typeIntros.general;
    prompt += '\n\n';

    // Main Goal
    prompt += `TASK: ${data.mainGoal}\n\n`;

    // Context
    if (data.context) {
        prompt += `CONTEXT:\n${data.context}\n\n`;
    }

    // Requirements
    if (data.requirements) {
        prompt += `REQUIREMENTS:\n${data.requirements}\n\n`;
    }

    // Output Format
    if (data.outputFormat) {
        prompt += `OUTPUT FORMAT: ${data.outputFormat}\n\n`;
    }

    // Tone
    if (data.tone) {
        const toneDescriptions = {
            professional: 'Professional and business-appropriate',
            casual: 'Casual, friendly, and conversational',
            technical: 'Technical and precise with proper terminology',
            creative: 'Creative, engaging, and imaginative',
            formal: 'Formal and academic',
            concise: 'Concise and to-the-point'
        };
        prompt += `TONE: ${toneDescriptions[data.tone]}\n\n`;
    }

    // Examples
    if (data.examples) {
        prompt += `EXAMPLES OF WHAT I'M LOOKING FOR:\n${data.examples}\n\n`;
    }

    // Avoid
    if (data.avoid) {
        prompt += `PLEASE AVOID:\n${data.avoid}\n\n`;
    }

    // Add type-specific guidance
    const typeGuidance = {
        creative: 'Please be creative and original in your response.',
        code: 'Please include clear comments and follow best practices. Explain your approach.',
        analysis: 'Please provide a thorough analysis with supporting evidence and clear reasoning.',
        brainstorm: 'Please provide multiple diverse ideas with brief explanations for each.',
        learning: 'Please explain concepts clearly with examples, as if teaching someone new to the topic.',
        editing: 'Please provide specific suggestions for improvement and explain why each change would be beneficial.'
    };

    if (typeGuidance[data.promptType]) {
        prompt += `${typeGuidance[data.promptType]}\n\n`;
    }

    // Final touch
    prompt += 'Please provide a comprehensive and well-structured response.';

    return prompt;
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
        // Reset all form fields
        const promptTypeEl = document.getElementById('promptType');
        const mainGoalEl = document.getElementById('mainGoal');
        const contextEl = document.getElementById('context');
        const requirementsEl = document.getElementById('requirements');
        const outputFormatEl = document.getElementById('outputFormat');
        const toneEl = document.getElementById('tone');
        const examplesEl = document.getElementById('examples');
        const avoidEl = document.getElementById('avoid');
        const outputSectionEl = document.getElementById('outputSection');

        if (promptTypeEl) promptTypeEl.value = 'general';
        if (mainGoalEl) mainGoalEl.value = '';
        if (contextEl) contextEl.value = '';
        if (requirementsEl) requirementsEl.value = '';
        if (outputFormatEl) outputFormatEl.value = '';
        if (toneEl) toneEl.value = '';
        if (examplesEl) examplesEl.value = '';
        if (avoidEl) avoidEl.value = '';

        // Hide output section
        if (outputSectionEl) {
            outputSectionEl.style.display = 'none';
        }

        // Update placeholders
        updateFields();

        // Scroll to top
        window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (error) {
        console.error('Error resetting form:', error);
        alert('An error occurred while resetting the form.');
    }
}

function updateFields() {
    // Update placeholders based on prompt type
    const promptType = document.getElementById('promptType');
    if (!promptType) return;
    
    const type = promptType.value;
    const mainGoal = document.getElementById('mainGoal');
    const context = document.getElementById('context');

    if (!mainGoal || !context) return;

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

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    const promptType = document.getElementById('promptType');
    if (promptType) {
        // Set initial placeholders
        updateFields();
        
        // Add event listener for changes
        promptType.addEventListener('change', updateFields);
    }
});
