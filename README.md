# whatsapp-ai-agent

Agente de IA para atendimento via WhatsApp (Twilio Agent Connect), com RAG
local e handoff para atendimento humano no Twilio Flex.

O quê e por quê estão no [spec.md](spec.md); a arquitetura técnica, no
[plan.md](plan.md); as fases e critérios de aceite, no [tasks.md](tasks.md);
as convenções de trabalho, no [CLAUDE.md](CLAUDE.md).

> **Status:** Fases 0-3 concluídas e mescladas na `dev` (núcleo de decisão,
> portas, fluxo completo com adapters fake, e o primeiro adapter real —
> `OllamaProvedorLLM`). Aguardando validação de modelo antes da Fase 4
> (RAG). Ver `tasks.md` pro detalhe de cada fase.

## Requisitos

- Python 3.11 ou superior
- [uv](https://docs.astral.sh/uv/) para gerenciar o ambiente e as dependências
- [Ollama](https://ollama.com) rodando localmente, com um modelo baixado
  (ver `.env.example`) — necessário a partir da Fase 3

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

As variáveis do Ollama (`OLLAMA_BASE_URL`, `OLLAMA_MODEL`) já são usadas a
partir da Fase 3. As do Twilio serão necessárias a partir da Fase 5. O
`.env` não vai pro git.

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
