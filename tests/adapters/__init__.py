"""Testes dos adapters — os unicos que tocam o mundo real.

Verificam que cada adapter cumpre o contrato da sua porta conversando com a
tecnologia de verdade (Ollama, FAISS, Twilio). Sao os mais lentos e frageis
da suite, e por isso ficam isolados aqui: uma falha neste diretorio aponta
pra integracao, nunca pra logica de decisao.

Quando a tecnologia nao esta disponivel na maquina, o teste se pula com uma
mensagem explicando o que falta — nao falha.

    llm/  OllamaProvedorLLM  (Fase 3)

TODO(Fases 4 a 6): um modulo de teste por adapter, conforme cada um for
implementado.
"""
