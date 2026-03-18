import os

dirs = [
    '.copilot-tracking/research',
    '.copilot-tracking/plans',
    '.copilot-tracking/details',
    '.copilot-tracking/prompts',
    '.copilot-tracking/changes'
]

for d in dirs:
    os.makedirs(d, exist_ok=True)

research_content = '''<!-- markdownlint-disable-file -->

# Task Research Notes: Setup Claude Code Segmented Agents in GitHub Copilot

## Research Executed

### External Research: System Prompt Alternatives
- **Aider**: Excellent for direct minimal terminal edits, highly precise but less conversational.
- **Roo Code (Roo-Cline)**: Exceptional open-source architecture for segmented routing (Architect vs Coder vs Explorer). 
- **Claude Code**: The official Anthropic offering. It inherently uses sub-agents ("Explore" and "Plan"). It remains the definitive state-of-the-art for software engineering with Claude models.
- **Decision**: We will proceed with Claude Code's Option 2 (Segmented Sub-Agents: Explore, Plan, Main), as requested, because it perfectly maps to the official Anthropic standard and fits well into Copilot .agent.md definitions.

### External References
- #githubRepo:"Piebald-AI/claude-code-system-prompts"
- #fetch:https://github.com/Piebald-AI/claude-code-system-prompts

### Standards References
- copilot-skill:/agent-customization/SKILL.md - Copilot customization standards.

## Recommended Approach
We will create three segmented Copilot agents in c:/Users/JOSAPHAT/AppData/Roaming/Code/User/prompts/:
1. \claude-explore.agent.md\ - Specialized for codebase exploration without making destructive changes.
2. \claude-plan.agent.md\ - Specialized for creating actionable task plans.
3. \claude-code.agent.md\ - The main coordinator CLI persona that interfaces with the user and executes.

These files will adopt the standard Copilot YAML frontmatter.
'''

plan_content = '''---
applyTo: ".copilot-tracking/changes/20260318-claude-segmented-agents-changes.md"
---

<!-- markdownlint-disable-file -->

# Task Checklist: Setup Claude Code Segmented Agents

## Overview
Implement the official Claude Code CLI system prompts as modular, segmented GitHub Copilot agents (Explore, Plan, Main).

## Objectives
- Create a dedicated Explore agent for safe codebase navigation.
- Create a dedicated Plan agent for robust problem breakdown.
- Create the Main Claude Code agent as the primary persona.

## Research Summary

### External References
- #file:../research/20260318-claude-segmented-agents-research.md - Analysis indicating Claude Code segmented architecture is optimal.

### Standards References
- #file:c:/Users/JOSAPHAT/AppData/Roaming/Code/User/prompts/memory-bank.instructions.md - Agent guidelines.

## Implementation Checklist

### [ ] Phase 1: Explorer and Planner Agents
- [ ] Task 1.1: Create Explorer Agent
  - Details: .copilot-tracking/details/20260318-claude-segmented-agents-details.md (Lines 11-20)
- [ ] Task 1.2: Create Planner Agent
  - Details: .copilot-tracking/details/20260318-claude-segmented-agents-details.md (Lines 22-31)

### [ ] Phase 2: Main Agent Setup
- [ ] Task 2.1: Create Main Claude Code Agent
  - Details: .copilot-tracking/details/20260318-claude-segmented-agents-details.md (Lines 35-43)

## Dependencies
- GitHub Copilot specific .agent.md frontmatter formatting requirements.
- Existing user prompt path: c:/Users/JOSAPHAT/AppData/Roaming/Code/User/prompts/

## Success Criteria
- Three new .agent.md files successfully created in the user prompts directory.
- Properly separated contexts mapped directly analogous to the Claude Code CLI's internal architecture.
'''

details_content = '''<!-- markdownlint-disable-file -->

# Task Details: Setup Claude Code Segmented Agents

## Research Reference
**Source Research**: #file:../research/20260318-claude-segmented-agents-research.md

## Phase 1: Explorer and Planner Agents

### Task 1.1: Create Explorer Agent
Create claude-explore.agent.md incorporating Anthropic's Explore sub-agent prompt.

- **Files**:
  - c:/Users/JOSAPHAT/AppData/Roaming/Code/User/prompts/claude-explore.agent.md - New file for the Explore sub-agent.
- **Success**:
  - Valid YAML frontmatter containing 
ame and description triggering the Explore persona.
- **Research References**:
  - #file:../research/20260318-claude-segmented-agents-research.md (Lines 8-15) - Segmented design justification.
- **Dependencies**: None.

### Task 1.2: Create Planner Agent
Create claude-plan.agent.md incorporating Anthropic's Plan sub-agent prompt.

- **Files**:
  - c:/Users/JOSAPHAT/AppData/Roaming/Code/User/prompts/claude-plan.agent.md - New file for the Plan sub-agent.
- **Success**:
  - Valid YAML frontmatter for planning tasks.
- **Research References**:
  - #file:../research/20260318-claude-segmented-agents-research.md (Lines 24-28) - Agent logic mapping.
- **Dependencies**: None.

## Phase 2: Main Agent Setup

### Task 2.1: Create Main Claude Code Agent
Rename/adapt existing draft or create fresh claude-code.agent.md with the main coordinator CLI prompt.

- **Files**:
  - c:/Users/JOSAPHAT/AppData/Roaming/Code/User/prompts/claude-code.agent.md - Core integration file.
- **Success**:
  - Includes CLI tone instructions and task routing guidelines.
- **Research References**:
  - #file:../research/20260318-claude-segmented-agents-research.md (Lines 26-28) - Coordinator logic.
- **Dependencies**: Phase 1 completion.

## Dependencies
- User prompts directory access.

## Success Criteria
- All three agents exist, contain accurate YAML, and encapsulate their respective system prompt constraints.
'''

prompt_content = '''---
mode: agent
model: Claude Sonnet 4
---

<!-- markdownlint-disable-file -->

# Implementation Prompt: Setup Claude Code Segmented Agents

## Implementation Instructions

### Step 1: Create Changes Tracking File
You WILL create 20260318-claude-segmented-agents-changes.md in #file:../changes/ if it does not exist.

### Step 2: Execute Implementation
You WILL follow #file:../../.github/instructions/task-implementation.instructions.md
You WILL systematically implement #file:../plans/20260318-claude-segmented-agents-plan.instructions.md task-by-task.
Ensure .agent.md files are created in c:/Users/JOSAPHAT/AppData/Roaming/Code/User/prompts/.

**CRITICAL**: If  uid{input:phaseStop:true} is true, you WILL stop after each Phase for user review.
**CRITICAL**: If  uid{input:taskStop:false} is true, you WILL stop after each Task for user review.

### Step 3: Cleanup
When ALL Phases are checked off ([x]) and completed you WILL do the following:
1. Provide a markdown style link and a summary of all changes from #file:../changes/20260318-claude-segmented-agents-changes.md to the user.
2. Provide markdown style links to the plan, details, and research tracking documents.
3. **MANDATORY**: You WILL attempt to delete .copilot-tracking/prompts/implement-claude-segmented-agents.prompt.md.

## Success Criteria
- [ ] Changes tracking file created
- [ ] All plan items implemented with working code (three .agent.md files)
- [ ] Project conventions followed
- [ ] Changes file updated continuously
'''

with open('.copilot-tracking/research/20260318-claude-segmented-agents-research.md', 'w', encoding='utf-8') as f:
    f.write(research_content)

with open('.copilot-tracking/plans/20260318-claude-segmented-agents-plan.instructions.md', 'w', encoding='utf-8') as f:
    f.write(plan_content)

with open('.copilot-tracking/details/20260318-claude-segmented-agents-details.md', 'w', encoding='utf-8') as f:
    f.write(details_content)

with open('.copilot-tracking/prompts/implement-claude-segmented-agents.prompt.md', 'w', encoding='utf-8') as f:
    f.write(prompt_content.replace(' uid', '$'))

print("Planning files created successfully.")
