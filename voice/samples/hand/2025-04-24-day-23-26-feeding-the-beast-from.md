---
title: "Day 23-26 – Feeding the Beast: From Bank/Credit Card Statements to Conversational Insights "
subtitle: ""
date: 2025-04-24
url: https://varunbhanot.substack.com/p/day-23-26-feeding-the-beast-from
words: 951
era: hand
---

# Day 23-26 – Feeding the Beast: From Bank/Credit Card Statements to Conversational Insights 

In the last [article](https://varunbhanot.substack.com/p/day-22-personal-finance-via-multi) of my #75DaysofGenerativeAI we introduced a high level walk through of personal finance app.  
Today we zoom out and walk through the entire **statement-to-insight pipeline** that keeps the bot smart, accurate, and surprisingly chatty.

[![](https://substackcdn.com/image/fetch/$s_!dn-j!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F5c2f89d9-f8d5-4acc-a8da-7f31d87b8250_1024x1024.png)](https://substackcdn.com/image/fetch/$s_!dn-j!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F5c2f89d9-f8d5-4acc-a8da-7f31d87b8250_1024x1024.png)

### **The "Upload & Chill" Moment**

I drop a PDF or CSV into the app, hit **Upload**, and… that's basically it.  
Under the hood four specialised agents hustle in assembly-line fashion:

1. **Parser Agent** – cracks open the raw file
2. **Extraction Agent** – pulls transaction tables
3. **Categorization Agent** – labels spending categories
4. **Vector-DB Ingestor** – stores everything for lightning retrieval

Let's peek at each stop.

### **Parser Agent – The LlamaParse Powerhouse**

The `parser_agent.py` looks deceptively simple:

```
def parse_document(state: InternalState) -> InternalState:
    parsed_data = parse_credit_card_pdf(state.file_path)
    return InternalState(
        **state.dict(exclude={"raw_text", "transactions", "uncategorized"}),
        raw_text=parsed_data["raw_text"],
        transactions=parsed_data["transactions"],
        uncategorized=[]
    )
```

But the real magic happens in `llamaparse_adapter.py`, where we leverage **LlamaParse** – a specialized document parsing API built on GPT-4o:

```
parser = LlamaParse(
    api_key=api_key,
    result_type=ResultType.MD,
    parsing_instruction="""
    EXTRACT ALL TABLES WITH FULL STRUCTURE. PRESERVE:
    - Numeric formatting (commas, decimals)
    - Column headers exactly as shown
    - Multi-line transaction descriptions
    - Empty cells as null values
    """,
    output_tables_as_HTML=False,  # Force markdown tables
    preserve_layout_alignment_across_pages=True,
    gpt4o_mode=True,
    analyze_tables=True,
    table_parsing_mode="matrix"
)
```

why LlamaParse? Because bank and credit card statements are **layout nightmares**:

* Tables split across pages
* Inconsistent column spacing
* Merged cells for running balances
* Footnotes mixed with transaction data

Traditional OCR fails spectacularly here, but LlamaParse's GPT-4o backend understands the *semantic structure* of financial documents. It converts even the messiest PDFs into clean Markdown tables – preserving every decimal point and transaction description.

### **Extraction Agent – The Regex Approach**

Extraction was one task which worked well with good old regex approach.

```
class TableExtractor:
    def __init__(self):
        # Regex pattern to match complete markdown tables
        self.table_pattern = re.compile(
            r'(\|.*\|)\s*\n(\|.*\|)\s*\n((?:\|.*\|\s*\n?)+)',
            re.MULTILINE
        )
```

This regex :

* First capture group: Table header row (`|Date|Description|Amount|)`
* Second capture group: Separator row (`|-----|-----------|------|)`
* Third capture group: All data rows (`|2023-04-01|GROCERY STORE|$42.50)`

The extractor then normalizes headers across different statement formats:

```
def normalize_header(self, header: str) -> str:
    """Standardize header names across different table formats"""
    header = header.replace('(in Rs.)', '').replace('*', '').strip()
    return 'Amount' if 'Amount' in header else header
```

This means `Amount (in Rs.)*` and `Debit Amount` both become simply `Amount`– creating a consistent schema regardless of which bank the statement came from.

### **Categorization Agent**

This is where things get *smart*. It uses Perplexity's API with a carefully crafted prompt

```
self.prompt_template = """You are a JSON parser. Extract the required information from the following JSON and return it in plain text without any code or additional explanations.

JSON Input:
{json_input}

Task:
Extract the transactions from the JSON and list them in plain text format. Also categorise the transaction according to your best knowledge. Example could be food, groceries etc but could be much more. Also if you are not sure mark as uncategorised. Also return in json format adding category the each field.
If its a person name catogarize as Personal Payment.
```

The agent then parses the LLM's response back into structured data.This approach combines the best of both worlds – LLM intelligence for categorization with deterministic parsing for data integrity.

### **Vector-DB Ingestor**

The `vector db agent` is where the magic of semantic search begins:

```
def _ensure_dynamic_schema(self):
    if not self.client.collections.exists(self.collection_name):
        self.client.collections.create(
            name=self.collection_name,
            properties=[
                wvcc.Property(name="source_type", data_type=wvcc.DataType.TEXT),
                wvcc.Property(name="normalized_data", data_type=wvcc.DataType.TEXT),
                wvcc.Property(name="raw_metadata", data_type=wvcc.DataType.TEXT)
            ],
            vectorizer_config=wvcc.Configure.Vectorizer.text2vec_huggingface(model="BAAI/bge-small-en-v1.5")
        )
```

This creates a Weaviate collection with a powerful embedding model – **BAAI/bge-small-en-v1.5** – specifically chosen for its performance on financial text.

But the real trick is the double normalization. Here too we use Perplexity AI to make sure there a normalization of keys irrespective of what kind of statement or headers are thrown to the parsing agent.This second LLM call ensures that even if the extraction agent missed something, we get a consistent schema.

```
def normalize_transaction_with_perplexity(self, item: Dict[str, Any]) -> Dict[str, Any]:
    prompt = f"""
You are a data normalization assistant. Given a transaction object as JSON, map it to the following canonical fields if possible:
- date
- description
- amount
- type (debit/credit/other)
- balance
- category
Return a JSON object with as many canonical fields as possible, using best judgment for field meanings. If a field is missing, leave it blank or null.

Transaction JSON:
{json.dumps(item, ensure_ascii=False)}
"""
    # Call Perplexity API with this prompt
    # ...
```

Once normalized, transactions are embedded and stored with their vectors:

```
embedding = self.embedder.embed_documents([embedding_text])[0]
batch.add_object(
    properties=processed,
    vector=embedding
)
```

### **Glue: State Models & LangGraph Workflow**

The entire pipeline is orchestrated through a **[LangGraph](https://github.com/langchain-ai/langgraph)** workflow:

```
workflow = StateGraph(
    state_schema=InternalState,
    input=InputState,
    output=OutputState
)

workflow.add_node("parse_document", parse_document)
workflow.add_node("extract_transactions", extract_transactions)
workflow.add_node("categorize_transactions", categorize_transactions)
workflow.add_node("store_in_vectordb", store_in_vectordb)

workflow.set_entry_point("parse_document")
workflow.add_edge("parse_document", "extract_transactions")
workflow.add_edge("extract_transactions", "categorize_transactions")
workflow.add_edge("categorize_transactions", "store_in_vectordb")
workflow.add_edge("store_in_vectordb", END)
```

This declarative approach means:

* Each agent receives exactly the state it needs
* Errors are isolated to specific nodes
* The workflow can be visualized and debugged
* New agents can be inserted without changing existing code

Here is the final graph for our Langraph agent

![](https://substackcdn.com/image/fetch/$s_!zkd-!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Ff9e83548-c792-4c0b-a2c6-2908793048db_930x59.png)

## **Why This Matters**

1. **Zero-friction ingestion** – Toss in any statement format; the pipeline figures it out.
2. **Explainability** – Every step—from category assignment to final chat answer—can be audited.
3. **Composable agents** – Swap Perplexity for OpenAI? Replace LlamaParse with another parser? One file change, done.
4. **Real-time Q&A** – The moment data lands in Weaviate, it's instantly searchable by the chatbot.

### **What's Next?**

* Better summarisation: monthly "Money Diaries" generated automatically
* Forecasting agent: predict next month's cash-flow using historic vectors
* Multi-modal: image receipts + text combined in CLIP embeddings

Stay tuned to next article where we focus on advance retrieving data techniques so that we can build a useful and amazing person finance buddy!
