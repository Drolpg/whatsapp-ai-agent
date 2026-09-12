"""A decisao de triagem e o fluxo que a usa.

Duas pecas, ambas sem dependencia externa:

`TriagemService` recebe uma `Conversa` e a resposta candidata gerada pela
IA, e decide se ela resolve o atendimento ou se a conversa deve ser
escalada pra um humano (ex: a IA pediu escalar explicitamente, ou o numero
de tentativas sem sucesso passou do limite). Repare no que ele *nao* faz:
nao gera a resposta e nao sabe quem a gerou — isso e problema de um
`ProvedorLLM` la em `adapters/`. Ele so decide o que fazer com ela.

`processar_mensagem_recebida` e a funcao que costura o fluxo inteiro:

    1. registra a mensagem do cliente na `Conversa`;
    2. busca trechos relevantes na `BaseConhecimento` (RAG);
    3. pede uma resposta candidata ao `ProvedorLLM`;
    4. entrega essa candidata ao `TriagemService`, que decide;
    5. conforme a decisao, ou responde pelo `Canal` ou aciona o
       `GatewayHandoff`.

Os passos 2, 3 e 5 falam com as interfaces de `ports.py`, nunca com Ollama,
FAISS ou Twilio direto: as implementacoes chegam prontas, passadas como
argumento pelo `main.py`. E por isso que este fluxo pode ser testado
inteiro com adapters falsos, sem nada real rodando.

TODO(Fase 2): implementar `processar_mensagem_recebida` e testar os dois
caminhos (resolvido pela IA e escalado pro humano) com adapters falsos.
"""

from dataclasses import dataclass
from enum import Enum

from core.conversa import Autor, Conversa

MARCADOR_ESCALAR = "[ESCALAR]"
"""Sinal combinado com a IA pra dizer "nao sei resolver isto".

A porta `ProvedorLLM` devolve texto puro, entao o pedido de escalonamento
precisa vir dentro do proprio texto. O prompt (la em `adapters/llm/`)
instrui o modelo a comecar a resposta com este marcador quando nao souber
responder; aqui so procuramos por ele.
"""

LIMITE_TENTATIVAS_PADRAO = 3
"""Quantas respostas da IA sem resolver antes de chamar um humano.

Tres e um meio-termo: da a IA espaco pra se corrigir depois de um
mal-entendido, sem deixar o cliente repetindo a mesma pergunta por muito
tempo. E ajustavel por conversa via `TriagemService(limite_tentativas=...)`.
"""


class Decisao(Enum):
    """O que fazer com a resposta candidata da IA."""

    RESOLVER = "RESOLVER"
    ESCALAR = "ESCALAR"


@dataclass(frozen=True)
class ResultadoTriagem:
    """A decisao tomada, com o que o chamador precisa pra agir.

    Em `RESOLVER`, `resposta` traz o texto a enviar pro cliente e `motivo` e
    vazio. Em `ESCALAR` e o contrario: `resposta` e `None` (nao ha nada pra
    enviar) e `motivo` explica pro atendente humano por que a conversa caiu
    no colo dele.
    """

    decisao: Decisao
    resposta: str | None = None
    motivo: str = ""

    @classmethod
    def resolver(cls, resposta: str) -> "ResultadoTriagem":
        return cls(decisao=Decisao.RESOLVER, resposta=resposta)

    @classmethod
    def escalar(cls, motivo: str) -> "ResultadoTriagem":
        return cls(decisao=Decisao.ESCALAR, motivo=motivo)


class TriagemService:
    """Decide, a cada resposta da IA, se ela resolve ou se chama um humano.

    Duas regras, nesta ordem:

    1. a IA sinalizou que nao sabe resolver (o `MARCADOR_ESCALAR` aparece na
       resposta);
    2. a IA ja tentou `limite_tentativas` vezes nesta conversa e o cliente
       continua voltando — sinal de que ela nao vai chegar la sozinha.

    Nao ha estado interno: a contagem de tentativas sai da propria
    `Conversa`, contando as mensagens que a IA ja enviou.
    """

    def __init__(self, limite_tentativas: int = LIMITE_TENTATIVAS_PADRAO) -> None:
        if limite_tentativas < 1:
            raise ValueError(
                f"limite_tentativas precisa ser pelo menos 1, recebido {limite_tentativas}"
            )
        self.limite_tentativas = limite_tentativas

    def decidir(self, conversa: Conversa, resposta_candidata: str) -> ResultadoTriagem:
        """Diz se a resposta candidata vai pro cliente ou se a conversa escala."""
        if self._ia_pediu_ajuda(resposta_candidata):
            return ResultadoTriagem.escalar("a IA sinalizou que nao sabe resolver")

        tentativas = self._tentativas_da_ia(conversa)
        if tentativas >= self.limite_tentativas:
            return ResultadoTriagem.escalar(
                f"a IA ja respondeu {tentativas} vezes sem resolver "
                f"(limite: {self.limite_tentativas})"
            )

        return ResultadoTriagem.resolver(resposta_candidata)

    def _ia_pediu_ajuda(self, resposta_candidata: str) -> bool:
        return MARCADOR_ESCALAR.lower() in resposta_candidata.lower()

    def _tentativas_da_ia(self, conversa: Conversa) -> int:
        return sum(1 for mensagem in conversa.mensagens if mensagem.autor is Autor.IA)
