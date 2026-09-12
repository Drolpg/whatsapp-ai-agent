# SPEC — whatsapp-ai-agent

## Objetivo

POC de um agente de IA para atendimento via WhatsApp, usando o Twilio Agent
Connect (TAC) como ponte com o canal, um LLM local (Llama via Ollama) com RAG
sobre uma base de conhecimento própria, e handoff para atendimento humano no
Twilio Flex quando a IA não resolve. Objetivo duplo: (1) demonstrar pro
cliente que a solução funciona hoje, sem custo de API, e que trocar o modelo
local por uma API paga (OpenAI, Anthropic, Bedrock) no futuro é uma troca
pequena, não um projeto novo; (2) servir de estudo guiado de Domain-Driven
Design (DDD) — cada fase existe tanto pra avançar o código quanto pra ensinar
um conceito específico de DDD.

## Por que DDD neste projeto

O requisito de negócio central ("hoje é Llama local, amanhã pode ser
qualquer API") é, na prática, um pedido de baixo acoplamento entre a regra de
negócio (o que decide se a IA responde ou escala) e a tecnologia que gera a
resposta (Ollama, OpenAI, Anthropic...). DDD, com a prática de **Ports &
Adapters** (arquitetura hexagonal), é o padrão desenhado exatamente pra esse
problema: o domínio define o que precisa (uma "porta"), e cada tecnologia
concreta é um "adaptador" plugável atrás dessa porta. A Fase 7 deste plano
existe só pra provar isso na prática, trocando o LLM sem tocar em nenhuma
linha de domínio.

## Linguagem ubíqua (Ubiquitous Language)

Termos do domínio, em português — é a linguagem que usaremos em nomes de
classes, métodos e commits, não só em conversa. Um dos pilares de DDD é que o
código fale a língua do negócio, não a língua do framework.

| Termo | Significado |
|---|---|
| Conversa | Uma troca de mensagens com um cliente, do início até o encerramento ou handoff. |
| Mensagem | Um item dentro de uma Conversa — quem enviou, o conteúdo, quando. |
| Triagem | O processo de decidir, a cada mensagem do cliente, se a IA responde ou se a conversa deve ser escalada. |
| Escalar / Handoff | Transferir a Conversa pra um atendente humano. |
| Base de Conhecimento | O conjunto de documentos/textos que a IA consulta pra responder (RAG). |
| Trecho | Um pedaço da Base de Conhecimento recuperado como relevante pra uma pergunta. |
| Resposta | O texto que a IA (ou o atendente) devolve ao cliente. |

## Bounded Context

Um único bounded context nesta POC: **Atendimento Assistido por IA**. Não há
necessidade de dividir em múltiplos contextos agora — o escopo é pequeno o
bastante pra caber em um.

## Modelo de domínio (camada `domain/`)

Esta camada não importa nada de fora (nem `twilio`, nem `langchain`, nem
`requests`) — é Python puro. Se um teste de domínio precisar de rede ou de
um arquivo, é sinal de que algo vazou de infraestrutura pra cá.

- **`Conversa`** (Entity, aggregate root): tem identidade (`conversa_id`),
  uma lista de `Mensagem`, e um `status` (`ATIVA`, `ESCALADA`, `ENCERRADA`).
  É o único ponto de entrada pra mudar o estado de uma conversa — nada muda
  uma `Mensagem` ou o `status` por fora dela.
- **`Mensagem`** (Value Object): imutável — autor (`CLIENTE` ou `IA`),
  conteúdo, timestamp. Dois `Mensagem` com os mesmos valores são iguais; não
  tem identidade própria.
- **`ResultadoTriagem`** (Value Object): o resultado de uma decisão de
  triagem — `RESOLVIDO` (com a resposta) ou `ESCALAR` (com o motivo).
- **`TriagemService`** (Domain Service): recebe uma `Conversa` e uma
  `Resposta` candidata da IA e decide se ela é suficiente ou se precisa
  escalar (regras de negócio puras — ex: a IA pediu escalar explicitamente,
  ou o número de tentativas sem sucesso passou de um limite). Não gera a
  resposta em si — só decide o que fazer com ela.

## Portas (camada `domain/ports.py`)

Interfaces (Protocols do Python) que o domínio e a aplicação dependem, mas
que só a infraestrutura implementa. Esse é o Dependency Inversion Principle
na prática: o domínio manda na forma do contrato, a infraestrutura obedece.

- **`ProvedorLLM`**: `gerar_resposta(mensagens, trechos_contexto) -> str`
- **`RepositorioBaseConhecimento`**: `buscar_trechos_relevantes(pergunta) -> list[Trecho]`
- **`CanalConversa`**: `enviar_mensagem(conversa_id, texto)` /
  callback de recebimento
- **`GatewayHandoff`**: `escalar(conversa, resumo, atributos) -> None`

## Casos de uso (camada `application/`)

Orquestram o domínio e as portas — não têm regra de negócio própria, só
sequenciam chamadas.

- **`ProcessarMensagemRecebida`**: recebe a mensagem, busca trechos
  relevantes (`RepositorioBaseConhecimento`), pede uma resposta ao LLM
  (`ProvedorLLM`), passa o resultado pro `TriagemService`, e ou responde
  pelo `CanalConversa` ou aciona `GatewayHandoff`.

## Adapters (camada `infrastructure/`) — um por fase

- **`OllamaProvedorLLM`** (Fase 3): implementa `ProvedorLLM` chamando um
  Llama local via Ollama.
- **`FaissRepositorioBaseConhecimento`** (Fase 4): implementa
  `RepositorioBaseConhecimento` com LangChain + embeddings locais + FAISS.
- **`TACCanalConversa`** (Fase 5): implementa `CanalConversa` usando o SDK
  do Twilio Agent Connect.
- **`StudioGatewayHandoff`** (Fase 6): implementa `GatewayHandoff` disparando
  o Studio Flow de handoff (`create_studio_handoff_tool`).
- **`AnthropicProvedorLLM`** / **`OpenAIProvedorLLM`** (Fase 7): segunda
  implementação de `ProvedorLLM`, só pra provar a troca.

## Estrutura de pastas

```
whatsapp-ai-agent/
  domain/
    __init__.py
    entidades.py        # Conversa
    value_objects.py     # Mensagem, ResultadoTriagem, Trecho
    services.py          # TriagemService
    ports.py              # ProvedorLLM, RepositorioBaseConhecimento, CanalConversa, GatewayHandoff
  application/
    __init__.py
    casos_de_uso.py       # ProcessarMensagemRecebida
  infrastructure/
    __init__.py
    llm/
      ollama_provider.py
      anthropic_provider.py   # fase 7
    knowledge/
      faiss_repository.py
    channels/
      tac_channel.py
    handoff/
      studio_gateway.py
  tests/
    domain/
    application/
    infrastructure/
  docs/
    SPEC.md              # este arquivo (cópia/origem)
    notas-internas/       # não vai pro git — racional, debug, diário
  main.py                 # composition root: monta os adapters e injeta nos casos de uso
  pyproject.toml
  .env.example
  README.md
  CLAUDE.md
```

## Fases (cada uma com objetivo de aprendizado + checkpoint)

Cada fase termina com perguntas de autoavaliação — só avançamos pra próxima
depois de você confirmar que testou e entendeu, seguindo o mesmo padrão já
usado no projeto de aprendizado Twilio (Sala de Triagem).

### Fase 0 — Esqueleto do projeto
Objetivo de aprendizado: por que as camadas ficam em pastas separadas e por
que isso importa (a regra é "domain nunca importa de infrastructure", nunca
o contrário).
Entrega: estrutura de pastas acima, módulos vazios com docstring explicando
o papel de cada um, `pyproject.toml` com só `pytest` como dependência,
`.env.example`, `README.md` de instalação. Zero lógica de negócio ainda.

### Fase 1 — Domínio puro
Objetivo de aprendizado: Entity vs. Value Object (identidade vs. igualdade
por valor), Aggregate Root, Domain Service — e por que tudo isso é testável
sem mock nenhum.
Entrega: `Conversa`, `Mensagem`, `ResultadoTriagem`, `TriagemService`
implementados e com testes unitários (sem I/O, sem framework).

### Fase 2 — Portas e caso de uso, com dublês de teste
Objetivo de aprendizado: Dependency Inversion Principle, Ports & Adapters, e
como testar um caso de uso inteiro usando implementações falsas
(in-memory) das portas, sem precisar de Ollama, Twilio ou nada real ainda.
Entrega: `ports.py`, `ProcessarMensagemRecebida`, testes de aplicação com
adapters fake.

### Fase 3 — Primeiro adapter real: LLM local
Objetivo de aprendizado: como um adapter concreto satisfaz uma porta
abstrata sem que o domínio saiba disso.
Entrega: `OllamaProvedorLLM`, testado isoladamente (chamando o Ollama de
verdade), ainda sem RAG nem Twilio.

### Fase 4 — RAG / Base de Conhecimento
Objetivo de aprendizado: como o RAG se encaixa como só mais um adapter
(`RepositorioBaseConhecimento`), sem contaminar o domínio com detalhes de
embeddings ou vetores.
Entrega: `FaissRepositorioBaseConhecimento` (LangChain + embeddings locais +
FAISS), script de ingestão de documentos.

### Fase 5 — Canal real (WhatsApp via TAC)
Objetivo de aprendizado: como conectar tudo a um sistema externo real sem
que esse sistema vaze pra dentro do domínio.
Entrega: `TACCanalConversa`, servidor rodando, primeira mensagem real indo e
voltando pelo WhatsApp (Sandbox ou número real).

### Fase 6 — Handoff ponta a ponta
Objetivo de aprendizado: como o `GatewayHandoff` é o único lugar que sabe
que "escalar" significa "Studio Flow + TaskRouter + Flex" — o resto do
sistema só sabe que "escalou".
Entrega: `StudioGatewayHandoff`, teste ponta a ponta: mensagem → IA não
resolve → Task aparece no Flex com resumo.

### Fase 7 — Prova de plugabilidade
Objetivo de aprendizado: ver com os próprios olhos o motivo de ter feito
tudo isso — trocar o LLM sem tocar em domain/application.
Entrega: `AnthropicProvedorLLM` (ou `OpenAIProvedorLLM`), troca feita só no
`main.py` (composition root), zero mudança em `domain/` ou `application/`.

## Papéis neste projeto

- **Sessão de revisão (esta conversa)**: mantém e revisa este SPEC.md,
  explica os conceitos de DDD por trás de cada fase, avalia o código
  entregue fase a fase, e entrega o prompt autocontido de cada fase pra
  sessão de implementação.
- **Sessão de implementação (VSCode/Claude Code local)**: implementa
  exatamente o escopo da fase corrente, a partir do prompt recebido, e para
  no checkpoint pra validação.
- Nenhuma fase avança sem você confirmar que rodou e entendeu a anterior.

## Convenções de trabalho

- Documentação em português; nomes de domínio (`domain/`, `application/`)
  em português, seguindo a linguagem ubíqua — nomes de infraestrutura podem
  usar termos técnicos em inglês onde for mais natural (ex: `FaissRepository`).
- Uma branch por fase: `feat/fase0-esqueleto`, `feat/fase1-dominio`, etc.
- Commits pequenos e focados, Conventional Commits, em português, no
  imperativo.
- Nenhuma fase é implementada sem o SPEC (ou a parte dela) já revisada.
- `git push`/merge pra `main` só acontece quando você pedir explicitamente.
- `notas-internas/` (racional de decisões, debug, diário de aprendizado) não
  vai pro git — mesma convenção do repositório `twilio_project`.

## Fora de escopo por enquanto

- Deploy em produção real.
- Autenticação/autorização de usuários administrativos.
- Suporte a múltiplos idiomas.
- Interface de administração da Base de Conhecimento.

## Referências

- Twilio Agent Connect (documentação): twilio.com/docs/conversations/agent-connect
- Twilio — Integrating Agent Connect with Flex for Human Handoff (blog): twilio.com/en-us/blog/developers/tutorials/product/twilio-agent-connect-flex-human-handoff
- Ollama + LangChain, RAG local: markaicode.com/build-local-rag-pipeline-ollama-langchain
- Documento "Integração de IA no atendimento via WhatsApp com o Twilio Flex" (levantamento de caminhos, entregue em 2026-09-11 no projeto `twilio_project`).
