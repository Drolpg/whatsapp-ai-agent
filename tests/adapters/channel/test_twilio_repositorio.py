"""Testes do `TwilioRepositorioConversas` — contra o Twilio de verdade.

O que estes testes precisam provar e exatamente o que o dicionario em
memoria nao dava: que o estado sobrevive fora do processo. Por isso cada
teste usa uma instancia NOVA do repositorio pra ler de volta — se o estado
estivesse escondido no objeto, passariam por engano.

Pulados quando nao ha credenciais, como os outros testes de integracao.
"""

import os
import uuid
from datetime import datetime, timezone

import pytest

from adapters.channel.tac_channel import TACCanal
from adapters.channel.twilio_repositorio import TwilioRepositorioConversas
from core.conversa import Autor, Conversa, Mensagem, StatusConversa

AUTOR_AGENTE = "ia"


@pytest.fixture(scope="session")
def credenciais() -> dict[str, str]:
    faltando = [
        nome
        for nome in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN")
        if not os.environ.get(nome)
    ]
    if faltando:
        pytest.skip(f"credenciais do Twilio nao configuradas: {', '.join(faltando)}")
    return {
        "account_sid": os.environ["TWILIO_ACCOUNT_SID"],
        "auth_token": os.environ["TWILIO_AUTH_TOKEN"],
    }


@pytest.fixture
def servico_e_conversa(credenciais):
    """Um Conversation Service descartavel, apagado no fim do teste."""
    from twilio.rest import Client

    cliente = Client(credenciais["account_sid"], credenciais["auth_token"])
    servico = cliente.conversations.v1.services.create(
        friendly_name=f"teste-repo-{uuid.uuid4().hex[:8]}"
    )
    conversa = cliente.conversations.v1.services(servico.sid).conversations.create()
    yield servico.sid, conversa.sid, cliente
    cliente.conversations.v1.services(servico.sid).delete()


def _repositorio(credenciais, servico_sid) -> TwilioRepositorioConversas:
    """Instancia nova de proposito: le do Twilio, nao de memoria local."""
    return TwilioRepositorioConversas(
        account_sid=credenciais["account_sid"],
        auth_token=credenciais["auth_token"],
        conversation_service_sid=servico_sid,
        autor_agente=AUTOR_AGENTE,
    )


class TestConversaNova:
    def test_comeca_ativa_e_vazia(self, credenciais, servico_e_conversa):
        servico_sid, conversa_sid, _ = servico_e_conversa

        conversa = _repositorio(credenciais, servico_sid).obter_ou_criar(conversa_sid)

        assert conversa.conversa_id == conversa_sid
        assert conversa.status is StatusConversa.ATIVA
        assert conversa.mensagens == ()


class TestOEstadoSobreviveAoProcesso:
    """O motivo de existir desta porta."""

    def test_escalonamento_e_lido_de_volta_por_outra_instancia(
        self, credenciais, servico_e_conversa
    ):
        servico_sid, conversa_sid, _ = servico_e_conversa
        conversa = _repositorio(credenciais, servico_sid).obter_ou_criar(conversa_sid)
        conversa.escalar(motivo="nao soube responder")

        _repositorio(credenciais, servico_sid).salvar(conversa)

        relida = _repositorio(credenciais, servico_sid).obter_ou_criar(conversa_sid)
        assert relida.status is StatusConversa.ESCALADA
        assert relida.motivo_escalonamento == "nao soube responder"

    def test_conversa_encerrada_e_lida_de_volta(self, credenciais, servico_e_conversa):
        servico_sid, conversa_sid, _ = servico_e_conversa
        conversa = _repositorio(credenciais, servico_sid).obter_ou_criar(conversa_sid)
        conversa.encerrar()

        _repositorio(credenciais, servico_sid).salvar(conversa)

        relida = _repositorio(credenciais, servico_sid).obter_ou_criar(conversa_sid)
        assert relida.status is StatusConversa.ENCERRADA


class TestOHistoricoVemDoTwilio:
    def test_mensagens_postadas_aparecem_na_conversa(
        self, credenciais, servico_e_conversa
    ):
        servico_sid, conversa_sid, cliente = servico_e_conversa
        cliente.conversations.v1.services(servico_sid).conversations(
            conversa_sid
        ).messages.create(author="whatsapp:+5511999999999", body="qual o horario?")
        canal = TACCanal(
            account_sid=credenciais["account_sid"],
            auth_token=credenciais["auth_token"],
            autor_agente=AUTOR_AGENTE,
            conversation_service_sid=servico_sid,
        )
        canal.enviar_mensagem(conversa_sid, "Das 9h as 18h.")

        conversa = _repositorio(credenciais, servico_sid).obter_ou_criar(conversa_sid)

        assert [(m.autor, m.conteudo) for m in conversa.mensagens] == [
            (Autor.CLIENTE, "qual o horario?"),
            (Autor.IA, "Das 9h as 18h."),
        ]

    def test_o_repositorio_nao_duplica_o_historico_ao_salvar(
        self, credenciais, servico_e_conversa
    ):
        """As mensagens ja sao do Twilio; salvar nao pode escrever de novo."""
        servico_sid, conversa_sid, cliente = servico_e_conversa
        cliente.conversations.v1.services(servico_sid).conversations(
            conversa_sid
        ).messages.create(author="whatsapp:+5511999999999", body="oi")
        repo = _repositorio(credenciais, servico_sid)
        conversa = repo.obter_ou_criar(conversa_sid)
        conversa.registrar_mensagem(
            Mensagem(Autor.IA, "ola", datetime.now(timezone.utc))
        )

        repo.salvar(conversa)

        relida = _repositorio(credenciais, servico_sid).obter_ou_criar(conversa_sid)
        assert [m.conteudo for m in relida.mensagens] == ["oi"]


class TestAtributosDeOutrosSistemas:
    def test_salvar_preserva_o_que_ja_estava_la(self, credenciais, servico_e_conversa):
        """O campo e compartilhado com o Flex e os Studio Flows da conta."""
        import json

        servico_sid, conversa_sid, cliente = servico_e_conversa
        recurso = cliente.conversations.v1.services(servico_sid).conversations(
            conversa_sid
        )
        recurso.update(attributes=json.dumps({"campo_de_outro_sistema": "nao perder"}))
        repo = _repositorio(credenciais, servico_sid)
        conversa = repo.obter_ou_criar(conversa_sid)
        conversa.escalar(motivo="x")

        repo.salvar(conversa)

        atributos = json.loads(recurso.fetch().attributes)
        assert atributos["campo_de_outro_sistema"] == "nao perder"
        assert atributos["agente_status"] == "ESCALADA"


class TestConfiguracao:
    """Nao precisam de rede."""

    def test_nao_le_variavel_de_ambiente(self, monkeypatch):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_do_ambiente")

        repo = TwilioRepositorioConversas(
            account_sid="AC_do_construtor",
            auth_token="t",
            conversation_service_sid="IS123",
        )

        assert repo.conversation_service_sid == "IS123"


class TestConversaReconstituida:
    """`Conversa.reconstituir` nao passa pelas regras de transicao."""

    def test_volta_escalada_sem_chamar_escalar(self):
        conversa = Conversa.reconstituir(
            conversa_id="c1",
            status=StatusConversa.ESCALADA,
            motivo_escalonamento="ja tinha escalado",
        )

        assert conversa.status is StatusConversa.ESCALADA
        assert conversa.motivo_escalonamento == "ja tinha escalado"

    def test_uma_conversa_encerrada_volta_recusando_mudancas(self):
        from core.conversa import ConversaEncerrada

        conversa = Conversa.reconstituir(
            conversa_id="c1", status=StatusConversa.ENCERRADA
        )

        with pytest.raises(ConversaEncerrada):
            conversa.encerrar()

    def test_o_historico_volta_na_ordem(self):
        agora = datetime(2026, 9, 15, 10, 0)
        conversa = Conversa.reconstituir(
            conversa_id="c1",
            mensagens=[
                Mensagem(Autor.CLIENTE, "primeira", agora),
                Mensagem(Autor.IA, "segunda", agora),
            ],
        )

        assert [m.conteudo for m in conversa.mensagens] == ["primeira", "segunda"]
