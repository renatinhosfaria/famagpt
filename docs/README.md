# FamaGPT - Consultor IA para Corretores de Imóveis

## 📋 Visão Geral

**FamaGPT** é o primeiro consultor de inteligência artificial especializado exclusivamente para **corretores de imóveis**, focado no mercado de **Uberlândia/MG**. O sistema opera via WhatsApp, fornecendo consultoria especializada, análises de mercado e suporte à tomada de decisões comerciais.

### 🎯 Objetivo Principal

Tornar-se a ferramenta indispensável para todo corretor de imóveis em Uberlândia, oferecendo:
- 🧠 **Consultoria Especializada 24/7** via WhatsApp
- 📊 **Análises Comparativas** para argumentação de vendas
- 🏘️ **Inteligência de Mercado** hiperlocal de Uberlândia
- 💰 **Suporte à Precificação** baseado em dados reais
- 🎯 **Argumentação de Vendas** personalizada por cliente

### 🏗️ Arquitetura Microserviços

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    Corretor     │    │   Orchestrator  │    │  Real Estate    │
│   (WhatsApp)    │────┤   (LangGraph)   │────┤   Specialist    │
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
│   Service   │    │  (Market    │    │ (Corretor   │    │ (Uberlândia │
│             │    │   Data)     │    │  Context)   │    │  Knowledge) │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                                │
                    ┌─────────────────┐
                    │   Database      │
                    │   Service       │
                    └─────────────────┘
```

### 🚀 Tecnologias Utilizadas

- **LangGraph**: Orquestração de workflows de consultoria
- **LangSmith**: Observabilidade e debugging de IA
- **OpenAI GPT-4**: Consultoria conversacional especializada
- **WhatsApp Business API**: Interface natural para corretores
- **PostgreSQL + PGVector**: Dados de mercado e embeddings
- **Redis**: Cache e contexto de conversas
- **Playwright**: Coleta de dados de mercado
- **FastAPI**: APIs RESTful assíncronas
- **Docker**: Containerização e orquestração

## 📁 Estrutura de Documentação

```
docs/
├── README.md                     # Este arquivo - Visão geral do projeto
├── PRD-FamaGPT-Corretor.md      # Product Requirements Document v3.0 (B2B Focus)
├── brownfield-architecture.md    # Arquitetura atual do sistema
├── CLAUDE.md                     # Instruções para AI agents
├── customer-discovery.md         # Research com corretores (planejado)
├── competitive-analysis.md       # Análise da concorrência (planejado)
└── market-research.md            # Pesquisa de mercado Uberlândia (planejado)
```

## ⚙️ Configuração e Instalação

### 1. Pré-requisitos

- Docker e Docker Compose
- Git
- Chaves de API necessárias:
  - `OPENAI_API_KEY`: Para IA e embeddings
  - `EVOLUTION_API_KEY`: Para WhatsApp Business
  - `LANGCHAIN_API_KEY`: Para observabilidade LangSmith

### 2. Setup Local

```bash
# Clone o repositório
git clone <repository>
cd famagpt

# Configure as variáveis de ambiente
cp .env.example .env
# Edite o .env com suas credenciais

# Inicie o sistema completo
chmod +x start.sh
./start.sh
```

### 3. Verificação de Funcionamento

```bash
# Health checks de todos os serviços
curl http://localhost:8000/health  # Orchestrator
curl http://localhost:8001/health  # Webhooks
curl http://localhost:8002/health  # Transcription
curl http://localhost:8003/health  # Web Search
curl http://localhost:8004/health  # Memory
curl http://localhost:8005/health  # RAG
curl http://localhost:8006/health  # Database
curl http://localhost:8007/health  # Specialist
```

## 🔧 Desenvolvimento

### Estrutura de Cada Serviço

```
service_name/
├── src/
│   ├── domain/          # Entidades de negócio
│   ├── application/     # Casos de uso
│   ├── infrastructure/  # Integrações externas
│   └── presentation/    # APIs FastAPI
├── tests/              # Testes do serviço
├── Dockerfile
└── requirements.txt
```

### Comandos Úteis

```bash
# Logs de todos os serviços
docker-compose logs -f

# Logs de serviço específico
docker-compose logs -f specialist

# Status dos containers
docker-compose ps

# Rebuild de serviço específico
docker-compose build specialist

# Restart de serviço específico
docker-compose restart specialist

# Acesso ao container para debugging
docker-compose exec specialist bash
```

## 👥 Target Audience

### Usuário Primário: Corretor de Imóveis
- **Localização**: Uberlândia/MG e região metropolitana
- **Experiência**: 2+ anos no mercado imobiliário
- **Perfil**: Mobile-first, results-driven, relationship-based
- **Necessidades**: Consultoria especializada, análises de mercado, argumentação técnica

### Segmentos de Corretores
1. **Estabelecidos** (40%): 5+ anos, 10+ vendas/mês, foco em eficiência
2. **Em Crescimento** (45%): 2-5 anos, 3-8 vendas/mês, construindo reputação
3. **Novatos** (15%): <2 anos, 1-3 vendas/mês, aprendendo mercado

## 📊 Métricas e KPIs

### Objetivos de Produto
- **Market Penetration**: 50% dos corretores ativos de Uberlândia (150+ corretores)
- **User Satisfaction**: NPS > 80
- **Retention**: >95% mensal
- **Performance**: <3s response time P95

### Objetivos de Negócio
- **Corretor ROI**: +25% conversão, +15% ticket médio
- **Revenue**: R$ 211K ARR (Year 1)
- **Unit Economics**: LTV/CAC > 20:1
- **Market Leadership**: #1 tool para corretores região

## 🗓️ Roadmap

### Q4 2025: Foundation & MVP
- Core consultant engine via WhatsApp
- Market intelligence de Uberlândia
- 50 corretores beta testing
- Product-market fit validation

### Q1 2026: Scale & Enhancement
- 100 corretores active users
- Advanced analytics features
- CRM integration capabilities
- R$ 15K MRR target

### Q2-Q4 2026: Regional Expansion
- Triângulo Mineiro coverage (5 cidades)
- 200+ corretores active
- R$ 30K MRR target
- Market leadership regional

## 💼 Business Model

### Pricing Strategy
- **Professional Corretor**: R$ 147/mês
- **Incluído**: Consultas ilimitadas, análises comparativas, market intelligence
- **Add-ons**: Premium reports (R$ 47/mês), Team licenses (15% discount)
- **Value Proposition**: ROI R$ 1.500+/mês justifica investment

### Go-to-Market
1. **Phase 1**: Influencer seeding (top 20 corretores)
2. **Phase 2**: Word-of-mouth + digital marketing
3. **Phase 3**: CRECI partnership + market dominance

## 🔍 Customer Discovery

### Research Findings (Planejado)
- Pain points dos corretores de Uberlândia
- Ferramentas atuais utilizadas
- Willingness to pay por consultoria IA
- Features mais valorizadas

### Validation Approach
- 20+ entrevistas com corretores
- Beta program com early adopters
- Metrics de engagement e satisfaction
- Iteração baseada em feedback

## 🏆 Competitive Advantage

### Diferenciação Única
1. **Hyperlocal Expertise**: Conhecimento exclusivo de Uberlândia
2. **B2B-First Design**: Construído especificamente para corretores
3. **AI-Native**: Consultor inteligente vs. ferramentas passivas
4. **WhatsApp Integration**: Interface natural e familiar
5. **Real-time Data**: Dados sempre atualizados do mercado

### Moat Defensável
- **Data Moat**: Knowledge base proprietária de Uberlândia
- **Network Effects**: Community de corretores locais
- **Switching Costs**: Workflow integration
- **Brand Recognition**: First mover advantage

## 📞 Suporte e Contato

### Para Desenvolvedores
- **Documentation**: Consulte `docs/brownfield-architecture.md`
- **API Reference**: Endpoints documentados via FastAPI
- **Issues**: GitHub Issues para bugs e feature requests

### Para Corretores (Beta)
- **Onboarding**: WhatsApp +55 (34) XXXXX-XXXX
- **Suporte**: Via WhatsApp durante horário comercial
- **Feedback**: Essencial para evolução do produto

## 🎯 Next Steps

### Para Stakeholders
1. Review do PRD-FamaGPT-Corretor.md
2. Approval para customer discovery phase
3. Budget allocation para MVP development
4. Team allocation para execution

### Para Desenvolvimento
1. Customer discovery com 20+ corretores
2. MVP refinement baseado em feedback
3. Beta program setup
4. Performance optimization para scale

---

🚀 **Desenvolvido para transformar corretores de imóveis em consultores de alta performance através de inteligência artificial especializada.**