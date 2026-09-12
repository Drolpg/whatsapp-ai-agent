# SPEC — whatsapp-ai-agent

## Objetivo

POC de um agente de IA para atendimento via WhatsApp, usando o Twilio Agent
Connect (TAC) como ponte com o canal, um LLM local (Llama via Ollama) com RAG
sobre uma base de conhecimento própria, e handoff para atendimento humano no
Twilio Flex quando a IA não resolve. Objetivo duplo: (1) demonstrar pro
cliente que a solução funciona hoje, sem custo de API, e que trocar o modelo
local por uma API paga (OpenAI, Anthropic, Bedrock) no futuro é uma troca
pequena, não um projeto novo; (2) servir de estudo guiado — cada fase existe
tanto pra avançar o código quanto pra ensinar um conceito específico.

## Metodologia: Spec-Driven Development (SDD)

Este projeto segue **Spec-Driven Development**: este `SPEC.md` é a fonte
única de verdade, escrita e revisada *antes* de qualquer código, e cada fase
só é considerada pronta quando o resultado bate com os critérios de aceite
descritos aqui. Isso é diferente de escolher uma arquitetura (como DDD) —
SDD é sobre *como conduzimos o processo* (spec → implementação → validação
contra a spec), não sobre *como o código é modelado por dentro*. Já
praticávamos isso informalmente nos outros projetos do usuário
(`twilio_project`); aqui só estamos dando nome à prática e reforçando com
critérios de aceite explícitos por fase.

Papéis, sem mudança: a sessão de revisão (esta conversa) mantém o SPEC.md,
explica os conceitos e avalia cada fase entregue; a sessão de implementação
(VSCode/Claude Code local) implementa exatamente o escopo da fase corrente a
partir de um prompt autocontido, e para no checkpoint pra validação.

## Decisão de arquitetura: sem DDD

Cogitamos originalmente Domain-Driven Design completo (Entities, Value
Objects, Aggregates, linguagem ubíqua formal). Decidimos não seguir por
esse caminho: o domínio deste projeto é fino — há, na prática, uma única
decisão relevante ("a IA resolveu ou precisa escalar?") — e modelar isso com
o ferramental completo de DDD ensinaria o ritual sem o motivo real de ele
existir (não há invariante complexa nem evento de domínio que justifique).

Mantemos só a parte de DDD que resolve um problema real deste projeto:
**separar a lógica de decisão da tecnologia que a executa**, via interfaces
simples (um padrão às vezes chamado de Ports & Adapters). É o que permite a
Fase 7 — trocar o LLM local por uma API paga — ser uma troca pequena e
isolada, sem tocar na lógica de negócio.

## Termos usados no projeto

| Termo | Significado |
|---|---|
| Conversa | Uma troca de mensagens com um cliente, do início até o encerramento ou handoff. |
| Mensagem | Um item dentro de uma Conversa — quem enviou, o conteúdo, quando. |
| Triagem | O processo de decidir, a cada mensagem do cliente, se a IA responde ou se a conversa deve ser escalada. |
| Escalar / Handoff | Transferir a Conversa pra um atendente humano. |
| Base de Conhecimento | O conjunto de documentos/textos que a IA consulta pra responder (RAG). |
| Trecho | Um pedaço da Base de Conhecimento recuperado como relevante pra uma pergunta. |

## Núcleo de decisão (`core/`)

Python puro — não importa `twilio`, `langchain`, `requests` nem nada que
fale com o mundo externo. Se um teste desta pasta precisar de rede ou de um
arquivo, é sinal de que algo vazou de infraestrutura pra cá.

- **`Conversa`**: id, lista de `Mensagem`, e um status (`ATIVA`, `ESCALADA`,
  `ENCERRADA`). É o único jeito de mudar o estado de uma conversa.
- **`Mensagem`**: autor (`CLIENTE` ou `IA`), conteúdo, timestamp. Simples,
  imutável.
- **`TriagemService`**: recebe a `Conversa` e uma resposta candidata da IA, e
  decide se ela é suficiente ou se precisa escalar (ex: a IA pediu escalar
  explicitamente, ou passou de um número de tentativas sem sucesso). Não
  gera a resposta — só decide o que fazer com ela.
- **`processar_mensagem_recebida`**: a função que orquestra tudo — busca
  trechos relevantes, pede resposta ao LLM, passa pro `TriagemService`, e ou
  responde pelo canal ou aciona o handoff. Fica aqui mesmo (não precisa de
  uma camada `application/` separada pra um fluxo deste tamanho).

## Portas (interfaces que os adapters implementam)

- **`ProvedorLLM`**: `gerar_resposta(mensagens, trechos_contexto) -> str`
- **`BaseConhecimento`**: `buscar_trechos_relevantes(pergunta) -> list[str]`
- **`Canal`**: `enviar_mensagem(conversa_id, texto)` / recebimento
- **`GatewayHandoff`**: `escalar(conversa, resumo, atributos) -> None`

## Adapters (`adapters/`) — um por fase

- **`OllamaProvedorLLM`** (Fase 3): Llama local via Ollama.
- **`FaissBaseConhecimento`** (Fase 4): LangChain + embeddings locais + FAISS.
- **`TACCanal`** (Fase 5): SDK do Twilio Agent Connect.
- **`StudioGatewayHandoff`** (Fase 6): dispara o Studio Flow de handoff.
- **`AnthropicProvedorLLM`** / **`OpenAIProvedorLLM`** (Fase 7): segunda
  implementação de `ProvedorLLM`, só pra provar a troca.

## Estrutura de pastas

```
whatsapp-ai-agent/
  core/
    __init__.py
    conversa.py       # Conversa, Mensagem
    triagem.py        # TriagemService, processar_mensagem_recebida
    ports.py          # ProvedorLLM, BaseConhecimento, Canal, GatewayHandoff
  adapters/
    __init__.py
    llm/
      ollama_provider.py
      anthropic_provider.py   # fase 7
    knowledge/
      faiss_repository.py
    channel/
      tac_channel.py
    handoff/
      studio_gateway.py
  tests/
    core/
    adapters/
  docs/
    SPEC.md            # cópia/origem
  notas-internas/       # não vai pro git — racional, debug, diário
  main.py                # composition root: monta os adapters e injeta
  pyproject.toml
  .env.example
  README.md
  CLAUDE.md
```

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

### Fase 4 — RAG / Base de Conhecimento
Aprendizado: como o RAG entra como só mais um adapter, sem vazar detalhes
de embeddings/vetores pro resto do sistema.
Critério de aceite: `FaissBaseConhecimento` (LangChain + embeddings locais +
FAISS) funcionando, com script de ingestão de documentos de teste.

### Fase 5 — Canal real (WhatsApp via TAC)
Aprendizado: como conectar a um sistema externo real sem que ele vaze pro
núcleo de decisão.
Critério de aceite: `TACCanal` funcionando, primeira mensagem real indo e
voltando pelo WhatsApp (Sandbox ou número real).

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

## Fora de escopo por enquanto

- Deploy em produção real.
- Autenticação/autorização de usuários administrativos.
- Suporte a múltiplos idiomas.
- Interface de administração da Base de Conhecimento.

## Referências

- Twilio Agent Connect (documentação): twilio.com/docs/conversations/agent-connect
- Twilio — Integrating Agent Connect with Flex for Human Handoff (blog): twilio.com/en-us/blog/developers/tutorials/product/twilio-agent-connect-flex-human-handoff
- Ollama + LangChain, RAG local: markaicode.com/build-local-rag-pipeline-ollama-langchain
- What is Spec-Driven Development? (IBM): ibm.com/think/topics/spec-driven-development
- Documento "Integração de IA no atendimento via WhatsApp com o Twilio Flex" (levantamento de caminhos, entregue em 2026-09-11 no projeto `twilio_project`).
