"""Portas (Ports) — os contratos que o dominio exige do mundo externo.

Aqui mora o Dependency Inversion Principle: o dominio define a *forma* do
contrato (Protocols do Python) e a infraestrutura obedece. Por isso as
portas ficam em `domain/`, e nao em `infrastructure/` — quem manda na
interface e quem a consome, nao quem a implementa.

E o que torna possivel o requisito central da POC: hoje o `ProvedorLLM` e
um Llama local via Ollama, amanha pode ser OpenAI, Anthropic ou Bedrock, e
nenhuma linha de `domain/` ou `application/` muda — so o adapter escolhido
no composition root (`main.py`).

Portas previstas:
    ProvedorLLM                    gerar_resposta(mensagens, trechos_contexto) -> str
    RepositorioBaseConhecimento    buscar_trechos_relevantes(pergunta) -> list[Trecho]
    CanalConversa                  enviar_mensagem(conversa_id, texto) + recebimento
    GatewayHandoff                 escalar(conversa, resumo, atributos) -> None

TODO(Fase 2): declarar as quatro portas como `typing.Protocol`, e exercita-las
nos testes com dubles in-memory (sem Ollama, sem Twilio).
"""
