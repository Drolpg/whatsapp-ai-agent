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

1. **Túnel**: `cloudflared tunnel --url http://localhost:5000` (ou
   `ngrok http 5000`) — anote a URL `https://...` gerada.
2. **Webhook do Conversation Service**: aponte o service do POC para o
   túnel. O filtro `onMessageAdded` é o que importa:

   ```bash
   curl -X POST "https://conversations.twilio.com/v1/Services/$SERVICE_SID/Configuration/Webhooks" \
     -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" \
     -d "Filters=onMessageAdded" \
     -d "PostWebhookUrl=https://<seu-túnel>/webhooks/twilio/mensagem" \
     -d "Method=POST"
   ```

3. **Pareie seu número com o sandbox**: no console, em *Messaging → Try it
   out → Send a WhatsApp message*, pegue o código e mande
   `join <duas-palavras>` do seu WhatsApp para `+1 415 523 8886`.
4. **Crie a Conversation e o participante** — este passo é obrigatório com
   o sandbox, ver a nota abaixo:

   ```python
   conv = client.conversations.v1.services(SERVICE_SID).conversations.create()
   client.conversations.v1.services(SERVICE_SID).conversations(conv.sid).participants.create(
       messaging_binding_address="whatsapp:+55SEUNUMERO",
       messaging_binding_proxy_address="whatsapp:+14155238886",
   )
   ```

5. Mande uma mensagem pelo WhatsApp. Uma pergunta coberta pela base
   (`qual o horário de atendimento?`) deve voltar respondida; uma que a
   base não cobre (`qual a política de reembolso?`) deve escalar — e o
   escalonamento aparece no log do servidor até a Fase 6 existir.

> **O sandbox não suporta autocreation.** Tentar registrar
> `whatsapp:+14155238886` via *Address Configuration* devolve `409
> Conflict`: o endereço precisa pertencer à sua conta, e o número do
> sandbox é da Twilio. Por isso o passo 4 — com um número WhatsApp próprio,
> a autocreation cuidaria disso.
> Ver [Trying Out WhatsApp with Conversations](https://www.twilio.com/docs/conversations/use-twilio-sandbox-for-whatsapp).

> **Mensagem criada pela API não dispara webhook** a menos que a chamada
> envie `X-Twilio-Webhook-Enabled: true`. Vale para testes que simulam uma
> mensagem do cliente pela API — sem o cabeçalho, o webhook simplesmente
> não é chamado e parece que a integração está quebrada.

A validação de assinatura (`X-Twilio-Signature`) fica sempre ligada em
produção. Se as requisições estiverem voltando `403`, quase sempre é a URL
que o Flask enxerga diferindo da que o Twilio chamou — confira se o túnel
está repassando os cabeçalhos `X-Forwarded-Proto` e `X-Forwarded-Host`.

> **Limitação conhecida:** as conversas ficam num dicionário em memória.
> Reiniciar o processo apaga as conversas em andamento, e rodar com mais de
> um worker faria a mesma conversa alternar entre históricos diferentes.
> É deliberado para a POC — ver o docstring de
> `adapters/channel/webhook.py`.
