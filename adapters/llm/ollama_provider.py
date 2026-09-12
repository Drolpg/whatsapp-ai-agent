"""`OllamaProvedorLLM` — implementa `ProvedorLLM` com um Llama local.

Fala com um Ollama rodando na maquina (`OLLAMA_BASE_URL`) e devolve texto
puro pro nucleo. Todo detalhe de HTTP, prompt template, modelo e parametros
de geracao fica preso aqui dentro: `core/` so conhece a assinatura
`gerar_resposta(mensagens, trechos_contexto) -> str`.

Vantagem pra POC: custo zero de API e nenhum dado saindo da maquina.

TODO(Fase 3): implementar o adapter e testa-lo isoladamente contra um Ollama
de verdade — ainda sem RAG e sem Twilio no caminho.
"""
