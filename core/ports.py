"""Portas: os contratos que o nucleo exige de quem fala com o mundo externo.

O nucleo precisa gerar texto, consultar documentos, enviar mensagens e
escalar atendimentos — mas nao deve saber *como* nada disso acontece. A
solucao e ele declarar aqui a forma do contrato (Protocols do Python) e
deixar `adapters/` implementar. Por isso as interfaces vivem em `core/` e
nao junto dos adapters: quem define o contrato e quem o consome, nao quem o
cumpre.

E o que torna possivel o requisito central da POC: hoje o `ProvedorLLM` e
um Llama local via Ollama, amanha pode ser OpenAI, Anthropic ou Bedrock, e
nenhuma linha de `core/` muda — so o adapter escolhido no `main.py`.

Interfaces previstas:
    ProvedorLLM       gerar_resposta(mensagens, trechos_contexto) -> str
    BaseConhecimento  buscar_trechos_relevantes(pergunta) -> list[str]
    Canal             enviar_mensagem(conversa_id, texto) + recebimento
    GatewayHandoff    escalar(conversa, resumo, atributos) -> None

TODO(Fase 2): declarar as quatro interfaces como `typing.Protocol` e
exercita-las nos testes com implementacoes falsas (em memoria), sem Ollama
e sem Twilio.
"""
