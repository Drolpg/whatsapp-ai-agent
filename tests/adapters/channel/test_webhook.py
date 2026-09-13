"""Testes do webhook — a entrada do canal, sem tocar no Twilio.

Usa o cliente de teste do Flask e as mesmas portas falsas do estilo de
`tests/core/test_fluxo.py`. O que se exercita aqui e a traducao: payload do
Twilio entra, `processar_mensagem_recebida` roda, resposta sai pelo canal.

A validacao de assinatura fica desligada na maioria dos testes (o cliente de
teste nao tem como assinar), mas tem uma classe so pra ela, com o validador
ligado.
"""

import pytest

from adapters.channel.webhook import ConversasEmMemoria, criar_app
from core.conversa import StatusConversa
from core.ports import RespostaLLM

AUTOR_AGENTE = "ia"
AUTH_TOKEN = "token_de_teste"
SID = "CH00000000000000000000000000000001"
ROTA = "/webhooks/twilio/mensagem"


class FakeBaseConhecimento:
    def __init__(self, trechos=None):
        self.trechos = ["a loja abre das 9h as 18h"] if trechos is None else trechos

    def buscar_trechos_relevantes(self, pergunta):
        return list(self.trechos)


class FakeProvedorLLM:
    def __init__(self, texto="Das 9h as 18h.", deve_escalar=False):
        self.resposta = RespostaLLM(texto=texto, deve_escalar=deve_escalar)
        self.chamadas = 0

    def gerar_resposta(self, mensagens, trechos_contexto):
        self.chamadas += 1
        return self.resposta


class FakeCanal:
    def __init__(self):
        self.enviadas = []

    def enviar_mensagem(self, conversa_id, texto):
        self.enviadas.append((conversa_id, texto))


class FakeGatewayHandoff:
    def __init__(self):
        self.escalonamentos = []

    def escalar(self, conversa, resumo, atributos):
        self.escalonamentos.append((conversa.conversa_id, resumo, atributos))


def _montar(trechos=None, deve_escalar=False, validar=False):
    base = FakeBaseConhecimento(trechos)
    llm = FakeProvedorLLM(deve_escalar=deve_escalar)
    canal = FakeCanal()
    handoff = FakeGatewayHandoff()
    conversas = ConversasEmMemoria()
    app = criar_app(
        base_conhecimento=base,
        provedor_llm=llm,
        canal=canal,
        gateway_handoff=handoff,
        auth_token=AUTH_TOKEN,
        autor_agente=AUTOR_AGENTE,
        conversas=conversas,
        validar_assinatura=validar,
    )
    return app.test_client(), base, llm, canal, handoff, conversas


def _payload(**extra):
    corpo = {
        "EventType": "onMessageAdded",
        "ConversationSid": SID,
        "Author": "whatsapp:+5511999999999",
        "Body": "qual o horario?",
        "MessageSid": "IM0001",
    }
    corpo.update(extra)
    return corpo


class TestMensagemDoCliente:
    def test_responde_204(self):
        cliente, *_ = _montar()

        resposta = cliente.post(ROTA, data=_payload())

        assert resposta.status_code == 204

    def test_a_resposta_da_ia_volta_pela_mesma_conversa(self):
        cliente, _, _, canal, _, _ = _montar()

        cliente.post(ROTA, data=_payload())

        assert canal.enviadas == [(SID, "Das 9h as 18h.")]

    def test_a_conversa_e_criada_na_primeira_mensagem(self):
        cliente, _, _, _, _, conversas = _montar()

        cliente.post(ROTA, data=_payload())

        assert len(conversas) == 1

    def test_a_segunda_mensagem_reusa_a_mesma_conversa(self):
        """O historico precisa sobreviver entre requisicoes HTTP."""
        cliente, _, _, _, _, conversas = _montar()

        cliente.post(ROTA, data=_payload(Body="qual o horario?"))
        cliente.post(ROTA, data=_payload(Body="e no sabado?"))

        conversa = conversas.obter_ou_criar(SID)
        assert len(conversas) == 1
        assert [m.conteudo for m in conversa.mensagens] == [
            "qual o horario?",
            "Das 9h as 18h.",
            "e no sabado?",
            "Das 9h as 18h.",
        ]

    def test_conversas_diferentes_nao_se_misturam(self):
        cliente, _, _, _, _, conversas = _montar()
        outro_sid = "CH00000000000000000000000000000002"

        cliente.post(ROTA, data=_payload())
        cliente.post(ROTA, data=_payload(ConversationSid=outro_sid))

        assert len(conversas) == 2


class TestQuandoOFluxoEscala:
    def test_aciona_o_handoff_e_nao_responde_ao_cliente(self):
        cliente, _, _, canal, handoff, _ = _montar(deve_escalar=True)

        cliente.post(ROTA, data=_payload())

        assert canal.enviadas == []
        assert [sid for sid, _, _ in handoff.escalonamentos] == [SID]

    def test_a_conversa_fica_escalada(self):
        cliente, _, _, _, _, conversas = _montar(deve_escalar=True)

        cliente.post(ROTA, data=_payload())

        assert conversas.obter_ou_criar(SID).status is StatusConversa.ESCALADA

    def test_base_vazia_escala_sem_chamar_o_llm(self):
        cliente, _, llm, _, handoff, _ = _montar(trechos=[])

        cliente.post(ROTA, data=_payload())

        assert llm.chamadas == 0
        assert len(handoff.escalonamentos) == 1


class TestOQueOWebhookIgnora:
    def test_a_propria_mensagem_do_agente(self):
        """Sem isto o agente responde a si mesmo, em laco infinito.

        O Twilio dispara onMessageAdded tambem quando somos nos que postamos.
        """
        cliente, _, llm, canal, _, _ = _montar()

        resposta = cliente.post(ROTA, data=_payload(Author=AUTOR_AGENTE))

        assert resposta.status_code == 204
        assert llm.chamadas == 0
        assert canal.enviadas == []

    def test_outros_tipos_de_evento(self):
        cliente, _, llm, _, _, _ = _montar()

        cliente.post(ROTA, data=_payload(EventType="onConversationAdded"))

        assert llm.chamadas == 0

    def test_mensagem_sem_texto(self):
        cliente, _, llm, _, _, _ = _montar()

        cliente.post(ROTA, data=_payload(Body="   "))

        assert llm.chamadas == 0

    def test_payload_sem_conversation_sid(self):
        cliente, _, llm, _, _, _ = _montar()

        resposta = cliente.post(ROTA, data=_payload(ConversationSid=""))

        assert resposta.status_code == 204
        assert llm.chamadas == 0


class TestValidacaoDeAssinatura:
    """Com o validador ligado, payload sem assinatura valida nao passa."""

    def test_requisicao_sem_assinatura_e_recusada(self):
        cliente, _, llm, _, _, _ = _montar(validar=True)

        resposta = cliente.post(ROTA, data=_payload())

        assert resposta.status_code == 403
        assert llm.chamadas == 0

    def test_assinatura_errada_e_recusada(self):
        cliente, _, llm, _, _, _ = _montar(validar=True)

        resposta = cliente.post(
            ROTA, data=_payload(), headers={"X-Twilio-Signature": "nao-e-valida"}
        )

        assert resposta.status_code == 403
        assert llm.chamadas == 0

    def test_assinatura_correta_passa(self):
        """Assina o payload como o Twilio assinaria, com o mesmo auth token."""
        from twilio.request_validator import RequestValidator

        cliente, _, llm, canal, _, _ = _montar(validar=True)
        corpo = _payload()
        url = f"http://localhost{ROTA}"
        assinatura = RequestValidator(AUTH_TOKEN).compute_signature(url, corpo)

        resposta = cliente.post(
            ROTA,
            data=corpo,
            headers={"X-Twilio-Signature": assinatura},
            base_url="http://localhost",
        )

        assert resposta.status_code == 204
        assert llm.chamadas == 1
        assert canal.enviadas == [(SID, "Das 9h as 18h.")]


class TestSaude:
    def test_responde_ok(self):
        cliente, *_ = _montar()

        assert cliente.get("/saude").status_code == 200
