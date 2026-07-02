# SYSTEM ARCHITECTURE BLUEPRINT: Autonomous Academic Matchmaking & Synthesis Pipeline

**To the AI Assisting me (Claude/etc.):** Act as an Elite Systems Architect. I am building a fully open-source, Agentic AI platform designed to automate the discovery of academic scholarships, funded PhD/Master's positions, and the subsequent generation of highly personalized application materials (Cold Emails, SOPs). 

Please review the following system design and expand upon it, providing necessary code structures, API routing designs, and optimization strategies. 

## 1. System Overview & Workflow
The system utilizes a deterministic State Machine (e.g., LangGraph) to orchestrate multiple specialized open-source LLMs. The workflow is strictly linear but allows for cyclical refinement:
1. **Context Ingestion:** Parse user CVs, transcripts, and financial/geographic constraints.
2. **Agentic Live Search:** Traverse the web and academic APIs to find active grants, open lab positions, and university scholarships.
3. **Knowledge Graph Construction:** Store findings in a localized Neo4j Graph Database (Applicant <-> Skills <-> Faculty <-> Funding).
4. **GraphRAG Matchmaking:** Score the best opportunities based on semantic and graph-proximity alignment.
5. **Artifact Synthesis:** Generate hallucination-free cold emails and Statement of Purpose (SOP) drafts tailored to the specific professor/scholarship.

## 2. Multi-Agent Topology (The "Who's Who")
Instead of one massive model, we route tasks to specialized agents:

*   **Agent 1: The Profiler (Data Extraction)**
    *   *Role:* Reads the messy user CV/PDFs and extracts structured JSON (Skills, GPA, Research Interests, Timeline).
*   **Agent 2: The Scout (Live Search & Retrieval)**
    *   *Role:* Armed with Python tool-calls. Queries OpenAlex (for papers), NSF/NIH (for funding), and uses Tavily/SearXNG for live web scraping of university "Opportunities" pages.
*   **Agent 3: The Matchmaker (Evaluator)**
    *   *Role:* Compares the User Profile against the Scout's findings using Vector Embeddings (Cosine Similarity) + Graph Traversal. Scores matches out of 100.
*   **Agent 4: The Scribe (Document Synthesis)**
    *   *Role:* Takes the highest-scoring matches and writes the Cold Emails and SOPs.
*   **Agent 5: The Quality Gate (Hallucination Checker)**
    *   *Role:* A strict validator that reads the generated SOP/Email and ensures *every* claim matches the user's CV and the Professor's actual research. Rejects and loops back to the Scribe if it detects hallucinations.

## 3. Open-Source Model Matrix
To optimize compute costs while maintaining state-of-the-art reasoning, we use a tiered open-source model approach:

*   **The Orchestrator / Quality Gate (Heavy Reasoning):** `Qwen2.5-72B-Instruct` or `Llama-3-70B-Instruct`. (Highest intelligence for routing tasks and verifying logic).
*   **The Scout / Profiler (Fast Parsing):** `Mistral-Nemo-12B` or `Llama-3-8B`. (Extremely fast, cheap, great at extracting JSON and calling tools).
*   **The Scribe (Creative/Writing):** `Qwen2.5-32B` (Excellent context window and nuance for academic writing).
*   **The Embedding Engine (For RAG):** `BAAI/bge-large-en-v1.5` (Top tier open-source embedding model for vectorizing text).

## 4. Infrastructure & Virtualization Strategy (Hosting & Real-World I/O)
To host this locally or on rented bare-metal servers using virtualization:

*   **Hypervisor Layer:** Proxmox VE (Virtual Environment).
*   **Model Serving (The "Brains"):** 
    *   Create isolated Ubuntu Linux VMs. Use PCIe Passthrough to give these VMs direct access to the GPUs (e.g., Nvidia RTX 4090s or A100s).
    *   Run **vLLM** or **Ollama** inside these VMs. This exposes the open-source models via an OpenAI-compatible REST API (e.g., `http://10.0.0.5:8000/v1/chat/completions`). 
    *   *Security Note:* The models themselves are "air-gapped" from the public internet. They do not browse the web.
*   **The Application/Agent Layer (The "Hands"):**
    *   Run a lightweight Docker Swarm or Kubernetes cluster. 
    *   Deploy the Python/LangGraph Orchestrator here. 
    *   *How it communicates with the real world:* This container *has* internet access. When the LLM decides it needs to search the web, it outputs a tool-call JSON `{"action": "search", "query": "MIT AI scholarships 2026"}`. The Python orchestrator executes the web scraper, downloads the HTML/text, and sends that text *back* to the isolated vLLM server as prompt context. 

## 5. Knowledge Base (KB) Architecture
*   **Vector Database:** Qdrant or Milvus (for fast semantic similarity searches of research papers).
*   **Graph Database:** Neo4j. This is critical. Instead of just chunking text, we build relationships: `(Student) -[HAS_SKILL]-> (Machine Learning) <-[REQUIRES]- (Scholarship_A)`. This prevents the AI from recommending scholarships the student isn't qualified for.

## 6. Output Deliverables Requested from Claude:
Please generate:
1. The **Python boilerplate** using LangGraph/LangChain to wire these 5 specific agents together.
2. The **Neo4j Cypher schema** to map the relationships between Students, Universities, Professors, and Scholarships.
3. A **Docker Compose** or architecture map demonstrating how the vLLM model servers communicate with the LangGraph orchestrator.
```eof

### How to use this:
Simply copy the markdown text above, paste it into your prompt box for your advanced reasoning model, and let it generate the codebase. This design ensures that you have enterprise-grade security (isolated models), high-speed routing, and a system that actually works in the real world without hallucinating facts on a student's Statement of Purpose.