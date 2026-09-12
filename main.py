"""Composition root — o unico lugar que conhece as duas metades do projeto.

Tudo no `core/` depende de interfaces: o fluxo de triagem pede um
`ProvedorLLM`, nao um Ollama; pede um `GatewayHandoff`, nao um Studio Flow.
Mas em algum momento alguem precisa escolher as implementacoes concretas e
amarrar as pecas. Esse alguem e este arquivo, e so ele.

Aqui os adapters de `adapters/` sao instanciados (lendo configuracao do
ambiente — ver `.env.example`) e passados pro fluxo de `core/triagem.py`.
Nenhuma outra parte do codigo faz `import` de um adapter concreto; por isso
trocar `OllamaProvedorLLM` por `AnthropicProvedorLLM` (Fase 7) e uma
mudanca de uma linha, aqui, sem tocar em `core/`.

Regra pratica: se voce precisar escrever regra de negocio neste arquivo, ela
esta no lugar errado — o lugar dela e `core/`.

TODO(Fase 5): montar os adapters e subir o servidor que expoe o webhook do
canal. Ate la, nao ha nada pra compor.
"""
