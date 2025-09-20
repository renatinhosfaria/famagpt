# Testes de Integração - FamaGPT

Este diretório contém os testes de integração para validar o funcionamento dos serviços do FamaGPT.

## 🚀 Como Executar

### 1. Instalar Dependências

```bash
pip install -r requirements.txt
```

### 2. Certificar que os Serviços Estão Rodando

```bash
# Iniciar todos os serviços
./start.sh

# Ou individualmente
docker-compose up -d
```

### 3. Executar os Testes

```bash
# Executar script principal
python run_tests.py

# Ou usar pytest diretamente
pytest test_integration.py -v
```

## 📋 O que é Testado

### 🏥 Health Checks
- Verifica se todos os serviços estão respondendo
- Valida status de saúde de cada endpoint

### 🗄️ Database Service
- Criação e recuperação de usuários
- Criação de conversas
- Salvamento de mensagens
- Fluxo completo de dados

### 🔗 Webhook Service
- Endpoints básicos
- Recepção de webhooks
- Validação de estruturas

### 🎼 Orchestrator Service
- Endpoints de saúde
- Conectividade básica

### 🔄 Integração Completa
- Fluxo webhook → orchestrator → database
- Processamento end-to-end
- Validação de dados persistidos

## 📊 Interpretando os Resultados

- ✅ **Verde**: Teste passou
- ❌ **Vermelho**: Teste falhou
- ⚠️  **Amarelo**: Teste passou parcialmente

## 🛠️ Adicionando Novos Testes

1. Crie uma nova classe de teste em `test_integration.py`
2. Implemente métodos async com `@pytest.mark.asyncio`
3. Use `httpx.AsyncClient` para requisições HTTP
4. Adicione validações usando `assert`

Exemplo:
```python
class TestNewService:
    @pytest.mark.asyncio
    async def test_new_feature(self):
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/endpoint")
            assert response.status_code == 200
            print("✅ New feature working")
```