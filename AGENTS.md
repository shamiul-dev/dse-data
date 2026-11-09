# AGENTS.md — Development Guidelines & Coding Standards

This document establishes the architectural principles, coding conventions, database rules, and workflows for **Promise ERP**. All AI agents and developers working in this repository must adhere to these guidelines to ensure consistency, reliability, and maintainability.

---

## 🚨 PRIME DIRECTIVE (TOP PRIORITY)

> [!IMPORTANT]
> **NEVER START CODING OR CHANGING ANYTHING UNTIL THE USER GIVES EXPLICIT PERMISSION WITH CLEAR INSTRUCTIONS.**
>
> - **Analyze & Plan First**: Always investigate, explain findings, and propose solutions or architectural plans before touching any code.
> - **Explicit Approval Required**: Do not write, edit, or delete any project files, configurations, database migrations, routes, or tests without explicit user consent and clear instructions.
> - **Report Changes to Existing Code**: Always report changes made to other people's code.
> - **No Assumptions or Unsolicited Edits**: Never perform proactive or speculative refactoring of unrelated components unless explicitly directed to do so.
> - **Escalate Guideline Conflicts & Blockers**: If following any rule or instruction in `AGENTS.md` causes an error, architectural conflict, test failure, or unexpected problem, **never silently implement a workaround or bypass the rule**. The agent must immediately stop, explicitly point out that adhering to the guideline caused the issue, explain why, and discuss it with the user first before proceeding.

---

## Feature Implementation & Code Consistency Standard

When a change is required to a file to implement or update a feature:

- **Inspect the Target File**: Carefully examine the target file's existing structure, naming conventions, return types, and design patterns before making any modifications.
- **Consult Reference & Sibling Files**: Look at similar files within the same domain or module (e.g., sibling controllers, services, resources, or components) to see how comparable features and workflows are structured.
- **Follow Established Coding Patterns**: Match the architecture, abstraction level, error handling, and query/caching conventions already used across the codebase rather than introducing novel or inconsistent styles.
