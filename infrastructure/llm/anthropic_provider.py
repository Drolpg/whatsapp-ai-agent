"""`AnthropicProvedorLLM` — a segunda implementacao de `ProvedorLLM`.

Este modulo existe por um motivo pedagogico antes de qualquer outro: provar,
na pratica, o que Ports & Adapters promete. Ele satisfaz exatamente o mesmo
contrato que `ollama_provider.py`, falando com uma API paga em vez de um
modelo local.

O criterio de sucesso da Fase 7 e negativo: trocar um adapter pelo outro no
`main.py` deve deixar `git diff` completamente vazio em `domain/` e em
`application/`. Se for preciso mudar qualquer coisa nessas camadas, o
desenho vazou.

TODO(Fase 7): implementar o adapter (Anthropic ou OpenAI) e fazer a troca
somente no composition root.
"""
