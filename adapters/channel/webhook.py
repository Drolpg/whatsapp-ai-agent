"""Entrada do canal: o endpoint HTTP que o Twilio chama.

A porta `Canal` cobre so a saida, de proposito — o docstring dela em
`core/ports.py` diz que "quem recebe e a implementacao, que chama
`processar_mensagem_recebida`". Este modulo e essa implementacao: traduz o
webhook do Twilio pros termos do projeto e aciona o fluxo. Nao e porta nova
e nao muda contrato nenhum.

POR QUE FLASK
O fluxo inteiro e sincrono e bloqueante — `requests` pro Ollama, busca no
FAISS, chamada ao Twilio. Nada disso e await-avel, entao o async do FastAPI
nao compraria concorrencia de verdade: cada requisicao iria pra um
threadpool de qualquer jeito, com uma camada a mais no meio. Flask faz o que
precisamos (form-encoded, que e o formato que o Twilio manda, e um cliente
de teste embutido) sem trazer Pydantic nem ASGI junto. Se um dia o
`ProvedorLLM` virar streaming, vale reabrir a conversa.

LIMITACAO CONHECIDA: A PRIMEIRA MENSAGEM DE UM CLIENTE NOVO
`onMessageAdded` nao dispara durante a autocreation — quando o Twilio cria a
Conversation por causa de uma mensagem que chegou, o evento da propria
mensagem que a criou nao e enviado. Com um numero WhatsApp proprio (que usa
autocreation), a primeira pergunta de um cliente novo cria a conversa e
*nao* chega aqui: o cliente so seria atendido a partir da segunda mensagem.

Na prova da Fase 5 isso nao apareceu porque a Conversation foi criada a mao,
que e o caminho obrigatorio com o Sandbox. Tratar esse caso provavelmente
significa assinar tambem `onConversationAdded` e ler a primeira mensagem
pela API — ainda nao feito.
Ver https://www.twilio.com/docs/conversations/inbound-autocreation

LIMITACAO CONHECIDA: ESTADO EM MEMORIA
As `Conversa` vivem num dicionario no processo (`ConversasEmMemoria`). Isso
e deliberado pra POC e tem consequencias reais:

- reiniciar o processo apaga todas as conversas em andamento;
- com mais de um worker (gunicorn -w 2, varias instancias), cada um teria
  sua propria copia, e a mesma conversa alternaria entre historicos
  diferentes — o limite de tentativas da triagem pararia de funcionar;
- nao ha expiracao: o dicionario so cresce.

Nao formalizamos isso como porta (um `RepositorioConversas`) porque seria
decidir sozinho uma mudanca de arquitetura que o resto do projeto herdaria.
Quando persistencia entrar de fato no escopo, e essa a discussao a ter.
"""

from datetime import datetime, timezone

from flask import Flask, Response, request
from twilio.request_validator import RequestValidator

from core.conversa import Conversa
from core.triagem import TriagemService, processar_mensagem_recebida

EVENTO_MENSAGEM_ADICIONADA = "onMessageAdded"
"""Unico evento do Twilio que nos interessa. Os outros sao ignorados."""


class ConversasEmMemoria:
    """Guarda as `Conversa` vivas por id, so enquanto o processo existir.

    Ver a limitacao documentada no topo do modulo. A interface e mantida
    minima de proposito: `obter_ou_criar` e a unica coisa que o webhook
    precisa, e quanto menor a superficie, mais facil de trocar depois.
    """

    def __init__(self) -> None:
        self._por_id: dict[str, Conversa] = {}

    def obter_ou_criar(self, conversa_id: str) -> Conversa:
        if conversa_id not in self._por_id:
            self._por_id[conversa_id] = Conversa(conversa_id=conversa_id)
        return self._por_id[conversa_id]

    def __len__(self) -> int:
        return len(self._por_id)


def criar_app(
    base_conhecimento,
    provedor_llm,
    canal,
    gateway_handoff,
    auth_token: str,
    autor_agente: str,
    triagem: TriagemService | None = None,
    conversas: ConversasEmMemoria | None = None,
    validar_assinatura: bool = True,
) -> Flask:
    """Monta o app Flask com as portas ja resolvidas.

    Recebe tudo pronto, como os adapters: quem escolhe as implementacoes
    concretas e le o ambiente e o `main.py`. E o que permite um teste montar
    o app com portas falsas e sem tocar no Twilio.

    `validar_assinatura=False` existe pro cliente de teste, que nao tem como
    assinar a requisicao. Em producao fica sempre ligado — o `main.py` nunca
    passa esse parametro.
    """
    app = Flask(__name__)
    # `is None` e nao `or`: ConversasEmMemoria define __len__, entao uma
    # instancia vazia e falsy — com `or`, o objeto recebido seria descartado
    # e trocado por um novo, e o estado das conversas iria pro limbo.
    triagem = TriagemService() if triagem is None else triagem
    conversas = ConversasEmMemoria() if conversas is None else conversas
    validador = RequestValidator(auth_token)

    @app.post("/webhooks/twilio/mensagem")
    def receber_mensagem() -> Response:
        if validar_assinatura and not _assinatura_confere(validador):
            return Response("assinatura invalida", status=403)

        if request.form.get("EventType") != EVENTO_MENSAGEM_ADICIONADA:
            return Response("", status=204)

        autor = request.form.get("Author", "")
        if autor == autor_agente:
            # O Twilio dispara onMessageAdded tambem quando *nos* postamos.
            # Sem este filtro o agente responderia a propria resposta, em laco.
            return Response("", status=204)

        conversa_id = request.form.get("ConversationSid", "")
        texto = request.form.get("Body", "")
        if not conversa_id or not texto.strip():
            return Response("", status=204)

        processar_mensagem_recebida(
            conversa=conversas.obter_ou_criar(conversa_id),
            texto_cliente=texto,
            timestamp=_agora(request.form.get("DateCreated")),
            base_conhecimento=base_conhecimento,
            provedor_llm=provedor_llm,
            triagem=triagem,
            canal=canal,
            gateway_handoff=gateway_handoff,
        )
        return Response("", status=204)

    @app.get("/saude")
    def saude() -> Response:
        return Response("ok", status=200)

    app.conversas = conversas
    return app


def _assinatura_confere(validador: RequestValidator) -> bool:
    """Confere o `X-Twilio-Signature` contra a URL e o corpo da requisicao.

    Sem isso, um endpoint exposto na internet aceita payload de qualquer um
    se passando pelo Twilio — e o payload manda o agente responder a quem
    quiser, no numero que quiser.

    A URL precisa ser byte a byte a que o Twilio chamou. Atras de proxy ou
    tunel (ngrok), `request.url` pode vir como `http://` enquanto o Twilio
    chamou `https://`; e por isso que se configura `ProxyFix` no `main.py`.
    """
    return validador.validate(
        request.url,
        request.form.to_dict(),
        request.headers.get("X-Twilio-Signature", ""),
    )


def _agora(date_created: str | None) -> datetime:
    """Usa o horario que o Twilio carimbou; cai pro relogio local se faltar.

    O `core/` nao tem relogio proprio de proposito (ver `Mensagem`), entao e
    aqui, na borda, que o horario entra no sistema.
    """
    if date_created:
        try:
            return datetime.fromisoformat(date_created.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)
