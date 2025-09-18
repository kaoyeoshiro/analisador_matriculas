# Sistema de Feedback Inteligente - Guia de Configuração

## Visão Geral

O sistema de feedback inteligente coleta dados de uso de forma não intrusiva, diferenciando entre:

- **Problemas reais** (reportados pelo usuário via botão)
- **Sucessos implícitos** (uso normal sem reclamações)

## Como Funciona

### 1. Feedback Automático Positivo
Enviado automaticamente quando:
- Usuário gera novo relatório sem ter reportado erro no anterior
- Usuário fecha aplicação sem ter reportado erro

### 2. Feedback Manual Negativo
- Botão "⚠️ Reportar Erro no Conteúdo" habilitado após gerar resultado
- Usuário descreve problema encontrado
- Sistema coleta descrição e contexto completo

## Configuração do Google Forms

### Passo 1: Criar Formulário

1. Acesse [Google Forms](https://forms.google.com)
2. Crie novo formulário: "Sistema de Feedback - Matrículas Confrontantes"
3. Adicione os seguintes campos:

#### Campo 1: Tipo de Feedback
- **Tipo**: Múltipla escolha
- **Título**: "Tipo de Feedback"
- **Opções**: ERRO, SUCESSO_AUTO
- **Obrigatório**: Sim

#### Campo 2: Descrição
- **Tipo**: Resposta longa
- **Título**: "Descrição do Problema"
- **Obrigatório**: Sim

#### Campo 3: Modelo LLM
- **Tipo**: Resposta curta
- **Título**: "Modelo LLM Utilizado"
- **Obrigatório**: Não

#### Campo 4: Data e Hora
- **Tipo**: Resposta curta
- **Título**: "Data e Hora"
- **Obrigatório**: Não

#### Campo 5: Versão
- **Tipo**: Resposta curta
- **Título**: "Versão do Sistema"
- **Obrigatório**: Não

### Passo 2: Obter Field IDs

1. Abra o formulário em modo de preenchimento
2. Pressione F12 para abrir Developer Tools
3. Procure pelos campos `input` com `name="entry.XXXXXXXXX"`
4. Anote os IDs de cada campo

### Passo 3: Obter URL de Envio

1. Na URL do formulário, substitua `/viewform` por `/formResponse`
2. Exemplo:
   - Original: `https://docs.google.com/forms/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/viewform`
   - Para envio: `https://docs.google.com/forms/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/formResponse`

### Passo 4: Configurar Aplicação

1. Copie `.env.example` para `.env`
2. Preencha com os valores obtidos:

```env
GOOGLE_FORM_URL=https://docs.google.com/forms/d/SEU_FORM_ID/formResponse
GOOGLE_FORM_FIELD_TIPO=entry.123456789
GOOGLE_FORM_FIELD_DESCRICAO=entry.987654321
GOOGLE_FORM_FIELD_MODELO=entry.789123456
GOOGLE_FORM_FIELD_TIMESTAMP=entry.321654987
GOOGLE_FORM_FIELD_VERSAO=entry.147258369
```

## Conectar com Google Sheets

1. No Google Forms, vá em "Respostas" → "Criar planilha"
2. Isso criará automaticamente uma planilha conectada
3. Todos os feedbacks aparecerão automaticamente na planilha

## Estrutura dos Dados Coletados

### Feedback Automático (SUCESSO_AUTO)
```json
{
  "tipo": "SUCESSO_AUTO",
  "descricao": "Relatorio do processo 12345 gerado sem problemas reportados - novo relatorio iniciado",
  "modelo": "google/gemini-2.5-pro",
  "timestamp": "2024-01-15 14:30:25",
  "versao": "1.0.0"
}
```

### Feedback Manual (ERRO)
```json
{
  "tipo": "ERRO",
  "descricao": "A matricula 67890 nao foi identificada corretamente no texto",
  "modelo": "google/gemini-2.5-pro",
  "timestamp": "2024-01-15 14:35:10",
  "versao": "1.0.0"
}
```

## Backup Local

O sistema salva automaticamente todos os feedbacks em:
```
dist/feedback_pendente.json
```

Este arquivo serve como:
- Backup em caso de falha no envio
- Debug e análise local
- Histórico completo dos últimos 100 feedbacks

## Análise dos Dados

A planilha resultante permite análises como:

- **Taxa de sucesso real**: `SUCESSO_AUTO / (SUCESSO_AUTO + ERRO) * 100`
- **Problemas por modelo**: Filtrar por campo "Modelo LLM"
- **Tendências temporais**: Agrupar por data/hora
- **Tipos de erro mais comuns**: Análise das descrições de erro
- **Performance por versão**: Comparar versões diferentes

## Segurança e Privacidade

- **Dados sensíveis**: Apenas números de processo, não conteúdo dos documentos
- **Anonimização**: Nenhum dado pessoal identificável é coletado
- **Controle**: Usuário controla quando reportar problemas
- **Transparência**: Sistema não é intrusivo nem oculto

## Troubleshooting

### Feedbacks não aparecem na planilha
1. Verifique se a URL está correta (deve terminar com `/formResponse`)
2. Confirme os Field IDs no formulário
3. Teste envio manual no formulário
4. Verifique logs no arquivo `feedback_pendente.json`

### Botão de feedback sempre desabilitado
1. Processe pelo menos um arquivo
2. Aguarde conclusão do processamento
3. Botão será habilitado automaticamente

### Erro de conexão
1. Verifique conexão com internet
2. Confirme se Google Forms está acessível
3. Feedbacks ficam salvos localmente até próxima tentativa

## Monitoramento

Para monitorar o sistema:

```python
from feedback_system import get_feedback_system

# Obter estatísticas
stats = get_feedback_system().get_estatisticas_locais()
print(f"Total: {stats['total']}")
print(f"Erros: {stats['erros']}")
print(f"Sucessos: {stats['sucessos']}")
print(f"Taxa de sucesso: {stats['taxa_sucesso']:.1f}%")
```
