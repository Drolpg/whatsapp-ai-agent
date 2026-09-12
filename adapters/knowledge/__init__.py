"""Implementacoes de `BaseConhecimento` — o lado RAG.

Embeddings, chunking, indice vetorial e score de similaridade sao detalhes
que moram aqui e nao vazam pra fora: o nucleo so pede
`buscar_trechos_relevantes(pergunta)` e recebe os trechos de texto.

    faiss_repository.py  LangChain + embeddings locais + FAISS  (Fase 4)
"""
