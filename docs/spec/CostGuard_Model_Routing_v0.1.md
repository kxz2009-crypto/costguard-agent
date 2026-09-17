# CostGuard Model Routing v0.1


# 1. Principle


Different tasks use different models.


No single model handles all workloads.



# 2. Task Routing


## Architecture


Primary:

GPT-5.6


Use:

- system design
- architecture decision
- complex reasoning



## Coding


Primary:

Codex / Grok 4.5


Use:

- implementation
- debugging
- refactoring



## Long Context Analysis


Primary:

Kimi K3


Use:

- large documents
- repository analysis
- specification review



## Batch Processing


Primary:

DeepSeek / Qwen local


Use:

- extraction
- classification
- formatting
- repetitive generation



# 3. Privacy Routing


If task contains:


- private data
- medical data
- internal documents


Prefer local model.



# 4. Scheduling Rules


Interactive window:


Quality first



Batch window:


Cost first



Sensitive task:


Privacy first



# 5. Model Selection Priority


1. Privacy

2. Accuracy

3. Cost

4. Speed
