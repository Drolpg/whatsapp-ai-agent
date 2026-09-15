"""`TACCanal` — implementa `Canal` via Twilio Agent Connect / Conversations.

Saida do WhatsApp: posta a resposta da IA na Conversation do Twilio, que se
encarrega de entregar no canal em que o cliente esta.

Este e o unico lugar do sistema que conhece `TWILIO_ACCOUNT_SID`,
`TWILIO_AUTH_TOKEN` e o formato da API do Twilio. A licao da Fase 5 e essa:
conectar um sistema externo real sem deixar que ele vaze pro nucleo de
decisao. A entrada — mensagens do cliente chegando — mora em `webhook.py`,
porque a porta `Canal` cobre so a saida (ver o docstring dela em
`core/ports.py`).

O QUE `conversa_id` E, DO LADO DO TWILIO
E o **Conversation SID** (`CHxxxxxxxx...`), e a escolha nao e arbitraria:

- e o identificador que o Twilio manda em todo webhook `onMessageAdded`
  (campo `ConversationSid`), entao a entrada ja o tem em maos;
- e exatamente o que o endpoint de envio precisa na URL
  (`/v1/Conversations/{sid}/Messages`), entao a saida tambem;
- e estavel durante toda a vida da conversa.

Com isso nao existe tabela de-para entre "id do nosso lado" e "id do lado do
Twilio": os dois sao o mesmo, e `Conversa.conversa_id` carrega o valor do
Twilio direto. O preco e que o `core/` guarda uma string cujo formato vem de
um fornecedor — mas ele a trata como identificador opaco, nunca a interpreta,
entao trocar de canal depois e trocar o que se coloca ali, sem mudar regra
nenhuma.

Endpoint confirmado na documentacao oficial:
https://www.twilio.com/docs/conversations/api/conversation-message-resource
"""

from twilio.rest import Client

AUTOR_AGENTE_PADRAO = "ia"
"""Valor do campo `Author` nas mensagens que este agente posta.

Serve pra duas coisas. Na conversa, identifica quem falou. E, mais
importante, e o que o webhook usa pra ignorar as proprias mensagens: o
Twilio dispara `onMessageAdded` tambem quando *nos* postamos, e sem esse
filtro o agente responderia a si mesmo em laco (ver `webhook.py`).
"""

LIMITE_CARACTERES_TWILIO = 1600
"""Tamanho maximo de `Body` aceito pela API de mensagens do Twilio."""


class TACCanal:
    """Entrega mensagens ao cliente por uma Conversation do Twilio.

    Como os outros adapters, recebe a configuracao pronta pelo construtor e
    nunca le `os.environ` — quem traduz ambiente em configuracao e o
    `main.py`.

    Nao herda de `core.ports.Canal`: satisfaz a porta por ter o metodo com a
    forma certa, que e o que `Protocol` verifica.
    """

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        autor_agente: str = AUTOR_AGENTE_PADRAO,
        conversation_service_sid: str | None = None,
    ) -> None:
        self.account_sid = account_sid
        self.autor_agente = autor_agente
        self.conversation_service_sid = conversation_service_sid
        self._cliente = Client(account_sid, auth_token)

    def enviar_mensagem(self, conversa_id: str, texto: str) -> None:
        """Posta `texto` na Conversation `conversa_id`.

        Deixamos qualquer erro do Twilio subir, ao contrario do que o
        `OllamaProvedorLLM` faz com falha de rede. A diferenca e o que da pra
        fazer a respeito: quando o LLM falha, ainda existe um plano B util
        (escalar pro humano). Quando o *canal* falha, nao ha plano B — e por
        ele que qualquer resposta sairia, inclusive um aviso de erro.
        Engolir a excecao aqui so transformaria "a mensagem nao chegou" em
        "a mensagem nao chegou e ninguem ficou sabendo".
        """
        self._conversa(conversa_id).messages.create(
            author=self.autor_agente,
            body=texto[:LIMITE_CARACTERES_TWILIO],
        )

    def _conversa(self, conversa_id: str):
        """Resolve a conversa no service certo.

        Este detalhe custou caro pra descobrir. `conversations.v1.conversations(sid)`
        procura a conversa no Conversation Service *padrao* da conta. Uma
        conversa criada dentro de outro service — o do POC, por exemplo — nao
        existe nesse caminho, e o Twilio devolve 404 (erro 20404).

        O sintoma era enganoso: a IA respondia certo, mas a resposta nunca
        chegava ao cliente, e o webhook estourava 500 no fim do processamento.
        Os testes de integracao nao pegaram porque a conversa de teste tinha
        sido criada no service padrao, onde o caminho curto funciona.

        Com `conversation_service_sid` definido, usamos o caminho com escopo
        de service, que e o correto em qualquer um dos dois casos.
        """
        v1 = self._cliente.conversations.v1
        if self.conversation_service_sid:
            return v1.services(self.conversation_service_sid).conversations(conversa_id)
        return v1.conversations(conversa_id)
