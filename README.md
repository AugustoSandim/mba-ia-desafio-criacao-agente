# Residencial Aurora - Assistente Virtual

Assistente virtual para o condominio Residencial Aurora, construido com Google ADK e exposto como API FastAPI.

## Arquitetura

O assistente segue uma arquitetura de agente principal com tres especialistas. O agente principal recebe todas as mensagens e delega para o especialista adequado. Cada especialista possui tools proprias e `disallow_transfer_to_peers=True`, impedindo transferencias entre especialistas.

### Agente Principal (`aurora`)

- **Arquivo**: `app/agents.py`, linhas 72-90
- **Modelo**: `gemini-3.6-flash`
- **Responsabilidade**: Receber todas as mensagens do morador e decidir qual especialista ativar com base no assunto. Nao possui tools proprias.
- **Ativacao**: E o agente raiz do Runner (`app/main.py`, linha 43). Toda mensagem enviada pela API chega primeiro a ele.
- **Motivo**: Centralizar o roteamento mantendo o prompt principal limpo, sem carregar dados ou regulamento no contexto.

### Especialista de Reservas (`especialista_reservas`)

- **Arquivo**: `app/agents.py`, linhas 12-39
- **Tools**: `app/tools/reservas.py` — `listar_reservas`, `verificar_disponibilidade`, `solicitar_reserva`, `cancelar_reserva_tool`
- **Responsabilidade**: Listar, verificar disponibilidade, criar e cancelar reservas de areas comuns.
- **Ativacao**: O agente principal delega quando a mensagem trata de reservas (descricao do agente indica isso ao modelo).
- **Motivo**: Isolar a logica de reservas com suas regras especificas — taxa, confirmacao para areas pagas, cancelamento direto para areas sem taxa.

### Especialista de Visitantes (`especialista_visitantes`)

- **Arquivo**: `app/agents.py`, linhas 41-55
- **Tools**: `app/tools/visitantes.py` — `listar_visitantes`, `solicitar_autorizacao_visitante`
- **Responsabilidade**: Listar visitantes autorizados e solicitar novas autorizacoes de entrada.
- **Ativacao**: O agente principal delega quando a mensagem trata de visitantes.
- **Motivo**: Autorizacao de visitantes sempre exige confirmacao; isolar impede que a logica de confirmacao interfira nas reservas.

### Especialista de Regulamento (`especialista_regulamento`)

- **Arquivo**: `app/agents.py`, linhas 57-70
- **Tools**: `app/tools/regulamento.py` — `consultar_regulamento`
- **Responsabilidade**: Consultar o regulamento interno (`dados/regulamento.md`) para responder duvidas sobre regras e normas.
- **Ativacao**: O agente principal delega quando a mensagem trata de regulamento, regras ou normas do condominio.
- **Motivo**: O regulamento e longo. Manter a busca em um especialista com ferramenta dedicada evita carregar o texto inteiro no contexto de todas as conversas.

### Fluxo de Confirmacao

Acoes que geram cobranca (reserva com taxa > 0) ou liberam acesso (autorizacao de visitante) passam por um fluxo de confirmacao:

1. A tool cria uma confirmacao pendente no banco (`app/database.py:criar_confirmacao`, linhas 205-218)
2. A resposta da API inclui a lista de confirmacoes pendentes
3. O morador responde via `POST /sessoes/{id}/confirmacoes`
4. O handler executa a acao diretamente no codigo (`app/main.py:processar_confirmacao`, linhas 109-168), sem passar pela tool do agente
5. Uma mensagem de sistema e enviada ao agente para gerar a resposta final

Essa abordagem evita o problema de retomada de tool call do ADK com sessao persistida — a acao e executada pelo codigo da API, nao pelo agente.

## Garantias

### Garantia 1: Cobranca ou acesso so com confirmacao

- **Arquivo**: `app/tools/reservas.py`, funcao `solicitar_reserva` (linhas 44-78)
- **Arquivo**: `app/tools/visitantes.py`, funcao `solicitar_autorizacao_visitante` (linhas 21-40)
- **Arquivo**: `app/main.py`, rota `processar_confirmacao` (linhas 109-168)
- **Arquivo**: `app/database.py`, funcao `criar_confirmacao` (linhas 205-218)

**Como funciona**: Quando `solicitar_reserva` detecta taxa > 0, ela NAO faz o INSERT na tabela de reservas — cria uma confirmacao pendente no banco e retorna uma mensagem informando o morador. Para visitantes, `solicitar_autorizacao_visitante` SEMPRE cria confirmacao pendente. A rota `POST /sessoes/{id}/confirmacoes` valida que o id pertence a sessao e esta pendente (409 caso contrario), e so entao executa o INSERT diretamente no codigo. Reservas de areas sem taxa (quadra) e cancelamentos executam imediatamente, sem confirmacao.

**Por que nao depende do modelo**: O INSERT so acontece dentro de `processar_confirmacao` (rota HTTP) ou dentro de `solicitar_reserva` quando `taxa == 0`. As tools nunca executam insercao para acoes com cobranca ou acesso. Mesmo que o modelo invente uma resposta dizendo que confirmou, o dado so e gravado quando a rota de confirmacoes e chamada com `confirmado: true`.

### Garantia 2: Cada sessao pertence a um apartamento

- **Arquivo**: `app/main.py`, rota `criar_sessao` (linhas 66-74) — define `state={"apartamento": req.apartamento}`
- **Arquivo**: `app/tools/reservas.py`, linha 17 — `tool_context.state["apartamento"]`
- **Arquivo**: `app/tools/reservas.py`, linha 54 — `tool_context.state["apartamento"]`
- **Arquivo**: `app/tools/reservas.py`, linha 87 — `tool_context.state["apartamento"]`
- **Arquivo**: `app/tools/visitantes.py`, linha 11 — `tool_context.state["apartamento"]`
- **Arquivo**: `app/tools/visitantes.py`, linha 28 — `tool_context.state["apartamento"]`

**Como funciona**: O apartamento e definido uma unica vez, na criacao da sessao, dentro do `state` do ADK. Todas as tools leem o apartamento exclusivamente de `tool_context.state["apartamento"]`. Nenhuma tool aceita apartamento como parametro de entrada.

**Por que nao depende do modelo**: O state da sessao e imutavel para o modelo — ele nao consegue alterar `tool_context.state["apartamento"]`. As tools fazem queries SQL filtrando por esse apartamento. Nao importa o que o morador escreva ("sou do 302"), as tools sempre operam com o apartamento da sessao.

### Garantia 3: Nada se perde no reinicio

- **Arquivo**: `app/main.py`, linhas 39-41 — `DatabaseSessionService(db_url="sqlite+aiosqlite:///...")` para sessoes ADK
- **Arquivo**: `app/database.py`, linhas 39-45 — SQLite com WAL mode para dados da aplicacao
- **Arquivo**: `app/main.py`, linhas 34-47 — lifespan reconecta aos bancos existentes no startup

**Como funciona**: O ADK usa `DatabaseSessionService` com SQLite, que persiste todas as sessoes e eventos em `data/sessions.db`. Os dados da aplicacao (reservas, visitantes, confirmacoes) ficam em `data/aurora.db`. Ambos sobrevivem ao reinicio da API.

**Por que nao depende do modelo**: A persistencia e configuracao de infraestrutura (SQLite + DatabaseSessionService). O modelo nao tem poder de escolher armazenamento em memoria ou descartar dados.

### Garantia 4: O regulamento e consultado, nao carregado

- **Arquivo**: `app/agents.py`, linhas 72-89 — instrucao do `agente_principal` nao contem regulamento
- **Arquivo**: `app/tools/regulamento.py`, funcao `consultar_regulamento` (linhas 37-63) — busca por relevancia
- **Arquivo**: `app/tools/regulamento.py`, funcao `_pontuar_capitulo` (linhas 29-34) — pontuacao por termos
- **Arquivo**: `app/tools/regulamento.py`, funcao `_carregar_capitulos` (linhas 16-26) — split por `## `

**Como funciona**: O agente principal nao recebe o regulamento nas instrucoes. Quando o morador pergunta sobre regras, o especialista de regulamento usa a tool `consultar_regulamento`, que le `dados/regulamento.md`, divide em capitulos por `## `, pontua cada capitulo por frequencia de termos da pergunta, e retorna apenas os 3 mais relevantes.

**Por que nao depende do modelo**: O texto do regulamento nunca esta no prompt de nenhum agente. A tool le o arquivo, filtra por relevancia e retorna so trechos pertinentes. Capitulos irrelevantes nunca entram nos eventos da sessao.

### Garantia 5: Dois moradores, uma reserva

- **Arquivo**: `app/database.py`, linhas 56-61 — `UNIQUE(area, data)` na tabela `reservas`
- **Arquivo**: `app/database.py`, funcao `criar_reserva` (linhas 135-157) — INSERT com `except IntegrityError`
- **Arquivo**: `app/database.py`, linhas 42-43 — `PRAGMA journal_mode=WAL` e `busy_timeout=5000`

**Como funciona**: A tabela `reservas` tem constraint `UNIQUE(area, data)`. Quando dois moradores aprovam a reserva da mesma area e data simultaneamente, o SQLite garante que apenas um INSERT tem sucesso. O segundo recebe `IntegrityError`, capturado por `criar_reserva`, que retorna uma mensagem de recusa sem erro de servidor (200, nao 500).

**Por que nao depende do modelo**: A exclusividade e imposta pelo banco de dados no instante da gravacao (constraint UNIQUE), nao por uma verificacao previa no codigo. Mesmo que a verificacao de disponibilidade retorne "livre" para ambos, o INSERT atomico garante que so um reserva com sucesso.

## Como rodar

### Pre-requisitos

- Python 3.12 ou superior
- [uv](https://docs.astral.sh/uv/) instalado
- Chave de API do Google AI Studio (Gemini)

### Variaveis de ambiente

Copie o arquivo de exemplo e preencha sua chave:

```bash
cp .env.example .env
```

Edite `.env` e preencha:

- `GOOGLE_API_KEY`: chave de API do Google AI Studio

### Instalar dependencias

```bash
uv sync
```

### Restaurar dados iniciais

```bash
uv run python restore.py
```

Esse comando cria o banco de dados `data/aurora.db` e popula com os dados de `dados/reservas.json` e `dados/visitantes.json`.

### Subir a API

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

A API estara disponivel em `http://localhost:8000`.

### Rotas da API

| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `/sessoes` | Criar sessao para um apartamento |
| POST | `/sessoes/{id}/mensagens` | Enviar mensagem ao assistente |
| POST | `/sessoes/{id}/confirmacoes` | Responder confirmacao pendente |
| GET | `/sessoes/{id}/eventos` | Listar eventos da sessao |
| GET | `/apartamentos/{num}/reservas` | Listar reservas de um apartamento |
| GET | `/apartamentos/{num}/visitantes` | Listar visitantes de um apartamento |
