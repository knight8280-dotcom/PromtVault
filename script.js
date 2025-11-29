// Prompt generation logic
function generatePrompt() {
    const promptType = document.getElementById('promptType').value;
    const mainGoal = document.getElementById('mainGoal').value.trim();
    const context = document.getElementById('context').value.trim();
    const requirements = document.getElementById('requirements').value.trim();
    const outputFormat = document.getElementById('outputFormat').value.trim();
    const tone = document.getElementById('tone').value;
    const examples = document.getElementById('examples').value.trim();
    const avoid = document.getElementById('avoid').value.trim();

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
    document.getElementById('generatedPrompt').textContent = generatedPrompt;
    document.getElementById('outputSection').style.display = 'block';
    document.getElementById('outputSection').scrollIntoView({ behavior: 'smooth' });
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

    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function updateFields() {
    // This function can be extended to show/hide fields based on prompt type
    // For now, it's a placeholder for future enhancements
    const promptType = document.getElementById('promptType').value;

    // You can add logic here to show different fields or provide suggestions
    // based on the selected prompt type
}

// Add some helpful placeholder updates based on prompt type
document.getElementById('promptType').addEventListener('change', function() {
    const type = this.value;
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
});
