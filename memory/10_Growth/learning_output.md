# 🧠 学习输出 (Feynman Output)

> **费曼学习法核心**: 每学一个知识点，用“大白话”写一段解释。如果你不能简单地解释它，你就没有真正理解它。

## 知识图谱增强检索生成 (GraphRAG / Knowledge Graph RAG)
- **日期**: 2026-01-XX  
- **一句话解释** (假设对方是文科生):  
  RAG 就像是开卷考试——大模型虽然聪明但记性不好，传统 RAG 给它递一本课本翻书找答案；而 GraphRAG 更进一步，不仅给课本，还给了知识之间的“关系地图”，让它能顺着逻辑链条推理出更准确、连贯的回答。  
- **核心逻辑/代码片段**:  
  ```python
  # 示例：基于 Neo4j 构建知识图谱并集成到 RAG 流程
  from langchain_community.graphs import Neo4jGraph
  from langchain.chains import GraphQAChain

  graph = Neo4jGraph(url="bolt://localhost:7687", username="neo4j", password="password")
  chain = GraphQAChain.from_llm(llm, graph=graph, verbose=True)
  result = chain.run("爱因斯坦和量子力学有什么关系？")
  ```
- **我的思考/应用场景**:  
  适用于需要强逻辑关联的领域（如医疗诊断、法律条文推理、科研文献综述），能显著提升答案的可解释性和准确性。

---

## [下一个知识点]  
...