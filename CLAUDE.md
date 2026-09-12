# whatsapp-ai-agent

Agente de IA para atendimento via WhatsApp (Twilio Agent Connect), com RAG
local e handoff para atendimento humano no Twilio Flex. POC construída com
Domain-Driven Design — ver `SPEC.md` pro plano completo, o modelo de
domínio e as fases.

## Contexto

Nasceu como demonstração dentro do projeto guarda-chuva de aprendizado
Twilio (repositório `twilio_project`), especificamente pra validar o
caminho "IA própria via Twilio Agent Connect" levantado no documento
"Integração de IA no atendimento via WhatsApp com o Twilio Flex". Ganhou
repositório próprio por ser uma aplicação backend com ciclo de vida
independente (Python, DDD), diferente dos Flex Plugins (React/TS) que
vivem em `twilio_project/plugins/`.

## Stack

- Python 3.11+, `uv` como gerenciador de pacotes/ambiente.
- Domínio e aplicação: Python puro, sem dependências externas.
- LLM local: Ollama (Llama 3.x) — trocável por API paga (OpenAI, Anthropic,
  Bedrock) sem tocar no domínio, ver Fase 7 do `SPEC.md`.
- RAG: LangChain + FAISS + embeddings locais (`nomic-embed-text` via Ollama).
- Canal WhatsApp / handoff: Twilio Agent Connect (TAC) + Studio + TaskRouter
  + Flex.
- Testes: `pytest`.

## Arquitetura

Domain-Driven Design com Ports & Adapters (arquitetura hexagonal):

```
domain/          <- regra de negócio pura, zero dependência externa
application/     <- casos de uso, orquestra domain + ports
infrastructure/  <- adapters concretos (Ollama, FAISS, TAC, Studio)
main.py          <- composition root: monta os adapters e injeta
```

Regra inegociável: `domain/` nunca importa de `application/` ou
`infrastructure/`. Se isso acontecer, é sinal de que algo vazou de camada.

Detalhes completos (modelo de domínio, portas, linguagem ubíqua, fases) em
`SPEC.md`.

## Convenções de trabalho

- Documentação em português; nomes de domínio seguem a linguagem ubíqua
  (também em português — ver `SPEC.md`); infraestrutura pode usar termos
  técnicos em inglês onde for mais natural.
- Cada fase do `SPEC.md` corresponde a uma entrega pequena, com checkpoint
  de validação antes de avançar pra próxima.
- Toda mudança passa por SPEC (ou uma seção dele) revisado antes do código.
- Implementação em fases pequenas, checkpoint de validação entre elas.

## Padrão de Git

Mesma convenção usada no `twilio_project`, mantida aqui pra consistência
entre sessões diferentes trabalhando no repositório.

### Branches

- Nunca commitar direto na `main`. Sempre criar branch nova a partir da
  `main` atualizada.
- Nome: `<tipo>/<escopo>-<descricao-curta-com-hifen>`, tudo minúsculo.
  - `<tipo>`: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `style`.
  - `<escopo>`: a fase ou a camada afetada (ex: `fase0`, `dominio`, `rag`).
  - Exemplos: `feat/fase0-esqueleto`, `feat/fase1-dominio`,
    `feat/fase3-ollama-provider`.

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

1. A sessão que revisa/planeja (esta) escreve ou atualiza o `SPEC.md` e
   entrega um prompt autocontido pra sessão que vai implementar.
2. A sessão que implementa (VSCode/Claude Code local) cria a branch, faz
   commits pequenos e focados, e testa localmente antes de qualquer merge.
3. Nenhuma branch é mesclada na `main` sem checkpoint de validação — você
   confirma que testou (rodando os testes e/ou testando manualmente) antes
   do merge, e idealmente volta pra esta sessão pra confirmar que o
   resultado bate com o que foi combinado no `SPEC.md`.
4. `git push`/merge pra `main` só acontece quando você pedir explicitamente
   — nenhuma sessão faz isso por conta própria.

### Documentação: o que vai pro git e o que não vai

- `SPEC.md`: vai pro git (plano formal, versionado).
- `CLAUDE.md` (este arquivo): vai pro git.
- `README.md`: vai pro git — só instruções de uso (instalação, configuração,
  como rodar, como testar), sem racional de decisão nem histórico de
  mudanças.
- `notas-internas/` (raiz do repo): **não vai pro git** — racional de
  decisões, histórico de debug, diário de aprendizado por fase. Se algo ali
  precisar virar conhecimento permanente, promove pro `SPEC.md`, pro
  `README.md` (só a parte de instrução) ou pra este arquivo.
