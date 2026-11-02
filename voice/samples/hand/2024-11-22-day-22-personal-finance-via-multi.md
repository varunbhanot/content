---
title: "Day 22 - Personal Finance via Multi-Agent LLM"
subtitle: "Managing monthly finances via a multi-agent app"
date: 2024-11-22
url: https://varunbhanot.substack.com/p/day-22-personal-finance-via-multi
words: 724
era: hand
---

# Day 22 - Personal Finance via Multi-Agent LLM

Welcome back to my [#75DaysofGenerativeAI](https://varunbhanot.substack.com/p/75-days-of-generative-ai) series. We’ve been developing fairly simple applications with sequential flows. One example is the LLMTwin, which is described [here](https://varunbhanot.substack.com/p/day-7-building-your-own-llm-twin).

This time we will build a more complex app to manage personal finance. Some of the features we will be covering

1. **Automated Statement Parsing**: Upload your credit card or bank statements, and our app extracts transaction details automatically
2. **Transaction Categorization:** Classify transactions into debits, credits, expenses, and savings with minimal manual effort.
3. **Personalized Insights**: Get month-wise narratives of your financial trends—what went well, what didn’t, and how you can improve.
4. **Chatbot Assistance**: Ask questions like 'What were my biggest expenses in March?' or 'How much did I save last quarter?'

## **What Are Multi-Agent Applications?**

A multi-agent application consists of multiple specialized agents or components that work together to achieve a shared goal. Each agent is responsible for a specific task, and they communicate dynamically to complete complex workflows.

**LangGraph** is a powerful library designed for building stateful, multi-actor applications using Large Language Models (LLMs). It serves as an orchestration framework that enables developers to create complex workflows involving single or multiple agents, making it ideal for advanced AI applications.

## LangGraph Vs LangChain

LangGraph is ideal for more complex, multi-agent workflows where maintaining state and dynamic decision-making are critical.

[![](https://substackcdn.com/image/fetch/$s_!iBFG!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F2cdb237b-999f-4669-99d6-8dfa3e126e88_943x310.png)](https://substackcdn.com/image/fetch/$s_!iBFG!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F2cdb237b-999f-4669-99d6-8dfa3e126e88_943x310.png)

## Why personal finance app as a MA app?

LangGraph's ability to handle **stateful, cyclical workflows** and its support for multi-agent coordination make it ideal for implementing such a system.

Here’s why LangGraph is suitable for the use case:

* **Stateful Workflows**: Your app needs to maintain state across tasks (e.g., parsing statements, categorizing transactions, generating summaries, and interacting via chatbot). LangGraph's state management ensures that data flows seamlessly between nodes.
* **Multi-Agent Collaboration**: Different tasks (e.g., OCR, transaction categorization, summarization) can be handled by specialized agents/nodes in the graph.
* **Iterative Decision-Making**: In cases where the system is unsure (e.g., ambiguous transactions), LangGraph can pause execution, query the user for clarification, and resume processing.
* **Dynamic Querying**: The chatbot functionality can leverage LangGraph's ability to query processed data dynamically and provide context-aware responses.

## **Tech Stack for the Personal Finance Application**

### **Core Framework**

* **LangGraph**:

  + Orchestrates multi-agent workflows as graphs.
  + Manages state across nodes and workflows, enabling complex task coordination.

### **2. Backend**

* **Python**:

  + The primary programming language for implementing workflows and integrating components.
* **FastAPI**:

  + Used for building RESTful APIs to handle user interactions.
  + Provides endpoints for uploading statements, querying data, and managing budgets.

### **3. Large Language Model (LLM)**

* **LLaMA 3**:

  + A state-of-the-art open-source LLM designed for efficient on-device or cloud-based use.
  + Integrated with LangGraph to handle tasks like financial summarization, chatbot queries, and transaction analysis.
  + Key Features:

    - JSON output mode for structured responses (e.g., categorizing transactions or grading document relevance).
    - Compact model variants (e.g., LLaMA 3.2) that can run locally or in the cloud.

### **4. AI and NLP**

* **LangChain**:

  + Integrated with LangGraph for handling LLM interactions and chaining tasks with external tools.
* **Prompt Engineering**:

  + Custom prompts designed to guide LLaMA 3 in generating financial insights and summaries.

### **5. OCR (Optical Character Recognition)**

* **Unstructured**:

  + A Python library designed for processing unstructured documents.
  + Extracts text from PDFs, scanned documents, or images with minimal templating.
  + Handles variability in document formats without requiring brittle templates.

### **6. Database**

* **PostgreSQL**:

  + Relational database used to store parsed transactions, categorized data, budgets, and summaries.
* **SQLAlchemy**:

  + ORM (Object Relational Mapping) library for interacting with the database in Python.

### **7. Embedding Store**

* **Pinecone/FAISS**:

  + Vector database used for storing embeddings of financial data to enable semantic search for chatbot queries.

### **8. State Management**

* LangGraph's built-in state management system ensures:

  + Persistent state across workflows.
  + Context sharing between nodes in the graph.

### **9. Deployment**

* **Docker**:

  + Containerization platform to package and deploy the application consistently across environments.
* **AWS/GCP/Azure**:

  + Cloud platforms for hosting backend services.

### **10. Monitoring & Observability**

* **LangSmith**:

  + For debugging, observability, and monitoring LangGraph workflows in production.

## Architecture

We will be following a clean architecture structure here with a clear distinction between API Layer, Application Layer, Domain Layer, and Infra layer.

[![](https://substackcdn.com/image/fetch/$s_!jytQ!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F855768c6-5fcb-4472-bd62-c4cab5efa31f_1878x782.png)](https://substackcdn.com/image/fetch/$s_!jytQ!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F855768c6-5fcb-4472-bd62-c4cab5efa31f_1878x782.png)

Architecture for the app by author

## Conclusion

Stay tuned as I post my learning and process of building the backend for the personal finance app. It’s a steep learning curve but I am pretty sure the outcome would be super useful not only for me but for everyone following this series. Till next time!
