"""Composition root — o unico lugar que conhece todas as camadas.

Tudo no sistema depende de abstracoes: o caso de uso pede um `ProvedorLLM`,
nao um Ollama; pede um `GatewayHandoff`, nao um Studio Flow. Mas em algum
momento alguem precisa escolher as implementacoes concretas e amarrar as
pecas. Esse alguem e este arquivo, e so ele.

Aqui os adapters de `infrastructure/` sao instanciados (lendo configuracao
do ambiente — ver `.env.example`) e injetados no construtor dos casos de uso
de `application/`. Nenhuma outra parte do codigo faz `import` de um adapter
concreto; por isso trocar `OllamaProvedorLLM` por `AnthropicProvedorLLM`
(Fase 7) e uma mudanca de uma linha, aqui, sem tocar em `domain/` nem em
`application/`.

Regra pratica: se voce precisar escrever regra de negocio neste arquivo,
ela esta no lugar errado — o lugar dela e `domain/`.

TODO(Fase 5): montar os adapters e subir o servidor que expoe o webhook do
canal. Ate la, nao ha nada pra compor.
"""
