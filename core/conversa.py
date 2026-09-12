"""Os dados de uma conversa: `Conversa` e `Mensagem`.

`Mensagem` e um item simples e imutavel: quem enviou (`CLIENTE` ou `IA`), o
conteudo e o timestamp. Depois de criada, nao muda.

`Conversa` guarda um id, a lista de mensagens e um status (`ATIVA`,
`ESCALADA` ou `ENCERRADA`). E o unico jeito de mudar o estado de uma
conversa — quem quiser acrescentar uma mensagem ou marcar como escalada
pede pra ela, em vez de mexer na lista ou no status por fora. Isso mantem
num lugar so as regras do tipo "nao se adiciona mensagem numa conversa
encerrada".
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Autor(Enum):
    """Quem enviou uma mensagem."""

    CLIENTE = "CLIENTE"
    IA = "IA"


class StatusConversa(Enum):
    """Em que ponto do atendimento a conversa esta.

    ATIVA      a IA ainda esta atendendo
    ESCALADA   passou pra um atendente humano
    ENCERRADA  acabou; nao aceita mais nenhuma mudanca
    """

    ATIVA = "ATIVA"
    ESCALADA = "ESCALADA"
    ENCERRADA = "ENCERRADA"


class ConversaEncerrada(RuntimeError):
    """Tentativa de mudar uma conversa que ja foi encerrada.

    Existe pra que o erro apareca na hora, em vez de a chamada ser ignorada
    em silencio e o problema so ser notado bem depois.
    """


@dataclass(frozen=True)
class Mensagem:
    """Um item de uma conversa. Imutavel e comparada pelos seus valores.

    O `timestamp` e sempre explicito, nunca preenchido com o relogio do
    sistema por padrao: isso mantem `core/` livre de efeito colateral e
    deixa os testes deterministicos.
    """

    autor: Autor
    conteudo: str
    timestamp: datetime


@dataclass
class Conversa:
    """Uma troca de mensagens com um cliente, do inicio ate o fim.

    Toda mudanca de estado passa por um metodo daqui (`registrar_mensagem`,
    `escalar`, `encerrar`), que checa se ela e valida antes de aplicar.
    `mensagens` devolve uma tupla justamente pra que ninguem de fora
    consiga acrescentar ou remover nada sem passar por esses metodos.
    """

    conversa_id: str
    _mensagens: list[Mensagem] = field(default_factory=list, repr=False)
    status: StatusConversa = StatusConversa.ATIVA
    motivo_escalonamento: str | None = None

    @property
    def mensagens(self) -> tuple[Mensagem, ...]:
        """As mensagens da conversa, na ordem em que chegaram."""
        return tuple(self._mensagens)

    def registrar_mensagem(self, mensagem: Mensagem) -> None:
        """Acrescenta uma mensagem ao fim da conversa.

        Vale tanto pra conversa ATIVA quanto pra ESCALADA — depois do
        handoff o atendente humano continua conversando pelo mesmo canal.
        """
        self._recusar_se_encerrada("registrar uma mensagem")
        self._mensagens.append(mensagem)

    def escalar(self, motivo: str) -> None:
        """Passa a conversa pra um atendente humano, guardando o porque."""
        self._recusar_se_encerrada("escalar")
        if self.status is StatusConversa.ESCALADA:
            raise ValueError(
                f"a conversa {self.conversa_id} ja foi escalada por: "
                f"{self.motivo_escalonamento}"
            )
        self.status = StatusConversa.ESCALADA
        self.motivo_escalonamento = motivo

    def encerrar(self) -> None:
        """Encerra a conversa. Depois disso nada mais muda nela."""
        self._recusar_se_encerrada("encerrar")
        self.status = StatusConversa.ENCERRADA

    def _recusar_se_encerrada(self, acao: str) -> None:
        if self.status is StatusConversa.ENCERRADA:
            raise ConversaEncerrada(
                f"nao da pra {acao}: a conversa {self.conversa_id} ja esta encerrada"
            )
