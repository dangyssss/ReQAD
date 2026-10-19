# ReQAD — System Design and Implementation

## 1. System Overview

**ReQAD (Requirement-Adaptive Quality Assurance and Diagnosis for Low-Code LLM Agents)** is an automated testing and diagnosis framework for low-code/no-code (LCNC) LLM agents. Given a natural-language description of a target agent and a developer’s testing request, ReQAD adapts its testing focus to the specified requirements and supports automated test planning, test execution, and result diagnosis. The framework aims to help end-user developers conduct systematic testing without extensive software testing expertise.

The system comprises three core components:

- **Planner Agent:** Interprets testing requirements, selects relevant quality dimensions, and generates targeted test plans and test cases.
- **Execution Engine:** Executes test cases through the Coze API and collects agent responses, tool-call traces, and runtime metrics.
- **Diagnosis Agent:** Evaluates test outcomes against the testing objectives and produces diagnostic reports with improvement suggestions.

In addition, the **Self-Evolving Rubric** serves as a cross-cutting rule mechanism that provides evaluation criteria for test-plan review and quality assessment and supports rule updates based on developer feedback.

ReQAD first generates a requirement-adapted test plan for developer review. After the developer confirms the plan, the system executes the selected tests and produces a diagnostic report in Markdown format.

## 2. Planner Agent

The Planner Agent translates a target agent’s natural-language description and the developer’s testing requirements into a structured, requirement-adapted test plan.

### 2.1 Requirement Classification and Testing Strategies

The system defines ten core quality dimensions: factual accuracy, logical reasoning, domain expertise, tool-use correctness, input robustness, adversarial robustness, safety and ethics, interaction quality, resource efficiency, and concurrency performance.

The Planner uses an LLM to analyze the target agent's functionality and the testing request, mapping the testing intent to an appropriate quality dimension. When a requirement falls outside the predefined dimensions, the system provides a **Custom Strategy** for generating tests specific to that requirement.

Different dimensions are associated with corresponding testing strategies and prompt templates so that generated tests target the intended quality attributes.

### 2.2 Test Plan and Test Case Generation

Based on the selected quality dimension, the Planner constructs a prompt incorporating the agent description, user request, and testing strategy. It generates two main outputs:

- **Testing Plan:** A human-readable Markdown document describing testing directions, scenarios, and expected behavior.
- **Test Cases:** Structured JSON records containing a case identifier, testing category, and test input.

Reference responses in the test plan provide semantic guidance for subsequent diagnosis; the target agent's outputs are not required to match them verbatim.

### 2.3 Test Plan Review

To check whether a generated plan aligns with its testing objectives, the Planner employs a rubric-based checklist audit.

Using the baseline rules, target agent description, testing request, and generated plan, the system dynamically constructs a checklist containing weighted scoring items and critical constraints.

An LLM then evaluates the plan against this checklist. The current acceptance criteria require a weighted total score of at least **70** and a score of at least **90** for each critical checklist item.

Plans that do not pass the audit are regenerated using the review feedback, with up to **three attempts**.

Relevant implementation is located in `PlannerAgent.py`, including `TEST_DEFINITIONS`, `_strategy_prompt_template`, and `PlannerAgent._double_audit`.

## 3. Execution Engine

The Execution Engine submits generated test cases to the target agent deployed on Coze and collects the resulting execution data.

The `CozeAgent` component in `coze_chat.py` encapsulates communication with the Coze API, including streaming response handling and a non-streaming fallback when needed.

The execution stage collects three principal categories of information:

- **Agent Responses:** Test inputs and the target agent's actual responses.
- **Tool Traces:** Available tool names, invocation results, and associated execution records.
- **Runtime Metrics:** Observable measurements such as response latency, token usage, and throughput.

Regular test cases are processed sequentially, while consistency sampling and concurrency-performance testing use their respective asynchronous request mechanisms.

These observations provide evidence for the Diagnosis Agent. The availability of individual measurements depends on the information returned by the Coze API.

The execution adapter is implemented primarily in `coze_chat.py`, while execution and diagnosis are coordinated in `DiagnosisAgent.py`.

## 4. Diagnosis Agent

The Diagnosis Agent analyzes collected responses and runtime observations, applies assessments suited to the selected quality dimensions, and generates a diagnostic report linked to the testing objectives.

### 4.1 Expert Persona Mapping

The system associates quality dimensions with corresponding expert roles and evaluation prompts.

For example, logical reasoning tests use a reasoning-audit expert persona, domain-expertise tests use a domain-expert persona, and tool-use tests use a tool-and-automation evaluation expert persona.

These expert roles are defined through prompts and rely on the underlying LLM for judgment; they are not separately trained specialist models.

The role mappings, evaluation criteria, and output structures are specified in `DiagnosisAgent._setup_strategies` and `EVAL_PROMPTS`.

### 4.2 Quality Assessment Mechanisms

Diagnosis uses different assessment approaches according to the testing category:

- **General quality assessment:** Examines the actual response, testing objective, and available execution evidence, applying a dimension-specific expert prompt to produce a structured judgment and explanation.
- **Response consistency assessment:** Collects additional responses to the same test input and compares the outputs to assess consistency. The current implementation performs **three additional samples**.
- **Concurrency performance assessment:** Issues concurrent requests in batches and calculates performance measures such as response latency, throughput, and request error rate.

This design combines the LLM's ability to make semantic judgments with observable runtime data, allowing each quality dimension to be assessed using relevant evidence.

### 4.3 Diagnostic Report Generation

The Diagnosis Agent consolidates assessments across tested dimensions into a Markdown diagnostic report.

The report is intended to present test outcomes, quality assessments, problem analyses, and corresponding improvement suggestions. Its purpose is to help developers understand how their agents performed and identify possible directions for refinement.

The main evaluation logic, expert prompts, and report-generation procedures are implemented in `DiagnosisAgent.py`.

## 5. Self-Evolving Rubric

The Self-Evolving Rubric provides a shared source of rules for test planning and diagnosis and supports revisions based on developer feedback.

### 5.1 Baseline Rules and Their Use

The rules are stored in `selfevolve_rubric.py` as a Python dictionary organizing checklist entries by quality dimension.

The system can convert these rules into natural-language text and incorporate them into relevant prompts.

During planning, the rubric is used to construct the checklist for auditing generated test plans. During diagnosis, rubric-related rules and review mechanisms provide criteria for quality assessment.

### 5.2 Feedback-Driven Rule Updates

Developers can provide natural-language feedback suggesting changes to existing evaluation rules.

The system uses an LLM to generate revised rule content from the current rules and developer feedback, then updates the corresponding rule file through the rule-management component.

The rule manager also provides version backups, rollback to earlier versions, and restoration of the initial rules.

This mechanism updates rule text based on natural-language feedback; it does not retrain the underlying language model.

### 5.3 Rule Changes and Additional Review

The system detects rubric updates by checking whether the rule file has changed.

When a change is detected, the diagnosis workflow provides an additional **Shadow Review** path that compares the primary and supplementary assessments to help examine the impact of rule changes on diagnostic results.

Rule definitions reside in `selfevolve_rubric.py`, while rule updates and version management are implemented in `selfevolve_manager.py`.

## 6. Implementation References

The following table maps the main system components to their corresponding source files, allowing readers to locate the concrete implementation described above.

| Component | Main source files | Responsibilities |
| --- | --- | --- |
| Main Controller | `main.py` | Application entry point, workflow coordination, developer confirmation, and report output. |
| Planner Agent | `PlannerAgent.py` | Requirement classification, testing strategies, case generation, and plan auditing. |
| Execution Engine | `coze_chat.py`, `DiagnosisAgent.py` | Coze API communication, test execution, and collection of responses and runtime data. |
| Diagnosis Agent | `DiagnosisAgent.py` | Expert persona mapping, dimension-specific assessment, and diagnostic report generation. |
| Self-Evolving Rubric | `selfevolve_rubric.py`, `selfevolve_manager.py` | Rule definitions, feedback-driven updates, and version management. |

Complete prompt templates and rule definitions remain in their respective source files, enabling readers to inspect the criteria and generation strategies actually used by the system.

This document complements the architectural description in the ReQAD paper and provides a concise technical reference for understanding how ReQAD is implemented.
