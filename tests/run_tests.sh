#!/bin/bash

# Script para executar testes automatizados do FamaGPT

echo "🧪 Executando testes automatizados do FamaGPT..."

# Cores para output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Função para imprimir com cor
print_color() {
    echo -e "${1}${2}${NC}"
}

# Verificar se pytest está instalado
if ! command -v pytest &> /dev/null; then
    print_color $RED "❌ pytest não está instalado!"
    echo "Instalando dependências de teste..."
    pip install -r tests/requirements.txt
fi

# Criar diretório para relatórios se não existir
mkdir -p tests/reports

print_color $BLUE "📋 Executando testes do Specialist Service..."
pytest tests/test_specialist.py -v --tb=short --cov=specialist --cov-report=html:tests/reports/specialist_coverage --cov-report=term

if [ $? -eq 0 ]; then
    print_color $GREEN "✅ Testes do Specialist Service passaram!"
else
    print_color $RED "❌ Testes do Specialist Service falharam!"
fi

print_color $BLUE "📋 Executando testes do RAG Service..."
pytest tests/test_rag.py -v --tb=short --cov=rag --cov-report=html:tests/reports/rag_coverage --cov-report=term

if [ $? -eq 0 ]; then
    print_color $GREEN "✅ Testes do RAG Service passaram!"
else
    print_color $RED "❌ Testes do RAG Service falharam!"
fi

print_color $BLUE "📋 Executando testes do Memory Service..."
pytest tests/test_memory.py -v --tb=short --cov=memory --cov-report=html:tests/reports/memory_coverage --cov-report=term

if [ $? -eq 0 ]; then
    print_color $GREEN "✅ Testes do Memory Service passaram!"
else
    print_color $RED "❌ Testes do Memory Service falharam!"
fi

print_color $BLUE "📋 Executando todos os testes com relatório combinado..."
pytest tests/ -v --tb=short --cov=. --cov-report=html:tests/reports/full_coverage --cov-report=term-missing --junit-xml=tests/reports/junit_report.xml

# Verificar resultado final
if [ $? -eq 0 ]; then
    print_color $GREEN "🎉 Todos os testes passaram com sucesso!"
    
    print_color $YELLOW "📊 Relatórios gerados em:"
    echo "   - Coverage HTML: tests/reports/full_coverage/index.html"
    echo "   - JUnit XML: tests/reports/junit_report.xml"
    echo "   - Coverage por serviço: tests/reports/[service]_coverage/"
    
else
    print_color $RED "❌ Alguns testes falharam!"
    exit 1
fi

print_color $BLUE "🔍 Executando verificação de qualidade de código..."

# Verificar se existem issues nos imports
print_color $YELLOW "Verificando imports..."
python -m py_compile specialist/main.py 2>/dev/null
if [ $? -eq 0 ]; then
    print_color $GREEN "✅ Specialist Service compila sem erros"
else
    print_color $YELLOW "⚠️  Specialist Service tem problemas de compilação"
fi

python -m py_compile rag/main.py 2>/dev/null
if [ $? -eq 0 ]; then
    print_color $GREEN "✅ RAG Service compila sem erros"
else
    print_color $YELLOW "⚠️  RAG Service tem problemas de compilação"
fi

python -m py_compile memory/main.py 2>/dev/null
if [ $? -eq 0 ]; then
    print_color $GREEN "✅ Memory Service compila sem erros"
else
    print_color $YELLOW "⚠️  Memory Service tem problemas de compilação"
fi

print_color $GREEN "✨ Verificação de testes concluída!"