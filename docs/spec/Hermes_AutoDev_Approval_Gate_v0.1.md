
Hermes AutoDev Approval Gate v0.1
1. Purpose

Define when Hermes can execute automatically and when human approval is required.

2. Automatic Allowed

Low risk:

documentation
tests
formatting
small bug fixes
non-breaking refactoring
3. Reviewer Required

Medium risk:

API changes
dependency updates
architecture changes
database changes
4. Human Approval Required

High risk:

production configuration
security permission
payment system
destructive operation
data deletion
Principle

Automation increases speed.

Approval preserves safety.
