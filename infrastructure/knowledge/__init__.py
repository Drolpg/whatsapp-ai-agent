"""Adapters da porta `RepositorioBaseConhecimento` — o lado RAG.

Embeddings, chunking, indice vetorial e score de similaridade sao detalhes
de implementacao que moram aqui e nao vazam pra fora: o dominio so pede
`buscar_trechos_relevantes(pergunta)` e recebe uma lista de `Trecho`.

    faiss_repository.py  LangChain + embeddings locais + FAISS  (Fase 4)
"""
