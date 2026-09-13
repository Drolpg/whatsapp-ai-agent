# whatsapp-ai-agent

Agente de IA para atendimento via WhatsApp (Twilio Agent Connect), com RAG
local e handoff para atendimento humano no Twilio Flex. POC construída com
Spec-Driven Development — ver `spec.md` (o quê e por quê), `plan.md`
(arquitetura técnica) e `tasks.md` (fases e critério de aceite).

## Contexto

Nasceu como demonstração dentro do projeto guarda-chuva de aprendizado
Twilio (repositório `twilio_project`), especificamente pra validar o
caminho "IA própria via Twilio Agent Connect" levantado no documento
"Integração de IA no atendimento via WhatsApp com o Twilio Flex". Ganhou
repositório próprio por ser uma aplicação backend com ciclo de vida
independente (Python), diferente dos Flex Plugins (React/TS) que vivem em
`twilio_project/plugins/`.

## Stack

- Python 3.11+, `uv` como gerenciador de pacotes/ambiente.
- Núcleo de decisão: Python puro, sem dependências externas.
- LLM local: Ollama (Llama 3.x) — trocável por API paga (OpenAI, Anthropic,
  Bedrock) sem tocar no núcleo de decisão, ver Fase 7 do `tasks.md`.
- RAG: LangChain + FAISS + embeddings locais (`nomic-embed-text` via Ollama).
- Canal WhatsApp / handoff: Twilio Agent Connect (TAC) + Studio + TaskRouter
  + Flex.
- Testes: `pytest`.

## Arquitetura

Sem Domain-Driven Design completo — o domínio deste projeto é fino demais
pra justificar Entities/Aggregates/Value Objects formais (ver a seção
"Decisão de arquitetura: sem DDD" no `plan.md` pro racional). Mantemos só a
separação que resolve um problema real: núcleo de decisão isolado da
tecnologia que o executa.

```
core/       <- lógica de decisão pura, zero dependência externa
adapters/   <- implementações concretas (Ollama, FAISS, TAC, Studio)
main.py     <- composition root: monta os adapters e injeta no core
```

Regra inegociável: `core/` nunca importa de `adapters/`. Se isso acontecer,
é sinal de que algo vazou de camada.

Detalhes completos (termos do projeto, portas, fases, critérios de aceite)
em `spec.md`, `plan.md` e `tasks.md`.

## Convenções de trabalho

- Documentação em português; nomes de domínio (`Conversa`, `Mensagem`,
  `Triagem`) seguem a língua do negócio; adapters podem usar termos
  técnicos em inglês onde for mais natural (ex: `FaissBaseConhecimento`).
- Cada fase de `tasks.md` corresponde a uma entrega pequena, validada contra
  um critério de aceite explícito antes de avançar pra próxima (Spec-Driven
  Development).
- Toda mudança passa por `spec.md`/`plan.md`/`tasks.md` (ou uma seção
  deles) revisado antes do código.

## Padrão de Git

Mesma convenção usada no `twilio_project`, mantida aqui pra consistência
entre sessões diferentes trabalhando no repositório.

### Branches

- **`main`**: só recebe merge quando o usuário autorizar explicitamente,
  sinalizando que aquele estado está pronto pra demonstração (ao cliente ou
  marco do projeto). Nunca recebe uma `feat/*` diretamente.
- **`dev`**: branch de integração — toda `feat/faseX-*` nasce a partir da
  `dev` atualizada e é mesclada de volta nela após o checkpoint de
  validação da fase.
- Nome de branch: `<tipo>/<escopo>-<descricao-curta-com-hifen>`, tudo
  minúsculo.
  - `<tipo>`: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `style`.
  - `<escopo>`: a fase ou a camada afetada (ex: `fase0`, `core`, `rag`).
  - Exemplos: `feat/fase0-esqueleto`, `feat/fase1-core`,
    `feat/fase3-ollama-provider`.
- Fluxo: `feat/faseX-*` → `dev` (após checkpoint) → `main` (só quando o
  usuário autorizar explicitamente).

### Commits

Formato (Conventional Commits):

```
<tipo>(<escopo>): <descrição curta, em português, no imperativo>

<corpo opcional — o quê e por quê, não como>
```

- Commits pequenos e focados — um commit por mudança logicamente coesa.
- **Sem assinatura/trailer de autoria de IA nos commits** (nem
  `Co-Authored-By: Claude`, nem menção equivalente) — decisão explícita do
  usuário. Se a ferramenta adicionar isso por padrão, remova antes de
  commitar.

### Fluxo entre sessões paralelas

1. A sessão que revisa/planeja (esta) escreve ou atualiza `spec.md`,
   `plan.md` e/ou `tasks.md` e entrega um prompt autocontido pra sessão que
   vai implementar.
2. A sessão que implementa (VSCode/Claude Code local) cria a branch a
   partir da `dev`, faz commits pequenos e focados, e testa localmente
   antes de qualquer merge.
3. Nenhuma branch é mesclada na `dev` sem o critério de aceite da fase
   cumprido — você confirma que testou antes do merge, e idealmente volta
   pra esta sessão pra confirmar que o resultado bate com `tasks.md`.
4. `git push`/merge pra `main` só acontece quando você pedir explicitamente
   — nenhuma sessão faz isso por conta própria.

### Documentação: o que vai pro git e o que não vai

- `spec.md`, `plan.md`, `tasks.md`: vão pro git (plano formal, versionado
  — divididos em três documentos desde 2026-09-13; ver a nota no topo de
  cada um).
- `CLAUDE.md` (este arquivo): vai pro git.
- `README.md`: vai pro git — só instruções de uso (instalação, configuração,
  como rodar, como testar), sem racional de decisão nem histórico de
  mudanças.
- `notas-internas/` (raiz do repo): **não vai pro git** — racional de
  decisões, histórico de debug, diário de aprendizado por fase. Se algo ali
  precisar virar conhecimento permanente, promove pro `spec.md`/`plan.md`/
  `tasks.md`, pro `README.md` (só a parte de instrução) ou pra este
  arquivo.
