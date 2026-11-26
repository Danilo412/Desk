# Atualizações do Desk

Clientes a partir da versão 0.12.0 buscam o manifesto `desk-update.json` na
última versão estável de https://github.com/Danilo412/Desk/releases.
Clientes anteriores precisam de uma primeira instalação desta versão.
O Desk precisa estar aberto e com acesso à internet para buscar as versões.

A busca acontece quinze segundos após abrir e a cada cinco minutos. Também
existe a opção “Verificar atualizações” no menu. Por padrão (a partir da
versão 0.15.0), o Desk baixa e verifica em segundo plano (`SHA-256` e
assinatura `Ed25519`) a atualização assim que ela é detectada, exibindo um
aviso discreto na tela inicial e na barra superior quando estiver pronta para
instalar. Sessões e gravações ativas nunca são interrompidas. Em
**Configurações > Atualizações**, o usuário pode ajustar se deseja baixar em
segundo plano e se quer abrir o instalador automaticamente ao fechar o Desk.
O instalador mantém o perfil local, número, favoritos e `internet.json`
existentes. Em uma instalação limpa, a configuração de conexão precisa ser
fornecida pelo proprietário.

O manifesto tem assinatura Ed25519 com a chave pública em `update_trust.py`.
O tamanho e SHA-256 do instalador são verificados no download e novamente
antes de executar. Versões iguais ou anteriores não são oferecidas. Downloads
mantêm a marca de origem da internet no Windows (`ZoneId=3`). O manifesto não
inclui convites, identidades, senhas ou credenciais TURN.

## Publicação pelo mantenedor

Compile, valide e publique com um único comando na raiz do repositório:

```console
scripts\dev.ps1 publish
```

Ou diretamente via Python:

```console
python scripts\publish_release.py --publish
```

Regras de segurança:
- Compile e teste a nova versão pública sem `internet.json`.
- A chave privada do manifesto (`%LOCALAPPDATA%\DeskPublisher\update-signing-key.dat`)
  é mantida apenas no computador do publicador, protegida com DPAPI, fora
  deste repositório. Nunca a inclua em código, instaladores ou artefatos.
- O publicador assina o manifesto somente depois de validar os testes, a
  compilação empacotada e o instalador correspondente.
- Uma versão estável só é oferecida no canal automático após sua publicação
  como release `Latest` com `desk-update.json` validado.

A assinatura interna do manifesto autentica a distribuição, mas NÃO é uma
assinatura Authenticode. O Windows pode bloquear os executáveis atuais. O
atualizador não desativa nem contorna essa proteção e mantém o Desk aberto
se o início do instalador falhar.
