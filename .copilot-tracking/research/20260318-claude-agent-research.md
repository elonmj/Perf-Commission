<!-- markdownlint-disable-file -->

# Task Research Notes: Setup Claude Code Agent in GitHub Copilot

## Research Executed

### File Analysis

- c:\Users\JOSAPHAT\AppData\Roaming\Code\User\prompts\claude-code-system.chatmode.md
  - Existing prompt draft found, missing GitHub Copilot required YAML frontmatter and standard `.agent.md` conventions.

### Code Search Results

- None
  - N/A

### External Research

- #githubRepo:"Piebald-AI/claude-code-system-prompts"
  - Found extensive collection of system prompts, utilities, and agent instructions meant for direct tool usage, bash commands, etc.
- #fetch:https://github.com/Piebald-AI/claude-code-system-prompts
  - Confirmed repository provides segmented system prompts for "Claude Code" (e.g. Explore agent, Plan agent, Tool descriptions). To port to Copilot, these must be consolidated into Copilot's `---` YAML block and markdown body architecture.

### Project Conventions

- Standards referenced: `copilot-skill:/agent-customization/SKILL.md`
- Instructions followed: Task Researcher Instructions

## Key Discoveries

### Project Structure

User data directory `c:\Users\JOSAPHAT\AppData\Roaming\Code\User\prompts\` contains a mix of `.chatmode.md`, `.agent.md`, and `.instructions.md`. `claude-code-system.chatmode.md` exists but isn't formalized as an active agent with proper Copilot frontmatter.

### Implementation Patterns

To build a GitHub Copilot custom agent based on Claude Code System Prompts:
1. File format must be `.agent.md`
2. Needs proper YAML frontmatter (`name`, `description`).
3. Must consolidate the behavior (Task management, TodoWrite, Bash tools routing) into text that Copilot's LLM engine understands.

### Complete Examples

```markdown
---
name: claude-code
description: "Use when: User wants to invoke the full Claude Code CLI-like developer experience."
---
# Tone and style
You are Claude Code, Anthropic's official CLI for Claude.
You should be concise, direct, and to the point.
(Include the rest of the claude-code-system.chatmode.md body here seamlessly)
```

### Technical Requirements

Copilot agents require distinct scoping. The Claude Code repo maps out `Explore`, `Plan`, and general `Claude CLI` sub-agents. 

## Recommended Approach

Convert the current `claude-code-system.chatmode.md` into `claude-code.agent.md` within your `c:\Users\JOSAPHAT\AppData\Roaming\Code\User\prompts\` directory. Add the required frontmatter so GitHub Copilot correctly indexes it. Incorporate the sub-agent structures (Plan vs Explore) as separate specialized `.agent.md` files or rely entirely on this monolithic one to handle requests.

## Implementation Guidance

- **Objectives**: Enable Claude Code behavioral prompting natively within VS Code's GitHub Copilot.
- **Key Tasks**: 
  1. Rename or create `claude-code.agent.md` in user prompts.
  2. Implement proper YAML frontmatter.
  3. Consolidate the system prompts from the repo into the file body.
- **Dependencies**: Copilot Custom Agents feature.
- **Success Criteria**: Typing `@claude-code` or `/claude-code` uses this structured prompt. 
