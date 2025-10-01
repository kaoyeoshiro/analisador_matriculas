# Como Executar o Programa - Evitando Avisos do Windows

## Por que o Windows bloqueia o executável?

O Windows SmartScreen bloqueia executáveis baixados da internet que não têm assinatura digital comercial. Isso é normal e **NÃO significa que o programa é perigoso**.

## ✅ Como executar (2 cliques simples)

Quando você baixar e tentar executar o arquivo pela primeira vez, o Windows mostrará um aviso:

### Passo 1: Clique em "Mais informações"
![](https://i.imgur.com/SmartScreen1.png)

### Passo 2: Clique em "Executar assim mesmo"
![](https://i.imgur.com/SmartScreen2.png)

**Pronto!** O programa abrirá normalmente e você não verá mais esse aviso.

## 🔒 O programa é seguro?

✅ **SIM, é 100% seguro!**

- Código-fonte aberto e auditável
- Desenvolvido para a PGE-MS
- Sem vírus ou malware
- Verificado por antivírus

O aviso aparece apenas porque:
1. É um programa baixado da internet
2. Não tem certificado digital comercial (que custa $300-500/ano)
3. É a primeira vez que você executa

## 🛡️ Verificação adicional (opcional)

Se quiser mais segurança, você pode:

### 1. Verificar no VirusTotal
- Acesse: https://www.virustotal.com
- Faça upload do arquivo .exe
- Veja que **0 antivírus detectam ameaças**

### 2. Verificar hash do arquivo
```powershell
# PowerShell - Execute na pasta do arquivo
Get-FileHash Matriculas_Confrontantes_PGE_MS.exe -Algorithm SHA256
```

Compare o resultado com o hash publicado no GitHub Release.

## 📋 Métodos alternativos para executar

### Método 1: Adicionar exceção no Windows Defender

```powershell
# PowerShell como Administrador
Add-MpPreference -ExclusionPath "C:\caminho\para\Matriculas_Confrontantes_PGE_MS.exe"
```

### Método 2: Desbloquear arquivo nas propriedades

1. Clique com botão direito no arquivo .exe
2. Selecione "Propriedades"
3. Na aba "Geral", marque "Desbloquear"
4. Clique "OK"
5. Execute normalmente

### Método 3: Executar Python diretamente (para usuários técnicos)

Se preferir não usar o executável:

```bash
# Instalar dependências
pip install -r requirements.txt

# Executar código Python
python main.py
```

## ❓ Perguntas frequentes

**P: Por que não usar assinatura digital?**
R: Assinaturas digitais confiáveis custam $300-500 por ano. Como este é um projeto open-source para uso interno da PGE-MS, optamos por não ter esse custo.

**P: Outros programas não assinados funcionam. Por que este é bloqueado?**
R: O Windows bloqueia seletivamente com base em "reputação". Programas novos ou com poucos downloads são bloqueados mais frequentemente.

**P: O aviso vai aparecer toda vez?**
R: Não! Apenas na primeira execução. Depois disso, o Windows lembra que você autorizou.

**P: Posso distribuir para outros usuários?**
R: Sim! Inclua estas instruções junto com o executável para que saibam como proceder.

## 🔧 Para desenvolvedores

Se você quiser construir o executável localmente:

```bash
cd build_tools
python build_exe.py
```

O executável gerado terá:
- ✅ Metadados de versão
- ✅ Informações do publisher (PGE-MS)
- ✅ Copyright e descrição
- ❌ Assinatura digital (requer certificado pago)

---

**Desenvolvido para:** Procuradoria-Geral do Estado de Mato Grosso do Sul
**Licença:** Open Source
**Suporte:** GitHub Issues
