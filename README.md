# whatsapp-ai-agent

Agente de IA para atendimento via WhatsApp (Twilio Agent Connect), com RAG
local e handoff para atendimento humano no Twilio Flex.

O plano completo, a decisão de arquitetura e os critérios de aceite de cada
fase estão no [SPEC.md](SPEC.md); as convenções de trabalho, no
[CLAUDE.md](CLAUDE.md).

> **Status:** Fase 0 (esqueleto). Ainda não há lógica de negócio nem testes —
> os módulos de `core/` e `adapters/` existem só com o docstring do seu papel.

## Requisitos

- Python 3.11 ou superior
- [uv](https://docs.astral.sh/uv/) para gerenciar o ambiente e as dependências

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

Nenhuma dessas variáveis é usada ainda — elas serão necessárias a partir da
Fase 3 (Ollama) e da Fase 5 (Twilio). O `.env` não vai pro git.

## Como rodar os testes

```bash
uv run pytest
```

A suíte ainda está vazia, então o pytest coleta zero testes e termina com
código de saída `5` (*no tests ran*). Isso é o resultado esperado na Fase 0 —
serve só pra confirmar que o ambiente está configurado corretamente.

## Como executar

```bash
uv run python main.py
```

O `main.py` é o composition root e ainda não faz nada — o servidor sobe a
partir da Fase 5.
