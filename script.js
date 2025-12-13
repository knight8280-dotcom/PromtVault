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

// Initialize fields on load
document.addEventListener('DOMContentLoaded', function() {
    updateFields();
});
