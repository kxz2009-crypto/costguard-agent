
Hermes Multi Model Routing v0.3
1. Purpose

Define automatic model selection strategy.

2. Model Roles
GLM-5.3-Flash

Role:

DevOS controller

Best for:

planning
routing
coordination
qwen3.8:27b

Role:

Coding worker

Best for:

implementation
tests
refactoring
GPT-5.6

Role:

Senior reasoning and review

Best for:

architecture
complex analysis
validation
Kimi K3

Role:

Long context reasoning

Best for:

large documents
planning
DeepSeek

Role:

Batch reasoning

Best for:

large scale analysis
cost efficient tasks
Codex

Role:

Emergency engineering

Use:

difficult debugging
architecture rescue
3. Routing Matrix
Task	Model
orchestration	GLM
coding	Qwen
review	GPT-5.6
long planning	K3
batch analysis	DeepSeek
troubleshooting	Codex
Principle

Use the cheapest capable model.

Escalate only when necessary.
