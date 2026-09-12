"""`FaissRepositorioBaseConhecimento` — implementa a porta de conhecimento.

Adapter de RAG: indexa a Base de Conhecimento com LangChain e embeddings
locais (`nomic-embed-text` via Ollama), guarda os vetores em um indice FAISS
em disco e, a cada pergunta, devolve os `Trecho` mais relevantes.

A licao da Fase 4 e que o RAG nao e uma camada nova nem um caso especial —
e so mais um adapter atras de uma porta ja existente. O caso de uso nao
muda uma linha por causa dele.

TODO(Fase 4): implementar o adapter e o script de ingestao de documentos
(o indice gerado fica fora do git, ver `.gitignore`).
"""
