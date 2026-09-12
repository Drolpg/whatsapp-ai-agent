"""A decisao de triagem e o fluxo que a usa.

Duas pecas, ambas sem dependencia externa:

`TriagemService` recebe uma `Conversa` e a resposta candidata gerada pela
IA, e decide se ela resolve o atendimento ou se a conversa deve ser
escalada pra um humano (ex: a IA pediu escalar explicitamente, ou o numero
de tentativas sem sucesso passou do limite). Repare no que ele *nao* faz:
nao gera a resposta e nao sabe quem a gerou — isso e problema de um
`ProvedorLLM` la em `adapters/`. Ele so decide o que fazer com ela.

`processar_mensagem_recebida` e a funcao que costura o fluxo inteiro:

    1. registra a mensagem do cliente na `Conversa`;
    2. busca trechos relevantes na `BaseConhecimento` (RAG);
    3. pede uma resposta candidata ao `ProvedorLLM`;
    4. entrega essa candidata ao `TriagemService`, que decide;
    5. conforme a decisao, ou responde pelo `Canal` ou aciona o
       `GatewayHandoff`.

Os passos 2, 3 e 5 falam com as interfaces de `ports.py`, nunca com Ollama,
FAISS ou Twilio direto: as implementacoes chegam prontas, passadas como
argumento pelo `main.py`. E por isso que este fluxo pode ser testado
inteiro com adapters falsos, sem nada real rodando.

TODO(Fase 1): implementar `TriagemService`.
TODO(Fase 2): implementar `processar_mensagem_recebida` e testar os dois
caminhos (resolvido pela IA e escalado pro humano) com adapters falsos.
"""
