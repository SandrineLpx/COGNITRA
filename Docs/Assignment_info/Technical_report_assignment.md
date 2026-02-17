# MSIS 549 — Technical Report Assignment
## Why This Assignment Matters
In the modern workplace, the ability to rapidly prototype an AI-powered solution is only half the job. The other half — and often the more valuable half — is communicating what you built clearly enough that others can understand it, evaluate it, and rebuild it at production quality.

This is exactly what product managers, technical leads, and entrepreneurial prototypers do every day: they build a working proof of concept, then write the documentation that lets an engineering team take it from prototype to product. The report you're writing here is that document. Imagine you've just built a quick but functional prototype of your tool. Now you need to hand it off to a team of engineers who have never seen it. Your report should give them everything they need: the problem context, the design rationale, the technical details, how you know it works, and where it falls short. If your report is clear enough that a capable engineer could rebuild your system from scratch — without talking to you — you've done it right.

This is a skill that will serve you throughout your career, whether you end up in product management, consulting, data science, or founding your own company. Treat this assignment as practice for that real-world handoff.

## Overview
You will submit a comprehensive technical report documenting your individual course project. This report communicates the complex technical work behind your AI-powered solution clearly and professionally.

Your report should tell the full story: the problem you identified, how you designed and built your solution, how well it works, and what you learned along the way. Write it as a replicable technical handoff — someone who has never seen your tool should be able to understand your approach, evaluate your decisions, and follow your steps to rebuild it.

## Format Requirements
Requirement	Details
Length	6–12 pages (excluding appendices)
Format	PDF, 12pt font, single-spaced, 1-inch margins
Submission	One report per student via Canvas
Deadline	Refer to the course schedule on the syllabus
Important: Include a link to your demo walkthrough video in your PDF report (see the separate Demo Recording assignment).

## Report Structure
Your report should follow this structure. Use it as a checklist to make sure you cover everything.

### 1. Student Information
Your name
A brief description of what you individually built, the tools you used, and the skills you developed
### 2. Executive Summary (1 page)
A concise overview of the problem, your solution, and key findings. Write this last — it should stand on its own as a snapshot of your entire project.

### 3. Main Content
#### Business Problem
Clearly describe the real-world problem or pain point you are addressing. Explain the current status quo and why an AI-powered solution is a promising approach. Motivate why this problem matters and who benefits from solving it.

#### Solution Approach & Design Process
Explain your overall solution strategy. This is where an engineer reading your handoff will decide whether your approach makes sense — so cover the design decisions you made: what approaches did you consider, and why did you choose the one you did? If you iterated on your design, describe what changed and why. Include diagrams or screenshots of your system architecture where helpful.

#### Data & Methodology
Describe the data you used (if applicable) and your technical methodology. How did you process or prepare your data? What models, APIs, or AI tools did you employ? Justify your choices.

#### Technical Implementation
This is the core of your handoff. Provide enough detail that an engineer could rebuild your system without needing to ask you questions. Document your key prompts, workflows, agent configurations, or code logic. Describe at least one meaningful iteration: what you changed, why, and whether it improved performance. Be transparent about the building process, including bottlenecks, frustrations, and workarounds — these are exactly the things a rebuilding team needs to know to avoid the same pitfalls.

Tips from past students: Include screenshots, code snippets, and workflow diagrams. The more transparent and detailed you are about your process, the stronger this section will be.

`document this in the technical report in solution approach and technical implementation as I started this project writting skill.md and references files in .md. And as i was nuilding my tool and making iteration with AI and the scripts, the .md were not used. then this is when this chat happened. Explained it with enough details that it is clear to an engneer reading it, and understand why that approach makes sense. Cover the design decisions that what made: what approaches was considered, and why this choice ? As the design has been iterated, describe what changed and why. Include diagrams and placeholder for screenshots of the system architecture where helpful. Describe at least one meaningful iteration: what was changed, why, and whether it improved performance. Be transparent about the building process, including bottlenecks, frustrations, and workarounds `


#### Results & Evaluation
Present your results clearly. How did you evaluate whether your tool works well? Define your success criteria and metrics (e.g., accuracy, time saved, user satisfaction, task completion rate). Include at least 2–3 test cases showing your system in action, and discuss what you observed — including failures or edge cases. Refer to the benchmarking guidance below for more detail.

#### Limitations & Future Work
Be honest about what your solution does not do well. What are its failure modes? What would you improve with more time? In a real handoff, this section is gold — it tells the engineering team where the prototype cuts corners and where they should invest effort to make the solution production-ready. This section demonstrates maturity and critical thinking.

#### Ethical Considerations
Discuss any ethical implications of your solution: potential biases, privacy concerns, misuse risks, fairness, or societal impacts. How did you mitigate these?

### 4. References & Code
Citations for any sources, papers, or tools referenced
Link to your project repository (e.g., GitHub)
Link to your demo walkthrough video
Benchmarking Guidance
A strong evaluation is what separates a good report from an excellent one. Your benchmark should include:

- Clear metrics you define up front (e.g., accuracy, time saved, hallucination rate, clarity, actionability)
- A scoring rubric (0–1 or 1–5 scale) with brief anchors for each level
- At least 2–3 test cases, including at least one edge case or ambiguous input
- Summary results and a brief failure analysis — what went wrong and why?
- Reproducibility: include your inputs and outputs so the benchmark could be re-run
- You may use any evaluation approach: human rubric scoring, LLM-as-judge, baseline comparison (A/B), or a combination. The key is rigor and honesty.

#### AI Disclosure
If you use AI tools (like ChatGPT, Claude, etc.) in writing your report, include a brief section at the end describing how they were used. This will not affect your grade but must be disclosed for academic integrity.

Grading Rubric (100 points — worth 25% of your final grade)
This assignment is graded out of 100 points. Your score is then scaled to 25% of your final course grade. The demo walkthrough is graded separately (see the Demo Recording Assignment).

Each section is graded on this scale:

Level	Score
Excellent	100% of points
Good	85% of points
Satisfactory	70% of points
Needs Improvement	50% of points
Insufficient	0–25% of points

1. Problem Definition & Solution (25 points)
Sub-criterion	Points
Clear problem statement	10
Well-reasoned solution approach	15
Excellent: The problem is real, specific, and well-motivated. The solution approach is logical, well-justified, and clearly connected to the problem.

Needs Improvement: The problem is vague or generic. The solution approach is not clearly connected to the stated problem.

2. Technical Implementation (30 points)
Sub-criterion	Points
Data processing & methodology	10
Implementation quality	10
Tool/platform selection justification	10
Excellent: Implementation runs end-to-end reliably. Clear documentation of prompts, iterations, and design choices. Tool selection is well-justified.

Needs Improvement: Implementation has significant gaps. Little documentation of the building process or tool choices.

3. Results & Analysis (25 points)
Sub-criterion	Points
Clear presentation of results	12
Thorough evaluation of solution	13
Excellent: Results are clearly presented with defined metrics. Evaluation includes multiple test cases, edge cases, and honest failure analysis.

Needs Improvement: Results are vague or not backed by defined metrics. Minimal or no benchmarking.

4. Professional Communication (20 points)
Sub-criterion	Points
Writing clarity & organization	10
Proper use of technical language	5
Visual elements (figures, tables, etc.)	5
Excellent: Writing is clear, well-organized, and professional. Technical language is used correctly. Figures, tables, and diagrams enhance the report.

Needs Improvement: Writing is disorganized or unclear. Few or no visual elements. Technical language is misused or absent.

Beware of "AI slop," i.e., content entirely AI-generated with very few human edits or direction. Make sure to proofread consistently.

Tips for a Strong Report
Start with your own thinking, then use AI to refine and enhance — not the other way around.
Be transparent about your process: what worked, what didn't, and what you'd do differently.
Include visuals — architecture diagrams, screenshots, result tables, and figures make your report significantly stronger.
Write for replicability — could an engineer who's never met you rebuild your system by reading your report? That's the bar.
Proofread — professional communication matters. Read your report out loud before submitting.