"""Casos de uso — o roteiro de cada operacao do sistema.

`ProcessarMensagemRecebida` e o caso de uso central da POC. Seu roteiro:

    1. registra a mensagem do cliente na `Conversa`;
    2. busca trechos relevantes na `RepositorioBaseConhecimento` (RAG);
    3. pede uma resposta candidata ao `ProvedorLLM`;
    4. entrega essa candidata ao `TriagemService`, que decide;
    5. conforme o `ResultadoTriagem`, ou responde pelo `CanalConversa`
       ou aciona o `GatewayHandoff`.

Repare que os passos 2, 3, 5 falam com *portas*, nao com Ollama, FAISS ou
Twilio — o caso de uso recebe as implementacoes por injecao de dependencia
no construtor e nunca descobre qual tecnologia esta do outro lado. O passo 4
e o unico que decide algo, e ele delega a decisao pro dominio.

TODO(Fase 2): implementar `ProcessarMensagemRecebida` com as portas
injetadas no construtor, e testar o fluxo inteiro com adapters fake.
"""
