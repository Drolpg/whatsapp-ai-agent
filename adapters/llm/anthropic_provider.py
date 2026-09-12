"""`AnthropicProvedorLLM` — a segunda implementacao de `ProvedorLLM`.

Este modulo existe antes de tudo por um motivo pedagogico: provar na pratica
o que a separacao entre nucleo e adapters promete. Ele cumpre exatamente o
mesmo contrato que `ollama_provider.py`, falando com uma API paga em vez de
um modelo local.

O criterio de aceite da Fase 7 e negativo: trocar um adapter pelo outro no
`main.py` deve deixar o `git diff` completamente vazio em `core/`. Se for
preciso mudar qualquer coisa la, o desenho vazou.

TODO(Fase 7): implementar o adapter (Anthropic ou OpenAI) e fazer a troca
somente no composition root.
"""
