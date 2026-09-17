# Hermes Model Routing v0.2


## Objective

Optimize model usage according to task value and cost.


# Default Routing


## Planning / Analysis

Priority:

1. GLM-5.3-Flash

2. GLM-5.3

3. Kimi K3

4. GPT-5.6

5. DeepSeek



## Engineering

Priority:

1. Codex

2. GPT-5.6



## Long Context Review

Priority:

1. Kimi K3

2. GPT-5.6



# Routing Rules


## Low value tasks

Examples:

- document formatting
- summary
- extraction
- planning

Use:

GLM Flash



## Medium tasks

Examples:

- architecture review
- technical analysis

Use:

GLM-5.3
Kimi K3



## High value tasks

Examples:

- production code modification
- difficult debugging

Use:

Codex



# Cost Principle


Do not consume premium models for low complexity tasks.


