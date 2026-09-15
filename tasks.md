# tasks — whatsapp-ai-agent

> Este documento é um de três: `spec.md` (o quê e por quê), `plan.md`
> (arquitetura técnica) e `tasks.md` (fases e critério de aceite — este
> arquivo). Dividido em 2026-09-13 a partir do `SPEC.md` único original —
> nada do conteúdo foi perdido, só redistribuído.
>
> Status em 2026-09-15: Fases 0 a 5 implementadas e mescladas na `dev`, com
> uma mensagem real indo e voltando pelo WhatsApp. A `main` segue no commit
> inicial, por decisão — ela só recebe merge quando houver um estado que
> valha mostrar ao cliente. Próxima fase: 6.
>
> Duas ressalvas conhecidas, nenhuma bloqueante: o handoff ainda só escreve
> no log (é a Fase 6), e o `llama3.2:3b` inventa detalhes em cerca de 1/3
> das respostas mesmo com o trecho certo em mãos — limite de capacidade do
> modelo, que a Fase 7 existe para trocar.

## Fases (cada uma com objetivo de aprendizado + critério de aceite)

Cada fase só é considerada pronta quando os critérios de aceite abaixo forem
verdadeiros — isso é o checkpoint de validação, e é a parte prática do SDD.

### Fase 0 — Esqueleto do projeto
Aprendizado: por que separar núcleo de decisão e adapters já vale a pena
antes mesmo de ter lógica — a estrutura de pastas já comunica a regra
("core/ não importa de adapters/").
Critério de aceite: estrutura de pastas acima existe, módulos com docstring
explicando o papel de cada um (sem jargão de DDD), `pyproject.toml` com
`pytest`, `.env.example`, `README.md` de instalação, `pytest` roda (mesmo
vazio) sem erro.

### Fase 1 — Núcleo de decisão puro
Aprendizado: por que lógica de negócio testável sem mock nenhum é mais
fácil de confiar — e como isso se paga na prática (testes rápidos, sem
rede, sem Docker).
Critério de aceite: `Conversa`, `Mensagem`, `TriagemService` implementados,
com testes unitários cobrindo pelo menos: resolvido sem escalar, escalado
por pedido explícito da IA, escalado por número de tentativas.

### Fase 2 — Portas e orquestração, com adapters falsos
Aprendizado: como testar o fluxo inteiro (`processar_mensagem_recebida`)
usando implementações fake das portas — sem precisar de Ollama, Twilio ou
nada real ainda.
Critério de aceite: `ports.py` definido, `processar_mensagem_recebida`
implementado e testado ponta a ponta com adapters fake (em memória).

### Fase 3 — Adapter real: LLM local
Aprendizado: como um adapter concreto satisfaz uma porta abstrata sem que
o `core/` saiba disso.
Critério de aceite: `OllamaProvedorLLM` funcionando contra um Ollama real
rodando localmente, testado isoladamente (ainda sem RAG nem Twilio).

### Fase 3.1 — Sinal de escalonamento estruturado
Aprendizado: por que um contrato entre dois sistemas não deve depender de
uma das partes acertar a grafia de uma string. O pedido de escalonamento
vinha como um marcador `[ESCALAR]` dentro do texto da resposta, e no
benchmark da Fase 3 o `llama3.2:3b` o corrompeu em 2 de 15 rodadas
(`[NESCALAR]`, `[NÃO SEGUIR]`) — nas duas, o pedido se perdeu e o texto
corrompido seguiria pro cliente.
Critério de aceite (cumprido):
- `ProvedorLLM.gerar_resposta` devolve `RespostaLLM(texto, deve_escalar)`
  em vez de `str`; `TriagemService` decide pelo campo, sem ler o texto.
- `MARCADOR_ESCALAR` e `_ia_pediu_ajuda` removidos do projeto inteiro.
- `OllamaProvedorLLM` usa output estruturado do Ollama (JSON schema em
  `format`), então não há mais string pra o modelo corromper.
- Benchmark de 4 cenários × 5 rodadas: zero respostas corrompidas.

Resultado em aberto, que motiva a Fase 4: o mecanismo ficou sólido, mas a
discriminação de cobertura não. O modelo segue o viés do prompt em vez de
olhar a base — com o prompt pendendo pra responder ele acerta 5/5 o cenário
coberto e 0/15 os descobertos; com o prompt pendendo pra escalar, o
espelho exato disso. A variante de verificação explícita, a melhor das
três, fica em 12/20. Nenhuma decide de fato.

### Fase 4 — RAG / Base de Conhecimento
Aprendizado: como o RAG entra como só mais um adapter, sem vazar detalhes
de embeddings/vetores pro resto do sistema — e por que a decisão de "a
base cobre isso?" pertence à recuperação (um score de similaridade é
mensurável) e não ao LLM (que, no benchmark da Fase 3.1, não conseguiu
discriminar cobertura de forma confiável nem com o prompt mais explícito:
12/20, falhando 0/5 no cenário sem contexto nenhum).
Critério de aceite:
- `FaissBaseConhecimento` (LangChain + embeddings locais + FAISS)
  funcionando, com script de ingestão de documentos de teste.
- `buscar_trechos_relevantes` aplica um limiar de similaridade
  internamente e devolve lista vazia quando nada no acervo passa do
  limiar — comportamento que o contrato atual de `BaseConhecimento` já
  prevê ("lista vazia é resposta válida"), então nenhuma mudança de porta
  é necessária.
- `processar_mensagem_recebida` ganha uma checagem antes de chamar
  `provedor_llm.gerar_resposta`: se `trechos_contexto` vier vazio, escala
  direto (sem gastar chamada de LLM), com motivo do tipo "a base de
  conhecimento não tem nada relevante pra esta pergunta". O
  `deve_escalar` do LLM vira sinal secundário — só é consultado quando a
  recuperação encontrou algo.
- Repetir o benchmark de 4 cenários × 5 rodadas: o cenário sem contexto
  deve resolver 5/5 por construção.
- Limiar de similaridade como constante configurável (padrão de
  `LIMITE_TENTATIVAS_PADRAO`), escolhida empiricamente a partir dos scores
  observados nos 4 cenários.

### Fase 5 — Canal real (WhatsApp via TAC)
Aprendizado: como conectar a um sistema externo real sem que ele vaze pro
núcleo de decisão.
Critério de aceite (cumprido): `TACCanal` funcionando, primeira mensagem
real indo e voltando pelo WhatsApp (Sandbox, com a Conversation e o
participante criados à mão — o Sandbox não suporta autocreation).

O que a fase entregou além do previsto, quase tudo descoberto porque houve
teste com tráfego real:

- `webhook.py`, a entrada do canal. Não é porta nova: a porta `Canal` cobre
  só a saída, de propósito.
- `RepositorioConversas`, com duas implementações. O estado das conversas
  vivia num dicionário do processo, e isso não sobrevivia a um restart nem
  a um segundo worker. Agora mora no próprio Twilio — histórico nas
  mensagens da Conversation, status nos `attributes` dela.
- Guarda de conversa escalada. Depois do handoff a IA continuava
  respondendo por cima do atendente, e uma segunda decisão de escalar
  estourava HTTP 500 — que o Twilio reenvia, virando erro em laço.
- Aviso ao cliente antes de escalar. Escalar em silêncio deixava a pessoa
  sem saber se a mensagem sequer chegou.
- Direcionamento por domínio. Recuperação vazia escalava na hora, então
  qualquer "oi" ia para a fila humana; agora o agente diz o que sabe tratar
  e dá a chance de reformular.
- Correção do contador de tentativas, que somava todas as respostas da IA:
  um cliente satisfeito com quatro perguntas era transferido na quarta.

Três armadilhas do Twilio que custaram tempo e ficam registradas:

- envio por `conversations.v1.conversations(sid)` resolve no Conversation
  Service **padrão**; conversa de outro service devolve 404;
- mensagem criada pela API só dispara webhook com o cabeçalho
  `X-Twilio-Webhook-Enabled: true`;
- o que **não** dispara na autocreation é `onMessageAdd` (pré-ação), e não o
  `onMessageAdded` que o webhook assina — os nomes enganam.

### Fase 6 — Handoff ponta a ponta
Aprendizado: como o `GatewayHandoff` é o único lugar que sabe que "escalar"
significa "Studio Flow + TaskRouter + Flex" — o resto do sistema só sabe
que "escalou".
Critério de aceite: `StudioGatewayHandoff` funcionando; teste ponta a ponta:
mensagem → IA não resolve → Task aparece no Flex com resumo.

### Fase 7 — Prova de plugabilidade
Aprendizado: ver na prática o motivo de ter separado tudo isso — trocar o
LLM sem tocar em `core/`.
Critério de aceite: `AnthropicProvedorLLM` (ou `OpenAIProvedorLLM`)
implementado; a troca acontece só no `main.py` (composition root); zero
mudança em `core/`.

## Convenções de trabalho

- Documentação em português; nomes de domínio (`Conversa`, `Mensagem`,
  `Triagem`) seguem a língua do negócio — nomes de infraestrutura podem usar
  termos técnicos em inglês onde for mais natural (ex: `FaissBaseConhecimento`).
- Branch por fase, a partir da `dev` (não da `main` — ver "Padrão de Git" no
  `CLAUDE.md`).
- Commits pequenos e focados, Conventional Commits, em português, no
  imperativo, sem trailer de coautoria de IA.
- `main` só recebe merge quando o usuário autorizar explicitamente,
  sinalizando estado pronto pra demonstração.
