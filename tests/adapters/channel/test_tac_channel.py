"""Testes do `TACCanal` — contra o Twilio de verdade, sem mock.

Mesmo espirito de `test_ollama_provider.py`: aqui o I/O real e o ponto. Como
isso depende de credenciais e de uma conta Twilio, os testes se pulam com
uma mensagem dizendo exatamente o que configurar.

Pra rodar, no `.env` (ou no ambiente):

    TWILIO_ACCOUNT_SID=ACxxxxxxxx...
    TWILIO_AUTH_TOKEN=...
    TWILIO_TEST_CONVERSATION_SID=CHxxxxxxxx...   # conversa descartavel

A `TWILIO_TEST_CONVERSATION_SID` e separada de proposito: estes testes
postam mensagens de verdade, e apontar pra uma conversa de cliente mandaria
texto de teste pra uma pessoa real.
"""

import os
import uuid

import pytest

from adapters.channel.tac_channel import LIMITE_CARACTERES_TWILIO, TACCanal


@pytest.fixture(scope="session")
def credenciais() -> dict[str, str]:
    """As credenciais do Twilio, ou pula os testes explicando o que falta."""
    faltando = [
        nome
        for nome in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_TEST_CONVERSATION_SID")
        if not os.environ.get(nome)
    ]
    if faltando:
        pytest.skip(
            "credenciais do Twilio nao configuradas: "
            f"{', '.join(faltando)}. Veja o docstring deste modulo."
        )
    return {
        "account_sid": os.environ["TWILIO_ACCOUNT_SID"],
        "auth_token": os.environ["TWILIO_AUTH_TOKEN"],
        "conversa_id": os.environ["TWILIO_TEST_CONVERSATION_SID"],
    }


@pytest.fixture
def canal(credenciais) -> TACCanal:
    return TACCanal(
        account_sid=credenciais["account_sid"],
        auth_token=credenciais["auth_token"],
    )


class TestEnviarMensagem:
    def test_posta_na_conversa_sem_levantar(self, canal, credenciais):
        canal.enviar_mensagem(
            credenciais["conversa_id"], f"teste automatizado {uuid.uuid4().hex[:8]}"
        )

    def test_a_mensagem_aparece_na_conversa_com_o_autor_do_agente(
        self, canal, credenciais
    ):
        """Le de volta pelo Twilio: e o que prova que a mensagem chegou la."""
        from twilio.rest import Client

        marca = f"teste {uuid.uuid4().hex[:8]}"
        canal.enviar_mensagem(credenciais["conversa_id"], marca)

        cliente = Client(credenciais["account_sid"], credenciais["auth_token"])
        mensagens = (
            cliente.conversations.v1.conversations(credenciais["conversa_id"])
            .messages.list(limit=20)
        )

        correspondente = [m for m in mensagens if m.body == marca]
        assert correspondente, f"mensagem '{marca}' nao apareceu na conversa"
        assert correspondente[0].author == canal.autor_agente

    def test_texto_longo_e_cortado_no_limite_do_twilio(self, canal, credenciais):
        """Acima de 1600 caracteres o Twilio recusa — cortamos antes."""
        canal.enviar_mensagem(credenciais["conversa_id"], "a" * (LIMITE_CARACTERES_TWILIO + 500))


class TestConfiguracao:
    """Estes nao precisam de rede: so conferem o contrato do construtor."""

    def test_nao_le_variavel_de_ambiente(self, monkeypatch):
        """A configuracao vem do construtor, como nos outros adapters."""
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_do_ambiente")

        canal = TACCanal(account_sid="AC_do_construtor", auth_token="token")

        assert canal.account_sid == "AC_do_construtor"

    def test_o_autor_do_agente_e_configuravel(self):
        canal = TACCanal(account_sid="AC", auth_token="t", autor_agente="atendente-ia")

        assert canal.autor_agente == "atendente-ia"
