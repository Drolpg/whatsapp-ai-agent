"""Configuracao comum da suite.

Carrega o `.env` antes de qualquer teste, pra que os testes de integracao
(Twilio, Ollama) encontrem as credenciais no mesmo lugar em que o `main.py`
as procura. Sem isto, preencher o `.env` nao teria efeito nenhum: os testes
liam `os.environ` direto, e um `.env` completo continuava resultando em
"credenciais nao configuradas".

`override=False` de proposito: variavel ja definida no ambiente ganha do
arquivo. E o que permite rodar um teste apontando pra outra conta sem editar
o `.env` — `TWILIO_TEST_CONVERSATION_SID=CHxxx uv run pytest`.
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
