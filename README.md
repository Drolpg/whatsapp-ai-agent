# whatsapp-ai-agent

Agente de IA para atendimento via WhatsApp (Twilio Agent Connect), com RAG
local e handoff para atendimento humano no Twilio Flex.

O quê e por quê estão no [spec.md](spec.md); a arquitetura técnica, no
[plan.md](plan.md); as fases e critérios de aceite, no [tasks.md](tasks.md);
as convenções de trabalho, no [CLAUDE.md](CLAUDE.md).

> **Status:** Fases 0 a 4 mescladas na `dev`; Fase 5 (canal WhatsApp) em
> revisão. O handoff para atendimento humano só existe a partir da Fase 6 —
> até lá, um escalonamento é registrado no log em vez de virar Task no
> Flex. Ver `tasks.md` pro detalhe de cada fase.

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

Sobe o webhook em `http://localhost:5000`. O `main.py` é o composition root:
é o único lugar que lê variáveis de ambiente e escolhe quais adapters usar.

### Ligando ao WhatsApp

O Twilio precisa alcançar o webhook, então numa máquina local é preciso
expor a porta:

1. **Túnel**: `ngrok http 5000` — anote a URL `https://...` gerada.
2. **Sandbox do WhatsApp**: no console do Twilio, em *Messaging → Try it
   out → Send a WhatsApp message*, siga as instruções para parear seu
   número com o sandbox (enviar `join <duas-palavras>` para o número do
   sandbox).
3. **Webhook**: no Conversation Service usado pelo sandbox, configure o
   webhook `onMessageAdded` para
   `https://<seu-túnel>/webhooks/twilio/mensagem`, método `POST`.
4. Mande uma mensagem pelo WhatsApp para o número do sandbox. Uma pergunta
   coberta pela base (`qual o horário de atendimento?`) deve voltar
   respondida; uma que a base não cobre (`qual a política de reembolso?`)
   deve escalar — e o escalonamento aparece no log do servidor até a Fase 6
   existir.

A validação de assinatura (`X-Twilio-Signature`) fica sempre ligada em
produção. Se as requisições estiverem voltando `403`, quase sempre é a URL
que o Flask enxerga diferindo da que o Twilio chamou — confira se o túnel
está repassando os cabeçalhos `X-Forwarded-Proto` e `X-Forwarded-Host`.

> **Limitação conhecida:** as conversas ficam num dicionário em memória.
> Reiniciar o processo apaga as conversas em andamento, e rodar com mais de
> um worker faria a mesma conversa alternar entre históricos diferentes.
> É deliberado para a POC — ver o docstring de
> `adapters/channel/webhook.py`.
