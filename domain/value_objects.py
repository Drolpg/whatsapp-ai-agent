"""Value Objects do dominio — objetos sem identidade, iguais por valor.

Um Value Object e imutavel e definido pelo que ele *e*, nao por *qual* ele
e: duas `Mensagem` com o mesmo autor, conteudo e timestamp sao a mesma
mensagem pro dominio. Por serem imutaveis, podem ser compartilhados sem
medo de efeito colateral — o contraste direto com a Entity de
`entidades.py`.

TODO(Fase 1): implementar `Mensagem` (autor CLIENTE/IA, conteudo,
timestamp), `ResultadoTriagem` (RESOLVIDO com a resposta, ou ESCALAR com o
motivo) e `Trecho` (pedaco da Base de Conhecimento recuperado como
relevante), todos imutaveis e com igualdade por valor.
"""
