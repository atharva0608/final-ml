# LLM Session Start Prompt Template

## Purpose

This is the **standardized prompt template** to use when starting a new LLM session. It ensures the LLM:
1. Pulls latest changes from GitHub
2. Reads the master navigation system
3. Checks for new problems
4. Follows the governance structure
5. Uses the comprehensive documentation system

---

## 📋 Copy This Prompt Template

Copy the prompt below and paste it into your LLM session. Replace `[BRANCH_NAME]` with your actual branch name if different from the default.

---

### Standard Session Start Prompt:

```
You are working on the spot optimizer platform codebase. This session should follow these steps:

## Step 1: Pull Latest Changes
First, pull the latest changes from the repository:
- Fetch and pull from origin/claude/aws-dual-mode-connectivity-fvlS3
- If there are conflicts, show them and ask for guidance
- Confirm the working directory is clean

## Step 2: Read Master Navigation
Read the master navigation file to understand the complete system:
- Read /info.md (master navigation - START HERE)
- This file contains the complete system overview, architecture, and navigation guide

## Step 3: Check for New Problems
Check if there are any new problems to fix:
- Read /problems/new_problem
- Look in the section "PASTE YOUR PROBLEMS HERE" (bottom of file)
- If problems exist, assign Problem IDs and begin investigation

## Step 4: Follow Governance Structure
Always follow the mandatory protocols:
- Read /instructions/master_rules.md (mandatory workflow)
- Check /progress/regression_guard.md (protected zones)
- Review /progress/fixed_issues_log.md (don't break recent fixes)
- Consult /index/feature_index.md (avoid duplication)

## Step 5: Execute Work
Based on problems found or tasks requested:
- Read relevant module info.md files for context
- Make changes following the documented workflows
- Update all cross-references and documentation
- Commit with proper format and Problem IDs

## Step 6: Update Documentation
After making changes:
- Update affected module info.md files
- Update /index/recent_changes.md
- Update /progress/fixed_issues_log.md (if fixing a bug)
- Remove fixed problems from /problems/new_problem

## Step 7: Commit and Push
- Commit with clear message including Problem IDs
- Push to origin/claude/aws-dual-mode-connectivity-fvlS3

Begin by executing Step 1.
```

---

## 🚀 Quick Start Prompt (Shorter Version)

If you just want to fix a problem quickly, use this shorter version:

```
Pull latest from origin/claude/aws-dual-mode-connectivity-fvlS3, then:

1. Read /info.md (master navigation)
2. Read /problems/new_problem (check for new problems in "PASTE YOUR PROBLEMS HERE" section)
3. Read /instructions/master_rules.md (mandatory protocols)
4. Fix any problems found following the documented workflows
5. Update all documentation and commit with Problem IDs

Start now.
```

---

## 🎯 Problem-Specific Prompt

If you've already added a problem to `/problems/new_problem`, use this:

```
I've added a new problem to /problems/new_problem (in the "PASTE YOUR PROBLEMS HERE" section).

Please:
1. Pull latest changes from origin/claude/aws-dual-mode-connectivity-fvlS3
2. Read /info.md for system navigation
3. Read /problems/new_problem and process the new problem I added
4. Follow /instructions/fix_protocol.md to investigate and fix
5. Update all documentation and commit

The problem details are in /problems/new_problem at the bottom. Start by pulling latest changes.
```

---

## 🔧 Maintenance Session Prompt

For documentation updates or enhancements without specific problems:

```
This is a documentation enhancement session.

1. Pull latest from origin/claude/aws-dual-mode-connectivity-fvlS3
2. Read /info.md (master navigation)
3. Read /index/info_md_dependency_map.md (see what needs enhancement)
4. Continue enhancing remaining modules following the comprehensive standard:
   - Priority 1: /backend/pipelines/info.md, /backend/auth/info.md
   - Priority 2: /frontend/src/services/info.md, /frontend/src/context/info.md
   - Use existing comprehensive modules as templates (500+ lines, complete flows)
5. Commit and push when done

Start with pulling latest changes.
```

---

## 📝 Custom Work Prompt Template

For specific tasks you want to assign:

```
Pull latest from origin/claude/aws-dual-mode-connectivity-fvlS3, then:

1. Read /info.md (master navigation) to understand the system
2. Read /instructions/master_rules.md (mandatory protocols)
3. Read /index/feature_index.md (check for existing functionality)

Task: [Describe your specific task here]

Requirements:
- [Specific requirement 1]
- [Specific requirement 2]
- [etc.]

Before making changes:
- Check /progress/regression_guard.md for protected zones
- Read relevant module info.md files for context
- Check /index/dependency_index.md for impact analysis

After making changes:
- Update all affected module info.md files
- Update /index/recent_changes.md
- Commit with clear message

Start now.
```

---

## 🎓 Examples

### Example 1: Fixing a Dashboard Bug

```
I've added a problem about the dashboard loading slowly to /problems/new_problem.

Pull latest from origin/claude/aws-dual-mode-connectivity-fvlS3, then:
1. Read /info.md for system navigation
2. Read /problems/new_problem (check "PASTE YOUR PROBLEMS HERE" section)
3. Process and fix the dashboard performance issue
4. Follow the bug fix protocol from /instructions/fix_protocol.md
5. Update documentation and commit

Start now.
```

### Example 2: Adding a New Feature

```
Pull latest from origin/claude/aws-dual-mode-connectivity-fvlS3, then:

1. Read /info.md (master navigation)
2. Read /instructions/master_rules.md (mandatory workflow)
3. Check /index/feature_index.md (ensure not duplicate)
4. Read /backend/api/info.md and /frontend/src/components/info.md (understand existing patterns)

Task: Add a new API endpoint to export cost data as CSV

Requirements:
- Endpoint: GET /client/costs/export?format=csv
- Should export last 30 days of cost data
- Follow existing API patterns from /backend/api/
- Update frontend to add "Export CSV" button

After implementation:
- Update /backend/api/info.md with new endpoint documentation
- Update /frontend/src/components/info.md with new button
- Update /index/feature_index.md with new feature
- Commit and push

Start now.
```

### Example 3: Continue Documentation Work

```
Pull latest from origin/claude/aws-dual-mode-connectivity-fvlS3.

This is a continuation of the comprehensive documentation project.

1. Read /info.md (master navigation)
2. Read /index/info_md_dependency_map.md (see status and priorities)
3. Continue enhancing modules following Priority 1:
   - Next: /backend/pipelines/info.md (3 optimizer types: LINEAR/CLUSTER/KUBERNETES)
   - Use /backend/workers/info.md as template (764 lines, complete flows)
   - Document all functions with line numbers
   - Map dependencies to database, APIs, frontend
   - Include performance benchmarks
4. Commit when done, then move to next priority module

Start now.
```

---

## 💡 Pro Tips

### Always Include These Elements:

1. **"Pull latest"** - Ensures you have current code
2. **"Read /info.md"** - Master navigation first
3. **"Read /problems/new_problem"** - Check for issues
4. **"Follow /instructions/master_rules.md"** - Mandatory protocols
5. **"Commit and push"** - Save your work

### Customize As Needed:

- Add specific module paths if you know what needs work
- Include specific requirements or constraints
- Reference existing patterns to follow
- Specify branch name if different from default

### For Best Results:

- Be specific about what you want
- Reference existing comprehensive modules as examples
- Ask for documentation updates after code changes
- Request cross-reference validation

---

## 🔗 Related Files

- **Master Navigation**: `/info.md`
- **Mandatory Rules**: `/instructions/master_rules.md`
- **Bug Fix Protocol**: `/instructions/fix_protocol.md`
- **Feature Index**: `/index/feature_index.md`
- **Dependency Map**: `/index/info_md_dependency_map.md`
- **Problem Intake**: `/problems/new_problem`

---

## 📊 Branch Information

**Current Branch**: `claude/aws-dual-mode-connectivity-fvlS3`
**Remote**: `origin/claude/aws-dual-mode-connectivity-fvlS3`

If using a different branch, replace in prompts above.

---

_Last Updated: 2025-12-25_
_Use these prompts to ensure consistent LLM session behavior_
_All prompts follow the LLM memory system and governance structure_
