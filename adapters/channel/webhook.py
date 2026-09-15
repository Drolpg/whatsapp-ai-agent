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

SOBRE A PRIMEIRA MENSAGEM DE UM CLIENTE NOVO
Ela chega aqui normalmente. Chegamos a documentar o contrario, por confundir
dois nomes parecidos: o que *nao* dispara durante a autocreation e
`onMessageAdd` (pre-acao, sem o "ed"), nao o `onMessageAdded` que este
webhook assina. Ver
https://www.twilio.com/docs/conversations/inbound-autocreation

ONDE VIVE O ESTADO
Numa implementacao de `RepositorioConversas`, injetada. `ConversasEmMemoria`
serve testes e execucao local; em producao o `main.py` injeta a versao que
guarda tudo na propria Conversation do Twilio, e ai o agente nao tem estado
proprio nenhum — reiniciar nao apaga conversa, e varios workers leem a mesma
verdade.
"""

from datetime import datetime, timezone

from flask import Flask, Response, request
from twilio.request_validator import RequestValidator

from core.conversa import Conversa
from core.triagem import TriagemService, processar_mensagem_recebida

EVENTO_MENSAGEM_ADICIONADA = "onMessageAdded"
"""Unico evento do Twilio que nos interessa. Os outros sao ignorados."""


class ConversasEmMemoria:
    """Implementacao de `RepositorioConversas` que vive no processo.

    Boa pra teste e pra rodar local sem Twilio. Nao serve pra producao:
    reiniciar apaga tudo, e com mais de um worker cada um teria a sua propria
    versao da mesma conversa. Pra isso existe a implementacao que guarda o
    estado no proprio Twilio.

    `salvar` nao faz nada porque nao precisa: os objetos sao os mesmos, entao
    o que o fluxo mudou ja esta refletido. Ela existe pra cumprir a porta —
    e pra que trocar de implementacao nao mude o codigo de quem chama.
    """

    def __init__(self) -> None:
        self._por_id: dict[str, Conversa] = {}

    def obter_ou_criar(self, conversa_id: str) -> Conversa:
        if conversa_id not in self._por_id:
            self._por_id[conversa_id] = Conversa(conversa_id=conversa_id)
        return self._por_id[conversa_id]

    def salvar(self, conversa: Conversa) -> None:
        self._por_id[conversa.conversa_id] = conversa

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
    conversas=None,
    validar_assinatura: bool = True,
) -> Flask:
    """Monta o app Flask com as portas ja resolvidas.

    Recebe tudo pronto, como os adapters: quem escolhe as implementacoes
    concretas e le o ambiente e o `main.py`. E o que permite um teste montar
    o app com portas falsas e sem tocar no Twilio.

    `conversas` e a implementacao de `RepositorioConversas`. Omitida, cai na
    de memoria, util pra teste e pra rodar local.

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
            app.logger.warning("recusado: assinatura invalida")
            return Response("assinatura invalida", status=403)

        evento = request.form.get("EventType")
        if evento != EVENTO_MENSAGEM_ADICIONADA:
            app.logger.info("ignorado: EventType=%s", evento)
            return Response("", status=204)

        autor = request.form.get("Author", "")
        if autor == autor_agente:
            # O Twilio dispara onMessageAdded tambem quando *nos* postamos.
            # Sem este filtro o agente responderia a propria resposta, em laco.
            app.logger.info("ignorado: mensagem do proprio agente")
            return Response("", status=204)

        conversa_id = request.form.get("ConversationSid", "")
        texto = request.form.get("Body", "")
        if not conversa_id or not texto.strip():
            app.logger.info(
                "ignorado: sem conversa ou sem texto (campos recebidos: %s)",
                sorted(request.form.keys()),
            )
            return Response("", status=204)

        conversa = conversas.obter_ou_criar(conversa_id)
        app.logger.info(
            "processando conversa=%s status=%s autor=%s texto=%r",
            conversa_id,
            conversa.status.value,
            autor,
            texto[:60],
        )
        resultado = processar_mensagem_recebida(
            conversa=conversa,
            texto_cliente=texto,
            timestamp=_agora(request.form.get("DateCreated")),
            base_conhecimento=base_conhecimento,
            provedor_llm=provedor_llm,
            triagem=triagem,
            canal=canal,
            gateway_handoff=gateway_handoff,
        )
        conversas.salvar(conversa)
        app.logger.info(
            "decisao=%s motivo=%s", resultado.decisao.value, resultado.motivo or "-"
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
