# Dutch AI Automation Agents

## Multi-Agent AI System for Automation Opportunity Discovery

A five-agent AI automation consulting pipeline designed to discover, research, validate, design, and rank potential AI automation opportunities across Dutch construction-related companies.
## System Architecture

![Dutch AI Automation Agents Architecture](architecture.png)
## 📊 Verified Pipeline Results

The system was executed against a dataset of Dutch construction-related companies and successfully progressed companies through the multi-agent pipeline.

| Pipeline Stage | Result |
|---|---:|
| Companies discovered | **83** |
| Companies researched | **50** |
| Companies validated | **50** |
| Solutions generated | **45** |
| Final opportunities ranked | **45** |

### Pipeline Completion

```text
83 Companies Discovered
          ↓
50 Companies Researched
          ↓
50 Companies Validated
          ↓
45 Solutions Generated
          ↓
45 Final Opportunities Ranked
The system combines web research, LLM-based analysis, structured data, and PostgreSQL to turn a broad business research problem into a prioritized list of actionable automation opportunities.

---

## 🎯 Project Objective

The goal of this project is to automate an early-stage AI consulting workflow:

> **Which companies could benefit from AI automation, what problems could be automated, and which opportunities are worth pursuing first?**

Instead of manually researching companies one by one, the system uses multiple specialized AI agents to move companies through a structured discovery and evaluation pipeline.

---

## 🧠 Five-Agent Architecture

The system consists of five specialized agents.

### 1. Discovery Agent

Identifies Dutch construction-related companies using web search and AI-assisted analysis.

**Responsibilities:**

- Search for relevant Dutch companies
- Collect company information
- Identify company websites and source URLs
- Estimate company size
- Store discovered companies in PostgreSQL
- Prevent duplicate companies

---

### 2. Research Agent

Investigates the companies discovered by Agent 1.

**Responsibilities:**

- Research company activities
- Analyze publicly available information
- Identify operational characteristics
- Collect evidence relevant to potential automation opportunities
- Store structured research results

---

### 3. Validation Agent

Evaluates whether identified opportunities represent legitimate automation opportunities.

**Responsibilities:**

- Analyze research findings
- Determine whether an automation opportunity exists
- Assess potential business value
- Reject weak or unsupported opportunities
- Store validation results

The validation stage acts as a gate in the pipeline. Companies that do not represent credible automation opportunities do not proceed to solution design.

---

### 4. Solution Agent

Transforms validated opportunities into potential AI automation solutions.

**Responsibilities:**

- Identify suitable automation approaches
- Define the proposed solution
- Connect business problems to AI and automation capabilities
- Evaluate potential implementation value
- Store proposed solutions

---

### 5. Final Ranking Agent

Prioritizes the strongest opportunities.

**Responsibilities:**

- Evaluate validated opportunities and proposed solutions
- Score automation opportunities
- Rank opportunities by potential value
- Produce the final prioritized opportunity dataset

---

## 🔄 Pipeline Architecture

```text
                         ┌──────────────────────┐
                         │   Dutch Companies    │
                         └───────────┬──────────┘
                                     │
                                     ▼
                         ┌──────────────────────┐
                         │  1. Discovery Agent  │
                         │                      │
                         │ Find target          │
                         │ companies            │
                         └───────────┬──────────┘
                                     │
                                     ▼
                         ┌──────────────────────┐
                         │   2. Research Agent  │
                         │                      │
                         │ Research companies   │
                         │ and operations       │
                         └───────────┬──────────┘
                                     │
                                     ▼
                         ┌──────────────────────┐
                         │ 3. Validation Agent  │
                         │                      │
                         │ Validate whether     │
                         │ opportunity exists   │
                         └───────────┬──────────┘
                                     │
                         ┌───────────┴───────────┐
                         │                       │
                         ▼                       ▼
                    REJECTED                 VALIDATED
                         │                       │
                         │                       ▼
                         │            ┌──────────────────────┐
                         │            │  4. Solution Agent   │
                         │            │                      │
                         │            │ Design AI /          │
                         │            │ automation solution  │
                         │            └───────────┬──────────┘
                         │                        │
                         │                        ▼
                         │            ┌──────────────────────┐
                         │            │ 5. Final Ranking     │
                         │            │       Agent          │
                         │            │                      │
                         │            │ Score and prioritize │
                         │            │ opportunities        │
                         │            └───────────┬──────────┘
                         │                        │
                         │                        ▼
                         │            ┌──────────────────────┐
                         │            │ Prioritized AI       │
                         │            │ Automation           │
                         │            │ Opportunities        │
                         │            └──────────────────────┘
                         │
                         ▼
                  Validation stops
                  the opportunity