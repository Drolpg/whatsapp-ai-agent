"""Camada de infraestrutura: os adapters concretos.

Cada modulo aqui implementa uma das portas declaradas em `domain/ports.py`,
traduzindo o contrato do dominio pra uma tecnologia especifica (Ollama,
FAISS, Twilio Agent Connect, Twilio Studio). E a unica camada que pode
importar bibliotecas externas e a unica que sabe que "escalar" significa,
na pratica, "Studio Flow + TaskRouter + Flex".

A dependencia aponta pra dentro: infraestrutura importa `domain/`, nunca o
contrario. Trocar um adapter por outro (Fase 7) e uma mudanca de uma linha
no `main.py`, sem tocar em `domain/` nem em `application/`.

Subpacotes, um por porta:
    llm/        ProvedorLLM                  (Fases 3 e 7)
    knowledge/  RepositorioBaseConhecimento  (Fase 4)
    channels/   CanalConversa                (Fase 5)
    handoff/    GatewayHandoff               (Fase 6)
"""
