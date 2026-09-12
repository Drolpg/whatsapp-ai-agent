"""Suite de testes, espelhando a estrutura do projeto.

A divisao em duas pastas torna visivel o custo de cada tipo de teste:

    tests/core/      logica de decisao: sem I/O, sem mock, sem framework
    tests/adapters/  integracao com as tecnologias reais

Se um teste em `tests/core/` um dia precisar de rede ou de arquivo, o
problema esta no codigo de producao, nao no teste.
"""
