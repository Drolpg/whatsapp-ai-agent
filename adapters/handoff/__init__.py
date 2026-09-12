"""Implementacoes de `GatewayHandoff` — a transferencia pro humano.

O nucleo so sabe que uma `Conversa` "escalou". O que isso significa em
termos operacionais — disparar um Studio Flow, criar uma Task no TaskRouter,
fazer ela aparecer pro atendente no Flex — e conhecimento exclusivo deste
subpacote.

    studio_gateway.py  Twilio Studio + TaskRouter + Flex  (Fase 6)
"""
