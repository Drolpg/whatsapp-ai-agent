# whatsapp-ai-agent

Agente de IA para atendimento via WhatsApp (Twilio Agent Connect), com RAG
local e handoff para atendimento humano no Twilio Flex.

O quê e por quê estão no [spec.md](spec.md); a arquitetura técnica, no
[plan.md](plan.md); as fases e critérios de aceite, no [tasks.md](tasks.md);
as convenções de trabalho, no [CLAUDE.md](CLAUDE.md).

> **Status:** Fases 0 a 3.1 mescladas na `dev` (núcleo de decisão, portas,
> fluxo completo, LLM local e escalonamento estruturado); Fase 4 (RAG) em
> revisão. Ainda não há canal real — o agente não fala com o WhatsApp até a
> Fase 5. Ver `tasks.md` pro detalhe de cada fase.

## Requisitos

- Python 3.11 ou superior
- [uv](https://docs.astral.sh/uv/) para gerenciar o ambiente e as dependências
- [Ollama](https://ollama.com) rodando localmente, com dois modelos
  baixados — necessário a partir da Fase 3:
  `ollama pull llama3.2:3b` (respostas) e
  `ollama pull nomic-embed-text` (embeddings do RAG)

## Instalação

```bash
git clone https://github.com/Drolpg/whatsapp-ai-agent.git
cd whatsapp-ai-agent
uv sync
```

O `uv sync` cria o virtualenv em `.venv/` e instala as dependências a partir
do `uv.lock`. Não é preciso ativar o ambiente manualmente: use `uv run`.

## Configuração

Copie o arquivo de exemplo e preencha os valores:

```bash
cp .env.example .env
```

As variáveis do Ollama já são usadas a partir da Fase 3. As do Twilio
serão necessárias a partir da Fase 5. O `.env` não vai pro git.

## Base de conhecimento

Antes de subir o agente, construa o índice vetorial a partir dos
documentos em `data/documentos/`:

```bash
uv run python scripts/ingerir_documentos.py
```

O índice vai para `data/faiss_index/` e não é versionado — rode o script
de novo sempre que os documentos mudarem.

## Como rodar os testes

```bash
uv run pytest
```

A suíte cobre `core/` (`Conversa`, `Mensagem`, `TriagemService`,
`processar_mensagem_recebida`) inteiramente com objetos fake, sem rede — e
o adapter `OllamaProvedorLLM` (Fase 3) contra um Ollama real. Os testes do
adapter Ollama pulam automaticamente (`SKIPPED`, não falham) se não houver
um Ollama rodando localmente ou sem nenhum modelo baixado.

## Como executar

```bash
uv run python main.py
```

O `main.py` é o composition root e ainda não faz nada — o servidor sobe a
partir da Fase 5.
