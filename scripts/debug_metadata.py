"""调试：检查 ChromaDB 中所有 chunks 的元数据。"""
import sys

sys.path.insert(0, 'E:/trae/cede/mcu-rag-qa-v2')

import chromadb

client = chromadb.PersistentClient(path='E:/trae/cede/mcu-rag-qa-v2/data/chroma_db')
collection = client.get_collection('mcu_qa')
results = collection.get()

print(f"Total chunks: {len(results['ids'])}")
print("-" * 60)

for i in range(len(results['ids'])):
    meta = results['metadatas'][i]
    content = results['documents'][i]
    doc_name = meta.get('doc_name', 'unknown')
    classification = meta.get('classification', 'unknown')
    level = meta.get('classification_level', 'unknown')
    tenant = meta.get('tenant_id', 'unknown')
    
    print(f"doc_name: {doc_name}")
    print(f"  classification: {classification}")
    print(f"  classification_level: {level}")
    print(f"  tenant_id: {tenant}")
    print(f"  content: {content[:60]}...")
    print()
