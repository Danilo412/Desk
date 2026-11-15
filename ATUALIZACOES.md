# Atualizações do Desk

Clientes a partir da versão 0.12.0 buscam o manifesto `desk-update.json` na
última versão estável de https://github.com/Danilo412/Desk/releases.
Clientes anteriores precisam de uma primeira instalação desta versão.
O Desk precisa estar aberto e com acesso à internet para buscar as versões.

A busca acontece quinze segundos após abrir e a cada seis horas. Também
existe a opção “Verificar atualizações” no menu. Não há instalação silenciosa:
o usuário escolhe baixar, depois confirma abrir o instalador. A sessão e a
gravação precisam estar encerradas. O instalador mantém o perfil local, número,
favoritos e internet.json existentes. Em uma instalação limpa, a configuração
de conexão precisa ser fornecida pelo proprietário.

O manifesto tem assinatura Ed25519 com a chave pública em update_trust.py.
O tamanho e SHA-256 do instalador são verificados no download e novamente
antes de executar. Versões iguais ou anteriores não são oferecidas. Downloads
mantêm a marca de origem da internet no Windows. O manifesto não inclui
convites, identidades, senhas ou credenciais TURN.

## Publicação pelo mantenedor

Compile e teste a nova versão pública sem internet.json. A chave privada do
manifesto é mantida apenas no computador do publicador, protegida com DPAPI,
fora deste repositório. Nunca a inclua em código, instaladores ou artefatos.
Um publicador com a chave assina o manifesto somente depois de validar a
compilação e publicar o instalador correspondente. Publique o manifesto por
último. Uma versão estável só é oferecida após sua publicação como release.

A assinatura interna do manifesto autentica a distribuição, mas NÃO é uma
assinatura Authenticode. O Windows pode bloquear os executáveis atuais. O
atualizador não desativa nem contorna essa proteção e mantém o Desk aberto
se o início do instalador falhar. A instalação, a reabertura e o áudio corrigido
no computador bloqueado ainda precisam de validação após liberar a execução
por um caminho de assinatura confiável.
