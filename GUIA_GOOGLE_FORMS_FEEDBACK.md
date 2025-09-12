# 📋 Guia Completo: Configurar Google Forms + Sheets para Feedback

## 🎯 Objetivo
Configurar um sistema para receber feedback dos usuários sobre a precisão do sistema de análise de matrículas.

---

## 🚀 Passo 1: Criar o Google Form

### 1.1. Acessar Google Forms
1. Vá para [forms.google.com](https://forms.google.com)
2. Clique em **"Criar formulário em branco"** ou use um template

### 1.2. Configurar o Formulário
**Título:** Sistema de Feedback - Análise de Matrículas Confrontantes

**Descrição:** 
```
Este formulário coleta feedback sobre a precisão do sistema automático de análise de matrículas. 
Seus comentários são fundamentais para melhorarmos o sistema.
```

### 1.3. Adicionar Campos (EXATAMENTE nesta ordem):

#### Campo 1: **Resultado da Análise**
- **Tipo:** Múltipla escolha
- **Pergunta:** "O sistema identificou corretamente as confrontações?"
- **Opções:**
  - ✅ Acertou
  - ❌ Errou
- **Obrigatório:** Sim

#### Campo 2: **Descrição do Problema**
- **Tipo:** Texto longo
- **Pergunta:** "Se errou, descreva onde foi o problema (opcional)"
- **Obrigatório:** Não

#### Campo 3: **Data e Hora**
- **Tipo:** Texto curto
- **Pergunta:** "Timestamp"
- **Obrigatório:** Sim

#### Campo 4: **Dados Técnicos**
- **Tipo:** Texto longo
- **Pergunta:** "Dados técnicos (preenchido automaticamente)"
- **Obrigatório:** Não

---

## 🔧 Passo 2: Obter IDs dos Campos

### 2.1. Abrir DevTools
1. No formulário, pressione **F12** (DevTools)
2. Vá para a aba **"Network"**
3. Preencha o formulário com dados de teste
4. Clique em **"Enviar"**

### 2.2. Encontrar a Requisição
1. Na aba Network, procure por uma requisição POST para `/formResponse`
2. Clique na requisição
3. Vá para a aba **"Payload"** ou **"Request"**
4. Copie os IDs dos campos (formato: `entry.XXXXXXXXX`)

### 2.3. Anotar os IDs
```
Campo 1 (Resultado): entry.123456789
Campo 2 (Descrição): entry.987654321  
Campo 3 (Timestamp): entry.555666777
Campo 4 (Dados Técnicos): entry.444333222
```

---

## 📊 Passo 3: Configurar Google Sheets

### 3.1. Vincular Planilha
1. No Google Forms, clique em **"Respostas"**
2. Clique no ícone do **Google Sheets** (planilha verde)
3. Escolha **"Criar uma nova planilha"**
4. Nomeie: `Feedback_Matriculas_Confrontantes`

### 3.2. Configurar Notificações
1. Na planilha criada, vá em **"Ferramentas"** → **"Regras de notificação"**
2. Configure para receber email a cada nova resposta
3. Escolha frequência: **"Imediatamente"**

---

## ⚙️ Passo 4: Atualizar o Código

### 4.1. Copiar URL do Formulário
1. No Google Forms, clique em **"Enviar"**
2. Copie o link do formulário
3. Troque `/viewform` por `/formResponse` no final da URL

### 4.2. Editar main.py
Substitua esta seção no arquivo `main.py`:

```python
# Configuração do Google Forms para Feedback
GOOGLE_FORM_CONFIG = {
    "url": "https://docs.google.com/forms/d/e/SEU_FORM_ID_AQUI/formResponse",
    "fields": {
        "resultado": "entry.123456789",      # Substituir pelo ID real
        "descricao": "entry.987654321",      # Substituir pelo ID real  
        "timestamp": "entry.555666777",      # Substituir pelo ID real
        "dados_tecnicos": "entry.444333222"  # Substituir pelo ID real
    }
}
```

**Substitua:**
- `SEU_FORM_ID_AQUI` pelo ID real do seu formulário
- `entry.XXXXXXXXX` pelos IDs reais encontrados no Passo 2.2

---

## 🧪 Passo 5: Testar o Sistema

### 5.1. Teste Manual
1. Acesse seu formulário diretamente
2. Preencha e envie uma resposta de teste
3. Verifique se aparece na planilha do Google Sheets

### 5.2. Teste Automatizado
1. Execute o sistema
2. Processe alguma matrícula
3. Quando aparecer o dialog de feedback, teste o envio
4. Verifique se a resposta chegou na planilha

---

## 📈 Passo 6: Analisar os Dados

### 6.1. Dashboard Automático
O Google Sheets criará automaticamente:
- Gráficos de pizza (Acertou vs Errou)
- Resumo de respostas
- Filtros por data

### 6.2. Métricas Importantes
- **Taxa de Acerto:** % de "Acertou" vs Total
- **Problemas Mais Comuns:** Análise dos comentários
- **Evolução Temporal:** Melhoria da precisão ao longo do tempo

### 6.3. Análise de Feedback
Examine regularmente:
- Padrões nos erros relatados
- Tipos de documentos que causam mais problemas
- Sugestões de melhoria dos usuários

---

## 🚨 Troubleshooting

### Problema: Não recebo respostas
**Solução:**
1. Verifique se os IDs dos campos estão corretos
2. Teste o formulário manualmente
3. Confirme que a URL está com `/formResponse`

### Problema: Erro de CORS
**Solução:**
1. O Google Forms pode bloquear alguns requests
2. Use o método de fallback (salvamento local)
3. Dados são salvos em `feedback_pendente.json`

### Problema: Muitas respostas duplicadas
**Solução:**
1. Adicione um campo de ID único no formulário
2. Use timestamps mais precisos
3. Implemente debouncing no código

---

## 🔒 Privacidade e LGPD

### Dados Coletados
- ✅ Resultado da análise (Acertou/Errou)
- ✅ Descrição de problemas (opcional)
- ✅ Timestamp da análise
- ✅ Dados técnicos (modelo de IA, arquivo processado)

### Dados NÃO Coletados
- ❌ Informações pessoais do usuário
- ❌ Conteúdo real dos documentos analisados
- ❌ Dados sensíveis das matrículas

### Conformidade
- Dados são usados apenas para melhoria do sistema
- Nenhuma informação pessoal é transmitida
- Usuário pode pular o feedback a qualquer momento

---

## 🎉 Benefícios do Sistema

### Para Desenvolvedores
- Feedback contínuo sobre precisão
- Identificação de padrões de erro
- Dados para treinar modelos futuros
- Métricas de performance

### Para Usuários
- Sistema que melhora com o tempo
- Correções baseadas em feedback real
- Transparência no desenvolvimento
- Participação ativa na evolução do sistema

---

## 📞 Suporte

Se tiver problemas:
1. Verifique todos os IDs dos campos
2. Teste o formulário manualmente
3. Consulte os logs do sistema (arquivo `feedback_pendente.json`)
4. Verifique as notificações de email do Google Sheets

**Lembre-se:** O sistema funciona mesmo offline, salvando feedback localmente para envio posterior!
