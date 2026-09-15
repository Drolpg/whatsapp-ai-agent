"""`TwilioRepositorioConversas` — guarda o estado da conversa no Twilio.

Implementa `RepositorioConversas` sem banco novo, aproveitando duas coisas
que o Twilio ja mantem por nos:

- **o historico** vive nas mensagens da Conversation. O cliente escreve por
  la e nossas respostas sao postadas por la, entao a lista ja esta completa e
  ordenada, sem precisarmos copiar nada;
- **o status** vai nos `attributes` da Conversation, um campo JSON livre que
  o Twilio guarda e devolve intacto.

O ganho e que o agente deixa de ter estado proprio. Reiniciar o processo nao
apaga conversa nenhuma, e varios workers leem a mesma verdade — os dois
problemas do dicionario em memoria que isto substitui.

O preco e uma ida ao Twilio por mensagem recebida (`fetch` da conversa mais
`list` das mensagens), e o limite de quantas mensagens se le de volta. Pra
uma conversa de atendimento, com dezenas de mensagens, isso e barato; pra
uma que dure milhares, a paginacao teria que entrar.

COMO O AUTOR VIRA `Autor`
Do lado do Twilio, autor e uma string livre: `whatsapp:+5511...` pro cliente,
e o `autor_agente` configurado pras nossas respostas. A traducao e por
igualdade com esse valor — qualquer outro autor e tratado como cliente, o
que e o lado seguro do erro: no maximo a IA conta uma mensagem a mais como
vinda de fora, nunca confunde mensagem de terceiro com resposta propria.
"""

import json
from datetime import datetime, timezone

from twilio.rest import Client

from adapters.channel.tac_channel import AUTOR_AGENTE_PADRAO
from core.conversa import Autor, Conversa, Mensagem, StatusConversa

MENSAGENS_LIDAS_PADRAO = 100
"""Quantas mensagens da conversa sao lidas de volta a cada mensagem nova."""

CHAVE_STATUS = "agente_status"
CHAVE_MOTIVO = "agente_motivo_escalonamento"
"""Chaves usadas dentro de `Conversation.attributes`.

Prefixadas de proposito: o campo e compartilhado com o resto da conta — o
Flex e os Studio Flows tambem escrevem la — e sobrescrever a chave de outro
sistema quebraria coisas fora do nosso alcance. Por isso `salvar` preserva
tudo que ja estiver no JSON e so mexe nestas duas.
"""


class TwilioRepositorioConversas:
    """Le e grava o estado da conversa na propria Conversation do Twilio.

    Como os outros adapters, recebe configuracao pronta e nunca le
    `os.environ`. Nao herda de `core.ports.RepositorioConversas`: satisfaz a
    porta por ter os metodos com a forma certa.
    """

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        conversation_service_sid: str | None = None,
        autor_agente: str = AUTOR_AGENTE_PADRAO,
        mensagens_lidas: int = MENSAGENS_LIDAS_PADRAO,
    ) -> None:
        self.conversation_service_sid = conversation_service_sid
        self.autor_agente = autor_agente
        self.mensagens_lidas = mensagens_lidas
        self._cliente = Client(account_sid, auth_token)

    def obter_ou_criar(self, conversa_id: str) -> Conversa:
        """Remonta a conversa a partir do que o Twilio guardou."""
        recurso = self._conversa(conversa_id)
        atributos = self._atributos(recurso)
        return Conversa.reconstituir(
            conversa_id=conversa_id,
            mensagens=self._mensagens(recurso),
            status=self._status(atributos),
            motivo_escalonamento=atributos.get(CHAVE_MOTIVO),
        )

    def salvar(self, conversa: Conversa) -> None:
        """Grava status e motivo nos atributos, preservando o resto do JSON.

        As mensagens nao sao gravadas: elas ja estao na Conversation, postadas
        pelo cliente e pelo `TACCanal`. Duplica-las aqui criaria duas versoes
        do mesmo historico, com a nossa fatalmente atrasada.
        """
        recurso = self._conversa(conversa.conversa_id)
        atributos = self._atributos(recurso)
        atributos[CHAVE_STATUS] = conversa.status.value
        if conversa.motivo_escalonamento is not None:
            atributos[CHAVE_MOTIVO] = conversa.motivo_escalonamento
        recurso.update(attributes=json.dumps(atributos))

    def _conversa(self, conversa_id: str):
        v1 = self._cliente.conversations.v1
        if self.conversation_service_sid:
            return v1.services(self.conversation_service_sid).conversations(conversa_id)
        return v1.conversations(conversa_id)

    def _atributos(self, recurso) -> dict:
        """Le os atributos como dicionario, tolerando lixo.

        Se outro sistema tiver escrito algo que nao e JSON de objeto, seguimos
        com um dicionario vazio em vez de derrubar o atendimento — o pior caso
        vira uma conversa tratada como nova, nao uma excecao no webhook.
        """
        try:
            atributos = json.loads(recurso.fetch().attributes or "{}")
        except (ValueError, TypeError):
            return {}
        return atributos if isinstance(atributos, dict) else {}

    def _status(self, atributos: dict) -> StatusConversa:
        try:
            return StatusConversa(atributos.get(CHAVE_STATUS, StatusConversa.ATIVA.value))
        except ValueError:
            return StatusConversa.ATIVA

    def _mensagens(self, recurso) -> list[Mensagem]:
        return [
            Mensagem(
                autor=Autor.IA if m.author == self.autor_agente else Autor.CLIENTE,
                conteudo=m.body or "",
                timestamp=m.date_created or datetime.now(timezone.utc),
            )
            for m in recurso.messages.list(limit=self.mensagens_lidas)
        ]
