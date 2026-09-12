"""Adapters da porta `ProvedorLLM` — quem gera o texto da resposta.

Existem dois (ou mais) adapters aqui de proposito: e este subpacote que
prova o requisito central da POC — trocar o modelo local por uma API paga
sem mexer na regra de negocio.

    ollama_provider.py     Llama local via Ollama      (Fase 3)
    anthropic_provider.py  API paga, so pra provar     (Fase 7)
"""
