---
title: "Day 31-32 : Understanding Memory Types in LangGraph"
subtitle: ""
date: 2025-06-14
url: https://varunbhanot.substack.com/p/day-31-32-understanding-memory-types
words: 1010
era: hand
---

# Day 31-32 : Understanding Memory Types in LangGraph

Welcome back to my [#75DaysofGenerativeAI](https://varunbhanot.substack.com/p/75-days-of-generative-ai) series!

[![](https://substackcdn.com/image/fetch/$s_!2bNY!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F9fac114a-29ee-4492-b13d-4091b0b97383_1024x1024.png)](https://substackcdn.com/image/fetch/$s_!2bNY!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F9fac114a-29ee-4492-b13d-4091b0b97383_1024x1024.png)

The recent ChatGPT memory upgrade – where it now references all past conversations automatically – has sparked fascinating discussions about AI memory architectures, particularly in multi-agent systems. This article looks at different types of memory systems that you can also use to provide similar experience in your LLM driven apps.

Memory systems in AI aren't just about storing data - they're about creating agents that can learn, adapt, and build relationships over time . Just like human memory has different types, AI systems need different memory architectures for different tasks

[![](https://substackcdn.com/image/fetch/$s_!deB0!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F8f2f6b16-b711-4c5f-aaa5-cb5fc256b5aa_1536x1024.png)](https://substackcdn.com/image/fetch/$s_!deB0!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F8f2f6b16-b711-4c5f-aaa5-cb5fc256b5aa_1536x1024.png)

## The Four Memory Types

### Working Memory - The Conversation Buffer

Working memory maintains short-term context for immediate tasks. his is essential for maintaining conversation flow and multi-step reasoning processes.

**Real-world application**: Customer service bots that remember the current conversation context, order numbers, and immediate customer needs

**Implementation approach**: Using LangChain's ConversationBufferMemory for session-based context management

**Example**:

```
# Initialize working memory for conversation context
working_memory = ConversationBufferMemory(
    return_messages=True,
    memory_key="chat_history"
)

class CustomerServiceBot:
    def __init__(self):
        self.llm = ChatOpenAI(api_key="your_api_key_here", temperature=0.7)
        self.memory = ConversationBufferMemory(return_messages=True)
        self.chain = ConversationChain(llm=self.llm, memory=self.memory)

    def respond(self, user_input):
        # Memory automatically maintains conversation context
        return self.chain.predict(input=user_input)

    def get_conversation_history(self):
        return self.memory.chat_memory.messages

# Example usage:
# bot = CustomerServiceBot()
# bot.respond("Hi, I have an issue with my order")
# bot.respond("My order number is 12345")
# bot.respond("When will it be delivered?")  # Bot remembers the order number!
```

### Episodic Memory - The Experience Vault

Episodic memory captures complete interaction episodes with full reasoning chains. This enables AI agents to learn from past experiences and improve performance over time.

**Real-world application**: AI tutoring systems that remember which explanation methods worked best for different types of student questions.

**Implementation approach**: Vector similarity search with structured episode schemas using tools like LangMem.

**Example:**

```
from langmem import create_memory_manager
from pydantic import BaseModel, Field
from typing import List

class Episode(BaseModel):
    observation: str
    thoughts: str
    action: str
    result: str
    tags: List[str] = Field(default=[])

class TutorBot:
    def __init__(self):
        self.episodic_manager = create_memory_manager(
            llm="openai:gpt-4o",
            namespace=("tutor", "episodes"),
            schemas=[Episode],
            instructions="Extract successful teaching episodes that led to student understanding"
        )

    def teach_concept(self, student_question, concept):
        similar_episodes = self.episodic_manager.search(
            query=f"teaching {concept} to confused student", limit=3
        )
        if similar_episodes:
            teaching_strategy = "Adapted from similar episodes"
        else:
            teaching_strategy = "Default approach"
        explanation = f"Explanation for {student_question} using {teaching_strategy}"
        student_understanding = 0.9  # Example score
        if student_understanding > 0.8:
            episode = Episode(
                observation=f"Student asked: {student_question}",
                thoughts=f"Used strategy: {teaching_strategy}",
                action=f"Provided explanation: {explanation}",
                result=f"Student understood with score: {student_understanding}",
                tags=[concept, "successful_explanation"]
            )
            self.episodic_manager.store(episode)
        return explanation
```

**Output**:

```
User: Can you explain loops?
Bot: Explanation for loops using Adapted from similar episodes
```

### Semantic Memory - The Knowledge Base

Semantic memory stores structured facts, user preferences, and domain knowledge. This creates personalized AI experiences that adapt to individual users.

**Real-world application**: Personal assistants that remember your work schedule, and communication style.

**Implementation approach**: Vector databases like Chroma or Pinecone combined with metadata filtering.

**Example**:

```
from langchain.docstore.document import Document
from sentence_transformers import SentenceTransformer
from langchain_community.vectorstores import Chroma

class CustomEmbeddings:
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        self.model = SentenceTransformer(model_name)
    def embed_query(self, text):
        return self.model.encode(text)
    def embed_documents(self, texts):
        return [self.model.encode(text) for text in texts]

class PersonalSemanticMemory:
    def __init__(self, user_id):
        self.user_id = user_id
        self.embeddings = CustomEmbeddings('all-MiniLM-L6-v2')
        self.vector_store = Chroma(
            collection_name=f"user_{user_id}_semantic",
            embedding_function=self.embeddings,
            persist_directory=f"./memory/semantic/{user_id}"
        )
    def store_preference(self, preference):
        doc = Document(
            page_content=preference["content"],
            metadata={
                "type": "preference",
                "category": preference.get("category", "general"),
                "value": preference.get("value", ""),
                "timestamp": datetime.now().isoformat(),
                "user_id": self.user_id
            }
        )
        self.vector_store.add_documents([doc])
        return doc
    def get_relevant_preferences(self, query, limit=5):
        return self.vector_store.similarity_search(
            query=query, k=limit, filter={"type": "preference"}
        )
```

**Output**:

```
User: I prefer concise explanations.
Bot: Preference stored.
User: What's your preferred learning style?
Bot: You prefer concise explanations.
```

### Procedural Memory - The Skill Library

Procedural memory stores optimized workflows, templates, and proven patterns. This enables AI systems to apply learned best practices consistently.

**Real-world application**: Code assistants that remember which programming patterns work best for specific types of problems.

**Implementation approach**: Redis-based key-value storage for fast pattern retrieval

**Example**:

```
import redis
import json

class ProceduralMemoryStore:
    def __init__(self):
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    def store_pattern(self, pattern_name, pattern_data):
        self.redis_client.set(f"pattern:{pattern_name}", json.dumps(pattern_data))
        return pattern_data
    def get_pattern(self, pattern_name):
        pattern_data = self.redis_client.get(f"pattern:{pattern_name}")
        if pattern_data:
            return json.loads(pattern_data)
        return None
    def find_patterns(self, context_type, limit=5):
        pattern_keys = self.redis_client.keys("pattern:*")
        patterns = []
        for key in pattern_keys:
            pattern_data = json.loads(self.redis_client.get(key))
            if context_type.lower() in pattern_data.get("category", "").lower():
                patterns.append(pattern_data)
        return patterns[:limit]
```

**Output**:

```
User: How do I define a function?
Bot: Here are the steps: 1. Define function 2. Add parameters 3. Write body 4. Return result
```

# Integrated Multi-Memory Agent

I decided to write a unified agent that combines all memory types for richer, more adaptive responses. Hence it usually a combination of one or more memory types that would be relevant for your app

### **How it works:**

```
class MultiMemoryAgent:
    def __init__(self, user_id):
        self.user_id = user_id
        self.working_memory = ConversationBufferMemory()
        self.episodic_memory = EpisodicMemoryManager()
        self.semantic_memory = PersonalSemanticMemory(user_id)
        self.procedural_memory = ProceduralMemoryStore()

    def process_input(self, user_input, context_type="general"):
        working_context = self.working_memory.load_memory_variables({})
        relevant_episodes = self.episodic_memory.search(user_input, limit=3)
        user_preferences = self.semantic_memory.get_relevant_preferences(user_input)
        applicable_patterns = self.procedural_memory.find_patterns(context_type)
        full_context = {
            "conversation_history": working_context,
            "similar_experiences": relevant_episodes,
            "user_preferences": user_preferences,
            "proven_patterns": applicable_patterns
        }
        response = f"Response to {user_input} using context: {full_context}"
        self.store_interaction(user_input, response, full_context)
        return response
```

**Output**:

```
User: Help me write a Python function for user authentication
Bot: Response to Help me write a Python function for user authentication using context: {\'conversation_history\': {\'history\': \'\'}, \'similar_experiences\': [], \'user_preferences\': [Document(metadata={\'category\': \'learning_style\', \'timestamp\': \'2025-06-14T12:55:31.582571\', \'user_id\': \'user_123\', \'value\': \'\', \'type\': \'preference\'}, page_content=\'I prefer concise explanations.\')], \'proven_patterns\': []}
```

As you can see, the agent combines multiple memory types to build a context specific to me.

## Future Directions and Emerging Trends

Research in AI memory systems explores autobiographical memory, collaborative memory networks, and emotional memory storage. These advances point toward AI systems that develop personal narratives and share knowledge across agent networks.

Its only gets better from here!

*This article is part of my #75DaysofGenerativeAI series. Follow along for more practical implementations and real-world insights into building production-grade AI systems.*

##
