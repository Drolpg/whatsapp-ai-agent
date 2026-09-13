"""Testes dos adapters de `ProvedorLLM`.

Diferente de `tests/core/`, aqui o I/O real e o ponto: estes testes sobem
uma chamada HTTP de verdade contra um Ollama rodando na maquina. Se ele nao
estiver de pe, os testes que dependem dele sao pulados com uma mensagem
explicando o porque — nao falham.

    test_ollama_provider.py  OllamaProvedorLLM contra um Ollama local
"""
