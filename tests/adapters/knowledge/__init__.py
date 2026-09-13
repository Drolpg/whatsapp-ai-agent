"""Testes dos adapters de `BaseConhecimento`.

Como em `tests/adapters/llm/`, o I/O real e o ponto: estes testes geram
embeddings de verdade (via Ollama) e montam um indice FAISS de verdade. Se o
Ollama ou o modelo de embeddings nao estiverem disponiveis, os testes sao
pulados com uma mensagem explicando o que falta — nao falham.

    test_faiss_repository.py  FaissBaseConhecimento contra um indice real
"""
