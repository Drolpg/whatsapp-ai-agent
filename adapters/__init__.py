"""Adapters: as implementacoes concretas das portas do nucleo.

Cada modulo aqui cumpre uma das interfaces declaradas em `core/ports.py`,
traduzindo o contrato pra uma tecnologia especifica (Ollama, FAISS, Twilio
Agent Connect, Twilio Studio). E a unica parte do projeto que pode importar
bibliotecas externas e a unica que sabe que "escalar" significa, na pratica,
"Studio Flow + TaskRouter + Flex".

A dependencia aponta pra dentro: os adapters importam `core/`, nunca o
contrario. Trocar um adapter por outro (Fase 7) e uma mudanca de uma linha
no `main.py`, sem tocar em `core/`.

Subpacotes, um por porta:
    llm/        ProvedorLLM       (Fases 3 e 7)
    knowledge/  BaseConhecimento  (Fase 4)
    channel/    Canal             (Fase 5)
    handoff/    GatewayHandoff    (Fase 6)
"""
