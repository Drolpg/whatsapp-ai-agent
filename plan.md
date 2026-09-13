# plan — whatsapp-ai-agent

> Este documento é um de três: `spec.md` (o quê e por quê), `plan.md`
> (arquitetura técnica — este arquivo) e `tasks.md` (fases e critério de
> aceite). Dividido em 2026-09-13 a partir do `SPEC.md` único original —
> nada do conteúdo foi perdido, só redistribuído.

## Metodologia: Spec-Driven Development (SDD)

Este projeto segue **Spec-Driven Development**: `spec.md`, `plan.md` e
`tasks.md` juntos são a fonte única de verdade, escritos e revisados
*antes* de qualquer código, e cada fase só é considerada pronta quando o
resultado bate com o critério de aceite descrito em `tasks.md`. Isso é
diferente de escolher uma arquitetura (como DDD) — SDD é sobre *como
conduzimos o processo* (spec → implementação → validação contra a spec),
não sobre *como o código é modelado por dentro*. Já praticávamos isso
informalmente nos outros projetos do usuário (`twilio_project`); aqui só
estamos dando nome à prática e reforçando com critérios de aceite
explícitos por fase.

Papéis, sem mudança: a sessão de revisão (esta conversa) mantém `spec.md`,
`plan.md` e `tasks.md`, explica os conceitos e avalia cada fase entregue; a
sessão de implementação (VSCode/Claude Code local) implementa exatamente o
escopo da fase corrente a partir de um prompt autocontido, e para no
checkpoint pra validação.

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

## Núcleo de decisão (`core/`)

Python puro — não importa `twilio`, `langchain`, `requests` nem nada que
fale com o mundo externo. Se um teste desta pasta precisar de rede ou de um
arquivo, é sinal de que algo vazou de infraestrutura pra cá.

- **`Conversa`**: id, lista de `Mensagem`, e um status (`ATIVA`, `ESCALADA`,
  `ENCERRADA`). É o único jeito de mudar o estado de uma conversa.
- **`Mensagem`**: autor (`CLIENTE` ou `IA`), conteúdo, timestamp. Simples,
  imutável.
- **`RespostaLLM`**: o que a IA devolve — `texto` (o que iria pro cliente) e
  `deve_escalar` (se ela se considera incapaz de responder). Dois campos
  separados de propósito: o pedido de escalonamento já morou dentro do
  próprio texto, como um marcador combinado, e o modelo o corrompia (ver
  Fase 3.1).
- **`TriagemService`**: recebe a `Conversa` e a `RespostaLLM` candidata, e
  decide se ela é suficiente ou se precisa escalar (a IA marcou
  `deve_escalar`, ou passou de um número de tentativas sem sucesso). Não
  gera a resposta, não sabe quem a gerou e não lê o texto dela — só decide
  o que fazer com ela.
- **`processar_mensagem_recebida`**: a função que orquestra tudo — busca
  trechos relevantes, pede resposta ao LLM, passa pro `TriagemService`, e ou
  responde pelo canal ou aciona o handoff. Fica aqui mesmo (não precisa de
  uma camada `application/` separada pra um fluxo deste tamanho).

## Portas (interfaces que os adapters implementam)

- **`ProvedorLLM`**: `gerar_resposta(mensagens, trechos_contexto) -> RespostaLLM`
- **`BaseConhecimento`**: `buscar_trechos_relevantes(pergunta) -> list[str]`
- **`Canal`**: `enviar_mensagem(conversa_id, texto)` / recebimento
- **`GatewayHandoff`**: `escalar(conversa, resumo, atributos) -> None`

Lista vazia é resposta válida de `BaseConhecimento`: significa que nada no
acervo ajuda com aquela pergunta. É isso que permite a decisão de cobertura
da Fase 4 morar na recuperação sem mudar assinatura de porta nenhuma — o
adapter aplica o limiar de similaridade internamente e devolve `[]`, e o
núcleo trata `[]` como "escala sem nem chamar o LLM".

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
  notas-internas/       # não vai pro git — racional, debug, diário
  main.py                # composition root: monta os adapters e injeta
  pyproject.toml
  .env.example
  README.md
  CLAUDE.md
  spec.md                # o quê e por quê
  plan.md                # arquitetura técnica (este arquivo)
  tasks.md               # fases e critério de aceite
```
