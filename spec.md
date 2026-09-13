# spec — whatsapp-ai-agent

> Este documento é um de três: `spec.md` (o quê e por quê — este arquivo),
> `plan.md` (arquitetura técnica) e `tasks.md` (fases e critério de
> aceite). Dividido em 2026-09-13 a partir do `SPEC.md` único original —
> nada do conteúdo foi perdido, só redistribuído. Nomenclatura seguindo a
> convenção do GitHub Spec Kit.

## Objetivo

POC de um agente de IA para atendimento via WhatsApp, usando o Twilio Agent
Connect (TAC) como ponte com o canal, um LLM local (Llama via Ollama) com RAG
sobre uma base de conhecimento própria, e handoff para atendimento humano no
Twilio Flex quando a IA não resolve. Objetivo duplo: (1) demonstrar pro
cliente que a solução funciona hoje, sem custo de API, e que trocar o modelo
local por uma API paga (OpenAI, Anthropic, Bedrock) no futuro é uma troca
pequena, não um projeto novo; (2) servir de estudo guiado — cada fase existe
tanto pra avançar o código quanto pra ensinar um conceito específico.

## Termos usados no projeto

| Termo | Significado |
|---|---|
| Conversa | Uma troca de mensagens com um cliente, do início até o encerramento ou handoff. |
| Mensagem | Um item dentro de uma Conversa — quem enviou, o conteúdo, quando. |
| Triagem | O processo de decidir, a cada mensagem do cliente, se a IA responde ou se a conversa deve ser escalada. |
| Escalar / Handoff | Transferir a Conversa pra um atendente humano. |
| Base de Conhecimento | O conjunto de documentos/textos que a IA consulta pra responder (RAG). |
| Trecho | Um pedaço da Base de Conhecimento recuperado como relevante pra uma pergunta. |

## Fora de escopo por enquanto

- Deploy em produção real.
- Autenticação/autorização de usuários administrativos.
- Suporte a múltiplos idiomas.
- Interface de administração da Base de Conhecimento.

## Referências

- Twilio Agent Connect (documentação): twilio.com/docs/conversations/agent-connect
- Twilio — Integrating Agent Connect with Flex for Human Handoff (blog): twilio.com/en-us/blog/developers/tutorials/product/twilio-agent-connect-flex-human-handoff
- Ollama + LangChain, RAG local: markaicode.com/build-local-rag-pipeline-ollama-langchain
- What is Spec-Driven Development? (IBM): ibm.com/think/topics/spec-driven-development
- Documento "Integração de IA no atendimento via WhatsApp com o Twilio Flex" (levantamento de caminhos, entregue em 2026-09-11 no projeto `twilio_project`).
