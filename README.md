# Sistema Multi-Agente IA com LangGraph - Arquitetura de Microserviços

## 📋 Visão Geral

Sistema avançado de inteligência artificial baseado em arquitetura de microserviços, utilizando LangGraph para orquestração de agentes especializados, seguindo os princípios da Clean Architecture.

### 🎯 Funcionalidades Principais

- **Orquestração Inteligente**: LangGraph para fluxos complexos entre agentes
- **LangSmith**: Observabilidade, depuração e análise de agentes
- **WhatsApp Integration (Evolution API)**: Recepção e envio de mensagens via webhook utilizando a Evolution API (https://doc.evolution-api.com/v2/api-reference/get-information)
- **Transcrição de Áudio**: Whisper para conversão de áudio em texto
- **Busca Web Avançada**: Scraping inteligente com Playwright
- **Memória Híbrida**: Sistema de curto e longo prazo
- **RAG (Retrieval-Augmented Generation)**: Pipeline completo de documentos
- **Especialista em Imóveis**: Agente focado no mercado de Uberlândia/MG
- **Banco de Dados**: Integração PostgreSQL via MCP

### 🏗️ Arquitetura

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   WhatsApp      │    │   Orchestrator  │    │   Specialist    │
│   Webhook       │────┤   (LangGraph)   │────┤   Agent         │
└─────────────────┘    └─────────┬───────┘    └─────────────────┘
                                 │                       
                       ┌─────────▼───────┐               
                       │   LangSmith     │               
                       │ (Observability) │               
                       └─────────────────┘               
                                 │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│Transcription│    │ Web Search  │    │   Memory    │    │    RAG      │
│   Service   │    │   Service   │    │   Service   │    │   Service   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                                │
                    ┌─────────────────┐
                    │   Database      │
                    │   Service       │
                    └─────────────────┘
```

### 🚀 Tecnologias Utilizadas

- **LangGraph**: Orquestração de agentes
- **LangSmith**: Observabilidade, depuração e análise de agentes
- **FastAPI**: APIs RESTful
- **PostgreSQL**: Banco de dados principal
- **PGVector**: Armazenamento vetorial
- **Redis**: Cache e comunicação entre serviços
- **Whisper**: Transcrição de áudio
- **Playwright**: Web scraping avançado
- **Docker**: Containerização
- **Clean Architecture**: Padrão arquitetural

## 📁 Estrutura do Projeto

```
ai-agent-system/
├── docker-compose.yml
├── .env.example
├── shared/              # Protocolos e utilitários compartilhados
├── orchestrator/        # Serviço de orquestração com LangGraph
├── webhooks/           # Integração WhatsApp
├── transcription/      # Serviço de transcrição
├── web_search/         # Busca e scraping web
├── memory/             # Sistema de memória híbrida
├── rag/               # Pipeline RAG
├── database/          # Integração banco de dados
└── specialist/        # Agente especialista em imóveis
```

## ⚙️ Configuração e Instalação

### 1. Pré-requisitos

- Docker e Docker Compose
- Git
- Chaves de API (OpenAI, Evolution API, etc.)

### 2. Configuração do Banco de Dados

O sistema utiliza um banco de dados PostgreSQL externo. Configure as seguintes variáveis de ambiente:

```bash
# ==============================================
# DATABASE CONFIGURATION
# ==============================================
# Exemplo (substitua pelos seus valores reais)
DATABASE_URL=postgresql://<DB_USER>:<DB_PASSWORD>@<DB_HOST>:5432/<DB_NAME>?sslmode=disable
PGDATABASE=<DB_NAME>
PGHOST=<DB_HOST>
PGPORT=5432
PGUSER=<DB_USER>
PGPASSWORD=<DB_PASSWORD>
```

Importante: nunca commit suas credenciais reais no repositório. Rotacione as senhas caso já tenham sido expostas e mantenha-as apenas no arquivo local `.env` (que não deve ser versionado).

### 3. Instalação

```bash
# Clone o repositório
git clone <repository>
cd ai-agent-system

# Configure as variáveis de ambiente
cp .env.example .env
# Edite o .env com suas credenciais (incluindo as configurações do banco acima)

# Inicie os serviços
chmod +x start.sh
./start.sh
```

### 3. Verificação

```bash
# Teste de saúde dos serviços
curl http://localhost:8000/api/v1/health  # Orchestrator
curl http://localhost:8001/health  # Webhooks
curl http://localhost:8002/health  # Transcription
# ... outros serviços
```

## 🔧 Uso e Exemplos

### Fluxo Básico de Conversação

1. **Recepção**: Mensagem chega via Evolution API webhook
2. **Orquestração**: LangGraph roteia para agentes apropriados
3. **Processamento**: Agentes especializados processam tarefas
4. **Integração**: Resultados são combinados
5. **Resposta**: Mensagem final enviada ao usuário

## 📊 Monitoramento

```bash
# Logs de todos os serviços
docker-compose logs -f

# Status dos containers
docker-compose ps

# Métricas de performance
docker stats
```

## 🔄 Desenvolvimento

### Adicionando Novos Agentes

1. Crie diretório seguindo Clean Architecture
2. Implemente interfaces do domínio
3. Adicione ao docker-compose.yml
4. Registre no workflow_graph
5. Configure comunicação via Redis

### Estrutura de Cada Serviço

```
service_name/
├── src/
│   ├── domain/          # Entidades e interfaces
│   ├── application/     # Casos de uso e serviços
│   ├── infrastructure/  # Implementações concretas
│   └── presentation/    # APIs e main.py
├── tests/
├── Dockerfile
└── requirements.txt
```

## 📋 Roadmap

- [ ] Arquitetura base com Clean Architecture
- [ ] Orquestração com LangGraph
- [ ] Integração WhatsApp
- [ ] Transcrição de áudio
- [ ] Sistema de memória híbrida
- [ ] Pipeline RAG
- [ ] Agente especialista
- [ ] Dashboard de monitoramento
- [ ] Autenticação JWT
- [ ] Testes automatizados
- [ ] CI/CD pipeline

## 🤝 Contribuição

1. Fork o projeto
2. Crie uma branch para sua feature
3. Implemente seguindo Clean Architecture
4. Adicione testes
5. Submeta um Pull Request

🚀 **Desenvolvido com foco em escalabilidade, manutenibilidade e performance**
