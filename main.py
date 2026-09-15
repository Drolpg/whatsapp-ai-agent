"""Composition root — o unico lugar que conhece as duas metades do projeto.

Tudo no `core/` depende de interfaces: o fluxo de triagem pede um
`ProvedorLLM`, nao um Ollama; pede um `GatewayHandoff`, nao um Studio Flow.
Mas em algum momento alguem precisa escolher as implementacoes concretas e
amarrar as pecas. Esse alguem e este arquivo, e so ele.

Repare que este e o unico modulo do projeto que le `os.environ`. Todos os
adapters recebem configuracao pronta pelo construtor — e o que permite
aponta-los pra um Ollama de teste, um indice temporario ou uma conversa
descartavel do Twilio sem mexer em variavel de ambiente nenhuma.

Regra pratica: se voce precisar escrever regra de negocio neste arquivo, ela
esta no lugar errado — o lugar dela e `core/`.

COMO RODAR

    cp .env.example .env          # e preencha as credenciais
    uv run python scripts/ingerir_documentos.py
    uv run python main.py

O servidor sobe em http://localhost:5000. Pro Twilio alcancar o webhook numa
maquina local, exponha a porta (ngrok http 5000) e aponte o webhook
`onMessageAdded` do seu Conversation Service pra
`https://<seu-tunel>/webhooks/twilio/mensagem`.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from adapters.channel.tac_channel import AUTOR_AGENTE_PADRAO, TACCanal
from adapters.channel.twilio_repositorio import TwilioRepositorioConversas
from adapters.channel.webhook import criar_app
from adapters.knowledge.faiss_repository import FaissBaseConhecimento
from adapters.llm.ollama_provider import OllamaProvedorLLM

RAIZ = Path(__file__).resolve().parent
CAMINHO_INDICE = RAIZ / "data" / "faiss_index"


class HandoffAindaNaoImplementado:
    """Marcador do `GatewayHandoff` ate a Fase 6 chegar.

    O `core/` ja aciona o handoff quando a triagem decide escalar, mas o
    adapter do Studio/TaskRouter/Flex so existe na Fase 6. Ate la, registra
    no log em vez de transferir de verdade — assim o fluxo roda inteiro e da
    pra ver *que* escalou e *por que*, sem fingir que a Task foi criada.
    """

    def escalar(self, conversa, resumo: str, atributos: dict) -> None:
        print(f"[HANDOFF PENDENTE] conversa={conversa.conversa_id} motivo={resumo}")


def _obrigatoria(nome: str) -> str:
    valor = os.environ.get(nome)
    if not valor:
        raise SystemExit(
            f"variavel de ambiente {nome} nao definida. "
            "Copie .env.example para .env e preencha (ver README.md)."
        )
    return valor


def montar_app():
    """Le o ambiente, instancia os adapters e devolve o app pronto.

    O `.env` e carregado aqui, e nao no topo do modulo, pra que importar
    `main` num teste nao tenha efeito colateral no ambiente do processo.
    Variavel ja definida no ambiente ganha do arquivo (`override=False`).
    """
    load_dotenv(RAIZ / ".env", override=False)

    base_url_ollama = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    autor_agente = os.environ.get("TWILIO_AUTOR_AGENTE", AUTOR_AGENTE_PADRAO)
    auth_token = _obrigatoria("TWILIO_AUTH_TOKEN")
    account_sid = _obrigatoria("TWILIO_ACCOUNT_SID")
    servico_conversas = os.environ.get("TWILIO_CONVERSATION_CONFIGURATION_ID")

    if not CAMINHO_INDICE.is_dir():
        raise SystemExit(
            f"indice nao encontrado em {CAMINHO_INDICE}. "
            "Rode: uv run python scripts/ingerir_documentos.py"
        )

    return criar_app(
        base_conhecimento=FaissBaseConhecimento(
            caminho_indice=CAMINHO_INDICE,
            base_url=base_url_ollama,
            modelo_embeddings=os.environ.get(
                "OLLAMA_EMBEDDINGS_MODEL", "nomic-embed-text"
            ),
        ),
        provedor_llm=OllamaProvedorLLM(
            base_url=base_url_ollama,
            model=_obrigatoria("OLLAMA_MODEL"),
            # Explicito, e generoso: um modelo local frio leva dezenas de
            # segundos na primeira chamada. Estourar o timeout aqui vira
            # escalonamento silencioso — o cliente e mandado pro humano por
            # lentidao da maquina, nao por limitacao do modelo.
            timeout_segundos=float(os.environ.get("OLLAMA_TIMEOUT_SEGUNDOS", "120")),
        ),
        canal=TACCanal(
            account_sid=account_sid,
            auth_token=auth_token,
            autor_agente=autor_agente,
            # Sem isto, o envio vai pro Conversation Service padrao e o
            # Twilio devolve 404 pra conversas que vivem em outro service —
            # ver o docstring de TACCanal._conversa.
            conversation_service_sid=servico_conversas,
        ),
        # O estado das conversas mora no proprio Twilio, e nao num dicionario
        # do processo: reiniciar o servidor nao apaga conversa nenhuma, e
        # varios workers leem a mesma verdade.
        conversas=TwilioRepositorioConversas(
            account_sid=account_sid,
            auth_token=auth_token,
            conversation_service_sid=servico_conversas,
            autor_agente=autor_agente,
        ),
        gateway_handoff=HandoffAindaNaoImplementado(),
        auth_token=auth_token,
        autor_agente=autor_agente,
    )


def main() -> None:
    import logging

    # O logger do Flask so aparece a partir de INFO; sem isto, todas as
    # linhas de diagnostico do webhook (o que foi ignorado e por que) somem,
    # e um 204 silencioso vira um mistero — foi o que aconteceu na Fase 5.
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    app = montar_app()
    app.logger.setLevel(logging.INFO)

    # O Twilio chama o webhook por https (via tunel ou load balancer), mas o
    # Flask ve http internamente. A validacao de assinatura exige a URL exata
    # que o Twilio usou, entao sem isto ela falha sempre — ver webhook.py.
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))


if __name__ == "__main__":
    main()
