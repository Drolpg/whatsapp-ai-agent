"""Testes de `Mensagem` e `Conversa` — objetos Python puros, sem I/O."""

import dataclasses
from datetime import datetime

import pytest

from core.conversa import Autor, Conversa, ConversaEncerrada, Mensagem, StatusConversa


def _mensagem(autor=Autor.CLIENTE, conteudo="oi", minuto=0):
    return Mensagem(autor=autor, conteudo=conteudo, timestamp=datetime(2026, 9, 12, 10, minuto))


class TestMensagem:
    def test_e_imutavel(self):
        mensagem = _mensagem()

        with pytest.raises(dataclasses.FrozenInstanceError):
            mensagem.conteudo = "outro texto"

    def test_duas_mensagens_com_os_mesmos_valores_sao_iguais(self):
        assert _mensagem() == _mensagem()

    def test_mensagens_com_conteudo_diferente_nao_sao_iguais(self):
        assert _mensagem(conteudo="oi") != _mensagem(conteudo="tchau")


class TestConversaNasce:
    def test_ativa_e_sem_mensagens(self):
        conversa = Conversa(conversa_id="c1")

        assert conversa.status is StatusConversa.ATIVA
        assert conversa.mensagens == ()


class TestRegistrarMensagem:
    def test_acrescenta_na_ordem_em_que_chegaram(self):
        conversa = Conversa(conversa_id="c1")
        primeira = _mensagem(conteudo="primeira", minuto=0)
        segunda = _mensagem(conteudo="segunda", minuto=1)

        conversa.registrar_mensagem(primeira)
        conversa.registrar_mensagem(segunda)

        assert conversa.mensagens == (primeira, segunda)

    def test_mensagens_nao_pode_ser_alterada_por_fora(self):
        conversa = Conversa(conversa_id="c1")
        conversa.registrar_mensagem(_mensagem())

        expostas = conversa.mensagens
        with pytest.raises((AttributeError, TypeError)):
            expostas.append(_mensagem(conteudo="intrusa"))

        assert len(conversa.mensagens) == 1

    def test_recusa_mensagem_em_conversa_encerrada(self):
        conversa = Conversa(conversa_id="c1")
        conversa.encerrar()

        with pytest.raises(ConversaEncerrada):
            conversa.registrar_mensagem(_mensagem())

    def test_aceita_mensagem_em_conversa_escalada(self):
        conversa = Conversa(conversa_id="c1")
        conversa.escalar(motivo="cliente pediu humano")

        conversa.registrar_mensagem(_mensagem(conteudo="atendente assumiu"))

        assert len(conversa.mensagens) == 1


class TestEscalar:
    def test_muda_o_status_para_escalada(self):
        conversa = Conversa(conversa_id="c1")

        conversa.escalar(motivo="a IA nao soube responder")

        assert conversa.status is StatusConversa.ESCALADA

    def test_guarda_o_motivo_do_escalonamento(self):
        conversa = Conversa(conversa_id="c1")

        conversa.escalar(motivo="a IA nao soube responder")

        assert conversa.motivo_escalonamento == "a IA nao soube responder"

    def test_recusa_conversa_ja_encerrada(self):
        conversa = Conversa(conversa_id="c1")
        conversa.encerrar()

        with pytest.raises(ConversaEncerrada):
            conversa.escalar(motivo="tarde demais")

    def test_recusa_conversa_ja_escalada(self):
        conversa = Conversa(conversa_id="c1")
        conversa.escalar(motivo="primeiro escalonamento")

        with pytest.raises(ValueError):
            conversa.escalar(motivo="segundo escalonamento")


class TestEncerrar:
    def test_muda_o_status_para_encerrada(self):
        conversa = Conversa(conversa_id="c1")

        conversa.encerrar()

        assert conversa.status is StatusConversa.ENCERRADA

    def test_conversa_escalada_pode_ser_encerrada_pelo_atendente(self):
        conversa = Conversa(conversa_id="c1")
        conversa.escalar(motivo="a IA nao soube responder")

        conversa.encerrar()

        assert conversa.status is StatusConversa.ENCERRADA

    def test_recusa_conversa_ja_encerrada(self):
        conversa = Conversa(conversa_id="c1")
        conversa.encerrar()

        with pytest.raises(ConversaEncerrada):
            conversa.encerrar()
